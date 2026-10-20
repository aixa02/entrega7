"""Creación del LLM y utilidades para leer sus respuestas."""

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import LLM_MODEL


def crear_llm() -> ChatGoogleGenerativeAI:
    # temperature=0: queremos decisiones de ruteo estables, no creatividad.
    return ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)


def texto(mensaje: BaseMessage) -> str:
    """Devuelve solo el texto de un mensaje.

    Gemini a veces devuelve el contenido como lista de bloques
    ([{'type': 'text', 'text': '...', 'extras': {...}}]), como se ve en el
    notebook de ejemplo. Nos quedamos solo con los bloques de texto.
    """
    contenido = mensaje.content
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in contenido
        )
    return str(contenido)
