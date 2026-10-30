import os
import re
from typing import Any

import fitz


class InvalidDocumentError(ValueError):
    """Raised when an uploaded document cannot be parsed or chunked."""


def _chunk_document_text(
    full_text: str, document_name: str
) -> list[dict[str, Any]]:
    full_text = full_text.strip()
    if not full_text:
        raise InvalidDocumentError("Tài liệu không chứa văn bản có thể xử lý.")

    chapter_pattern = re.compile(
        r"(CHƯƠNG\s+(?:[IVXLCDM]+|\d+)\b[:\s\-]*[^\n]*)",
        re.IGNORECASE,
    )
    article_pattern = re.compile(
        r"(Điều\s+\d+\s*[.:]?\s*[^\n]*)",
        re.IGNORECASE,
    )
    chapters = [
        {"title": match.group(1).strip(), "start_pos": match.start()}
        for match in chapter_pattern.finditer(full_text)
    ]
    if not chapters:
        chapters = [{"title": "QUY ĐỊNH CHUNG", "start_pos": 0}]

    articles = list(article_pattern.finditer(full_text))
    if not articles:
        chunk_size = 2000
        overlap = 200
        chunks = []
        start = 0
        while start < len(full_text):
            end = min(start + chunk_size, len(full_text))
            content = full_text[start:end].strip()
            if content:
                chunks.append(
                    {
                        "chunk_id": len(chunks) + 1,
                        "chapter": chapters[0]["title"],
                        "article_title": f"Phần {len(chunks) + 1}",
                        "raw_content": content,
                        "enriched_text": (
                            f"[Tài liệu: {document_name}]\n"
                            f"[{chapters[0]['title']}]\n\n{content}"
                        ),
                    }
                )
            if end == len(full_text):
                break
            start = end - overlap
        return chunks

    chunks = []
    for index, article in enumerate(articles):
        end_pos = (
            articles[index + 1].start()
            if index + 1 < len(articles)
            else len(full_text)
        )
        article_title = article.group(1).strip()
        article_content = full_text[article.end():end_pos].strip()
        active_chapter = chapters[0]["title"]
        for chapter in chapters:
            if article.start() >= chapter["start_pos"]:
                active_chapter = chapter["title"]
            else:
                break

        chunks.append(
            {
                "chunk_id": len(chunks) + 1,
                "chapter": active_chapter,
                "article_title": article_title,
                "raw_content": article_content,
                "enriched_text": (
                    f"[Tài liệu: {document_name}]\n"
                    f"[{active_chapter}]\n"
                    f"[{article_title}]\n\n"
                    f"{article_content}"
                ),
            }
        )
    return chunks


def extract_and_chunk_document(
    file_content: bytes, document_name: str
) -> list[dict[str, Any]]:
    extension = os.path.splitext(document_name)[1].lower()
    if extension == ".pdf":
        try:
            with fitz.open(stream=file_content, filetype="pdf") as document:
                full_text = "\n".join(
                    page.get_text("text") for page in document
                )
        except fitz.FileDataError as exc:
            raise InvalidDocumentError("Tệp PDF không hợp lệ.") from exc
    elif extension == ".txt":
        try:
            full_text = file_content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidDocumentError(
                "Tệp TXT phải được mã hóa UTF-8."
            ) from exc
    else:
        raise InvalidDocumentError("Chỉ chấp nhận định dạng file PDF hoặc TXT.")

    return _chunk_document_text(full_text, document_name)


def extract_and_chunk_pdf_dynamic_pymupdf(
    pdf_path: str,
) -> list[dict[str, Any]]:
    with open(pdf_path, "rb") as pdf_file:
        return extract_and_chunk_document(
            pdf_file.read(), os.path.basename(pdf_path)
        )


def embed_chunks_with_gemini(
    chunks: list[dict[str, Any]], embedding_service=None
) -> list[dict[str, Any]]:
    if embedding_service is None:
        from script.embedding_service import GeminiEmbeddingService

        embedding_service = GeminiEmbeddingService()

    for chunk in chunks:
        chunk["embedding"] = embedding_service.generate(
            chunk["enriched_text"], task_type="RETRIEVAL_DOCUMENT"
        )
    return chunks


def push_chunks_to_supabase(
    chunks: list[dict[str, Any]],
    document_name: str,
    position: str | None,
    system_level: str,
    supabase_client=None,
) -> int:
    supabase_service = None
    if supabase_client is None:
        from database.supabase_general_service import SupabaseService

        supabase_service = SupabaseService()

    records = []
    for chunk in chunks:
        embedding = chunk.get("embedding")
        if not embedding:
            raise InvalidDocumentError(
                f"Chunk {chunk['chunk_id']} chưa có vector embedding."
            )
        records.append(
            {
                "document_name": document_name,
                "position": position,
                "system_level": system_level,
                "chapter": chunk["chapter"],
                "article_title": chunk["article_title"],
                "raw_content": chunk["raw_content"],
                "enriched_text": chunk["enriched_text"],
                "embedding": embedding,
            }
        )

    if not records:
        raise InvalidDocumentError(
            "Không có nội dung hợp lệ để lưu vào Supabase."
        )

    if supabase_service is not None:
        saved_records = supabase_service.upsert("document_chunks", records)
    else:
        response = (
            supabase_client.table("document_chunks").upsert(records).execute()
        )
        saved_records = response.data
    return len(saved_records or [])


def process_uploaded_document(
    file_content: bytes,
    document_name: str,
    position: str | None,
    system_level: str,
    embedding_service=None,
    supabase_client=None,
) -> dict[str, int]:
    chunks = extract_and_chunk_document(file_content, document_name)
    vectorized_chunks = embed_chunks_with_gemini(chunks, embedding_service)
    saved_count = push_chunks_to_supabase(
        vectorized_chunks,
        document_name,
        position,
        system_level,
        supabase_client,
    )
    return {"chunks_total": len(chunks), "chunks_saved": saved_count}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--position", required=True)
    parser.add_argument("--system-level", required=True)
    args = parser.parse_args()

    pdf_file_path = "document.pdf"
    if not os.path.exists(pdf_file_path):
        raise FileNotFoundError(f"Không tìm thấy file '{pdf_file_path}'.")

    with open(pdf_file_path, "rb") as pdf_file:
        result = process_uploaded_document(
            pdf_file.read(),
            os.path.basename(pdf_file_path),
            args.position,
            args.system_level,
        )
    print(
        "Hoàn tất vector hóa: "
        f"{result['chunks_saved']}/{result['chunks_total']} chunks."
    )
