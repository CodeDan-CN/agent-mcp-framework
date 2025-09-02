### 如何启动项目
##### 下载相关依赖（已有conda环境和npm环境）
1.首先你要跳转到当前项目根目录中,下载python依赖
```bash
pip install -r requirements.txt
```

2.然后你要跳转到tool目录中的add_tree,init_tree下,进行node依赖的下载
```bash
npm install
```

##### 进行环境变量设置
在启动cli.py之前，设置下述环境变量
MODEL_NAME=gpt-4o-mini;
MODEL_TYPE=openai;
MODEL_API_KEY=your_api_key;
MODEL_BASE_URL=https://api.aigc369.com/v1;
OUTPUT_PATH=/Users/codedan/local/project/crawlee/agent-mcp-framework/file 

其中OUTPUT_PATH替换成你机器存在的目录，爬取中间过程文件和最终csv均会在此

##### 启动cli.py，并且输入你的要求
启动会看到命令行中出现
Nav Tree MCP Server running on stdio
✅ Connected to 1 tool services,name:../tool/init_tree/index.js
✅ Connected to 2 tool services,name:../tool/node_filter/tree_node_filter.py
Nav Tree MCP Server running on stdio
✅ Connected to 3 tool services,name:../tool/add_tree/index.js

MCP Client Started!
Type your queries or 'quit' to exit.

Query:

这个时候输入你的指令：帮我爬取https://www.digitalchina.com/和其子链中的产品和服务信息，边爬边剪枝，完成第三层爬取和剪枝之后，结束即可
这样就可以触发mcp agent思考，安排爬取流程。
