import logging
import re
from typing import TypeAlias, Union

import html2text
from bs4 import BeautifulSoup, Comment, PageElement, Tag, NavigableString

OneElement: TypeAlias = Union[PageElement, Tag, NavigableString]

logger = logging.getLogger(__name__)

class DomCleanError(Exception):
    """自定义异常类，用于表示DOM清洗错误"""
    pass


class DomDataClean:
    def __init__(self, dom: str):
        self.dom = dom

    def clean(self) -> str:
        """清洗dom并转换为文本"""
        body = self.clean_dom_tags()
        cleaned_data = self.cleaned_dom_to_text(body)
        return cleaned_data

    def clean_dom_tags(self) -> BeautifulSoup:
        """清洗dom里面不需要的标签和属性"""
        try:
            soup = BeautifulSoup(self.dom, features='html.parser')
            for child in soup.find_all(['div', 'table']):
                # 排除自身是 span 的情况
                if child.name != 'span':
                    self._process_element(child, soup)
            body = soup.find("body")
            if not body:
                raise DomCleanError("No <body> tag found in the HTML content.")

            for tag in body.find_all(
                    ['link', 'style', 'script', 'head', 'header', 'foot', 'footer', 'img', 'button']):
                tag.extract()

            for tag in body.find_all('div', class_=lambda x: x and ('header' in x or 'footer' in x)):
                tag.extract()

            for comment in body.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()

            # 找到所有 <select> 元素
            for select in soup.find_all('select'):
                select.decompose()  # 移除 <select> 标签及其内容

            # 删除所有剩余标签中的class、style、href内容
            for tag in body.find_all(True):
                if 'class' in tag.attrs:
                    del tag['class']
                if 'style' in tag.attrs:
                    del tag['style']
                if 'href' in tag.attrs:
                    del tag['href']
            return body
        except Exception as e:
            logger.error(f"DOM Clean Error: {e}")
            raise DomCleanError(f"DOM Clean Exception: {e}")

    @staticmethod
    def cleaned_dom_to_text(body: BeautifulSoup) -> str:
        """
        实现逻辑：
        1. 保留所有table标签的内容并转换为md格式
        2. 将所有的HTML标签去除，仅保留纯文本，注意以下两点：
            a. 遇到标签时，需要将标签去除，并删除标签带来的所有换行，即保证处理后的文本段落和网页上显示的一致
            b. 每一个标签在去除的时候，保留其原有的缩进，保证清洗后的内容缩进和原来一致，保留了原有的层级结构信息
        """

        # 保留所有table标签的内容并转换为md格式
        tables = body.find_all('table')
        md_tables = []
        for table in tables:
            md_tables.append(html2text.html2text(str(table.prettify())))

        def remove_tags_with_indentation(soup):
            """删除所有的HTML标签，但是将层级信息以缩进的空格来体现"""
            lines = soup.prettify().splitlines()
            cleaned_lines = []
            table_count = 0
            table_level = 0
            table_on = 0
            skip = 0
            indent = 0
            indentation = 0
            for line in lines:
                # if table_on == 0:
                if '<table' in line:
                    table_level += 1  # 进入新的表格层级
                    if table_level == 1:  # 只处理最外层表格内容
                        text = re.sub(r'<[^>]+>', '', md_tables[table_count])
                        cleaned_lines.append(text)
                        table_count += 1
                        skip = 1
                        continue
                elif '</table' in line:
                    table_level -= 1  # 离开当前表格层级
                    if table_level == 0:  # 最外层表格结束
                        skip = 0
                        continue
                elif skip == 0 and indent == 0 and table_level == 0:
                    # Remove tags but keep indentation
                    text = re.sub(r'<[^>]+>', '', line)
                    if len(text.strip()) > 0:
                        stripped_line = text.lstrip()
                        indentation = len(line) - len(stripped_line)
                        cleaned_lines.append(text)
                        indent = 1
                elif skip == 0 and indent == 1 and table_level == 0:
                    pattern = re.compile(r'</[^>]+>')
                    if pattern.search(line):
                        text = re.sub(r'<[^>]+>', '', line)
                        indent = 0
                    else:
                        text = indentation * ' ' + re.sub(r'<[^>]+>', '', line)
                    cleaned_lines.append(text)
            return '\n'.join(cleaned_lines)

        cleaned_content = remove_tags_with_indentation(body)

        # 删除多余的空行
        cleaned_content = re.sub(r'\n\s*\n+', '\n', cleaned_content)
        cleaned_content = re.sub(r'-->', '', cleaned_content)

        return cleaned_content

    def _process_element(self, element: OneElement, soup: BeautifulSoup):
        self._remove_newlines_and_nbsp_from_spans(element)
        spans = element.find_all('span', recursive=False)
        i = 0
        while i < len(spans):
            start = i
            # 查找连续的 span
            while i + 1 < len(spans) and spans[i].find_next_sibling() == spans[i + 1]:
                i += 1

            nested_spans = []
            for j in range(start, i + 1):
                nested_spans.extend(spans[j].find_all('span', recursive=True))

            # 找到多个连续的 span 或者存在嵌套的 span
            if i > start or nested_spans:
                # 合并文本
                merged_text = ''.join(span.get_text() for span in spans[start:i + 1])

                for nested_span in nested_spans:
                    merged_text += nested_span.get_text()

                new_span = soup.new_tag('span')
                new_span.string = merged_text
                spans[start].insert_after(new_span)
                # 删除旧的 span
                for j in range(start, i + 1):
                    spans[j].decompose()

            i += 1

        # 递归处理子 span
        for span in element.find_all('span', recursive=False):
            self._process_element(span, soup)

    @staticmethod
    def _remove_newlines_and_nbsp_from_spans(element: OneElement) -> None:
        """移除span中的换行符和&nbsp;字符"""
        spans = element.find_all('span', recursive=True)
        for span in spans:
            text = span.get_text()
            # 替换掉&nbsp;字符，并移除换行符
            text = text.replace('\xa0', ' ').replace('\u00a0', ' ').replace('&nbsp;', ' ').replace('\n', ' ')
            span.string = text
