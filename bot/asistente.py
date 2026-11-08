"""Llamada a la API de Claude (Anthropic). Cada empresa usa su propia llave.

Si se le pasan herramientas (la agenda, v3.1), Claude puede pedir usarlas: el bot las
ejecuta y le devuelve el resultado, hasta que Claude escribe la respuesta final.
"""
import json
from dataclasses import dataclass

from anthropic import Anthropic

from .reglas import opciones_de_modelo

MAX_VUELTAS = 6  # llamadas a herramientas por mensaje, como mucho


@dataclass(frozen=True)
class Respuesta:
    texto: str
    entrada: int = 0  # tokens que leyo Claude (manual + conversacion)
    salida: int = 0   # tokens que escribio


def _bloque(b) -> dict:
    """Un bloque de la respuesta de Claude, como dict para volver a mandarlo."""
    if getattr(b, "type", "") == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    return {"type": "text", "text": getattr(b, "text", "")}


class Asistente:
    def __init__(self, api_key: str, modelo: str, instrucciones: str, max_tokens: int = 600, cliente=None):
        self._cliente = cliente or Anthropic(api_key=api_key, timeout=30.0, max_retries=2)
        self._modelo = modelo
        self._instrucciones = instrucciones
        self._max_tokens = max_tokens

    def responder(self, historial: list[dict], extra_sistema: str = "", herramientas=None, ejecutar=None) -> Respuesta:
        mensajes = [dict(m) for m in historial]
        entrada = salida = 0
        pedido = {"model": self._modelo, "max_tokens": self._max_tokens,
                  "system": self._instrucciones + (extra_sistema or ""), **opciones_de_modelo(self._modelo)}
        if herramientas and ejecutar:
            pedido["tools"] = herramientas
        for _ in range(MAX_VUELTAS):
            r = self._cliente.messages.create(messages=mensajes, **pedido)
            uso = getattr(r, "usage", None)
            entrada += int(getattr(uso, "input_tokens", 0) or 0)
            salida += int(getattr(uso, "output_tokens", 0) or 0)
            usos = [b for b in r.content if getattr(b, "type", "") == "tool_use"]
            if not usos or not ejecutar:
                texto = "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
                return Respuesta(texto, entrada, salida)
            mensajes.append({"role": "assistant", "content": [_bloque(b) for b in r.content]})
            resultados = []
            for b in usos:
                try:
                    resultado = ejecutar(b.name, b.input or {})
                except Exception as e:  # una herramienta que falla no tumba la conversación
                    resultado = {"ok": False, "motivo": f"error_interno: {e.__class__.__name__}"}
                resultados.append({"type": "tool_result", "tool_use_id": b.id,
                                   "content": json.dumps(resultado, ensure_ascii=False, default=str)})
            mensajes.append({"role": "user", "content": resultados})
        return Respuesta("", entrada, salida)
