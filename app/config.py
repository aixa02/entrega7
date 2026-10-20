"""Configuración compartida (se lee del .env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

# load_dotenv va primero: LangSmith lee sus variables (LANGSMITH_*) del entorno.
load_dotenv()

RAIZ = Path(__file__).resolve().parent.parent

# --- LLM ---
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash")

# --- RAG de la Pre-entrega 4 (mismo índice de Pinecone) ---
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
INDEX_NAME = os.getenv("INDEX_NAME", "fastapi-docs-rag")
NAMESPACE = "fastapi-docs"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNKS_PATH = str(RAIZ / "chunks.json")
TOP_K = 5

# --- Orquestador (Pre-entrega 6) ---
MAX_PASOS = 6
RECURSION_LIMIT = 25

# --- API, Redis y worker ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
QUEUE_NAME = "tasks_queue"
JOB_PREFIX = "job:"
WORKERS = int(os.getenv("WORKERS", "5"))  # cuántos jobs se procesan en paralelo

# --- HITL ---
INFORMES_DIR = RAIZ / "informes"
