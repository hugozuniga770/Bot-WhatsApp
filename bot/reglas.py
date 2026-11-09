"""Reglas del bot y del panel.

Todas son funciones puras: no usan la red, ni la base de datos, ni el reloj.
La hora (`ahora`, `hoy`) siempre llega como parametro, asi los tests deciden la hora.
"""
import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# El asistente escribe esta marca cuando hay que pasarle el chat a la duena.
MARCA_HUMANO = "[PASAR_A_HUMANO]"

# Precios por millon de tokens (USD), de platform.claude.com/docs/en/about-claude/pricing
# consultados el 07/11/2026. Se pueden cambiar por empresa desde el panel.
PRECIOS = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}
MODELO_POR_DEFECTO = "claude-haiku-5-5"

# Haiku 5.5 trae el razonamiento (thinking) encendido por defecto. Para responder
# WhatsApp no hace falta: apagarlo da respuestas mas rapidas y mas baratas, y evita
# que el pensamiento se coma el limite de tokens. Fuente: platform.claude.com/docs/en/
# build-with-claude/thinking (consultada el 08/11/2026). En Sonnet 5.5 "disabled" da
# error 400, por eso solo se aplica a los modelos de esta lista.
MODELOS_SIN_RAZONAMIENTO = ("claude-haiku-5-5",)


def opciones_de_modelo(modelo: str) -> dict:
    """Parametros extra para la API segun el modelo."""
    if modelo in MODELOS_SIN_RAZONAMIENTO:
        return {"thinking": {"type": "disabled"}}
    return {}


# ---------------------------------------------------------------- mensajes de Meta

@dataclass(frozen=True)
class MensajeEntrante:
    id: str
    numero: str
    tipo: str
    texto: str = ""
    media_id: str = ""  # foto o documento (por ejemplo, un comprobante de pago)


def extraer_mensajes(payload) -> list[MensajeEntrante]:
    """Saca los mensajes de clientes del JSON que manda Meta.

    Ignora los avisos de estado (enviado, entregado, leido), que llegan
    al mismo webhook pero no son mensajes.
    """
    mensajes = []
    if not isinstance(payload, dict):
        return mensajes
    if payload.get("object") in OBJETOS_SOCIALES:
        return _extraer_sociales(payload)
    for entrada in payload.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            if cambio.get("field", "messages") != "messages":
                continue
            valor = cambio.get("value") or {}
            for m in valor.get("messages") or []:
                if not m.get("id") or not m.get("from"):
                    continue
                tipo = m.get("type", "")
                texto, media_id = "", ""
                if tipo == "text":
                    texto = ((m.get("text") or {}).get("body") or "").strip()
                elif tipo in ("image", "document"):
                    media = m.get(tipo) or {}
                    media_id, texto = str(media.get("id") or ""), (media.get("caption") or "").strip()
                mensajes.append(MensajeEntrante(m["id"], m["from"], tipo, texto, media_id))
    return mensajes


# ---------------------------------------------------------------- Messenger e Instagram (v3.3)
# Un chat de Messenger o Instagram se guarda igual que uno de WhatsApp, pero en vez del
# número lleva un prefijo y el id que Meta le da a esa persona en esa página: "fb:<PSID>"
# o "ig:<IGSID>". Así las tablas no cambian y no se mezcla con un número de teléfono.
OBJETOS_SOCIALES = {"page": "messenger", "instagram": "instagram"}
PREFIJOS = {"messenger": "fb:", "instagram": "ig:"}
NOMBRES_CANAL = {"whatsapp": "WhatsApp", "messenger": "Messenger", "instagram": "Instagram"}
# Lo más largo que acepta cada canal en un mensaje de texto (documentación de Meta, 09/11/2026)
LIMITE_TEXTO = {"whatsapp": 4096, "messenger": 2000, "instagram": 1000}


def canal_de(destino: str) -> str:
    """'fb:123' -> 'messenger', 'ig:123' -> 'instagram', '59170000001' -> 'whatsapp'."""
    for canal, prefijo in PREFIJOS.items():
        if (destino or "").startswith(prefijo):
            return canal
    return "whatsapp"


def id_social(destino: str) -> str:
    """El id que entiende Meta, sin el prefijo del canal."""
    canal = canal_de(destino)
    return destino[len(PREFIJOS[canal]):] if canal in PREFIJOS else destino


def etiqueta_contacto(destino: str) -> str:
    """Cómo se nombra a un cliente en los avisos al dueño y en el panel."""
    canal = canal_de(destino)
    if canal == "whatsapp":
        return f"+{destino}"
    return f"de {NOMBRES_CANAL[canal]} (...{destino[-4:]})"


def _extraer_sociales(payload: dict) -> list[MensajeEntrante]:
    """Mensajes de Messenger (object "page") o Instagram (object "instagram").

    Se ignoran los ecos (lo que manda la propia página, también desde Business Suite),
    las lecturas y las entregas. Un botón tocado (postback) se trata como texto.
    """
    canal = OBJETOS_SOCIALES[payload["object"]]
    prefijo = PREFIJOS[canal]
    mensajes = []
    for entrada in payload.get("entry") or []:
        propio = str(entrada.get("id") or "")
        for evento in entrada.get("messaging") or []:
            remitente = str((evento.get("sender") or {}).get("id") or "")
            if not remitente or remitente == propio:
                continue
            m = evento.get("message")
            if isinstance(m, dict):
                if m.get("is_echo") or not m.get("mid"):
                    continue
                texto = (m.get("text") or "").strip()
                if texto:
                    mensajes.append(MensajeEntrante(m["mid"], prefijo + remitente, "text", texto))
                    continue
                adjuntos = m.get("attachments") or []
                tipo_meta = (adjuntos[0].get("type") if adjuntos and isinstance(adjuntos[0], dict) else "") or ""
                url = str(((adjuntos[0].get("payload") or {}) if adjuntos else {}).get("url") or "")
                tipo = {"image": "image", "file": "document"}.get(tipo_meta, tipo_meta or "desconocido")
                if (m.get("sticker_id") or (adjuntos and (adjuntos[0].get("payload") or {}).get("sticker_id"))):
                    tipo, url = "sticker", ""
                mensajes.append(MensajeEntrante(m["mid"], prefijo + remitente, tipo, "", url if tipo in ("image", "document") else ""))
            elif isinstance(evento.get("postback"), dict):
                p = evento["postback"]
                texto = (p.get("title") or p.get("payload") or "").strip()
                ident = p.get("mid") or f"postback:{remitente}:{evento.get('timestamp', '')}"
                if texto:
                    mensajes.append(MensajeEntrante(str(ident), prefijo + remitente, "text", texto))
    return mensajes


@dataclass(frozen=True)
class FallaDeEntrega:
    """Meta avisa que no pudo entregar un mensaje que mandó el bot (status "failed")."""
    id: str
    numero: str
    codigo: int | None = None
    detalle: str = ""


# Códigos de error de la WhatsApp Cloud API, explicados para el panel.
# Fuente: developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes (08/11/2026).
MOTIVOS_DE_FALLA = {
    131047: "pasaron más de 24 horas desde el último mensaje de esa persona, y WhatsApp no deja escribirle primero",
    131026: "ese número no puede recibirlo (puede que no use WhatsApp o tenga una versión vieja)",
    131030: "ese número no está en la lista de destinatarios de prueba de Meta",
    131049: "Meta decidió no entregarlo para cuidar la experiencia de los usuarios",
    131050: "esa persona pidió no recibir mensajes de marketing",
    131056: "se mandaron demasiados mensajes seguidos a ese número; hay que esperar un rato",
    130429: "se superó el límite de envíos de la cuenta",
    131031: "la cuenta de WhatsApp Business está bloqueada",
    131042: "hay un problema con el método de pago de la cuenta de Meta",
    368: "la cuenta está bloqueada por un tiempo por no cumplir las políticas de WhatsApp",
}


def extraer_fallas(payload) -> list[FallaDeEntrega]:
    """Saca del JSON de Meta los avisos de mensajes que no se pudieron entregar.

    Los avisos de enviado, entregado y leído se ignoran (BOT-RF-09).
    """
    fallas = []
    if not isinstance(payload, dict):
        return fallas
    for entrada in payload.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            if cambio.get("field", "messages") != "messages":
                continue
            for estado in (cambio.get("value") or {}).get("statuses") or []:
                if estado.get("status") != "failed" or not estado.get("id"):
                    continue
                error = (estado.get("errors") or [{}])[0] or {}
                codigo = error.get("code")
                detalle = ((error.get("error_data") or {}).get("details") or error.get("message")
                           or error.get("title") or "")
                fallas.append(FallaDeEntrega(estado["id"], str(estado.get("recipient_id") or ""),
                                             codigo if isinstance(codigo, int) else None, str(detalle)[:200]))
    return fallas


def texto_de_falla(falla: FallaDeEntrega) -> str:
    """El texto que queda en la Actividad del panel."""
    motivo = MOTIVOS_DE_FALLA.get(falla.codigo) or falla.detalle or "Meta no dio el motivo"
    codigo = f" (código {falla.codigo})" if falla.codigo else ""
    return f"Meta no pudo entregar un mensaje a {ocultar_numero(falla.numero)}: {motivo}{codigo}."


def firma_valida(cuerpo: bytes, cabecera: str | None, secreto: str) -> bool:
    """Comprueba que la peticion viene de Meta (cabecera X-Hub-Signature-256)."""
    if not secreto or not cabecera or not cabecera.startswith("sha256="):
        return False
    esperada = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, cabecera[len("sha256="):])


# ---------------------------------------------------------------- conversacion

def recortar_historial(historial: list[dict], limite: int) -> list[dict]:
    """Deja los ultimos `limite` mensajes y hace que empiece por el cliente."""
    recorte = [dict(m) for m in historial[-limite:]] if limite > 0 else []
    while recorte and recorte[0]["role"] != "user":
        recorte.pop(0)
    return recorte


def separar_marca(respuesta: str) -> tuple[str, bool]:
    """Quita la marca de derivacion del texto y dice si estaba."""
    pide_humano = MARCA_HUMANO in respuesta
    return respuesta.replace(MARCA_HUMANO, "").strip(), pide_humano


def esta_pausado(pausado_hasta: datetime | None, ahora: datetime) -> bool:
    return pausado_hasta is not None and ahora < pausado_hasta


def fin_de_pausa(ahora: datetime, horas: float) -> datetime:
    return ahora + timedelta(hours=horas)


def ocultar_numero(numero: str) -> str:
    """Para los registros (logs): solo los ultimos 4 digitos del cliente."""
    return "..." + numero[-4:] if len(numero) > 4 else "..."


def lista_de_numeros(texto: str) -> set[str]:
    """'+591 7000 0001, 59170000002' -> {'59170000001', '59170000002'}"""
    return {n for n in (normalizar_numero(p) for p in re.split(r"[,;\n]+", texto or "")) if n}


# ---------------------------------------------------------------- empresas y formularios

def normalizar_numero(numero: str) -> str:
    """'+591 700-00001' -> '59170000001' (formato que usa Meta)."""
    return re.sub(r"\D", "", numero or "")


def crear_slug(nombre: str) -> str:
    """'Sentirse Única SRL' -> 'sentirse-unica-srl'"""
    sin_tildes = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")
    return slug[:40].strip("-") or "empresa"


def enmascarar(secreto: str) -> str:
    """Para mostrar una llave guardada sin revelarla: 'sk-ant-…a1b2'."""
    if not secreto:
        return ""
    if len(secreto) <= 10:
        return "…" + secreto[-2:]
    return secreto[:7] + "…" + secreto[-4:]


def errores_de_formato(campos: dict) -> dict[str, str]:
    """Revisa que cada dato tenga la forma correcta antes de probarlo de verdad.

    Solo revisa los campos que vienen con valor: los vacios se tratan aparte
    (en el alta, un secreto vacio significa 'dejar el que ya estaba').
    """
    errores = {}
    clave = campos.get("anthropic_key", "")
    if clave and not clave.startswith("sk-ant-"):
        errores["anthropic_key"] = "La llave de Claude empieza con sk-ant-. Revisa que la copiaste completa."
    for campo, nombre in (("meta_app_id", "El App ID"), ("phone_number_id", "El Phone number ID")):
        valor = campos.get(campo, "")
        if valor and not re.fullmatch(r"\d{6,25}", valor):
            errores[campo] = f"{nombre} son solo números (entre 6 y 25)."
    secreto = campos.get("meta_app_secret", "")
    if secreto and not re.fullmatch(r"[0-9a-fA-F]{32}", secreto):
        errores["meta_app_secret"] = "El App Secret tiene 32 letras y números (0-9, a-f). Usa el botón Mostrar en Meta y cópialo entero."
    token = campos.get("whatsapp_token", "")
    if token and (len(token) < 50 or " " in token):
        errores["whatsapp_token"] = "El token es un texto largo, sin espacios (suele empezar con EAA). Revisa que lo copiaste completo."
    numero = campos.get("dueno_numero", "")
    if numero and not re.fullmatch(r"\d{8,15}", numero):
        errores["dueno_numero"] = "Escribe el número con código de país, por ejemplo 591 70000000."
    saldo = campos.get("saldo_usd", "")
    if saldo:
        try:
            if float(saldo) < 0:
                raise ValueError
        except ValueError:
            errores["saldo_usd"] = "Escribe solo el monto en dólares, por ejemplo 5 o 5.50."
    return errores


# ---------------------------------------------------------------- creditos y uso

def dia_local(ahora: datetime, zona: str) -> date:
    """El dia del calendario en la zona del negocio (Bolivia por defecto)."""
    return ahora.astimezone(ZoneInfo(zona)).date()


def costo_usd(entrada: int, salida: int, precio_entrada: float, precio_salida: float) -> float:
    return entrada * precio_entrada / 1_000_000 + salida * precio_salida / 1_000_000


def serie_diaria(uso: list[dict], hoy: date, dias: int, precio_entrada: float, precio_salida: float) -> list[dict]:
    """Una fila por dia (los ultimos `dias`, incluido hoy), con ceros donde no hubo uso."""
    por_dia = {u["dia"]: u for u in uso}
    serie = []
    for i in range(dias - 1, -1, -1):
        d = hoy - timedelta(days=i)
        u = por_dia.get(d, {})
        entrada, salida = int(u.get("entrada", 0)), int(u.get("salida", 0))
        serie.append({
            "dia": d,
            "llamadas": int(u.get("llamadas", 0)),
            "tokens": entrada + salida,
            "costo": costo_usd(entrada, salida, precio_entrada, precio_salida),
        })
    mayor = max((s["tokens"] for s in serie), default=0)
    for s in serie:
        s["altura"] = round(100 * s["tokens"] / mayor) if mayor else 0
    return serie


def resumen_credito(saldo_usd, desde: date | None, uso: list[dict], hoy: date,
                    precio_entrada: float, precio_salida: float, ventana: int = 7) -> dict:
    """Estima cuanto saldo queda y para cuantos dias alcanza.

    - `saldo_usd` es lo que habia en platform.claude.com el dia `desde`.
    - Se resta lo gastado desde ese dia segun los tokens contados por el bot.
    - El gasto diario es el promedio de los ultimos `ventana` dias (o de los
      dias que lleva funcionando, si son menos).
    """
    if saldo_usd in (None, "") or desde is None:
        return {"estado": "sin_saldo"}
    saldo = float(saldo_usd)
    gastado = sum(costo_usd(int(u["entrada"]), int(u["salida"]), precio_entrada, precio_salida)
                  for u in uso if u["dia"] >= desde)
    restante = max(0.0, saldo - gastado)

    inicio = hoy - timedelta(days=ventana - 1)
    con_uso = [u for u in uso if inicio <= u["dia"] <= hoy and (u["entrada"] or u["salida"])]
    if con_uso:
        primer_dia = min(u["dia"] for u in con_uso)
        dias_observados = (hoy - max(inicio, primer_dia)).days + 1
        gasto_ventana = sum(costo_usd(int(u["entrada"]), int(u["salida"]), precio_entrada, precio_salida)
                            for u in con_uso)
        gasto_diario = gasto_ventana / dias_observados
    else:
        gasto_diario = 0.0

    resumen = {
        "estado": "ok",
        "saldo": saldo,
        "gastado": gastado,
        "restante": restante,
        "porcentaje": round(100 * restante / saldo) if saldo > 0 else 0,
        "gasto_diario": gasto_diario,
        "dias": None,
        "hasta": None,
    }
    if restante <= 0:
        resumen["estado"] = "agotado"
    elif gasto_diario > 0:
        dias = int(restante / gasto_diario + 1e-9)  # 4.7 / 0.1 = 46.999... en punto flotante
        resumen["dias"] = dias
        resumen["hasta"] = hoy + timedelta(days=dias)
        if dias < 7:
            resumen["estado"] = "poco"
    else:
        resumen["estado"] = "sin_uso"
    return resumen


# ---------------------------------------------------------------- presentacion

def hace(momento: datetime | None, ahora: datetime) -> str:
    """'hace 5 min', 'hace 3 h', 'hace 2 días'."""
    if momento is None:
        return "nunca"
    segundos = int((ahora - momento).total_seconds())
    if segundos < 60:
        return "hace un momento"
    if segundos < 3600:
        return f"hace {segundos // 60} min"
    if segundos < 86400:
        return f"hace {segundos // 3600} h"
    dias = segundos // 86400
    return "hace 1 día" if dias == 1 else f"hace {dias} días"


# ---------------------------------------------------------------- agenda del negocio (v3.0)

ESTADOS_CITA = {
    "pendiente_pago": "Pendiente de pago",
    "por_revisar": "Pago por revisar",
    "confirmada": "Confirmada",
    "atendida": "Atendida",
    "no_asistio": "No asistió",
    "cancelada": "Cancelada",
}
# Las canceladas liberan el horario; todas las demás lo ocupan.
ESTADOS_QUE_OCUPAN = ("pendiente_pago", "por_revisar", "confirmada", "atendida", "no_asistio")
METODOS_PAGO = ("efectivo", "qr", "transferencia", "otro")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
ROLES = {"dueno": "Dueña o dueño", "asistente": "Asistente"}
DURACION_POR_DEFECTO = 30


def leer_hora(texto: str):
    """'10:30' -> (10, 30); None si no es una hora válida."""
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", texto or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return (h, mi) if 0 <= h < 24 and 0 <= mi < 60 else None


def momento_local(dia: date, hora: str, zona: str) -> datetime | None:
    """Fecha del calendario + '10:30' en la zona del negocio -> datetime con zona."""
    hm = leer_hora(hora)
    return datetime(dia.year, dia.month, dia.day, hm[0], hm[1], tzinfo=ZoneInfo(zona)) if hm else None


def rango_del_dia(dia: date, zona: str) -> tuple[datetime, datetime]:
    inicio = datetime(dia.year, dia.month, dia.day, tzinfo=ZoneInfo(zona))
    return inicio, inicio + timedelta(days=1)


def se_superponen(inicio_a, fin_a, inicio_b, fin_b) -> bool:
    return inicio_a < fin_b and inicio_b < fin_a


def choques(inicio: datetime, fin: datetime, citas: list[dict], salvo_id=None) -> list[dict]:
    """Las citas que ya ocupan algo de ese horario (sin contar la que se está editando)."""
    return [c for c in citas if c["estado"] in ESTADOS_QUE_OCUPAN and c["id"] != salvo_id
            and se_superponen(inicio, fin, c["inicio"], c["fin"])]


def errores_de_horario(turnos: list[dict]) -> dict[int, str]:
    """Revisa cada fila del horario semanal: {indice: error}."""
    errores = {}
    for i, t in enumerate(turnos):
        desde, hasta = leer_hora(t.get("desde", "")), leer_hora(t.get("hasta", ""))
        if not isinstance(t.get("dia"), int) or not 0 <= t["dia"] <= 6:
            errores[i] = "Elige el día."
        elif not desde or not hasta:
            errores[i] = "Escribe las horas así: 10:30."
        elif hasta <= desde:
            errores[i] = "La hora de salida tiene que ser después de la de entrada."
    return errores


def esta_bloqueado(dia: date, bloqueos: list[dict]) -> dict | None:
    return next((b for b in bloqueos if b["desde"] <= dia <= b["hasta"]), None)


def turnos_del_horario(dia: date, agenda: dict, zona: str) -> list[dict]:
    """Los turnos que salen del horario semanal para ese día (sin mirar las citas)."""
    duracion = timedelta(minutes=int((agenda or {}).get("duracion") or DURACION_POR_DEFECTO))
    turnos = []
    for t in (agenda or {}).get("turnos", []):
        if t.get("dia") != dia.weekday():
            continue
        inicio, tope = momento_local(dia, t.get("desde", ""), zona), momento_local(dia, t.get("hasta", ""), zona)
        if not inicio or not tope:
            continue
        while inicio + duracion <= tope:
            turnos.append({"inicio": inicio, "fin": inicio + duracion, "sede": t.get("sede", "")})
            inicio += duracion
    return sorted(turnos, key=lambda x: x["inicio"])


def agenda_del_dia(dia: date, agenda: dict, citas: list[dict], bloqueos: list[dict], zona: str) -> dict:
    """Todo lo de un día, en orden: las citas y los turnos libres que quedan.

    Un turno del horario está libre si ninguna cita que ocupa se le superpone.
    Un día bloqueado (feriado, vacaciones) no tiene turnos libres, pero sí muestra
    las citas que ya hubiera.
    """
    del_dia = [c for c in citas if c["inicio"].astimezone(ZoneInfo(zona)).date() == dia and c["estado"] != "cancelada"]
    bloqueo = esta_bloqueado(dia, bloqueos)
    libres = [] if bloqueo else [t for t in turnos_del_horario(dia, agenda, zona) if not choques(t["inicio"], t["fin"], del_dia)]
    items = [{"tipo": "cita", "inicio": c["inicio"], "cita": c} for c in del_dia]
    items += [{"tipo": "libre", "inicio": t["inicio"], "turno": t} for t in libres]
    items.sort(key=lambda x: (x["inicio"], x["tipo"]))
    return {"dia": dia, "items": items, "citas": len(del_dia), "libres": len(libres), "bloqueo": bloqueo}


def semana_de(dia: date) -> list[date]:
    lunes = dia - timedelta(days=dia.weekday())
    return [lunes + timedelta(days=i) for i in range(7)]


def cuadricula_mes(anio: int, mes: int) -> list[list[date]]:
    """Semanas (de lunes a domingo) que cubren el mes, con los días vecinos para completar."""
    primero = date(anio, mes, 1)
    siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
    dia, semanas = primero - timedelta(days=primero.weekday()), []
    while dia < siguiente:
        semanas.append([dia + timedelta(days=i) for i in range(7)])
        dia += timedelta(days=7)
    return semanas


def normalizar_usuario(texto: str) -> str:
    """'Giovanna.Daza ' -> 'giovanna.daza'. Solo letras sin tilde, números, punto, guion y guion bajo."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9._-]", "", sin_tildes.strip().lower().replace(" ", "."))


def errores_de_usuario(usuario: str, nombre: str) -> dict[str, str]:
    errores = {}
    if not 3 <= len(usuario) <= 30:
        errores["usuario"] = "El usuario tiene que tener entre 3 y 30 letras o números."
    if not (nombre or "").strip():
        errores["nombre"] = "Escribe el nombre de la persona."
    return errores


def errores_de_clave(nueva: str, repetida: str) -> dict[str, str]:
    if len(nueva or "") < 8:
        return {"nueva": "La contraseña tiene que tener al menos 8 caracteres."}
    if nueva != repetida:
        return {"repetida": "Las dos contraseñas no son iguales."}
    return {}


def bolivianos(valor) -> str:
    """2100 -> 'Bs 2.100'; 62.5 -> 'Bs 62,50'."""
    if valor is None:
        return "—"
    valor = float(valor)
    entero = f"{int(round(valor)):,}".replace(",", ".")
    return f"Bs {entero}" if abs(valor - round(valor)) < 0.005 else f"Bs {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- archivos y trato (v3.1.1)
EXTENSIONES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "application/pdf": "pdf"}


def tipo_de_archivo(datos: bytes) -> str | None:
    """El tipo REAL de un archivo, mirando sus primeros bytes (no lo que dice quien lo manda).

    Solo se aceptan fotos (PNG, JPG, WEBP) y PDF. Cualquier otra cosa (HTML, SVG, scripts)
    devuelve None: así un "comprobante" falso no puede ejecutar código en el panel.
    """
    cabeza = bytes(datos[:16]) if datos else b""
    if cabeza.startswith(b"\x89PNG"):
        return "image/png"
    if cabeza.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if cabeza[:4] == b"RIFF" and cabeza[8:12] == b"WEBP":
        return "image/webp"
    if cabeza.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def trato(empresa: dict) -> str:
    """'usted' o 'tu', según lo que eligió el negocio (por defecto, usted)."""
    return "tu" if (empresa or {}).get("trato") == "tu" else "usted"

