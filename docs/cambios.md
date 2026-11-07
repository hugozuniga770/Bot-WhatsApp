# Registro de cambios

Aquí se registra todo cambio a algo ya escrito o acordado: un requisito, una decisión, el manual o una regla. Cada cambio tiene motivo, fuente y fecha, para que nada cambie en silencio.

- Decisiones: [decisiones.md](decisiones.md) · Glosario: [glosario.md](glosario.md)

| ID | Fecha | Qué cambia | Antes | Después | Motivo | Fuente | Estado | Afecta |
|---|---|---|---|---|---|---|---|---|
| C-01 | 07/11/2026 | Estructura del proyecto | Un solo `bot.py` (fase 1): historial en memoria, sin tests, solo en la PC con túnel | Paquete `bot/` en capas (app, servicios, reglas, almacén), MongoDB, derivación con pausa, 17 tests, CI y despliegue en Render desde GitHub | Tenerlo como proyecto en un repositorio y que funcione 24/7 | Pedido de Hugo, 07/11/2026 | Aplicado | Todo el repositorio |
