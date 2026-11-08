"""Filtros para las plantillas: dinero, tokens, fechas y tiempos relativos."""
from datetime import date, datetime

from . import reglas
from .seguridad import token_csrf

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def dinero(valor) -> str:
    if valor is None:
        return "—"
    valor = float(valor)
    if 0 < valor < 0.01:
        return f"USD {valor:.4f}"
    return f"USD {valor:,.2f}"


def tokens(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} M".replace(".", ",")
    if n >= 1_000:
        return f"{n / 1_000:.1f} mil".replace(".", ",")
    return str(n)


def fecha(d) -> str:
    if d is None:
        return "—"
    if isinstance(d, datetime):
        d = d.date()
    return f"{d.day} {MESES[d.month - 1]}"


def duracion(dias) -> tuple:
    """(cifra, unidad) para mostrar en grande: 298 -> (298, 'días'); 2922 -> (8, 'años')."""
    dias = int(dias or 0)
    if dias >= 365:
        anios = dias // 365
        return anios, "año" if anios == 1 else "años"
    return dias, "día" if dias == 1 else "días"


def telefono(numero: str) -> str:
    numero = numero or ""
    if numero.startswith("591") and len(numero) == 11:
        return f"+591 {numero[3:]}"
    return f"+{numero}" if numero else "—"


def registrar_filtros(app):
    from .app import ctx

    app.jinja_env.filters.update(dinero=dinero, tokens=tokens, fecha=fecha, telefono=telefono, duracion=duracion)

    @app.context_processor
    def comunes():
        ahora = ctx().ahora()
        return {"ahora": ahora, "csrf": token_csrf, "hace": lambda dt: reglas.hace(dt, ahora)}
