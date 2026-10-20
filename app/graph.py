"""Orquestador multi-agente de la Pre-entrega 6 + nodo HITL + checkpointer de Redis."""

from typing import Literal

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents import crear_nodo_analista, crear_nodo_investigador, crear_nodo_sintesis, crear_nodo_supervisor
from app.hitl import enrutar_aprobacion, nodo_aprobacion_humana, nodo_guardar_informe
from app.state import AgentState


def enrutar(state: AgentState) -> Literal["investigador", "analista", "sintesis"]:
    if state["next_agent"] == "FINISH":
        return "sintesis"
    return state["next_agent"]


def construir_grafo(llm: BaseChatModel, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    grafo = StateGraph(AgentState)

    # Orquestador de la Pre-entrega 6 (sin cambios)
    grafo.add_node("supervisor", crear_nodo_supervisor(llm))
    grafo.add_node("investigador", crear_nodo_investigador(llm))
    grafo.add_node("analista", crear_nodo_analista(llm))
    grafo.add_node("sintesis", crear_nodo_sintesis(llm))

    # Nuevo: aprobación humana antes de la acción crítica
    grafo.add_node("aprobacion_humana", nodo_aprobacion_humana)
    grafo.add_node("guardar_informe", nodo_guardar_informe)

    grafo.add_edge(START, "supervisor")
    grafo.add_conditional_edges("supervisor", enrutar)
    grafo.add_edge("investigador", "supervisor")
    grafo.add_edge("analista", "supervisor")
    grafo.add_edge("sintesis", "aprobacion_humana")
    grafo.add_conditional_edges("aprobacion_humana", enrutar_aprobacion)
    grafo.add_edge("guardar_informe", END)

    # El checkpointer es lo que permite pausar y reanudar: guarda el estado en Redis
    # después de cada nodo, identificado por thread_id (= job_id).
    return grafo.compile(checkpointer=checkpointer)
