import fs from 'fs';
import {Configuration, PlaywrightCrawler, purgeDefaultStorages} from 'crawlee';
import { JSDOM } from 'jsdom';
import { Mutex } from 'async-mutex';
import path from "path";
import {fileURLToPath} from "url";
import * as JSON5 from "zod/v4";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const urlMutex = new Mutex();
// 确保 logs 目录存在
const logsDir = path.join(__dirname, '../logs');

let prefix_output_path = process.env.OUTPUT_PATH
// let prefix_output_path = "/Users/codedan/local/project/crawlee/agent-mcp-framework/tool/add_tree"


if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir, { recursive: true });
}
const logFilePath = path.join(logsDir, 'navCrawlerAdd.log');

let filter_url = '';

function isAllowedDomain(url) {
    try {
        const hostname = new URL(url).hostname;
        const temp_filter_url = new URL(filter_url).hostname;
        return hostname.endsWith(temp_filter_url);
    } catch {
        return false;
    }
}

function logToFile(...args) {
  const message = args.join(' ');
  console.log(message);
  fs.appendFileSync(logFilePath, `[${new Date().toISOString()}] ${message}\n`);
}

export async function crawlNavTree({
    inputPath = '',
    level,
    concurrency = 5
} = {}) {
    // === 初始化逻辑 ===
    const outputPath = prefix_output_path + `/add_tree${level}.json`
    if (!inputPath) {
        throw new Error('inputPath 不能为空');
    }

    if (!fs.existsSync(inputPath)) {
        throw new Error(`输入文件不存在: ${inputPath}`);
    }

    const fileContent = fs.readFileSync(inputPath, 'utf-8').trim();
    if (!fileContent) {
        throw new Error(`输入文件为空: ${inputPath}`);
    }

    let data;
    try {
        // 支持 JSON5（允许注释、尾逗号等）
        data = JSON.parse(fileContent);
    } catch (err) {
        console.error('JSON/JSON5 解析失败，请检查文件格式');
        throw err;
    }
    filter_url = data.url
    const navTree = data.nav_tree || [];

    const urlMap = new Map();

    // 1️⃣ 初始化 uniqueList
    let uniqueList = [];
    if (data.unique && data.unique.length > 0) {
        uniqueList = [...new Set(data.unique)];
    } else {
        function initLowScoreUrls(node) {
            if (!node) return [];
            let urls = [];
            if (!node.children || node.children.length === 0) {
                if (node.score_norm < 0.6 && node.url) urls.push(node.url);
            } else {
                node.children.forEach(child => {
                    urls = urls.concat(initLowScoreUrls(child));
                });
            }
            return urls;
        }
        uniqueList = initLowScoreUrls(navTree);
    }

    function initUrlMap(node) {
        if (!node) return;
        if (node.url) {
            if (urlMap.has(node.url)) {
                if (!uniqueList.includes(node.url)) uniqueList.push(node.url);
            } else {
                urlMap.set(node.url, node);
            }
        }
        if (node.children && node.children.length > 0) {
            node.children.forEach(child => initUrlMap(child));
        }
    }

    navTree.forEach(node => initUrlMap(node));

    function getLeafNodes(tree) {
        let leaves = [];
        for (const node of tree) {
            if (!node.children || node.children.length === 0) {
                // 只保留 score_norm > 0.7 的叶子节点
                if (
                    node.score_norm && node.score_norm > 0.6
                  &&
                  node.url &&
                  node.url.trim() !== '' &&
                  node.url !== '#'
                ) {
                  leaves.push(node);
                }

            } else {
                leaves = leaves.concat(getLeafNodes(node.children));
            }
        }
        return leaves;
    }


    async function getOrCreateNode(url, title) {
        if (urlMap.has(url)) {
            const node = urlMap.get(url);
            if (!node.features) node.features = [node.title];
            if (!node.features.includes(title)) node.features.push(title);
            if (!uniqueList.includes(url)) uniqueList.push(url);
            return null;
        }
        if (uniqueList.includes(url)) return null;
        const node = { title, url, features: [title], children: [] };
        urlMap.set(url, node);
        return node;
    }

    async function buildChildTree(html, baseUrl, parentLeafUrl) {
        const dom = new JSDOM(html);
        const document = dom.window.document;
        const children = [];

        logToFile(`\n--- Crawling leaf node: ${parentLeafUrl} ---`);

        for (const a of document.querySelectorAll('a')) {
            const href = a.href;
            if (!href || href.startsWith('javascript')) continue;

            const fullUrl = href.startsWith('http') ? href : new URL(href, baseUrl).href;
            if (!isAllowedDomain(fullUrl)) continue; // ✅ 域名限制
            const title = a.textContent.trim() || '(empty title)';

            const node = await urlMutex.runExclusive(async () => {
                const n = await getOrCreateNode(fullUrl, title);
                if (n) children.push({ ...n, children: [] });
                return n;
            });

            if (node) {
                logToFile(`  [+] Added child: ${fullUrl} (title: "${title}")`);
            } else {
                logToFile(`  [*] Exists, feature updated only: ${fullUrl} (title: "${title}")`);
            }
            logToFile(`--- Finished leaf node: ${parentLeafUrl}, total children added: ${children.length} ---\n`);
        }

        return children;
    }

    async function crawlLeafNode(leafNode) {
        if (!leafNode.url) return;
        const storageDir = path.join(__dirname, `./storage_${Date.now()}`);
        process.env.CRAWLEE_STORAGE_DIR = storageDir;
        const crawler = new PlaywrightCrawler({
            maxConcurrency: 1,
            async requestHandler({ page, request }) {
                await page.route('**/*', route => {
                    const type = route.request().resourceType();
                    if (type === 'image' || type === 'media' || type === 'font') {
                        route.abort();
                    } else {
                        route.continue();
                    }
                });

                logToFile(`Crawling: ${request.url}`);
                const html = await page.content();
                const childrenTree = await buildChildTree(html, request.url, leafNode.url);
                leafNode.children = childrenTree;
            }
        });

        await crawler.addRequests(
            [{ url: leafNode.url }]
                .filter(r =>
                    typeof r.url === 'string' &&
                    r.url.trim() !== '' &&
                    r.url.startsWith('http') &&
                    isAllowedDomain(r.url) // ✅ 域名限制
                )
        );
        await crawler.run();
        await crawler.teardown();
    }

    async function asyncPool(poolLimit, array, iteratorFn) {
        const ret = [];
        const executing = [];
        for (const item of array) {
            const p = Promise.resolve().then(() => iteratorFn(item));
            ret.push(p);

            if (poolLimit <= array.length) {
                const e = p.then(() => executing.splice(executing.indexOf(e), 1));
                executing.push(e);
                if (executing.length >= poolLimit) {
                    await Promise.race(executing);
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }
        }
        return Promise.all(ret);
    }

    // === 主逻辑 ===
    const leafNodes = getLeafNodes(navTree);
    await asyncPool(concurrency, leafNodes, crawlLeafNode);
    logToFile(`关闭爬虫程序中.....`);
    // 收尾: 关闭爬虫 & 删除 storage
    const storagePath = path.join(__dirname, 'storage');
    logToFile(`回收爬虫程序产生的脏数据.....`);
    if (fs.existsSync(storagePath)) {
        fs.rmSync(storagePath, { recursive: true, force: true });
    }
    fs.writeFileSync(
        outputPath,
        JSON.stringify({ ...data, nav_tree: navTree, unique: uniqueList }, null, 2),
        'utf-8'
    );

    logToFile('叶子节点子树更新完成，保存到', outputPath);

    return outputPath;
}

// await crawlNavTree({
//     inputPath:'/Users/codedan/local/project/crawlee/agent-mcp-framework/file/data_scored1.json',
//     level:1
// });