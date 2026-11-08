# Registro de cambios

Aquí se registra todo cambio a algo ya escrito o acordado: un requisito, una decisión, el manual o una regla. Cada cambio tiene motivo, fuente y fecha, para que nada cambie en silencio.

- Decisiones: [decisiones.md](decisiones.md) · Glosario: [glosario.md](glosario.md)

| ID | Fecha | Qué cambia | Antes | Después | Motivo | Fuente | Estado | Afecta |
|---|---|---|---|---|---|---|---|---|
| C-01 | 07/11/2026 | Estructura del proyecto | Un solo `bot.py` en la PC con túnel | Paquete en capas, MongoDB, derivación, 17 tests, CI, Render | Tenerlo como proyecto y 24/7 | Pedido de Hugo, 07/11/2026 | Aplicado (v1.0) | Todo el repositorio |
| C-02 | 07/11/2026 | Base de datos (D-03) | MongoDB Atlas | PostgreSQL en Neon, con tests contra Postgres real en el CI | Hugo prefiere PostgreSQL | Pedido de Hugo, 07/11/2026 | Incluido en v2.0 (el parche v1.1 no se aplicó aparte) | `almacen.py`, CI, docs |
| C-03 | 07/11/2026 | Comandos de PowerShell | Rutas fijas con `C:\Users\hugor` | `$env:USERPROFILE`, para la PC y la laptop | En la laptop el usuario es `sebas` | Error de Hugo en la laptop, 07/11/2026 | Incluido en v2.0 | `docs/despliegue.md` |
| C-04 | 08/11/2026 | Alcance (BOT-RF-12 a 19) | Una sola empresa, llaves en variables de entorno, sin panel | Multiempresa con webhook por empresa, panel, enlaces de alta, verificaciones reales, modo prueba, estimación de crédito, números ignorados | Sumar empresas fácil, configurar desde el celular, ver créditos | Pedido de Hugo, 07/11/2026 | Aplicado (v2.0) | Todo el código y los docs |
| C-05 | 08/11/2026 | `instrucciones.md` | El manual de una empresa, con espacios `[completar]` | Plantilla común con `$negocio`, `$dueno`, `$info`; lo propio de cada empresa se carga en el panel | Varias empresas comparten las reglas | Consecuencia de C-04 | Aplicado (v2.0) | `instrucciones.md`, `manual.py` |
| C-06 | 08/11/2026 | Variables de entorno | `ANTHROPIC_API_KEY`, `WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `APP_SECRET`, `VERIFY_TOKEN`, `DATABASE_URL` | `DATABASE_URL`, `ADMIN_PASSWORD`, `CLAVE_MAESTRA` (generada por Render) | Las llaves son de cada empresa y viven cifradas en la base (D-14) | Consecuencia de C-04 | Aplicado (v2.0) | `config.py`, `render.yaml`, `.env.example` |
| C-07 | 08/11/2026 | Requisitos BOT-RF-06, 07 y 08 | Una llave y un webhook globales | Por empresa; los errores de Claude quedan en la Actividad del panel | Consecuencia de C-04 | Consecuencia de C-04 | Aplicado (v2.0) | `servicios.py`, `app.py`, tests |
| C-08 | 08/11/2026 | Llamadas a Claude con Haiku 5.5 (D-21) | Sin parámetro `thinking`; la prueba de la llave pedía `max_tokens=1`; un 400 se mostraba solo con su número | `thinking: disabled` para Haiku 5.5; la prueba pide 16 tokens; el panel muestra el motivo que da la API | Haiku 5.5 trae el razonamiento encendido por defecto: con 1 token la prueba daba error 400 y en el bot gastaba tokens pensando | Error en el panel durante el alta de Sentirse Única, 08/11/2026 | Aplicado (v2.1) | `reglas.py`, `asistente.py`, `verificaciones.py`, tests |
