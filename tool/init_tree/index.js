import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { crawlNavTree } from "./navCrawlerTool.js"; // 你实现的爬虫方法

// 创建 MCP 服务
const server = new McpServer({
  name: "nav-tree-crawler",
  version: "1.0.0",
  capabilities: {
    resources: {},
    tools: {},
  },
});

// 注册 MCP 工具
server.tool(
  "crawl_nav_tree",
  "Crawl the navigation tree of a given website URL，return json file path",
  {
    url: z.string().url().describe("The website URL to crawl"),
  },
  async ({ url }) => {
    try {
      const filePath = await crawlNavTree(url); // 调用你原来的方法
      return {
        content: [
          {
            type: "text",
            text: filePath
          }
        ]
      };
    } catch (err) {
      console.error("Error in crawl_nav_tree:", err);
      return {
        content: [
          {
            type: "text",
            text: `Failed to crawl URL: ${url}. Error: ${err.message}`,
          },
        ],
      };
    }
  }
);

// 启动 MCP 服务器
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Nav Tree MCP Server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error in main():", error);
  process.exit(1);
});

// await crawlNavTree("https://www.tongrentang.com/"); // 注意这里传入 level

