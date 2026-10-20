"""Supervisor: router inteligente y controlador de flujo, con rúbrica de validación."""

from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.config import MAX_PASOS
from app.llm import texto
from app.state import AgentState


class DecisionSupervisor(BaseModel):
    # 'evaluacion' va primero a propósito: el modelo aplica la rúbrica ANTES de decidir.
    evaluacion: str = Field(description="Aplicación breve de la rúbrica a las contribuciones actuales")
    next: Literal["investigador", "analista", "FINISH"] = Field(
        description="Próximo agente a invocar, o FINISH si la tarea ya está completa"
    )
    instruccion: str = Field(
        description="Tarea concreta para el especialista elegido. Si es una corrección, "
        "indicar qué falta o qué está mal. Vacío si es FINISH."
    )


SUPERVISOR_PROMPT = """Sos el Supervisor de un equipo con dos especialistas:
- investigador: busca información en la documentación de FastAPI. No valida datos.
- analista: valida objetos JSON contra un esquema. No busca información.

Dada la conversación actual, decidí quién debe intervenir ahora o si es momento de finalizar.

RÚBRICA (aplicala a las contribuciones antes de decidir):
1. Datos: ¿el investigador encontró en la documentación TODO lo que la tarea necesita,
   citando la fuente? Si falta algo o no cita fuente → 'investigador' con una instrucción
   que diga qué falta.
2. Análisis: si la tarea pide validar datos, ¿el analista validó TODOS los JSON pedidos,
   usando el esquema del investigador? Si falta alguno → 'analista' indicando cuál.
3. Consistencia: ¿el análisis usa el mismo esquema que encontró el investigador? Si se
   contradicen, mandá a corregir al agente cuyo aporte no coincide con la documentación.
4. Suficiencia: si los puntos 1 a 3 se cumplen → 'FINISH'. No pidas mejoras de estilo:
   solo se refina si falta información o hay un error.

Reglas:
- La instrucción debe ser concreta y autocontenida: el especialista NO ve la conversación,
  solo tu instrucción. Incluí los datos que necesite (por ejemplo, los JSON a validar).
- Al investigador pedile las búsquedas en inglés (la documentación está en inglés).
- No repitas el mismo agente si ya cumplió su parte.

Intervenciones usadas: {pasos} de {max_pasos}.

Contribuciones hasta ahora:
{contribuciones}
"""


def formatear_contribuciones(state: AgentState) -> str:
    return "\n\n".join(
        f"- [paso {c['paso']}] {c['agente']} (tarea: {c['instruccion']}):\n{c['aporte']}"
        for c in state.get("contribuciones", [])
    ) or "(ninguna todavía)"


def crear_nodo_supervisor(llm: BaseChatModel):
    llm_supervisor = llm.with_structured_output(DecisionSupervisor)

    async def nodo_supervisor(state: AgentState) -> dict:
        pasos = state.get("pasos", 0)

        # Condición de parada dura: aunque el LLM quiera seguir delegando, se corta.
        if pasos >= MAX_PASOS:
            aviso = f"Se alcanzó el máximo de {MAX_PASOS} intervenciones. Paso a la síntesis."
            return {
                "next_agent": "FINISH",
                "instruccion": "",
                "messages": [AIMessage(content=aviso, name="supervisor")],
            }

        prompt_sistema = SUPERVISOR_PROMPT.format(
            pasos=pasos, max_pasos=MAX_PASOS, contribuciones=formatear_contribuciones(state)
        )
        pregunta_original = texto(state["messages"][0])

        decision: DecisionSupervisor = await llm_supervisor.ainvoke(
            [SystemMessage(content=prompt_sistema), HumanMessage(content=f"Tarea original: {pregunta_original}")]
        )

        destino = "síntesis final" if decision.next == "FINISH" else decision.next
        resumen = f"Evaluación: {decision.evaluacion}\n→ Delego a: {destino}"
        if decision.next != "FINISH":
            resumen += f"\n→ Instrucción: {decision.instruccion}"

        return {
            "next_agent": decision.next,
            "instruccion": decision.instruccion,
            # Se registra la decisión en 'messages' para poder seguir el flujo de delegación.
            "messages": [AIMessage(content=resumen, name="supervisor")],
        }

    return nodo_supervisor
