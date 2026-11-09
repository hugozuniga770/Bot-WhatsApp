"""Seguridad del panel (BOT-RF-14): contraseña, sesion, CSRF y limite de intentos."""
import hmac
import secrets
import threading
import time
from functools import wraps

from flask import abort, redirect, request, session, url_for


def token_csrf() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def exigir_csrf() -> None:
    enviado = request.form.get("csrf") or request.headers.get("X-CSRF", "")
    if not enviado or not hmac.compare_digest(enviado, session.get("csrf", "")):
        abort(400, "El formulario venció. Vuelve a cargar la página e inténtalo de nuevo.")


def requiere_admin(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("panel.entrar", siguiente=request.path))
        if request.method == "POST":
            exigir_csrf()
        return vista(*args, **kwargs)
    return envoltura


def ip_cliente() -> str:
    """La IP de quien se conecta, para el bloqueo por intentos (BOT-RF-14 y 21).

    En Render, delante del servicio está Cloudflare, que escribe la IP real en
    CF-Connecting-IP (y en True-Client-IP) y reemplaza lo que mande el navegador.
    El primer valor de X-Forwarded-For NO sirve: Render conserva el que manda quien
    hace la petición, así que cambiándolo en cada intento se saltaba el bloqueo (C-20, D-39).
    Fuera de Render (en tu PC) se usa la dirección de la conexión.
    """
    for cabecera in ("CF-Connecting-IP", "True-Client-IP"):
        valor = (request.headers.get(cabecera) or "").strip()
        if valor:
            return valor[:64]
    return request.remote_addr or ""


class Limitador:
    """Despues de `maximo` contraseñas incorrectas desde una IP, la bloquea `minutos`."""

    def __init__(self, maximo: int = 5, minutos: int = 15, reloj=time.monotonic):
        self._maximo, self._segundos, self._reloj = maximo, minutos * 60, reloj
        self._fallos: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def bloqueado(self, ip: str) -> bool:
        with self._lock:
            ahora = self._reloj()
            recientes = [t for t in self._fallos.get(ip, []) if ahora - t < self._segundos]
            self._fallos[ip] = recientes
            return len(recientes) >= self._maximo

    def fallo(self, ip: str) -> None:
        with self._lock:
            self._fallos.setdefault(ip, []).append(self._reloj())

    def limpiar(self, ip: str) -> None:
        with self._lock:
            self._fallos.pop(ip, None)


def password_correcta(intento: str, real: str) -> bool:
    return hmac.compare_digest(intento.encode(), real.encode())
