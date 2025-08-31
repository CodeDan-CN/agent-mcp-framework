import asyncio
import logging

from playwright.async_api import async_playwright, Page

logger = logging.getLogger(__name__)


class CrawlError(Exception):
    """自定义异常类，用于表示爬取错误"""
    pass


class WebCrawler:

    @classmethod
    async def crawl(cls, url: str):
        """使用 Playwright 爬取网页内容"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            )

            await context.route("**/*", cls.block_resource)  # 应用资源过滤
            page = await context.new_page()
            content = await cls.navigate_page(page, url)
            await context.close()
            await browser.close()
            return content

    @classmethod
    async def block_resource(cls, route):
        """阻止加载图片、媒体文件、字体和样式表"""
        if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
            await route.abort()
        else:
            await route.continue_()

    @classmethod
    async def navigate_page(cls, page: Page, url: str) -> str:
        """访问指定的页面，返回网页抓取是否成功和页面dom，如果抓取失败返回失败信息"""
        try:
            response = await page.goto(url, timeout=90000, wait_until='domcontentloaded')
            await cls.scroll_to_bottom(page)
            if response.ok or response.status == 304:
                content = await page.content()
                return content
            else:
                err_msg = f"Navigate failed: StatusCode {response.status}, StatusText: {response.status_text}"
                logger.warning(err_msg)
                raise CrawlError(err_msg)
        except Exception as e:
            logger.error(f"Navigate Exception: {e}")
            raise CrawlError(f"Navigate Exception: {e}")

    @classmethod
    async def scroll_to_bottom(cls, page, scroll_pause_time=1, max_scroll_count=10):
        """滚动页面到最下方，确保按需加载内容被加载出来"""
        scroll_count = 0
        last_height = await page.evaluate("() => document.body.scrollHeight")

        while scroll_count < max_scroll_count:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(scroll_pause_time)
            new_height = await page.evaluate("() => document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_count += 1
