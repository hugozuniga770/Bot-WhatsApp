"""Alta y edicion de empresas: formularios, llaves cifradas y enlaces de alta."""
import hashlib
import secrets
from datetime import date, datetime, timedelta

from . import reglas
from .manual import CAMPOS_NEGOCIO

SECRETOS = ("anthropic_key", "meta_app_secret", "whatsapp_token")
DIAS_ENLACE = 7

# Campos que puede llenar quien recibe el enlace de alta (y el admin).
CAMPOS_PUBLICOS = ("nombre", "dueno_nombre", "dueno_numero", "trato", "saldo_usd",
                   "meta_app_id", "phone_number_id")
# Campos que solo ve y cambia el admin.
CAMPOS_ADMIN = ("modelo", "precio_entrada", "precio_salida", "numeros_ignorados",
                "pausa_horas", "historial_limite", "instrucciones_extra")


def nuevo_token_verificacion() -> str:
    """La palabra secreta que Meta usa una vez para verificar el webhook."""
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_empresa(almacen, nombre: str, ahora: datetime) -> dict:
    """Crea la empresa en borrador, con su webhook propio (slug + palabra secreta)."""
    base = reglas.crear_slug(nombre)
    slug, n = base, 2
    while almacen.empresa_por_slug(slug):
        slug, n = f"{base}-{n}", n + 1
    precio_e, precio_s = reglas.PRECIOS[reglas.MODELO_POR_DEFECTO]
    return almacen.crear_empresa(nombre.strip(), slug, ahora, {
        "verify_token": nuevo_token_verificacion(),
        "modelo": reglas.MODELO_POR_DEFECTO,
        "precio_entrada": precio_e,
        "precio_salida": precio_s,
        "trato": "usted",
        "pausa_horas": 12,
        "historial_limite": 20,
        "info": {},
    })


def crear_enlace(almacen, empresa_id: int, ahora: datetime) -> str:
    """Devuelve el token del enlace. En la base solo queda su hash."""
    token = secrets.token_urlsafe(32)
    almacen.crear_invitacion(hash_token(token), empresa_id, ahora + timedelta(days=DIAS_ENLACE), ahora)
    return token


def buscar_enlace(almacen, token: str, ahora: datetime):
    """(empresa, None) si el enlace sirve; (None, motivo) si no."""
    invitacion = almacen.invitacion(hash_token(token)) if token else None
    if not invitacion:
        return None, "Este enlace no existe. Revisa que lo copiaste completo o pide uno nuevo."
    if invitacion["usada"]:
        return None, "Este enlace ya se usó. Si necesitas cambiar algo, pide uno nuevo."
    if ahora >= invitacion["vence"]:
        return None, "Este enlace venció. Pide uno nuevo."
    return almacen.empresa(invitacion["empresa_id"]), None


def leer_formulario(form, es_admin: bool) -> tuple[dict, dict, dict]:
    """(cambios, secretos, errores). Un secreto vacio = dejar el que ya estaba."""
    cambios = {}
    for campo in CAMPOS_PUBLICOS + (CAMPOS_ADMIN if es_admin else ()):
        if campo in form:
            cambios[campo] = form.get(campo, "").strip()
    cambios["dueno_numero"] = reglas.normalizar_numero(cambios.get("dueno_numero", ""))
    cambios["trato"] = "tu" if cambios.get("trato") == "tu" else "usted"
    cambios["info"] = {campo: form.get(f"info_{campo}", "").strip() for campo, _, _ in CAMPOS_NEGOCIO}
    secretos = {campo: "".join(form.get(campo, "").split()) for campo in SECRETOS if form.get(campo, "").strip()}

    errores = reglas.errores_de_formato({**cambios, **secretos})
    if not cambios.get("nombre"):
        errores["nombre"] = "Escribe el nombre del negocio."
    if es_admin:
        for campo in ("precio_entrada", "precio_salida", "pausa_horas", "historial_limite"):
            try:
                valor = float(cambios.get(campo) or 0)
                if valor < 0:
                    raise ValueError
                cambios[campo] = int(valor) if campo == "historial_limite" else valor
            except ValueError:
                errores[campo] = "Escribe un número."
        if cambios.get("historial_limite", 1) < 2:
            errores["historial_limite"] = "Al menos 2 mensajes."
    return cambios, secretos, errores


def guardar(almacen, cifrador, empresa: dict, cambios: dict, secretos: dict, hoy: date, ahora: datetime) -> dict:
    cambios = dict(cambios)
    saldo = cambios.pop("saldo_usd", "")
    if saldo != "" and saldo is not None and float(saldo) != float(empresa.get("saldo_usd") or -1):
        cambios["saldo_usd"] = float(saldo)
        cambios["saldo_desde"] = hoy.isoformat()
    for campo, valor in secretos.items():
        cambios[f"{campo}_cif"] = cifrador.cifrar(valor)
    return almacen.actualizar_empresa(empresa["id"], cambios, ahora)


def secretos_de(empresa: dict, cifrador) -> dict:
    return {campo: cifrador.descifrar(empresa.get(f"{campo}_cif", "")) for campo in SECRETOS}


def mascaras(empresa: dict, cifrador) -> dict:
    return {campo: reglas.enmascarar(valor) for campo, valor in secretos_de(empresa, cifrador).items()}
