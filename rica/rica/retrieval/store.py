"""Qdrant hybrid store: FastEmbed dense (bge-small) + BM25 sparse, in-process (§7.3 step 7)."""

import sys

from fastembed import TextEmbedding
from langchain_core.embeddings import Embeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient, models

from rica.settings import Settings

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
DENSE_DIM = 384
SPARSE_MODEL = "Qdrant/bm25"
PAYLOAD_INDEXES = ("kind", "source", "doc_id", "folder")


class FastEmbedDense(Embeddings):
    def __init__(self, cache_dir: str):
        self._model = TextEmbedding(DENSE_MODEL, cache_dir=cache_dir)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


def ensure_collection(client: QdrantClient, name: str) -> bool:
    """Creates the collection if missing. Returns True when it was created."""
    if client.collection_exists(name):
        return False
    client.create_collection(
        name,
        vectors_config={"dense": models.VectorParams(size=DENSE_DIM, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    for field in PAYLOAD_INDEXES:
        client.create_payload_index(name, f"metadata.{field}", models.PayloadSchemaType.KEYWORD)
    return True


def vector_store(settings: Settings, client: QdrantClient) -> QdrantVectorStore:
    cache = str(settings.fastembed_cache)
    return QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection,
        embedding=FastEmbedDense(cache),
        sparse_embedding=FastEmbedSparse(model_name=SPARSE_MODEL, cache_dir=cache),
        retrieval_mode=RetrievalMode.HYBRID,
        vector_name="dense",
        sparse_vector_name="sparse",
    )


if __name__ == "__main__":
    # Debug search: python -m rica.retrieval.store "query"
    settings = Settings()
    store = vector_store(settings, QdrantClient(url=settings.qdrant_url))
    for doc, score in store.similarity_search_with_score(" ".join(sys.argv[1:]), k=5):
        print(f"{score:.3f}  {doc.metadata['source']} › {doc.metadata['heading_path']}  #{doc.metadata['chunk_index']}")
        print("       " + doc.page_content[:160].replace("\n", " ") + "\n")
