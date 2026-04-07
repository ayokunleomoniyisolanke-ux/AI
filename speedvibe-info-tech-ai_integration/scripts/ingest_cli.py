"""
CLI: scrape https://speedvibeinfotech-hub.com.ng (or --url) and ingest into Chroma.

Usage (from speedvibe-info-tech-ai_integration):
  set PYTHONPATH=.
  python scripts/ingest_cli.py
  python scripts/ingest_cli.py --max-pages 30 --url https://speedvibeinfotech-hub.com.ng
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run(base_url: str, max_pages: int) -> None:
    from speedvibe_integration.config import settings
    from speedvibe_integration.rag_chroma import SpeedvibeChromaRAG
    from speedvibe_integration.scraper import SpeedvibeWebsiteScraper

    if not settings.OPENAI_API_KEY:
        logger.error("Set OPENAI_API_KEY in .env (copy from .env.example)")
        sys.exit(1)

    rag = SpeedvibeChromaRAG()
    scraper = SpeedvibeWebsiteScraper(base_url, max_pages=max_pages)
    pages = await scraper.scrape_website()
    ok = 0
    for page in pages:
        try:
            await rag.store_page_content(
                url=page["url"],
                title=page["title"],
                content=page["content"],
                metadata={"scraped_from": base_url},
            )
            ok += 1
        except Exception as e:
            logger.error("Store failed %s: %s", page.get("url"), e)
    logger.info("Done: stored %s / %s pages", ok, len(pages))


def main() -> None:
    p = argparse.ArgumentParser(description="Ingest Speedvibe site into Chroma RAG")
    p.add_argument(
        "--url",
        default=None,
        help="Base URL (default: SPEEDVIBE_BASE_URL from env or speedvibeinfotech-hub.com.ng)",
    )
    p.add_argument("--max-pages", type=int, default=50)
    args = p.parse_args()

    from speedvibe_integration.config import settings

    url = args.url or settings.SPEEDVIBE_BASE_URL
    asyncio.run(run(url, args.max_pages))


if __name__ == "__main__":
    main()
