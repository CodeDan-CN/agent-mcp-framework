import json
import re
from typing import List, Union

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from template import prompt, generate_prompt, generate_param_prompt


def extract_json_from_response(text):
    # 移除 <think>...</think> 内容
    text = re.sub(r'<think>[\s\S]*?</think>', '', text)
    # 优先提取 ```json ... ``` 中的内容
    match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    json_str = match.group(1) if match else text
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}")


# 模拟的响应内容类
class FakeTextContent(BaseModel):
    text: str
    type: str


class FakeToolContent(BaseModel):
    type: str
    name: str
    input: dict


class ToolCallResult(BaseModel):
    type: str
    result: Union[FakeTextContent, FakeToolContent, List[FakeToolContent]]
    node_number: int = 0


class ToolResultItem(BaseModel):
    name: str  # 工具名称
    result: str  # 工具返回的结果


class UserQuery(BaseModel):
    user_input: str  # 用户的自然语言问题
    tool_chain: List[str]  # 工具链名称列表
    tool_result: List[ToolResultItem]  # 工具执行结果列表


class ModelAdapter:
    def __init__(self, model_name: str, model_type: str, api_key: str, base_url: str):
        self.generate_prompt = generate_prompt
        self.client = init_chat_model(model_name, model_provider=model_type, temperature=0, api_key=api_key,
                                      base_url=base_url)

        self.system_prompt = prompt
        self.generate_param_prompt = generate_param_prompt

    def create(self, messages: list, tools: list):
        """
        将 messages 与 tools 信息封装后调用模型，并返回一个 FakeResponse 对象。
        """
        # 针对简单实现，这里只取最后一条消息内容作为用户输入
        user_message = messages
        # 拼接工具信息（注意实际情况可能需要更灵活的处理）
        # combined_input = f"{json.dumps(tools)}\n那么我的问题是:{user_message}"
        combined_input = "{tools_info}\n那么我的问题是:{user_message}"
        # 调用模型的聊天接口，使用流式输出
        messages = ChatPromptTemplate([
            ("system", self.system_prompt),
            ("human", combined_input)
        ]).invoke({"tools_info": json.dumps(tools), "user_message": user_message})
        response_text = ""
        for chunk in self.client.stream(input=messages):
            response_text += chunk.content  # 累加每个块的内容

        print("model (full response):", response_text)
        # 尝试解析 JSON，如果解析失败，就直接使用原文本
        result = None
        try:
            parsed_result = extract_json_from_response(response_text)
            print(parsed_result)
            if isinstance(parsed_result, dict):
                type = parsed_result['type']
                if type == 'text':
                    call_info = FakeTextContent(text=parsed_result['text'], type=type)
                else:
                    call_info = FakeToolContent(type=type, name=parsed_result['name'], input=parsed_result['input'])
                result = ToolCallResult(type=type, result=call_info)
            else:
                call_info = []
                for item in parsed_result:
                    call_info.append(FakeToolContent(type=item['type'], name=item['name'], input=item['input']))
                result = ToolCallResult(type="chain", result=call_info)
        except Exception:
            print("转化出错")
        return result

    def generate_context(self, generate_info: UserQuery):
        # 调用模型的聊天接口，使用流式输出
        messages = ChatPromptTemplate([
            ("system", self.generate_prompt),
            ("human", "{user_input}")
        ]).invoke({"user_input": json.dumps(generate_info.model_dump())})
        response_text = ""
        for chunk in self.client.stream(input=messages):
            response_text += chunk.content  # 累加每个块的内容

        print("model (full response):", response_text)
        call_info = FakeTextContent(text=response_text, type="text")
        return ToolCallResult(type="text", result=call_info)

    def generate_param_by_current_node(self,
                                       chain_history: List[dict],
                                       current_node_info: dict,
                                       user_input: str):
        # 组建输入
        input_template = {
            "user_input": user_input,
            "chain_history": chain_history,
            "current_node_info": current_node_info,
        }
        messages = ChatPromptTemplate([
            ("system", self.generate_param_prompt),
            ("human", "{user_input}")
        ]).invoke({"user_input": json.dumps(input_template)})
        response_text = ""
        for chunk in self.client.stream(input=messages):
            response_text += chunk.content  # 累加每个块的内容
        print("model (full response):", response_text)
        return extract_json_from_response(response_text)
