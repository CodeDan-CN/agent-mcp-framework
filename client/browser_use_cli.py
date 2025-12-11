# 根据browser-use给出具体的策略
import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from browser_use import Agent,Browser

from dataclasses import dataclass
from langchain_openai import ChatOpenAI
from browser_use.llm import ChatDeepSeek


API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-9bd21df8fa2648c1896ff03be93e1481")

# MSEDGE_POSITION=  os.getenv("EXECUTABLE_PATH", "")

@dataclass
class NewsListStrategy:
    """新闻列表爬取策略"""
    base_url: str
    list_urls: List[str]
    pagination_pattern: str = None
    next_page_selector: str = None
    list_item_selector: str = None
    link_selector: str = None
    max_pages: int = 5
    wait_conditions: List[str] = None


class NewsListStrategyGenerator:
    def __init__(self, url, llm, browser, output_path=None):
        self.url=url
        self.llm=llm
        self.browser=browser
        # ✅ 正确设置输出路径
        if output_path is None or output_path == "":
            # 使用相对路径的绝对路径表示，避免路径问题
            base_dir = Path(__file__).parent.parent
            self.output_path = base_dir / "tool" / "data.json"
        else:
            self.output_path = Path(output_path)

        # ✅ 确保输出目录存在
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    async def generate_news_list_strategy(self, website_url: str) :
        """生成新闻列表页面爬取策略"""

        try:
            print(f"🔍 开始分析网站: {website_url}")
            analysis_task = get_prompt_txt(website_url)
            # 在需要时创建 Agent
            agent= Agent(
                task=analysis_task,  # 必需的 task 参数
                llm=self.llm,
                browser= self.browser
            )
            result = await agent.run()
            # 处理爬取到的数据列表页面
            # ✅ 关键修改：从Agent生成的results.json文件中提取结构化数据
            # structured_data = self._extract_final_result(result)

            structured_data = self.get_extract_json(result)
            # 保存到你指定的输出文件
            self._save_to_json(structured_data)
            return structured_data
        except Exception as e:
            print(f"❌ 策略生成失败: {e}")
            return self._get_fallback_strategy(website_url)

    def get_extract_json(self,result):
        extracted_content = result.history[-1].result[-1].extracted_content

        return extracted_content

    def _extract_structured_nav_data(self, agent_result):
        """从Agent结果中提取结构化导航数据"""
        # 方法3：尝试从提取的内容中解析
        try:
            # 检查是否有extracted_content字段
            if hasattr(agent_result, 'extracted_content') and agent_result.extracted_content:
                content = agent_result.extracted_content
                # 提取JSON部分
                start = content.find('{')
                end = content.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = content[start:end]
                    data = json.loads(json_str)
                    return self._transform_to_target_format(data)
        except:
            pass

        # 如果都失败，返回原始结果
        return {"raw_result": str(agent_result)[:500]}  # 只保留前500字符

    def _extract_final_result(self, agent_result):
        """从Agent结果中提取Final Result JSON"""

        # 情况1: 如果result是字符串且包含"Final Result:"
        if isinstance(agent_result, str):
            return self._parse_final_result_from_string(agent_result)

        # 情况2: 如果result是ActionResult对象
        elif hasattr(agent_result, 'extracted_content'):
            content = agent_result.extracted_content
            return self._parse_final_result_from_string(content)

        # 情况3: 如果result是AgentHistoryList
        elif hasattr(agent_result, 'all_results'):
            # 获取最后一个结果（应该是最终结果）
            all_results = agent_result.all_results
            if all_results and len(all_results) > 0:
                last_result = all_results[-1]
                if hasattr(last_result, 'extracted_content'):
                    content = last_result.extracted_content
                    return self._parse_final_result_from_string(content)

        # 情况4: 直接尝试解析
        try:
            if isinstance(agent_result, (dict, list)):
                # 如果已经是JSON格式，直接使用
                return agent_result
        except:
            pass

        # 如果都失败，返回错误
        return {"error": "无法提取Final Result", "raw": str(agent_result)[:200]}

    def _parse_final_result_from_string(self, text):
        """从文本中解析Final Result JSON"""

        # 方法1: 查找"Final Result:"后面的JSON
        import re

        # 查找"📄 Final Result:"或"Final Result:"后面的JSON
        patterns = [
            r'📄\s*Final Result:\s*(\{[\s\S]*\})',
            r'Final Result:\s*(\{[\s\S]*\})',
            r'```json\s*(\{[\s\S]*\})\s*```',
            r'(\{[\s\S]*\"url\"[\s\S]*\"nav_tree\"[\s\S]*\})'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                try:
                    json_str = match.group(1).strip()
                    data = json.loads(json_str)

                    # 确保格式正确
                    if 'url' in data and 'nav_tree' in data:
                        return data
                except json.JSONDecodeError as e:
                    print(f"JSON解析错误: {e}")
                    continue

        # 方法2: 如果没有明确标记，尝试查找整个文本中的JSON
        try:
            # 查找第一个{和最后一个}
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                data = json.loads(json_str)
                if 'url' in data and 'nav_tree' in data:
                    return data
        except:
            pass

        # 如果都失败，返回原始文本的部分内容
        return {"error": "未找到有效的JSON", "text_preview": text[:200]}

    def _process_result(self, result):
        """处理Agent返回的结果"""
        try:
            # 尝试解析为JSON
            if isinstance(result, str):
                # 清理可能存在的代码块标记
                cleaned = result.strip()
                if cleaned.startswith('```json'):
                    cleaned = cleaned[7:]  # 移除 ```json
                if cleaned.endswith('```'):
                    cleaned = cleaned[:-3]  # 移除 ```

                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    # 如果不是JSON，返回原始字符串
                    return {"content": cleaned}
            else:
                # 如果result不是字符串，直接返回
                return result if isinstance(result, dict) else {"result": result}

        except Exception as e:
            print(f"⚠️ 结果处理异常: {e}")
            return {"raw_result": str(result), "process_error": str(e)}

    def _save_to_json(self, data):
        """保存数据到JSON文件"""
        try:
            # 转换为可序列化的格式
            if hasattr(data, 'dict'):  # 处理Pydantic模型
                data_to_save = data.dict()
            elif isinstance(data, (dict, list, str, int, float, bool, type(None))):
                data_to_save = data
            else:
                data_to_save = str(data)

            # 添加元数据
            # 写入文件
            with open(self.output_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f,
                          ensure_ascii=False,  # 支持中文
                          indent=2,  # 美化格式
                          default=str)  # 处理不可序列化的对象

            print(f"✅ 数据已保存到: {self.output_path}")
            print(f"📁 文件大小: {os.path.getsize(self.output_path)} 字节")

        except Exception as e:
            print(f"❌ 保存文件失败: {e}")
            # 尝试保存简化版本
            try:
                with open(self.output_path, 'w', encoding='utf-8') as f:
                    f.write(f"保存失败，错误信息: {str(e)}\n原始数据: {str(data)[:500]}")
            except:
                pass


    def _parse_strategy_result(self, result, website_url: str) -> NewsListStrategy:
        """解析Browser-use的分析结果"""

        content = result if isinstance(result, str) else str(result)

        # 尝试提取JSON数据
        json_match = re.search(r'\{[^{}]*"[^"]*"[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return NewsListStrategy(
                    base_url=data.get('base_url', website_url),
                    list_urls=data.get('list_urls', []),
                    pagination_pattern=data.get('pagination_pattern'),
                    next_page_selector=data.get('next_page_selector', '.next, .pagination-next, a[rel="next"]'),
                    list_item_selector=data.get('list_item_selector', '.news-item, .article-item, .list-item'),
                    link_selector=data.get('link_selector', 'a[href*="/news/"], a[href*="/article/"], a.title'),
                    max_pages=data.get('max_pages', 5),
                    wait_conditions=['networkidle']
                )
            except json.JSONDecodeError:
                pass

        # 如果JSON解析失败，从文本中提取URL
        urls = self._extract_urls_from_text(content, website_url)
        return NewsListStrategy(
            base_url=website_url,
            list_urls=urls,
            next_page_selector='.next, .pagination-next, a[rel="next"]',
            list_item_selector='.news-item, .article-item, .list-item',
            link_selector='a[href*="/news/"], a[href*="/article/"], a.title',
            max_pages=5,
            wait_conditions=['networkidle']
        )

    def _extract_urls_from_text(self, text: str, base_url: str) -> List[str]:
        """从文本中提取新闻列表URL"""
        urls = []

        # 查找URL模式
        url_patterns = [
            r'https?://[^\s<>"\'{}|\\^`\[\]]+',
            r'list\.aspx\?[^\s<>"\']*',
            r'news/list[^\s<>"\']*',
            r'article/list[^\s<>"\']*'
        ]

        for pattern in url_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if any(keyword in match.lower() for keyword in ['news', 'article', 'list', 'category']):
                    if match.startswith('/'):
                        full_url = base_url.rstrip('/') + match
                    elif not match.startswith('http'):
                        full_url = base_url.rstrip('/') + '/' + match.lstrip('/')
                    else:
                        full_url = match

                    if full_url not in urls:
                        urls.append(full_url)

        return urls[:10]  # 限制数量

    def _get_fallback_strategy(self, website_url: str) -> NewsListStrategy:
        """获取回退策略"""
        common_list_patterns = [
            f"{website_url.rstrip('/')}/news",
            f"{website_url.rstrip('/')}/articles",
            f"{website_url.rstrip('/')}/blog",
            f"{website_url.rstrip('/')}/category/news",
            f"{website_url.rstrip('/')}/list"
        ]

        return NewsListStrategy(
            base_url=website_url,
            list_urls=common_list_patterns,
            next_page_selector='.next, .pagination-next, a[rel="next"]',
            list_item_selector='.news-item, .article-item, .list-item',
            link_selector='a[href*="/news/"], a[href*="/article/"]',
            max_pages=3,
            wait_conditions=['networkidle']
        )

async def scraping_pre_tasks(url, llm, browser, output_path):
    generator = NewsListStrategyGenerator(url,llm, browser, output_path)
    strategies = await generator.generate_news_list_strategy(url)

async def init_strategy(url: str,output_path):
    # Events.startup(application)
    # 1. 初始化 DeepSeek 模型
    llm = ChatDeepSeek(
        base_url='https://api.deepseek.com/v1',
        model='deepseek-chat',
        api_key=API_KEY,
    )
    # browser = Browser(
    #     headless=True,
    #     profile_directory='Default'
    # )
    browser = Browser(
        # 核心配置
        id="browser_2",  # 浏览器实例ID
        headless=False,   # 无头模式
        user_data_dir='./user_data',  # 保存会话数据
        # 浏览器启动参数
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-web-security',
            '--disable-blink-features=AutomationControlled',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
            '--disable-plugins',
            '--disable-translate',
        ],

        # 视口和窗口设置
        viewport={'width': 1920, 'height': 1080},
        window_size={'width': 1920, 'height': 1080},

        # 用户代理
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',

        # 用户数据目录（保存cookies等）
        profile_directory='Default',

        # 安全设置
        disable_security=True,
        ignore_default_args=['--enable-automation'],

        # 性能设置
        wait_between_actions=0.1,  # 操作间等待时间
        minimum_wait_page_load_time=2.0,  # 最小页面加载等待
    )
    date_now = datetime.now()
    two_days_ago = date_now - timedelta(days=2)
    two_days_str = two_days_ago.strftime("%Y-%m-%d")
    date_now_str = date_now.strftime("%Y-%m-%d")

    current_date_period = f"""{two_days_str}-{date_now_str}"""

    scraping_tasks = [
        scraping_pre_tasks(url, llm, browser, output_path)
    ]

    results = await asyncio.gather(*scraping_tasks)
    print(results)


### website_url 为需要爬取的具体地址，
### need_spider_all: True为是否需要直接爬取整个网站的产品及服务内容，False为只爬取第一部分
def get_prompt_txt(website_url: str, need_spider_all:bool = False):
    if need_spider_all:
        return  f"""
                    目标：完整爬取官网所有页面的产品服务和解决方案数据，当前官网url为{website_url}
                    多维度分页处理方案：
    
                    一、分页类型识别与应对：
                    🔹 传统分页器：数字页码 → 遍历所有页码
                    🔹 下一页模式：Next按钮 → 循环点击直到结束  
                    🔹 加载更多：Load More按钮 → 持续点击直到无新内容
                    🔹 无限滚动：滚动到底部 → 模拟滚动触发加载
                    🔹 标签页切换：Tab切换 → 逐个标签页提取
    
                    二、数据提取精度保障：
                    ✅ 标题清洗：去除多余空格、特殊符号、数字标记
                    ✅ URL标准化：相对路径转绝对路径，去除跟踪参数
                    ✅ 分类验证：确保每个条目正确归类
                    ✅ 去重机制：基于URL和标题内容的联合去重
    
                    三、异常处理机制：
                    ⚠️ 页面加载超时 → 重试机制
                    ⚠️ 分页元素缺失 → 尝试替代定位方式
                    ⚠️ 数据重复出现 → 智能去重过滤
                    ⚠️ 反爬虫拦截 → 调整操作频率
    
                    四、进度监控与报告：
                    📊 实时记录已爬取页面数量
                    📊 统计各类别数据条目
                    📊 监控数据增长趋势
                    📊 识别爬取完成状态
    
                    执行流程：
                    1. 提取当前页面的所有产品服务和解决方案条目
                    2. 识别分页机制并遍历所有页面
                    3. 收集所有数据到统一数组
                    4. 数据去重和清理
    
                    数据格式要求：
                    返回纯JSON数组，每个元素包含：
                    - category: 分类（"products_services" 或 "solutions"）
                    - title: 清理后的标题文本
                    - content: 需要进入到产品的详情页中总结一下内容
                    - url: 完整URL地址  
                    - page: 页码
                    类似于以下输出：
                    ```json
                        {{
                            "result": [{{
                                "category":"",
                                "title": "",
                                "content":"",
                                "url":"",
                                "page":""
                            }}]
                        }}
                    ```
                    最终输出完整的分页数据集。
                    """
    else:
        return f"""
           ## 任务：识别网站中的产品和服务导航链接，需要进入的网站为 {website_url}

            ### 目标
            在当前网页中，直接找到所有指向**产品**或**服务**相关内容的导航链接，无需点击进入子页面。
            
            ### 操作步骤
            1. **全面扫描导航区域**
               - 查找页面上所有导航菜单、侧边栏、页脚链接
               - 包括：主导航、二级菜单、快速链接、页脚导航等
            
            2. **识别产品/服务相关链接**
               - 重点关注包含以下关键词的链接文本：
                 * 产品类：产品、解决方案、服务、功能、特性、定价、套餐、版本
                 * 商业类：购买、订购、试用、演示、咨询、报价、客户、案例
                 * 行业类：行业解决方案、应用场景、使用案例
                 - 常见产品词：Product, Solution, Service, Feature, Pricing, Plan, Package, Demo, Trial
                 - 中文产品词：产品、解决方案、服务、功能、定价、套餐、演示、试用
            
            3. **收集链接信息**
               对于每个疑似产品/服务的链接，提取：
               - 链接文本（完整文本）
               - 链接URL（完整的href属性值）
               - 所在位置（如：主导航、页脚、侧边栏等）
               - 可见性（是否直接可见，还是需要悬停/点击展开）
            
            4. **排除无关链接**
               - 跳过明显无关的链接：首页、关于我们、新闻动态、博客、帮助文档、技术支持、联系我们（除非是"商务联系"）
               - 跳过非导航性链接：登录、注册、搜索图标等（除非是"企业注册"）
               - 跳过功能性链接：语言切换、下载APP等
            
            ### 输出格式
            请以JSON形式返回结果，以下为返回的内容格式：
            ```json
            {{
                  "url": "这里为跳转进入的网站url",
                  "nav_tree": [
                    {{
                      "title": "首页",
                      "url": "这里为具体栏目的url",
                      "children": [], # 这里为二级的导航链接
                      "features": [] # 这个是特征不需要提取，默认为空数组即可
                    }},
                    {{
                      "title": "帮助中心",
                      "url": "https://www.giant.com.cn/",
                      "children": [
                        {{
                          "title": "Q&A",
                          "url": "http://www.giant.com.cn/index.php/index/faq.html",
                          "children": [],
                          "features": []
                        }},
                        {{
                          "title": "帮助说明",
                          "url": "http://www.giant.com.cn/index.php/index/help.html",
                          "children": [],
                          "features": []
                        }}
                      ],
                      "features": []
                    }}
                  ]
                }}
                只返回JSON，不要其他任何解释文字。
            """

if __name__ == '__main__':
     url = "https://www.t-head.cn/"
     output_path="../tool/data.json"
     asyncio.run(init_strategy(url,output_path))
