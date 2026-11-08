"""Arma el manual (instrucciones del sistema) de cada empresa.

La plantilla comun es instrucciones.md, en la raiz del repositorio: lo que
cambies ahi vale para todas las empresas. Lo propio de cada empresa (que vende,
precios, horario...) se llena desde el panel o desde el enlace de alta.
"""
from string import Template

# (campo, titulo en el manual, ayuda en el formulario)
CAMPOS_NEGOCIO = (
    ("rubro", "Qué vendemos o qué servicio damos", "Ejemplo: venta de ropa para niños y uniformes escolares."),
    ("productos", "Productos o servicios y precios", "Uno por línea, con su precio. Ejemplo: Axilas, sesión: Bs 80."),
    ("horario", "Horario de atención", "Ejemplo: lunes a viernes de 9:00 a 19:00, sábados de 9:00 a 13:00."),
    ("ubicacion", "Ubicación", "Dirección y una referencia. Puedes pegar el enlace de Google Maps."),
    ("pagos", "Formas de pago", "Ejemplo: efectivo, QR y transferencia."),
    ("envios", "Envíos, delivery o reservas", "Cómo se entrega o cómo se reserva. Si no aplica, déjalo vacío."),
    ("preguntas", "Preguntas frecuentes y sus respuestas", "Las que más te hacen, cada una con su respuesta."),
    ("nunca", "Lo que nunca debes decir o prometer", "Ejemplo: no dar diagnósticos, no prometer resultados, no hacer descuentos."),
)


def componer(plantilla: str, empresa: dict) -> str:
    negocio = empresa.get("nombre") or "el negocio"
    dueno = empresa.get("dueno_nombre") or "la persona a cargo"
    bloques = []
    for campo, titulo, _ in CAMPOS_NEGOCIO:
        valor = (empresa.get("info") or {}).get(campo, "").strip()
        bloques.append(f"## {titulo}\n{valor if valor else 'Sin información. Si preguntan, di que ' + dueno + ' le confirmará.'}")
    extra = (empresa.get("instrucciones_extra") or "").strip()
    return Template(plantilla).safe_substitute(
        negocio=negocio,
        dueno=dueno,
        trato="usted" if empresa.get("trato", "usted") == "usted" else "tú",
        info="\n\n".join(bloques),
        extra=f"\n# Indicaciones adicionales\n{extra}\n" if extra else "",
    )
