"""Human-in-the-loop: pausa antes de guardar el informe y endpoint de aprobación."""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import interrupt
from pydantic import BaseModel

from app.config import INFORMES_DIR
from app.llm import texto
from app.jobs import JobStatus, actualizar_job, encolar, leer_job
from app.state import AgentState

# ---------------------------------------------------------------------------
# Nodos del grafo
# ---------------------------------------------------------------------------


async def nodo_aprobacion_humana(state: AgentState) -> dict:
    """Pausa obligatoria antes de la acción crítica (guardar el informe).

    interrupt() detiene el grafo y guarda el estado en el checkpointer (Redis).
    Cuando se reanuda con Command(resume=...), el nodo se vuelve a ejecutar desde
    el principio e interrupt() devuelve la decisión humana. Por eso no hay nada
    con efectos secundarios ANTES de esta línea.
    """
    decision = interrupt(
        {
            "accion": "guardar_informe",
            "mensaje": "Revisá el borrador y aprobá o rechazá su guardado.",
            "borrador": state.get("respuesta_final", ""),
        }
    )
    return {"aprobacion": {"aprobado": bool(decision.get("aprobado")), "comentario": decision.get("comentario")}}


def enrutar_aprobacion(state: AgentState) -> Literal["guardar_informe", "__end__"]:
    aprobacion = state.get("aprobacion") or {}
    return "guardar_informe" if aprobacion.get("aprobado") else END


def _escribir_informe(nombre: str, contenido: str) -> str:
    INFORMES_DIR.mkdir(exist_ok=True)
    ruta = INFORMES_DIR / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return str(ruta)


async def nodo_guardar_informe(state: AgentState, config: RunnableConfig) -> dict:
    """Acción crítica con efecto secundario: escribe el informe en disco.

    Solo se llega acá si un humano aprobó. La escritura de archivos es una
    operación sync, así que va a un thread para no bloquear el event loop.
    """
    job_id = config["configurable"]["thread_id"]
    aprobacion = state.get("aprobacion") or {}
    contenido = (
        f"# Informe {job_id}\n\n"
        f"**Consulta:** {texto(state['messages'][0])}\n\n"
        f"{state.get('respuesta_final', '')}\n\n"
        f"---\nAprobado por revisión humana. Comentario: {aprobacion.get('comentario') or '(sin comentario)'}\n"
    )
    ruta = await asyncio.to_thread(_escribir_informe, f"{job_id}.md", contenido)
    return {"informe_path": ruta}


# ---------------------------------------------------------------------------
# Endpoint de aprobación
# ---------------------------------------------------------------------------

router = APIRouter()


class Aprobacion(BaseModel):
    aprobado: bool
    comentario: str | None = None


@router.post("/tasks/{job_id}/approve", status_code=202)
async def aprobar_tarea(job_id: str, body: Aprobacion):
    job = await leer_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_id no encontrado")
    if job["status"] != JobStatus.WAITING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"El job está en {job['status']}, no espera aprobación")

    # No se reanuda acá: se encola, igual que una tarea nueva, para no bloquear la API.
    await actualizar_job(job_id, status=JobStatus.PENDING, aprobado=body.aprobado)
    await encolar({"job_id": job_id, "accion": "reanudar", "aprobado": body.aprobado, "comentario": body.comentario})
    return {"job_id": job_id, "status": JobStatus.PENDING, "aprobado": body.aprobado}
