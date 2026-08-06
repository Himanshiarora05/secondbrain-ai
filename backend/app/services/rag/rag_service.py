from sentence_transformers import SentenceTransformer


class RAGService:

    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 1000):

        if not text:
            return []

        chunks = []

        for i in range(0, len(text), chunk_size):
            chunks.append(text[i:i + chunk_size])

        return chunks

    def create_embeddings(self, chunks):

        if not chunks:
            return []

        embeddings = self.model.encode(
            chunks,
            convert_to_numpy=True
        )

        return embeddings