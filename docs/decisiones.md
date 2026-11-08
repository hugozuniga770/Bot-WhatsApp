# Decisiones

- Proyecto: Bots de WhatsApp con Claude · Responsable: Hugo Zúñiga
- Fecha: 08/11/2026 · Versión: v2.0
- Relacionados: [README](../README.md) · [Arquitectura](arquitectura.md) · [Cambios](cambios.md) · [Glosario](glosario.md)

**Marcas:**
- **[ACUERDO]:** lo decidió Hugo.
- **[PROPUESTA]:** lo propuso Claude al armar el proyecto; Hugo lo confirma o lo cambia al revisar (y lo registra en `cambios.md`).
- **[PROVISIONAL]:** se usa mientras no se resuelva algo abierto.
- **Pendiente:** todavía no hay decisión.

| ID | Decisión | Alternativas que se miraron | Por qué | Estado |
|---|---|---|---|---|
| D-00 | Programarlo nosotros, con la API de Claude | Plataforma con mensualidad; n8n o Make; agente de IA de Meta | Lo más barato y con control total sobre cómo responde | [ACUERDO] (07/11/2026) |
| D-01 | Python con Flask | Node.js; FastAPI | Simple y conocido | [PROPUESTA] |
| D-02 | Render, plan gratis | Render Starter (USD 7 al mes, no se duerme); Google Cloud Run; Oracle Cloud gratis; Cloudflare Workers (reescribir en JavaScript) | Gratis y se despliega solo desde GitHub. Costo: se duerme tras 15 min sin tráfico. Pasar a Starter es cambiar `plan` en `render.yaml` | [PROVISIONAL] |
| D-03 | PostgreSQL en Neon, plan gratis | MongoDB Atlas (v1.0); Postgres de Render (vence a los 30 días); Supabase (pausa proyectos inactivos) | Hugo prefirió PostgreSQL. Tablas simples, claves únicas para no responder dos veces, revisión con SQL. Si la base tiene tablas de la v1.x, el servicio se detiene con un aviso | [ACUERDO] (07/11/2026) |
| D-04 | Modelo `claude-haiku-5-5` por defecto, cambiable por empresa | Modelos más grandes | Rápido y económico: USD 0.10 / 0.50 por millón de tokens de entrada / salida (página oficial, 07/11/2026) | [PROPUESTA] |
| D-05 | Cómo se conecta el número de la mamá | Proveedor con coexistencia; número aparte; pasar su número solo a la API | Depende de si quiere seguir usando su app con el mismo número y de cuánto cuesta el proveedor | Pendiente |
| D-06 | Derivación con la marca `[PASAR_A_HUMANO]` y pausa por chat | Herramientas (tool use) de Claude; clasificador aparte | Simple de leer, probar y explicar en el manual | [PROPUESTA] |
| D-07 | Responder 200 a Meta al instante y atender en un hilo; un proceso con 4 hilos | Atender dentro de la petición | Meta no reenvía mientras Claude piensa; los reenvíos igual se frenan por id | [PROPUESTA] |
| D-08 | Solo texto; el resto recibe un aviso fijo | Transcribir audios; mandar fotos a Claude | Primera versión acotada. Los audios son comunes en Bolivia: primera mejora candidata | [PROVISIONAL] |
| D-09 | Render despliega solo si el CI pasa (`autoDeployTrigger: checksPass`) | Desplegar en cada push | Un push con tests en rojo no llega a los clientes | [PROPUESTA] |
| D-10 | Durante una pausa no se guardan los mensajes del cliente | Guardarlos | Sin ver las respuestas del dueño (D-05), el bot podría contestar cosas ya resueltas | [PROVISIONAL] |
| D-11 | En los logs, los números salen recortados | Número completo | Los logs no necesitan datos personales | [PROPUESTA] |
| D-12 | Tests de contrato del almacén contra memoria y contra PostgreSQL real; el CI falla si alguno se salta | Probar Postgres a mano | Si el CI pasa, el almacén de producción ya se probó de verdad | [PROPUESTA] |
| D-13 | Multiempresa en una sola instalación, con un webhook por empresa (`/webhook/<slug>`) | Un servicio por empresa; un webhook único que reparte por número | Hugo pidió sumar empresas fácil. Con un webhook por empresa, cada una verifica la firma con su propio App Secret antes de leer nada | [ACUERDO] (07/11/2026) |
| D-14 | Llaves de cada empresa en la base, cifradas con `CLAVE_MAESTRA` | Variables de entorno por empresa | Se cargan desde el celular sin tocar Render; si alguien copia la base, no puede leerlas. Costo: si se pierde la `CLAVE_MAESTRA`, hay que volver a cargar las llaves | [PROPUESTA] |
| D-15 | Saldo de Claude estimado: el bot cuenta los tokens y resta del saldo cargado | Leer el saldo por API | La Admin API de Anthropic no está disponible para cuentas individuales y no devuelve el saldo (documentación oficial, 07/11/2026). La estimación usa el promedio de los últimos 7 días y se corrige al actualizar el saldo | [PROPUESTA] |
| D-16 | Panel con páginas hechas en el servidor (Flask + Jinja), JavaScript mínimo y sin compilar | React o Vue | Un solo servicio, nada que compilar; sin JavaScript igual funciona. Diseño propio: paleta tajibo (verde pino, salvia y rosa tajibo), Bricolage Grotesque y Atkinson Hyperlegible, pensado para el celular | [PROPUESTA] |
| D-17 | Alta por enlace de un solo uso que vence en 7 días; en la base solo el hash | Que el dueño cree una cuenta | El dueño no necesita usuario ni contraseña, y el enlace no se puede reusar | [ACUERDO] (07/11/2026) |
| D-18 | Al enviar el alta, la empresa queda "en prueba": el bot solo le responde al dueño | Activarla directo | Se prueba con el número real sin que los clientes vean errores | [PROPUESTA] |
| D-19 | Activar exige una verificación sin fallas | Activar sin verificar | Evita dejar activo un bot con una llave mala | [PROPUESTA] |
| D-21 | Razonamiento (thinking) apagado en Haiku 5.5 | Dejarlo encendido (por defecto) | Para responder WhatsApp no hace falta. Apagado, las respuestas son más rápidas y baratas, y la estimación de crédito se mantiene. En Sonnet 5.5 "disabled" da error 400, así que solo se aplica a los modelos de `MODELOS_SIN_RAZONAMIENTO` (documentación oficial, 08/11/2026) | [PROPUESTA] |
| D-22 | Pool de conexiones preparado para Neon: `connect_timeout` 10 s, keepalives, `max_idle` 60 s, `reconnect_timeout` 60 s, un reintento si se corta una consulta y 503 si la base no responde | Abrir una conexión nueva en cada consulta (más lento); dejar los valores por defecto | Neon duerme la base y corta conexiones; con los valores por defecto, un intento colgado dejaba al pool sin conexiones por minutos. Probado apagando y prendiendo PostgreSQL: el panel responde 503 en 15 s y se recupera en unos 7 s | [PROPUESTA] |
| D-20 | Un solo administrador con contraseña y bloqueo por intentos | Usuarios y permisos por empresa | Alcanza para Hugo; agregar usuarios sería una versión futura | [PROVISIONAL] |
