from dotenv import load_dotenv
from langchain_google_community import GoogleSearchAPIWrapper
from langchain_community.utilities.bing_search import BingSearchAPIWrapper
from mcp.server import FastMCP

import os
# os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
# os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
load_dotenv()  # 自动加载 .env 文件
google_api_key = os.environ["GOOGLE_API_KEY"]
google_cse_id = os.environ["GOOGLE_CSE_ID"]
# Initialize FastMCP server
mcp = FastMCP("Search")

# 初始化搜索器（用你的 API Key 和 CSE ID）
search = GoogleSearchAPIWrapper(
    google_api_key=google_api_key,
    google_cse_id=google_cse_id,
    k=5  # 返回前5条结果
)

@mcp.tool(name="google_search")
async def google_search_info(query: str) -> str:
    """
    Perform a Google search and return formatted results.

    Uses Google Search to find information based on the query and returns
    the specified number of results in a formatted string.

    Args:
        query (str): The search term or phrase to look up on Google.
    """
    # 搜索关键词
    results = search.results(query, 1)
    return str(results[0].get("snippet"))

# 请替换为你自己的 Bing 订阅密钥
bing_subscription_key = "d41d328a36aa498abe25a7ee9864126c"
# 默认的 Bing 搜索 API endpoint
bing_search_url = "https://api.bing.microsoft.com/v7.0/search"

# 初始化 BingSearchAPIWrapper
bing_search = BingSearchAPIWrapper(
    bing_subscription_key=bing_subscription_key,
    bing_search_url=bing_search_url,
    k=5  # 返回前5条结果
)

@mcp.tool(name="bing_search")
async def bing_search_info(query: str) -> str:
    """
    Perform a Bing search and return formatted results.

    Uses Bing Search to find information based on the query and returns
    the specified number of results in a formatted string.

    Args:
        query (str): The search term or phrase to look up on Bing.
    """
    # 搜索关键词
    results = bing_search.results(query, 1)
    return str(results[0].get("snippet"))

@mcp.tool(name="book_flight")
async def book_flight(departure_city: str,destination_city:str,date:str) -> str:
    """
    Book a flight ticket based on departure city, destination, and date.

    Automatically books a flight for the user using the provided travel details
    and returns a confirmation message including a generated order number.

    Args:
        departure_city (str): The city from which the user will depart.
        destination_city (str): The city to which the user wants to travel.
        date (str): The desired date of the flight in YYYY-MM-DD format.
    """
    return f"已帮您定好日期为{date}，从{departure_city}到{destination_city}的机票，订单号为:1122334455667788"

@mcp.tool(name="weather_search")
async def weather_search(city: str,date:str) -> str:
    """
    Retrieve the weather forecast for a given city and date.

    Uses a weather information service to fetch and return the forecast for the specified
    city and date in a human-readable format.

    Args:
        city (str): The name of the city to get the weather information for.
        date (str): The date to retrieve the weather forecast for, in YYYY-MM-DD format.
    """
    return f"日期{date},城市：{city}的天气为晴天转多云"


@mcp.tool(name="order_info")
async def order_info(order: str) -> str:
    """
    Retrieve the current status of a flight using the order number.
    Args:
    order (str): The flight order number used to retrieve flight status information.
    """
    return f"根据订单号{order},查询出当前此次航班的在线情况为 停泊状态"


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')



