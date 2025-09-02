import csv
import json
import logging
import os
import re
from typing import Any
import asyncio

from json_repair import json_repair
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseLanguageModel

from template import PRODUCT_EXTRACT_PROMPT
from tool.data_extract.crawl_webpage import WebCrawler
from tool.data_extract.dom_data_clean import DomDataClean

api_key = os.environ["MODEL_API_KEY"]
base_url = os.environ["MODEL_BASE_URL"]
model_name = os.environ["MODEL_NAME"]
model_type = os.environ["MODEL_TYPE"]
output_dir = os.environ["OUTPUT_PATH"]

llm = init_chat_model(model_name, model_provider=model_type, temperature=0, api_key=api_key,
                      base_url=base_url)

logger = logging.getLogger(__name__)


class ProductExtract:

    @classmethod
    async def extract(cls, input_path: str, llm: BaseLanguageModel = llm, score_norm_threshold: float = 0.7, max_concurrent: int = 8):
        """产品信息抽取"""
        # 从json文件中读取数据
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 过滤所有符合分数阈值的 URL
        nav_tree = data.get("nav_tree", [])
        filtered_urls = cls.collect_urls(nav_tree, score_norm_threshold)

        # 并发处理每个 URL
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)
        tasks = [cls.extract_by_url(llm, url, semaphore) for url in filtered_urls]
        all_results = await asyncio.gather(*tasks)
        for res in all_results:
            results.extend(res)

        unique_results = cls.deduplicate_results(results)
        # 保存结果到csv文件
        output_path = f"{output_dir}/product_extract_results.csv"
        cls.write_results_to_csv(unique_results, output_path)
        logger.info(f"Extraction completed. Results saved to {output_path}")

    @classmethod
    async def extract_by_url(cls, llm: BaseLanguageModel, url: str, sem: asyncio.Semaphore) -> list[dict]:
        """按照url进行网页产品信息抽取"""
        try:
            async with sem:
                dom = await WebCrawler.crawl(url)
                content = DomDataClean(dom=dom).clean()
                messages = [
                    {"role": "system", "content": PRODUCT_EXTRACT_PROMPT},
                    {"role": "user", "content": content}
                ]
                response = await llm.ainvoke(messages)
                json_data = cls.extract_json_from_output(response.content)
                logger.info(f"Extracted {len(json_data)} products from {url}")
                if not isinstance(json_data, list):
                    raise ValueError(f"Expected a list but got {type(json_data)}")
                result = [
                    {
                        "product_url": url,
                        "product_name": item.get("name", ""),
                        "product_description": item.get("description", "")
                    }
                    for item in json_data if isinstance(item, dict)
                ]
        except Exception as e:
            logger.warning(f"Error processing URL {url}: {e}")
            result = []
        return result

    @staticmethod
    def collect_urls(node: list, score_norm_threshold: float = 0.7) -> list[str]:
        """筛选所有符合分数阈值的 URL"""
        urls = []
        queue = list(node)
        while queue:
            node = queue.pop(0)
            if node.get('score_norm', 0) >= score_norm_threshold and 'url' in node:
                urls.append(node['url'])
            queue.extend(node.get('children', []))
        return urls

    @staticmethod
    def extract_json_from_output(output: str) -> Any:
        """json解析"""
        match = re.search(r"```(json)?(.*?)```", output, re.DOTALL)
        if match:
            json_str = match.group(2)
        else:
            json_str = output

        try:
            json_parse = json_repair.loads(json_str)
            return json_parse
        except Exception:
            raise ValueError(f"Failed to decode JSON:{json_str[:1000]}")

    @staticmethod
    def write_results_to_csv(results: list[dict], output_path: str) -> None:
        """将结果写入CSV文件"""
        if not results:
            logger.info("No products extracted.")
            return
        fieldnames = results[0].keys()
        with open(output_path, "w", encoding="utf-8", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in results:
                writer.writerow(row)

    @staticmethod
    def normalize_name(name: str) -> str:
        """标准化产品名，去重时使用"""
        if not name:
            return ""
        # 转小写，去空格，去掉特殊符号
        name = name.lower().strip()
        name = re.sub(r"[\s\-_·.]+", " ", name)  # 连续符号和多空格替换为单空格
        return name

    @classmethod
    def deduplicate_results(cls, results: list[dict]) -> list[dict]:
        """以product_name为主，去重，保留description最长的记录"""
        best_records = {}
        for item in results:
            norm_name = cls.normalize_name(item.get("product_name", ""))
            if not norm_name:
                continue  # 跳过无效名字
            # 如果已有同名，比较description长度
            existing = best_records.get(norm_name)
            if existing:
                if len(item.get("product_description", "")) > len(existing.get("product_description", "")):
                    best_records[norm_name] = item
            else:
                best_records[norm_name] = item
        return list(best_records.values())


if __name__ == "__main__":
    import asyncio

    asyncio.run(ProductExtract.extract("/Users/codedan/local/project/crawlee/agent-mcp-framework/file/data_scored3.json",llm, score_norm_threshold=0.7, max_concurrent=8))
