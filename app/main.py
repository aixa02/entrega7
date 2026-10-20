"""API REST del orquestador multi-agente.

Levantar con:  uvicorn app.main:app
"""

import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from pydantic import BaseModel

from app.agents.research_agent import _rag
from app.config import REDIS_URL, WORKERS
from app.graph import construir_grafo
from app.hitl import router as hitl_router
from app.jobs import JobStatus, crear_job, encolar, leer_job, redis_client
from app.llm import crear_llm
from app.observability import configurar_observabilidad
from app.worker import task_worker


def crear_checkpointer():
    """Checkpointer de LangGraph en Redis (requiere Redis Stack o Redis 8+)."""
    return AsyncRedisSaver.from_conn_string(REDIS_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configurar_observabilidad()

    # Cargar el modelo de embeddings y BM25 es lento y sync: se hace una vez,
    # en un thread, antes de recibir pedidos.
    await asyncio.to_thread(_rag)

    async with crear_checkpointer() as checkpointer:
        await checkpointer.asetup()  # crea los índices de checkpoints en Redis
        grafo = construir_grafo(crear_llm(), checkpointer)

        # Varios workers en el mismo event loop: procesan jobs en paralelo.
        workers = [asyncio.create_task(task_worker(f"worker-{i}", grafo)) for i in range(1, WORKERS + 1)]
        yield
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    await redis_client.aclose()


app = FastAPI(title="API Orquestador Multi-Agente", lifespan=lifespan)
app.include_router(hitl_router)


class TaskRequest(BaseModel):
    query: str


@app.post("/tasks", status_code=202)
async def crear_tarea(request: TaskRequest):
    """Encola la tarea y devuelve el job_id al instante (no espera al agente)."""
    job_id = str(uuid.uuid4())
    await crear_job(job_id, request.query)  # primero el estado, después la cola
    await encolar({"job_id": job_id, "accion": "iniciar"})
    return {"job_id": job_id, "status": JobStatus.PENDING}


@app.get("/tasks/{job_id}")
async def estado_tarea(job_id: str):
    job = await leer_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_id no encontrado")
    return job


@app.get("/health")
async def health():
    await redis_client.ping()
    return {"status": "ok"}
