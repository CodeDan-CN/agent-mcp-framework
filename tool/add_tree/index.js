import { crawlNavTree } from './crawl_nav_with_features.js';

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

// 创建 MCP 服务
const server = new McpServer({
  name: "nav-tree-crawler",
  version: "1.0.0",
  capabilities: {
    resources: {},
    tools: {},
  },
});

server.tool(
  "crawl_add_tree",
  "Crawl the next level or specified level of a pruned navigation tree JSON and return the updated JSON file path",
  {
    tree_json_path: z.string().describe("Path to the pruned navigation tree JSON file to continue crawling"),
    level: z.number().int().optional().describe("当前层级数字"),
  },
  async ({ tree_json_path, level }) => {
    try {
      const filePath = await crawlNavTree({inputPath:tree_json_path, level:level}); // 注意这里传入 level
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
            text: `Failed to crawl tree. Error: ${err.message}`,
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

// await crawlNavTree({inputPath:"/Users/codedan/local/project/crawlee/agent-mcp-framework/file/data_scored2.json", level:3}); // 注意这里传入 level
