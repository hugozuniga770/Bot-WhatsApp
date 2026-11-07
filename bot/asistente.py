"""Llamada a la API de Claude (Anthropic)."""
from anthropic import Anthropic


class Asistente:
    def __init__(self, modelo: str, instrucciones: str, max_tokens: int = 600, cliente=None):
        # Anthropic() lee ANTHROPIC_API_KEY del entorno.
        self._cliente = cliente or Anthropic(timeout=30.0, max_retries=2)
        self._modelo = modelo
        self._instrucciones = instrucciones
        self._max_tokens = max_tokens

    def responder(self, historial: list[dict]) -> str:
        respuesta = self._cliente.messages.create(
            model=self._modelo,
            max_tokens=self._max_tokens,
            system=self._instrucciones,
            messages=historial,
        )
        return "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text").strip()
