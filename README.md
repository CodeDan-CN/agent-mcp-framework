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