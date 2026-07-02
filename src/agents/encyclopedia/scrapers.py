"""
网页抓取器 — 从京东/天猫/官网抓取商品信息
"""

import re
from typing import Optional

from bs4 import BeautifulSoup
from parsel import Selector

from src.utils.http_client import AsyncHTTPClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BaseScraper:
    """抓取器基类"""

    name: str = "base"

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy

    async def fetch(self, url: str) -> str:
        """抓取页面 HTML"""
        async with AsyncHTTPClient(proxy=self.proxy) as client:
            response = await client.get(url)
            return response.text

    def parse_price(self, text: str) -> Optional[float]:
        """从文本中提取价格"""
        if not text:
            return None
        match = re.search(r'[\d,]+(?:\.\d{2})?', str(text))
        if match:
            return float(match.group().replace(',', ''))
        return None

    async def search(self, keyword: str) -> dict:
        """搜索商品，返回 {title, price, url}"""
        raise NotImplementedError


class JDScraper(BaseScraper):
    """京东商品抓取器（需要处理反爬）"""

    name = "jd"

    async def search(self, keyword: str) -> dict:
        """在京东搜索商品"""
        search_url = f"https://search.jd.com/Search?keyword={keyword}&enc=utf-8"
        try:
            html = await self.fetch(search_url)
            sel = Selector(text=html)

            # 京东页面结构可能变化，以下为示例选择器
            first_item = sel.css(".gl-item:first-child")
            title = first_item.css(".p-name em::text").get()
            price_text = first_item.css(".p-price i::text").get()
            item_url = first_item.css(".p-img a::attr(href)").get()

            return {
                "channel": "jd",
                "title": title.strip() if title else f"京东搜索结果: {keyword}",
                "price": self.parse_price(price_text),
                "url": f"https:{item_url}" if item_url and item_url.startswith("//") else item_url,
                "in_stock": True,
            }
        except Exception as e:
            logger.warning(f"京东搜索失败: {e}")
            return {"channel": "jd", "title": keyword, "price": None, "url": search_url, "in_stock": True}


class TmallScraper(BaseScraper):
    """天猫商品抓取器"""

    name = "tmall"

    async def search(self, keyword: str) -> dict:
        """在天猫搜索商品"""
        search_url = f"https://list.tmall.com/search_product.htm?q={keyword}"
        try:
            html = await self.fetch(search_url)
            soup = BeautifulSoup(html, "lxml")

            first_item = soup.select_one(".product")
            title = first_item.select_one(".productTitle").text if first_item else None
            price = first_item.select_one(".productPrice").text if first_item else None
            item_url = first_item.select_one(".productImg")["href"] if first_item else None

            return {
                "channel": "tmall",
                "title": title.strip() if title else f"天猫搜索结果: {keyword}",
                "price": self.parse_price(price),
                "url": item_url,
                "in_stock": True,
            }
        except Exception as e:
            logger.warning(f"天猫搜索失败: {e}")
            return {"channel": "tmall", "title": keyword, "price": None, "url": search_url, "in_stock": True}


# 注册可用的抓取器
SCRAPERS: dict[str, BaseScraper] = {
    "jd": JDScraper(),
    "tmall": TmallScraper(),
}
