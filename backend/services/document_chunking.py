import os
import re
from typing import Any

import fitz


class InvalidDocumentError(ValueError):
    """Raised when an uploaded document cannot be parsed or chunked."""


MAX_CHUNK_SIZE = 2000
OVERLAP_SIZE = 200


def _split_sentences_clean(text: str) -> list[str]:
    """Tách câu tương đối an toàn cho tiếng Việt / đa ngữ, giữ trọn câu."""
    parts = re.split(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ỹ0-9\"“'(\[])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_words_clean(text: str, max_size: int) -> list[str]:
    """Chỉ dùng khi một câu đơn lẻ dài hơn max_size; chia theo từ, không cắt giữa từ."""
    words = text.split()
    chunks: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # Nếu 1 từ/chuỗi đơn lẻ dài hơn max_size thì buộc giữ nguyên
            current = word

    if current:
        chunks.append(current)
    return chunks


def _get_clean_overlap(prev_text: str, overlap_size: int) -> str:
    """Lấy phần overlap ở cuối chunk trước nhưng bắt đầu từ đầu câu/từ để không cắt giữa dòng."""
    if overlap_size <= 0 or not prev_text:
        return ""

    sentences = _split_sentences_clean(prev_text)
    selected: list[str] = []
    total = 0

    for sent in reversed(sentences):
        if not sent:
            continue
        if total + len(sent) > overlap_size:
            if not selected:
                selected.append(sent)
            break
        selected.insert(0, sent)
        total += len(sent) + 1

    overlap = " ".join(selected).strip()
    if len(overlap) > overlap_size and " " in overlap:
        # Cắt bớt từ đầu theo khoảng trắng để không vượt quá overlap_size
        trimmed = overlap[-overlap_size:]
        first_space = trimmed.find(" ")
        overlap = trimmed[first_space + 1 :].strip() if first_space != -1 else trimmed

    return overlap


def _chunk_unstructured_block(
    text: str,
    max_chunk_size: int = MAX_CHUNK_SIZE,
    overlap_size: int = OVERLAP_SIZE,
) -> list[str]:
    """
    Chia khối văn bản không có Điều theo từng đoạn (\n\n).
    Không cắt giữa đoạn nếu đoạn <= max_chunk_size; không cắt giữa dòng/từ.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chunk_size:
        return [text]

    # Tách theo đoạn văn (ít nhất 1 dòng trống giữa các đoạn)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]

    units: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chunk_size:
            units.append(para)
        else:
            # Đoạn quá dài -> tách theo câu, giữ nguyên từng dòng/câu
            sentences = _split_sentences_clean(para)
            if len(sentences) <= 1:
                units.extend(_split_words_clean(para, max_chunk_size))
                continue

            sent_buf = ""
            for sent in sentences:
                candidate = f"{sent_buf} {sent}".strip() if sent_buf else sent
                if len(candidate) <= max_chunk_size:
                    sent_buf = candidate
                else:
                    if sent_buf:
                        units.append(sent_buf)
                    if len(sent) > max_chunk_size:
                        units.extend(_split_words_clean(sent, max_chunk_size))
                        sent_buf = ""
                    else:
                        sent_buf = sent
            if sent_buf:
                units.append(sent_buf)

    # Gom các đoạn/unit thành các chunk hoàn chỉnh <= max_chunk_size
    chunks: list[str] = []
    current = ""

    for unit in units:
        if not current:
            current = unit
            continue

        joined = f"{current}\n\n{unit}"
        if len(joined) <= max_chunk_size:
            current = joined
        else:
            chunks.append(current)
            overlap = _get_clean_overlap(current, overlap_size)
            if overlap and len(f"{overlap}\n\n{unit}") <= max_chunk_size:
                current = f"{overlap}\n\n{unit}"
            else:
                current = unit

    if current:
        chunks.append(current)

    return chunks


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
        chapters = [{"title": "NỘI DUNG TỔNG QUÁT", "start_pos": 0}]

    articles = list(article_pattern.finditer(full_text))

    # Nhánh 1: Tài liệu có cấu trúc "Điều ..."
    if articles:
        chunks: list[dict[str, Any]] = []
        for index, article in enumerate(articles):
            end_pos = (
                articles[index + 1].start()
                if index + 1 < len(articles)
                else len(full_text)
            )
            article_title = article.group(1).strip()
            article_content = full_text[article.end() : end_pos].strip()

            active_chapter = chapters[0]["title"]
            for chapter in chapters:
                if article.start() >= chapter["start_pos"]:
                    active_chapter = chapter["title"]
                else:
                    break

            parts = _chunk_unstructured_block(article_content)
            if not parts and article_content:
                parts = [article_content]

            total_parts = len(parts)
            for part_idx, part in enumerate(parts, start=1):
                title_label = (
                    article_title
                    if total_parts == 1
                    else f"{article_title} (Phần {part_idx}/{total_parts})"
                )
                chunks.append(
                    {
                        "chunk_id": len(chunks) + 1,
                        "chapter": active_chapter,
                        "article_title": title_label,
                        "raw_content": part,
                        "enriched_text": (
                            f"[Tài liệu: {document_name}]\n"
                            f"[{active_chapter}]\n"
                            f"[{title_label}]\n\n"
                            f"{part}"
                        ),
                    }
                )
        return chunks

    # Nhánh 2: Tài liệu không có "Điều ..." -> chia theo đoạn hoàn chỉnh
    raw_chunks = _chunk_unstructured_block(full_text)
    chunks = []
    for idx, content in enumerate(raw_chunks, start=1):
        chapter_title = chapters[0]["title"]
        for chapter in chapters:
            pos = full_text.find(content[:60])
            if pos != -1 and pos >= chapter["start_pos"]:
                chapter_title = chapter["title"]

        section_title = f"Đoạn {idx}"
        chunks.append(
            {
                "chunk_id": idx,
                "chapter": chapter_title,
                "article_title": section_title,
                "raw_content": content,
                "enriched_text": (
                    f"[Tài liệu: {document_name}]\n"
                    f"[{chapter_title}]\n"
                    f"[{section_title}]\n\n"
                    f"{content}"
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
