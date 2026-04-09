"""FastAPI routes for Speedvibe RAG + chat (mount under /api/v1)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, WebSocket

from speedvibe_integration.chat import handle_speedvibe_chat
from speedvibe_integration.config import settings
from speedvibe_integration.rag_chroma import SpeedvibeChromaRAG
from speedvibe_integration.schemas import (
    SpeedvibeChatRequest,
    SpeedvibeChatResponse,
    SpeedvibeKnowledgeStats,
    SpeedvibeScrapeRequest,
    SpeedvibeScrapeResponse,
    SpeedvibeSearchResponse,
    SpeedvibeSearchResult,
)
from speedvibe_integration.scraper import SpeedvibeWebsiteScraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/speedvibe", tags=["Speedvibe Info Tech"])

_rag_singleton: SpeedvibeChromaRAG | None = None


def _get_rag() -> SpeedvibeChromaRAG:
    global _rag_singleton
    if _rag_singleton is None:
        _rag_singleton = SpeedvibeChromaRAG()
    return _rag_singleton


async def _scrape_and_store(base_url: str, max_pages: int) -> None:
    try:
        rag = _get_rag()
        logger.info("[Speedvibe] Starting scrape for %s", base_url)
        scraper = SpeedvibeWebsiteScraper(base_url, max_pages=max_pages)
        pages = await scraper.scrape_website()
        stored = 0
        for page in pages:
            try:
                await rag.store_page_content(
                    url=page["url"],
                    title=page["title"],
                    content=page["content"],
                    metadata={"scraped_from": base_url},
                )
                stored += 1
            except Exception as e:
                logger.error("[Speedvibe] Failed to store %s: %s", page.get("url"), e)
        logger.info("[Speedvibe] Ingest done: %s/%s pages stored", stored, len(pages))
    except Exception as e:
        logger.error("[Speedvibe] Scrape task failed: %s", e)


@router.websocket("/web-call")
async def speedvibe_web_call_endpoint(websocket: WebSocket) -> None:
    """
    Gemini Live voice. Uses main backend's handler when `app` is available;
    otherwise uses standalone `gemini_voice` (same protocol as LMS widget).
    """
    try:
        from app.modules.telephonics.gemini_live import handle_gemini_web_call

        await handle_gemini_web_call(websocket, assistant="speedvibe")
    except ImportError:
        from speedvibe_integration.gemini_voice import handle_speedvibe_gemini_web_call

        await handle_speedvibe_gemini_web_call(websocket)


@router.post("/chat", response_model=SpeedvibeChatResponse)
async def speedvibe_chat(request: SpeedvibeChatRequest) -> SpeedvibeChatResponse:
    return await handle_speedvibe_chat(request)


@router.post("/scrape", response_model=SpeedvibeScrapeResponse)
async def trigger_scrape(
    request: SpeedvibeScrapeRequest,
    background_tasks: BackgroundTasks,
) -> SpeedvibeScrapeResponse:
    base = str(request.website_url) if request.website_url else settings.SPEEDVIBE_BASE_URL
    background_tasks.add_task(_scrape_and_store, base, request.max_pages)
    return SpeedvibeScrapeResponse(
        message=f"Scraping started for {base} (max {request.max_pages} pages)",
        status="started",
    )


@router.get("/stats", response_model=SpeedvibeKnowledgeStats)
async def stats() -> Any:
    rag = _get_rag()
    s = rag.get_stats()
    return SpeedvibeKnowledgeStats(
        total_documents=s["total_documents"],
        collection_name=s.get("collection_name", "speedvibe_knowledge_base"),
        database_type=s.get("database_type", "ChromaDB"),
    )


@router.get("/search", response_model=SpeedvibeSearchResponse)
async def search_knowledge(query: str, top_k: int = 3) -> SpeedvibeSearchResponse:
    rag = _get_rag()
    results = await rag.search_relevant_content(query, top_k=top_k)
    return SpeedvibeSearchResponse(
        query=query,
        results=[
            SpeedvibeSearchResult(
                content=r["content"],
                source_url=r["source_url"],
                page_title=r.get("page_title"),
                similarity=r["similarity"],
            )
            for r in results
        ],
    )


@router.delete("/reset")
async def reset_kb() -> dict[str, str]:
    try:
        rag = _get_rag()
        rag.reset_collection()
        return {"message": "Speedvibe knowledge base reset"}
    except Exception as e:
        return {"error": str(e)}
