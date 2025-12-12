import os
import shutil

from client.browser_use_cli import init_strategy
from mcp.server import FastMCP

mcp = FastMCP()

output_dir = os.environ["OUTPUT_PATH"]

@mcp.tool(name="crawl_nav_tree")
async def start_first_tree_tool(url):
    """
    通过browser-use来开展第一层树的提取工作
    """
    output_path = f"""{output_dir}/data.json"""
    res = await init_strategy(url,output_path)
    # 把res这个文件地址对应的文件拷贝到output_path这个对应的文件下
    # 第二步：把 res_path 指向的文件最终保存为 output_path
    return res

if __name__ == "__main__":
    mcp.run(transport='stdio')