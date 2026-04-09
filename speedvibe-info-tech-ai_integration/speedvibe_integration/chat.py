"""Text chat with RAG — mirrors LMS chatbot flow."""
from __future__ import annotations

import logging

import httpx

from speedvibe_integration.config import settings
from speedvibe_integration.constants import SPEEDVIBE_SYSTEM_INSTRUCTIONS
from speedvibe_integration.rag_chroma import SpeedvibeChromaRAG
from speedvibe_integration.schemas import SpeedvibeChatRequest, SpeedvibeChatResponse

logger = logging.getLogger(__name__)

_rag: SpeedvibeChromaRAG | None = None


def _get_rag() -> SpeedvibeChromaRAG:
    global _rag
    if _rag is None:
        _rag = SpeedvibeChromaRAG()
    return _rag


async def handle_speedvibe_chat(chat_input: SpeedvibeChatRequest) -> SpeedvibeChatResponse:
    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        logger.error(
            "OPENAI_API_KEY is missing or empty; set it in .env next to app.py (see .env.example)."
        )
        return SpeedvibeChatResponse(
            response="Chat is not configured: add OPENAI_API_KEY to the server .env file."
        )

    try:
        rag = _get_rag()
    except Exception as e:
        logger.warning("Speedvibe RAG unavailable: %s", e)
        rag = None

    try:
        relevant_docs: list[dict] = []
        if rag:
            relevant_docs = await rag.search_relevant_content(chat_input.message, top_k=3)

        context = ""
        if relevant_docs:
            parts = []
            for doc in relevant_docs:
                if doc.get("similarity", 0) > 0.2:
                    title = doc.get("page_title") or doc.get("source_url") or "Source"
                    preview = (doc.get("content") or "")[:800]
                    parts.append(f"[Source: {title}]\n{preview}")
            if parts:
                context = "\n\n### RELEVANT INFORMATION:\n" + "\n\n".join(parts)

        system_prompt = SPEEDVIBE_SYSTEM_INSTRUCTIONS + context

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.OPENAI_CHAT_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": chat_input.message},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 600,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
            return SpeedvibeChatResponse(response=reply)

    except Exception as e:
        logger.error("Speedvibe chat error: %s", e)
        return SpeedvibeChatResponse(
            response="I'm having trouble connecting. Please try again in a moment."
        )
