"""Estado de los jobs y cola de trabajo, ambos en Redis."""

import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from redis import asyncio as aioredis

from app.config import JOB_PREFIX, QUEUE_NAME, REDIS_URL

redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)


class JobStatus(StrEnum):
    PENDING = "PENDING"                     # en la cola, esperando un worker
    RUNNING = "RUNNING"                     # un worker lo está ejecutando
    WAITING_APPROVAL = "WAITING_APPROVAL"   # pausado por el HITL
    DONE = "DONE"                           # terminó (aprobado o rechazado)
    FAILED = "FAILED"                       # hubo una excepción


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def crear_job(job_id: str, query: str) -> dict[str, Any]:
    job = {
        "job_id": job_id,
        "status": JobStatus.PENDING,
        "query": query,
        "created_at": _ahora(),
        "updated_at": _ahora(),
    }
    await redis_client.set(f"{JOB_PREFIX}{job_id}", json.dumps(job))
    return job


async def leer_job(job_id: str) -> dict[str, Any] | None:
    data = await redis_client.get(f"{JOB_PREFIX}{job_id}")
    return json.loads(data) if data else None


async def actualizar_job(job_id: str, **campos: Any) -> dict[str, Any]:
    job = await leer_job(job_id) or {"job_id": job_id}
    job.update(campos, updated_at=_ahora())
    await redis_client.set(f"{JOB_PREFIX}{job_id}", json.dumps(job, default=str))
    return job


async def encolar(mensaje: dict[str, Any]) -> None:
    """RPUSH agrega al final de la cola; el worker saca del principio (FIFO)."""
    await redis_client.rpush(QUEUE_NAME, json.dumps(mensaje))


async def desencolar(timeout: int = 5) -> dict[str, Any] | None:
    """BLPOP espera hasta `timeout` segundos a que haya un mensaje, sin bloquear el event loop."""
    item = await redis_client.blpop(QUEUE_NAME, timeout=timeout)
    return json.loads(item[1]) if item else None
