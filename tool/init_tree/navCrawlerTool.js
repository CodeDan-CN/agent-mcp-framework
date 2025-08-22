import { PlaywrightCrawler } from 'crawlee';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';
import OpenAI from 'openai';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 确保 logs 目录存在
const logsDir = path.join(__dirname, '../logs');
if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir, { recursive: true });
}
const logFilePath = path.join(logsDir, 'navCrawler.log');

// 日志函数：打印到控制台 + 写入文件
function logToFile(...args) {
  const message = args.join(' ');
  console.log(message);
  fs.appendFileSync(logFilePath, `[${new Date().toISOString()}] ${message}\n`);
}

const client = new OpenAI({
  apiKey: "sk-", // 建议用环境变量
  baseURL: 'https://api.aigc369.com/v1',
});

const NAV_SELECTORS = [
  '.side-cont', '.nav', '.navbar', '.menu', '.main-nav',
  'header nav', 'nav', '#nav', '#navbar'
];

// 调用 LLM 解析 HTML -> JSON
async function getNavFromHtml(html) {
  const prompt = `
你是一个前端导航结构分析专家。
我给你网站导航相关的 HTML，请你识别其中的导航栏入口及其子链接层级，返回 JSON 数组。
每个节点格式如下：
- title: 导航标题文本
- url: 链接地址（如果有）
- children: 子节点数组（如果有）
- features: 特征数组

请只返回纯 JSON，且不要包含任何代码块或额外说明。

HTML 内容：
${html}
  `;

  logToFile("调用 LLM 解析导航 HTML...")
  const completion = await client.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [{ role: 'user', content: prompt }],
    temperature: 0,
  });

  const content = completion.choices[0].message.content.trim();
   logToFile('解析导航结构 JSON 成功，模型原始输出:', content);
  try {
    return JSON.parse(content);
  } catch (err) {
    logToFile('解析导航结构 JSON 失败，模型原始输出:', content);
    throw err;
  }
}

// 获取顶层导航 HTML 容器
async function getTopLevelNavHtml(page, selectors) {
  const topLevelContainers = new Set();

  for (const sel of selectors) {
    const els = await page.$$(sel);
    if (els.length === 0) continue;

    for (const el of els) {
      const topAncestorHtml = await page.evaluate((element) => {
        function findTopAncestor(el) {
          while (el.parentElement) {
            const p = el.parentElement;
            const tag = p.tagName.toLowerCase();
            const cls = p.className.toLowerCase();

            if (
              tag === 'nav' ||
              tag === 'aside' ||
              cls.includes('nav') ||
              cls.includes('navigation') ||
              cls.includes('menu') ||
              cls.includes('sidebar')
            ) {
              el = p;
            } else {
              break;
            }
          }
          return el.outerHTML;
        }
        return findTopAncestor(element);
      }, el);

      topLevelContainers.add(topAncestorHtml);
    }
  }

  return Array.from(topLevelContainers);
}

/**
 * MCP 工具: crawlNavTree
 * @desc 爬取指定 URL，抽取导航栏 HTML，调用大模型识别导航树，返回 JSON
 * @param {string} url - 要爬取的目标页面 URL
 * @returns {object} { url, nav_tree }
 */
export async function crawlNavTree(url) {
  console.log(`开始运行爬取工具，当前目标页面：${url}`)
  let result = null;

  const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 1,
    headless: true,
    launchContext: {
      launchOptions: { headless: true, args: ['--no-sandbox'] },
    },
    requestHandlerTimeoutSecs: 60,

    async requestHandler({ page, request }) {
      logToFile(`打开页面: ${request.url}`);
      await page.goto(request.url, { waitUntil: 'networkidle' });

      let navHtmlParts = await getTopLevelNavHtml(page, NAV_SELECTORS);
      let navHtml = navHtmlParts.length > 0
        ? navHtmlParts.join('\n')
        : await page.$eval('body', e => e.outerHTML);

      const navTree = await getNavFromHtml(navHtml);
      result = {
        url: request.url,
        nav_tree: navTree
      };
      logToFile(`返回内容: ${result}`);
    }
  });

  // 运行爬虫
  await crawler.run([url]);
  logToFile(`关闭爬虫程序中.....`);
  // 收尾: 关闭爬虫 & 删除 storage
  await crawler.teardown();
  const storagePath = path.join(__dirname, 'storage');
  logToFile(`回收爬虫程序产生的脏数据.....`);
  if (fs.existsSync(storagePath)) {
    fs.rmSync(storagePath, { recursive: true, force: true });
  }
  logToFile(`初始树工具调用完毕`);
  const filePath = await saveJsonToFile(result,"/Users/codedan/local/project/crawlee/agent-mcp-framework/file")
  return filePath;
}

async function saveJsonToFile(data, folderPath, fileName = 'data.json') {
    // 确保文件夹存在，不存在则创建
    if (!fs.existsSync(folderPath)) {
        fs.mkdirSync(folderPath, { recursive: true });
    }

    const filePath = path.join(folderPath, fileName);
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
    console.log(`JSON 数据已保存到: ${filePath}`);
    return filePath
}

