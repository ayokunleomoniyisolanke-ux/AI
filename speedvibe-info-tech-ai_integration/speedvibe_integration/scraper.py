"""
Crawl https://speedvibeinfotech-hub.com.ng (or another same-origin site) for RAG ingestion.
Same-origin BFS pattern as app/modules/lms/scraper.py.
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class SpeedvibeWebsiteScraper:
    def __init__(self, base_url: str, max_pages: int = 50):
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith("http"):
            self.base_url = "https://" + self.base_url
        self.max_pages = max_pages
        self.visited: set[str] = set()
        self.domain = urlparse(self.base_url).netloc

    async def scrape_page(self, url: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; SpeedvibeRAGBot/1.0)"},
                )
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            main_content = (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", class_="content")
                or soup.body
            )

            if main_content:
                text = main_content.get_text(separator=" ", strip=True)
            else:
                text = soup.get_text(separator=" ", strip=True)

            text = " ".join(text.split())

            links: list[str] = []
            for link in soup.find_all("a", href=True):
                full_url = urljoin(url, link["href"])
                if self._is_valid_url(full_url):
                    links.append(full_url)

            logger.info("[Speedvibe] Scraped %s | %s chars | %s links", url, len(text), len(links))

            return {
                "url": url,
                "title": title,
                "content": text,
                "links": list(set(links)),
            }

        except Exception as e:
            logger.error("[Speedvibe] Error scraping %s: %s", url, e)
            return None

    def _is_valid_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.netloc != self.domain:
                return False

            excluded_extensions = [".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".mp4", ".mp3"]
            if any(parsed.path.lower().endswith(ext) for ext in excluded_extensions):
                return False

            excluded_paths = ["/api/", "/admin/", "/login/", "/search?"]
            if any(excluded in parsed.path.lower() for excluded in excluded_paths):
                return False

            return True

        except Exception:
            return False

    async def scrape_website(self) -> list[dict]:
        to_visit = [self.base_url]
        pages_data: list[dict] = []

        logger.info("[Speedvibe] Starting scrape: %s (max %s pages)", self.base_url, self.max_pages)

        while to_visit and len(pages_data) < self.max_pages:
            url = to_visit.pop(0)

            if url in self.visited:
                continue

            self.visited.add(url)

            page_data = await self.scrape_page(url)

            if page_data and len(page_data["content"]) > 100:
                pages_data.append(page_data)

                for link in page_data["links"]:
                    if link not in self.visited and link not in to_visit:
                        to_visit.append(link)

            await asyncio.sleep(0.5)

        logger.info("[Speedvibe] Scraping complete: %s pages", len(pages_data))
        return pages_data
