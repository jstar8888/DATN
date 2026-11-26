from typing import Any

from database.supabase_general_service import SupabaseService
from agents.configurable_llm import get_retrieval_settings
from script.embedding_service import GeminiEmbeddingService
from utils.event_bus import global_event_bus


class RAGSearchAgent:
    """Retrieve relevant document chunks using Supabase vector search."""

    def __init__(
        self,
        embedding_service: GeminiEmbeddingService | None = None,
        supabase_service: SupabaseService | None = None,
        match_threshold: float | None = None,
        match_count: int | None = None,
    ):
        self.embedding_service = embedding_service
        self.supabase_service = supabase_service
        self.match_threshold = match_threshold
        self.match_count = match_count

    def search(
        self,
        query: str,
        match_threshold: float | None = None,
        match_count: int | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Embed a query and retrieve matching chunks from Supabase."""
        if run_id:
            global_event_bus.publish_event(
                run_id,
                "rag_search",
                "started",
                {"message": "Đang tìm kiếm các đoạn tài liệu."},
                agent="rag_search",
            )

        try:
            retrieval_settings = get_retrieval_settings()
            effective_match_threshold = (
                match_threshold
                if match_threshold is not None
                else (
                    self.match_threshold
                    if self.match_threshold is not None
                    else retrieval_settings["rag_match_threshold"]
                )
            )
            effective_match_count = (
                match_count
                if match_count is not None
                else (
                    self.match_count
                    if self.match_count is not None
                    else retrieval_settings["rag_match_count"]
                )
            )

            embedding_service = self.embedding_service
            if embedding_service is None:
                embedding_service = GeminiEmbeddingService()
                self.embedding_service = embedding_service

            supabase_service = self.supabase_service
            if supabase_service is None:
                supabase_service = SupabaseService()
                self.supabase_service = supabase_service

            query_embedding = embedding_service.generate(
                query, task_type="RETRIEVAL_QUERY"
            )
            chunks = supabase_service.rpc(
                "match_document_chunks",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": effective_match_threshold,
                    "match_count": effective_match_count,
                },
            )
            if chunks is None:
                chunks = []
            if not isinstance(chunks, list) or any(
                not isinstance(chunk, dict) for chunk in chunks
            ):
                raise TypeError(
                    "Supabase RPC match_document_chunks must return a list of rows."
                )
        except Exception:
            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "rag_search",
                    "failed",
                    {"message": "Không thể nhận các đoạn tài liệu từ Supabase."},
                    agent="rag_search",
                )
            raise

        if run_id:
            global_event_bus.publish_event(
                run_id,
                "rag_search",
                "completed",
                {
                    "has_chunks": bool(chunks),
                    "chunk_count": len(chunks),
                    "chunks": [
                        {
                            key: chunk.get(key)
                            for key in (
                                "document_name",
                                "chapter",
                                "article_title",
                            )
                        } | {
                            "similarity": chunk.get(
                                "similarity", chunk.get("similarity_score")
                            )
                        }
                        for chunk in chunks
                    ],
                },
                agent="rag_search",
            )
        return chunks
