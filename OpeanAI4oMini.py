import json
import re
from typing import List, Union
from openai import OpenAI
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
    text:str
    type:str


class FakeToolContent(BaseModel):
    type:str
    name:str
    input:dict


class ToolCallResult(BaseModel):
    type:str
    result:Union[FakeTextContent, FakeToolContent,List[FakeToolContent]]
    node_number:int = 0


class ToolResultItem(BaseModel):
    name: str  # 工具名称
    result: str  # 工具返回的结果

class UserQuery(BaseModel):
    user_input: str  # 用户的自然语言问题
    tool_chain: List[str]  # 工具链名称列表
    tool_result: List[ToolResultItem]  # 工具执行结果列表

class GPT4oMiniAdapter:
    def __init__(self, api_key: str, base_url: str):
        self.generate_prompt = generate_prompt
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.system_prompt = prompt
        self.generate_param_prompt = generate_param_prompt

    def create(self, model: str, max_tokens: int, messages: list, tools: list):
        """
        将 messages 与 tools 信息封装后调用模型，并返回一个 FakeResponse 对象。
        """
        # 针对简单实现，这里只取最后一条消息内容作为用户输入
        user_message = messages
        # 拼接工具信息（注意实际情况可能需要更灵活的处理）
        combined_input = f"{json.dumps(tools)}\n那么我的问题是:{user_message}"

        # 调用模型的聊天接口，使用流式输出
        chat_completion = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": combined_input}
            ],
            stream=False
        )

        # response_texts = []
        # for chunk in chat_completion:
        #     if chunk.choices[0].delta.content:
        #         response_texts.append(chunk.choices[0].delta.content)
        #         # 这里可以考虑实时处理，也可以统一处理
        # response_text = "".join(response_texts)
        response_text = chat_completion.choices[0].message.content
        # 尝试解析 JSON，如果解析失败，就直接使用原文本
        result = None
        try:
            parsed_result = extract_json_from_response(response_text)
            print(parsed_result)
            if isinstance(parsed_result,dict):
                type = parsed_result['type']
                if type == 'text':
                    call_info = FakeTextContent(text=parsed_result['text'], type=type)
                else:
                    call_info = FakeToolContent(type=type, name=parsed_result['name'], input=parsed_result['input'])
                result=ToolCallResult(type=type, result=call_info)
            else:
                call_info = []
                for item in parsed_result:
                    call_info.append(FakeToolContent(type=item['type'], name=item['name'], input=item['input']))
                result = ToolCallResult(type="chain", result=call_info)
        except Exception:
            print("转化出错")
        return result


    def generate_context(self, model: str, max_tokens: int, generate_info: UserQuery):
        chat_completion = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self.generate_prompt},
                {"role": "user", "content": json.dumps(generate_info.model_dump())},
            ],
            stream=False
        )
        response_text = chat_completion.choices[0].message.content
        print(response_text)
        call_info = FakeTextContent(text=response_text, type="text")
        return ToolCallResult(type="text", result=call_info)

    def generate_param_by_current_node(self, model: str,
                                       max_tokens: int,
                                       chain_history:List[dict],
                                       current_node_info:dict,
                                       user_input:str):
        # 组建输入
        input = {
            "user_input":user_input,
            "chain_history":chain_history,
            "current_node_info":current_node_info,
        }

        chat_completion = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self.generate_param_prompt},
                {"role": "user", "content": json.dumps(input)},
            ],
            stream=False
        )
        response_text = chat_completion.choices[0].message.content
        print(response_text)
        return extract_json_from_response(response_text)

       # input = {
       #      "user_input":"用户输入",
       #      "chain_history":[
       #          {
       #              "name": "工具名称1",
       #              "result":"工具1的输出"
       #          },
       #          {
       #              "name": "工具名称2",
       #              "result": "工具2的输出"
       #          },
       #          // 如果存在更多，以此类推，工具调用链中的信息只用于辅助当前节点进行参数提取
       #      ],
       #      "current_node_info":{
       #              "name": "当前工具节点名称",
       #              "description": "当前工具的介绍",
       #              "input_schema": {
       #                  // 当前工具的输入参数结构
       #              }
       #      }
       #
       #  }











































