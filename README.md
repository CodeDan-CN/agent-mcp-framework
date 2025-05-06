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

