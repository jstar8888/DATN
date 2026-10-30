import os
from google import genai
from google.genai import types


class GeminiEmbeddingService:
    """Generate Gemini embeddings for documents and user queries."""

    def __init__(self, client=None, api_key=None):
        # Ưu tiên nhận client, nếu không có thì khởi tạo từ api_key hoặc biến môi trường GEMINI_API_KEY
        if client:
            self.client = client
        else:
            key = api_key or os.environ.get("GEMINI_API_KEY")
            self.client = genai.Client(api_key=key)

    def generate(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT"):
        response = self.client.models.embed_content(
            model="gemini-embedding-001",  # Hoặc "gemini-embedding-001" tùy theo model bạn muốn dùng
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=768,
            ),
        )
        return response.embeddings[0].values