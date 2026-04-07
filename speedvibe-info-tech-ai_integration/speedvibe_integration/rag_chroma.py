"""ChromaDB RAG for Speedvibe Info Tech (standalone, no Pinecone)."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

import chromadb
import httpx
from chromadb.config import Settings as ChromaSettings

from speedvibe_integration.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "speedvibe_knowledge_base"


def _doc_id(url: str) -> str:
    if len(url) <= 500:
        return url
    return "sv_" + hashlib.sha256(url.encode()).hexdigest()


class SpeedvibeChromaRAG:
    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for RAG")

        self.client = chromadb.PersistentClient(
            path=str(settings.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Speedvibe Info Tech website RAG"},
        )
        logger.info("Speedvibe Chroma RAG initialized at %s", settings.chroma_path)

    async def create_embedding(self, text: str) -> tuple[list[float], int]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": text[:8000],
                    "model": settings.OPENAI_EMBEDDING_MODEL,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
            tokens = data.get("usage", {}).get("total_tokens", 0)
            return embedding, tokens

    async def store_page_content(
        self,
        url: str,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        doc_id = _doc_id(url)
        embedding, _ = await self.create_embedding(content)

        page_metadata = {
            "source_url": url,
            "page_title": title or "Untitled",
            "created_at": datetime.utcnow().isoformat(),
            **(metadata or {}),
        }

        try:
            existing = self.collection.get(ids=[doc_id])
            exists = len(existing["ids"]) > 0
        except Exception:
            exists = False

        if exists:
            self.collection.update(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[page_metadata],
            )
            logger.info("Updated Chroma doc: %s", url)
        else:
            self.collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[page_metadata],
            )
            logger.info("Stored Chroma doc: %s", url)

    async def search_relevant_content(self, query: str, top_k: int = 3) -> list[dict]:
        try:
            query_embedding, _ = await self.create_embedding(query)
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

            docs: list[dict] = []
            if results["ids"] and len(results["ids"][0]) > 0:
                for i in range(len(results["ids"][0])):
                    distance = results["distances"][0][i]
                    similarity = 1 / (1 + distance)
                    docs.append(
                        {
                            "content": results["documents"][0][i],
                            "source_url": results["metadatas"][0][i].get("source_url", ""),
                            "page_title": results["metadatas"][0][i].get("page_title", "Untitled"),
                            "similarity": similarity,
                        }
                    )
            return docs
        except Exception as e:
            logger.error("Chroma search error: %s", e)
            return []

    def get_stats(self) -> dict:
        try:
            count = self.collection.count()
            return {
                "total_documents": count,
                "collection_name": COLLECTION_NAME,
                "database_type": "ChromaDB",
            }
        except Exception as e:
            return {
                "total_documents": 0,
                "collection_name": COLLECTION_NAME,
                "database_type": "ChromaDB",
                "error": str(e),
            }

    def reset_collection(self) -> None:
        self.client.delete_collection(name=COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Speedvibe Info Tech website RAG"},
        )
        logger.info("Speedvibe Chroma collection reset")
