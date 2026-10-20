"""Recuperador híbrido de la Pre-entrega 4 (BM25 + Pinecone), sin cambios de lógica.

Se reutiliza tal cual: el agente investigador lo usa como herramienta.
"""

import json
import re

from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore

from app.config import CHUNKS_PATH, EMBEDDING_MODEL, INDEX_NAME, NAMESPACE, TOP_K


def tokenizar(texto: str) -> list[str]:
    """Pasa a minúsculas y separa por palabras, ignorando signos de puntuación."""
    return re.findall(r"\w+", texto.lower())


def cargar_chunks() -> list[Document]:
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return [Document(page_content=d["page_content"], metadata=d["metadata"]) for d in data]


class RAGSystem:
    """Recuperador híbrido: BM25 (léxico) + Pinecone (semántico)."""

    def __init__(self, k: int = TOP_K, pesos: tuple = (0.5, 0.5)):
        self.k = k

        self.bm25 = BM25Retriever.from_documents(cargar_chunks(), preprocess_func=tokenizar)
        self.bm25.k = k

        vectorstore = PineconeVectorStore(
            index_name=INDEX_NAME,
            embedding=HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL),
            namespace=NAMESPACE,
        )
        self.vectorial = vectorstore.as_retriever(search_kwargs={"k": k})

        self.hibrido = EnsembleRetriever(
            retrievers=[self.bm25, self.vectorial],
            weights=list(pesos),
        )

    def buscar(self, query: str, modo: str = "hibrido") -> list[Document]:
        """Devuelve los top-k documentos. modo: 'hibrido', 'bm25' o 'vectorial'."""
        retriever = {
            "hibrido": self.hibrido,
            "bm25": self.bm25,
            "vectorial": self.vectorial,
        }[modo]
        return retriever.invoke(query)[: self.k]
