### 如何启动项目

第一步：依赖安装
pip install -r requirements.txt

第二步：在项目根目录下创建.env文件，补充下述环境变量
```text
GOOGLE_API_KEY=""
GOOGLE_CSE_ID=""
BING_API_KEY=""
BING_SEARCH_URL="https://api.bing.microsoft.com/v7.0/search"
MODEL_API_KEY =""
MODEL_BASE_URL=""
MCP_TOOL_PATH ="tool.py path url "
MODEL_NAME ="gpt-4o-mini"
MODEL_TYPE = "openai"
```

第三步：启动cli.py文件即可

问题实例1（预计调用google_search或者bing_search工具，这两个工具需要配置好代理）： 小米su7怎么样？

问题实例2（预计不调用工具）： 你好啊

问题实例3（预计调用组合工具链）：帮我预定2025年5月6日武汉到广州的机票，并且帮我看看那趟航班的信息和两地的天气

问题实例4（对话记忆功能）：
组合问题：
    问题1: 今天是2025年5月6日，我在武汉，帮我看看现在武汉天气怎么样
    问题2: 帮我预定一趟去广东的飞机
    问题3: 给我展示一下这趟航班的信息



### 2025年4月份迭代计划
（1）初步搭建mcp客户端 （☑️）
（2）替换统一调用模型（☑️）
（3）调研langchain的graph工作流节点（☑️）

### 2025年5月份迭代计划
（1）调研开源项目intel opea的微服务组成架构，改写成本项目的微服务架构，并结合langgraph进行统一微服务节点工作流编排
（2）fastapi微服务架构搭建
（3）langgraph工作流编排搭建
（4）提示词使用规范化（langchain v3）（☑️）
（5）新增聊天历史功能 (☑️)

### 2025年6月份迭代计划
待定

