import asyncio
import json
import os
from typing import Optional
from contextlib import AsyncExitStack

from langchain_core.messages import HumanMessage, AIMessage
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
from agent_collections import ToolResultItem, UserQuery, ModelAdapter

load_dotenv()  # load environment variables from .env
api_key = os.environ["MODEL_API_KEY"]
base_url = os.environ["MODEL_BASE_URL"]
tool_path = os.environ["MCP_TOOL_PATH"]
model_name = os.environ["MODEL_NAME"]
model_type = os.environ["MODEL_TYPE"]

message_history = []


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.model_adapter = ModelAdapter(model_name=model_name, model_type=model_type, api_key=api_key,
                                          base_url=base_url)

    # methods will go here

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = await self.session.list_tools()
        available_tools = [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]

        # Initial Claude API call
        message_history.append(HumanMessage(content=query))
        response = self.model_adapter.create(
            messages=messages,
            history=message_history,
            tools=available_tools
        )
        print(response)
        # 根据返回类型进行输出 TODO：暂不考虑历史记录
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
                result = await self.session.call_tool(tool_name, tool_params)
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
                for tool in chain_full:
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
                    result = await self.session.call_tool(current_tool_name, current_tool_input)
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

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    client = MCPClient()
    try:
        await client.connect_to_server(tool_path)
        # await client.connect_to_server("D:\\local\\pycharm\\mcp_demo\\server\\echo_server.py")

        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
