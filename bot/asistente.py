"""Llamada a la API de Claude (Anthropic). Cada empresa usa su propia llave."""
from dataclasses import dataclass

from anthropic import Anthropic


@dataclass(frozen=True)
class Respuesta:
    texto: str
    entrada: int = 0  # tokens que leyo Claude (manual + conversacion)
    salida: int = 0   # tokens que escribio


class Asistente:
    def __init__(self, api_key: str, modelo: str, instrucciones: str, max_tokens: int = 600, cliente=None):
        self._cliente = cliente or Anthropic(api_key=api_key, timeout=30.0, max_retries=2)
        self._modelo = modelo
        self._instrucciones = instrucciones
        self._max_tokens = max_tokens

    def responder(self, historial: list[dict]) -> Respuesta:
        r = self._cliente.messages.create(
            model=self._modelo,
            max_tokens=self._max_tokens,
            system=self._instrucciones,
            messages=historial,
        )
        texto = "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
        uso = getattr(r, "usage", None)
        return Respuesta(texto, int(getattr(uso, "input_tokens", 0) or 0), int(getattr(uso, "output_tokens", 0) or 0))
