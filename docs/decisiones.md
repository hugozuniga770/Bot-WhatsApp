# Decisiones

- Proyecto: Bot de WhatsApp con Claude (negocio de mi mamá) · Responsable: Hugo Zúñiga
- Fecha: 07/11/2026
- Relacionados: [README](../README.md) · [Arquitectura](arquitectura.md) · [Cambios](cambios.md) · [Glosario](glosario.md)

**Marcas:**
- **[ACUERDO]:** lo decidió Hugo.
- **[PROPUESTA]:** lo propuso Claude al armar el proyecto; Hugo lo confirma o lo cambia al revisar (y lo registra en `cambios.md`).
- **[PROVISIONAL]:** se usa mientras no se resuelva algo abierto.
- **Pendiente:** todavía no hay decisión.

| ID | Decisión | Alternativas que se miraron | Por qué | Estado |
|---|---|---|---|---|
| D-00 | Programarlo nosotros, con la API de Claude, en vez de una plataforma ya armada o el agente de IA de Meta | Plataforma con mensualidad; n8n o Make; agente de Meta | Es lo más barato y da control total sobre cómo responde | [ACUERDO] (07/11/2026) |
| D-01 | Python 3.13 con Flask | Node.js; FastAPI | Simple y conocido; Flask alcanza para tres rutas | [PROPUESTA] |
| D-02 | Render, plan gratis | Render Starter (USD 7 al mes, no se duerme); Google Cloud Run (pide tarjeta y limita el CPU después de responder, lo que choca con D-07); Oracle Cloud gratis (una VM de verdad, pero mucho más trabajo); Cloudflare Workers (habría que reescribir en JavaScript) | Gratis, se despliega solo desde GitHub y corre el código tal cual. Costo: se duerme tras 15 min sin tráfico y el primer mensaje después tarda alrededor de un minuto. Si eso molesta, pasar a Starter solo cambia `plan` en `render.yaml` | [PROVISIONAL] |
| D-03 | MongoDB Atlas, plan gratuito M0, para historial, pausas e ids atendidos | Postgres gratis de Render (vence a los 30 días); SQLite (Render gratis borra el disco) | No vence, y Hugo ya trabajó con MongoDB | [PROPUESTA] |
| D-04 | Modelo `claude-haiku-5-5`, cambiable con `CLAUDE_MODEL` | Modelos más grandes | Rápido y económico para respuestas cortas; si responde mal, se cambia sin tocar código | [PROPUESTA] |
| D-05 | Cómo se conecta el número de la mamá | Proveedor con coexistencia; número aparte para el bot; pasar su número solo a la API | Depende de si ella quiere seguir usando su app con el mismo número y de cuánto cuesta el proveedor. Ver [despliegue, paso 8](despliegue.md#paso-8-número-de-tu-mamá--pendiente-d-05) | Pendiente |
| D-06 | Derivación con una marca en el texto (`[PASAR_A_HUMANO]`) y pausa de 12 h por chat | Herramientas (tool use) de Claude; un clasificador aparte | La marca es lo más simple de leer, probar y cambiar desde el manual | [PROPUESTA] |
| D-07 | Responder 200 a Meta al instante y atender en un hilo; un proceso con 4 hilos | Atender dentro de la petición | Evita que Meta reenvíe mientras Claude piensa; los reenvíos igual se frenan por id (BOT-RF-05) | [PROPUESTA] |
| D-08 | Solo texto; el resto recibe un aviso fijo | Transcribir audios con otro servicio; mandar las fotos a Claude | Primera versión acotada. Los audios son comunes en Bolivia: es la primera mejora candidata | [PROVISIONAL] |
| D-09 | Render despliega solo si el CI pasa (`autoDeployTrigger: checksPass`) | Desplegar en cada push | Un push con tests en rojo no llega a los clientes | [PROPUESTA] |
| D-10 | Durante una pausa no se guardan los mensajes del cliente | Guardarlos | Las respuestas de la dueña no se ven (D-05); si se guardaran solo las preguntas, al volver el bot podría contestar cosas que ella ya resolvió | [PROVISIONAL] |
| D-11 | En los logs, los números salen recortados (`...1234`) | Número completo | Los logs no necesitan datos personales completos | [PROPUESTA] |
