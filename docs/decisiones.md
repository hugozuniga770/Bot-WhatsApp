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
| D-22 | Conexiones a Neon con un pool propio (`PoolSimple`): si no hay una conexión libre y sana, se abre en el mismo pedido; las libres de más de 4 min se descartan (Neon duerme a los 5); `connect_timeout` 15 s, keepalives, un reintento, y 503 + aviso si la base no responde. El formulario comprueba la base antes de enviar | psycopg-pool (v2.0 a v2.2): con Neon dormido no volvía a conectar; una conexión nueva por consulta (más lenta) | Probado: con la base apagada, el formulario avisa al instante y conserva las llaves; al prenderla, guarda al primer intento; con conexiones cortadas, la siguiente consulta funciona | [PROPUESTA] (v2.3) |
| D-23 | Páginas de privacidad y de borrado de datos generadas por empresa (mismo servicio, públicas, sin contraseña); el borrado lo hace el administrador desde el panel cuando el bot deriva el pedido | Una página fija por servicio; borrado automático al recibir "borrar mis datos" | Cada negocio tiene su propia app de Meta, así que cada uno necesita sus URL. Pasar por el dueño evita borrados por error o por mensajes de terceros. Es un texto base para revisar con el negocio, no asesoría legal | [PROPUESTA] (v2.4) |
| D-20 | Un solo administrador con contraseña y bloqueo por intentos | Usuarios y permisos por empresa | Alcanza para Hugo; agregar usuarios sería una versión futura | [PROVISIONAL] |
| D-24 | El token de verificación del webhook se cambia desde el panel cuando haga falta; no se intenta ocultarlo de los registros | Configurar los registros para que no muestren la dirección; cambiarlo solo al verificar | Meta lo manda en la dirección (`?hub.verify_token=…`) y quien la anota es Render, fuera del código del bot. El token solo sirve para el saludo inicial de Meta: los mensajes se aceptan solo si vienen firmados con el App Secret (BOT-RF-07). Cambiarlo no corta nada; solo hay que pegar el nuevo en Meta si se vuelve a verificar | [PROPUESTA] (v2.5) |
