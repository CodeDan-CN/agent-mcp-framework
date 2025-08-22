import asyncio
import os
from typing import Optional, List
from contextlib import AsyncExitStack

from langchain_core.messages import HumanMessage, AIMessage
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
from agent_collections import ToolResultItem, UserQuery, ModelAdapter

load_dotenv()  # load environment variables from .env
api_key = os.environ["MODEL_API_KEY"]
base_url = os.environ["MODEL_BASE_URL"]
# tool_path = os.environ["MCP_TOOL_PATH"]
model_name = os.environ["MODEL_NAME"]
model_type = os.environ["MODEL_TYPE"]

message_history = []


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.exit_stack = AsyncExitStack()
        self.model_adapter = ModelAdapter(model_name=model_name, model_type=model_type, api_key=api_key,
                                          base_url=base_url)
        self.stdio_pairs = []
        # Holds active ClientSession objects for each tool server
        self.sessions: List[Optional[ClientSession]] = []

    # methods will go here

    async def connect_to_server(self, server_script_paths: List[str]):
        """
          For each script path in server_script_paths:
          1. Determine interpreter (Python or Node)
          2. Launch stdio client subprocess
          3. Initialize and store a ClientSession
          """
        python_exec = os.getenv("PYTHON_EXECUTABLE", "python")
        env = os.environ.copy()
        for path in server_script_paths:
            command = python_exec if path.endswith(".py") else "node"
            server_params = StdioServerParameters(command=command, args=[path], env=env)
            # Enter stub client and session contexts
            stdio_pair = await self.exit_stack.enter_async_context(stdio_client(server_params))
            self.stdio_pairs.append(stdio_pair)
            # Perform handshake or initialization protocol
            session = await self.exit_stack.enter_async_context(ClientSession(*stdio_pair))
            await session.initialize()
            self.sessions.append(session)
            print(f"✅ Connected to {len(self.sessions)} tool services,name:{path}")

    async def call_tool_by_name(self, tool_name: str, tool_args: dict):
        """
               Searches all connected sessions for a tool matching tool_name,
               invokes it with tool_args, and returns the result.

               Raises ValueError if no matching tool is found.
               """
        for session in self.sessions:
            response = await session.list_tools()
            for tool in response.tools:
                if tool.name == tool_name:
                    print(f"🔧 Invoking {tool_name} with args: {tool_args}")
                    return await session.call_tool(tool_name, tool_args)
        raise ValueError(f"Tool '{tool_name}' not found among sessions.")

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]
        responses = [await session.list_tools() for session in self.sessions]
        available_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            }
            for response in responses
            for tool in response.tools
        ]
        # Ask the model for dispatch instructions
        response = self.model_adapter.create(
            messages=messages,
            history=message_history,
            tools=available_tools
        )
        # 根据返回类型进行输出
        # 先写第一种，即文本类型，说明不需要调用工具（可能是结束也可能是调用工具的条件不足），直接获得返回
        while True:
            type = response.type
            if type == "text":
                context = response.result.text
                message_history.append(AIMessage(content=context))
                return context
            elif type == "tool":
                # 说明其判断只需要执行一次工具就可以获取到结果
                tool_name, tool_params = response.result.name, response.result.input
                # Execute tool call
                result = await self.call_tool_by_name(tool_name, tool_params)
                print("工具结果：", result.content[0].text)
                # 需要一个用户问题、工具调用历史进行回答的Agent
                tool_chain = [response.result.name]
                tool_result = ToolResultItem(name=response.result.name, result=result.content[0].text)
                generate_info = UserQuery(user_input=query, tool_chain=tool_chain, tool_result=[tool_result])
                response = self.model_adapter.generate_context(
                    generate_info=generate_info,
                    history = message_history
                )

            elif type == "chain":
                print("工具chain执行中")
                # 获取当前属于哪一个节点
                chain_full = response.result
                chain_history = []
                tool_chain = []
                tool_result = []
                for index,tool in enumerate(chain_full):
                    current_tool_name = tool.name
                    tool_chain.append(current_tool_name)
                    # 根据名字获取工具的详细信息
                    current_node_info = next((tool for tool in available_tools if tool["name"] == current_tool_name),
                                             None)
                    response = self.model_adapter.generate_param_by_current_node(
                        current_node_info=current_node_info,
                        chain_history=chain_history,
                        user_input=query,
                        history= message_history
                    )
                    current_tool_input = response
                    # Execute tool call
                    if 'tree_json_path' in current_tool_input and "tree_json_path" in chain_full[index]:
                        current_tool_input["tree_json_path"] = chain_full[index]["tree_json_path"]
                    if 'level' in current_tool_input and "level" in tool.input:
                        current_tool_input["level"] = tool.input["level"]
                    print(f"当前节点工具名称{current_tool_name},参数为:{current_tool_input}")
                    result = await self.call_tool_by_name(current_tool_name, current_tool_input)
                    print("工具结果：", result.content[0].text)
                    # 制作执行历史
                    chain_history.append(
                        {
                            "name": current_tool_name,
                            "result": result.content[0].text
                        }
                    )
                    tool_result.append(ToolResultItem(name=current_tool_name, result=result.content[0].text))
                # 将工具调用历史等交给大模型，让大模型生成总结
                generate_info = UserQuery(user_input=query, tool_chain=tool_chain, tool_result=tool_result)
                response = self.model_adapter.generate_context(
                    generate_info=generate_info,
                    history= message_history
                )
            else:
                print("类型解析失败")
                return ""

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n" + response)
                # 删除一下当前目录下的storage目录

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    client = MCPClient()
    try:
        await client.connect_to_server(["/Users/codedan/local/project/crawlee/agent-mcp-framework/tool/init_tree/index.js","/Users/codedan/local/project/crawlee/agent-mcp-framework/tool/node_filter/tree_node_filter.py","/Users/codedan/local/project/crawlee/agent-mcp-framework/tool/add_tree/index.js"])
        # await client.connect_to_server("D:\\local\\pycharm\\mcp_demo\\server\\echo_server.py")

        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
