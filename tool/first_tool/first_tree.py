import os

from client.browser_use_cli import init_strategy
from mcp.server import FastMCP

mcp = FastMCP()

output_dir = os.environ["OUTPUT_PATH"]

@mcp.tool(name="first_tree")
async def start_first_tree_tool(url):
    """
    通过browser-use来开展第一层树的提取工作
    """
    output_path = f"""{output_dir}/data.json"""
    res = await init_strategy(url,output_path)
    return output_path

if __name__ == "__main__":
    mcp.run(transport='stdio')