# Cómo sumar una empresa nueva

- Proyecto: Bots de WhatsApp con Claude · Responsable: Hugo Zúñiga · Versión: v3.2
- Relacionados: [README](../README.md) · [Despliegue](despliegue.md) · [Decisiones](decisiones.md)

El panel tiene, en cada empresa, una lista de **Puesta en marcha** (BOT-RF-31) que dice qué falta. Esta guía es el mismo camino, explicado.

## Lo que necesita cada negocio

| Qué | De quién | Para qué |
|---|---|---|
| Portafolio de Meta (business.facebook.com) y una app de WhatsApp | Del negocio | El número desde el que responde el bot |
| Cuenta de Claude con créditos (platform.claude.com) | Del negocio, o la tuya si cobras el servicio | Las respuestas. Si es la tuya, el crédito estimado del panel es por empresa, pero el saldo real es uno solo |
| Celular de la dueña o el dueño | Del negocio | Probar el bot (en prueba solo le responde a ese número) y recibir avisos |

## Paso a paso

1. **Crear:** panel → **Agregar una empresa** → **Crear y generar enlace** → **Enviar por WhatsApp**.
2. **Alta:** el dueño llena los 6 pasos desde su celular. Cada paso explica dónde está cada dato y tiene botones **Probar**. En el paso 5 conecta el webhook, y ahí mismo están las dos direcciones para **publicar la app en Meta** (privacidad y borrado de datos).
3. **Revisar en el panel:**
   - **Verificar todo** en verde;
   - **Lo que el bot sabe**, con al menos 4 de los 8 temas (si falta, completa el paso 2 en **Editar datos y llaves**).
4. **Accesos:** en **Agenda del negocio → Crear un acceso**, uno para la dueña y, si hay, otro para la asistente. Manda cada contraseña temporal por WhatsApp; se muestra una sola vez.
5. **Opcional, si van a usar la agenda:** la dueña carga su **Horario**. Si quieren que el bot agende y cobre adelantos, configura **Pagos → Configurar cobros**.
6. **Prueba en vivo:** el dueño le escribe al número del negocio. El bot le responde solo a él, porque la empresa está **En prueba**.
7. **Activar para todos**, cuando la Puesta en marcha diga 5 de 5.

## Antes de tener clientes reales: los límites de lo gratis

- **Render gratis se duerme** tras 15 minutos sin mensajes. El primer mensaje después tarda alrededor de un minuto (medido: unos 50 segundos al despertar). Con clientes reales conviene el plan **Starter** de Render: se cambia `plan: free` por `plan: starter` en `render.yaml` (D-02).
- **Neon gratis tiene un tope mensual de horas de cómputo.** Con varios negocios mandando mensajes todo el día, la base pasa más tiempo despierta y el tope puede alcanzar. Revisa el uso en el panel de Neon cada semana. Si pasa del 70 %, sube de plan antes de que se corte.
- **Créditos de Claude:** el panel estima para cuántos días alcanza cada empresa. Cuando un negocio recargue, actualiza su saldo en el panel.
- **Número de prueba de Meta:** solo le escribe a los 5 números de su lista. Para clientes reales hace falta un número propio conectado y, para límites más altos, la verificación del negocio en Meta.
