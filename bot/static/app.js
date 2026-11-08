// Panel de bots: pasos del formulario, copiar, probar llaves y estado del webhook.
// Todo funciona sin JavaScript; esto solo lo hace más cómodo en el celular.
document.documentElement.classList.add("js");

document.addEventListener("DOMContentLoaded", () => {
  // Copiar al portapapeles
  document.querySelectorAll("[data-copiar]").forEach((boton) => {
    boton.addEventListener("click", async () => {
      const campo = document.querySelector(boton.dataset.copiar);
      try {
        await navigator.clipboard.writeText(campo.value);
      } catch {
        campo.select();
        document.execCommand("copy");
      }
      const texto = boton.textContent;
      boton.textContent = "Copiado";
      setTimeout(() => (boton.textContent = texto), 1600);
    });
  });

  // Confirmar acciones que cambian el estado del bot
  document.querySelectorAll("form[data-confirmar]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (!confirm(form.dataset.confirmar)) e.preventDefault();
    });
  });

  // Botones que tardan (verificar, enviar prueba)
  document.querySelectorAll("button[data-ocupado]").forEach((boton) => {
    boton.form?.addEventListener("submit", () => {
      boton.disabled = true;
      boton.textContent = boton.dataset.ocupado;
    });
  });

  const form = document.querySelector("form.asistente");
  if (form) asistente(form);
});

function asistente(form) {
  const pasos = [...form.querySelectorAll(".paso")];
  const indicador = [...document.querySelectorAll(".pasos-indicador li")];
  const anterior = form.querySelector("[data-anterior]");
  const siguiente = form.querySelector("[data-siguiente]");
  const csrf = form.querySelector("input[name=csrf]").value;
  let actual = 0;
  let sondeo = null;

  // Si el servidor marcó errores, abrir el primer paso que tenga uno
  const conError = pasos.findIndex((p) => p.querySelector(".con-error"));
  if (conError >= 0) actual = conError;

  function mostrar(i) {
    actual = Math.max(0, Math.min(i, pasos.length - 1));
    pasos.forEach((p, n) => (p.hidden = n !== actual));
    indicador.forEach((li, n) => {
      li.classList.toggle("hecho", n < actual);
      li.classList.toggle("actual", n === actual);
    });
    anterior.style.visibility = actual === 0 ? "hidden" : "visible";
    siguiente.hidden = actual === pasos.length - 1;
    const webhook = pasos[actual].querySelector("[data-webhook-estado]");
    if (webhook) vigilarWebhook(webhook); else detenerSondeo();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  anterior.addEventListener("click", () => mostrar(actual - 1));
  siguiente.addEventListener("click", () => {
    const invalidos = [...pasos[actual].querySelectorAll("input, textarea")].filter((c) => !c.checkValidity());
    pasos[actual].querySelectorAll(".error-campo.js-error").forEach((e) => e.remove());
    if (invalidos.length) {
      invalidos.forEach((c) => {
        const caja = c.closest(".campo");
        caja?.classList.add("con-error");
        const aviso = document.createElement("p");
        aviso.className = "error-campo js-error";
        aviso.textContent = c.validity.valueMissing ? "Este dato hace falta para seguir." : "Revisa este dato.";
        c.after(aviso);
        c.addEventListener("input", () => { caja?.classList.remove("con-error"); aviso.remove(); }, { once: true });
      });
      invalidos[0].scrollIntoView({ block: "center", behavior: "smooth" });
      invalidos[0].focus({ preventScroll: true });
      return;
    }
    mostrar(actual + 1);
  });

  // Probar llaves en vivo (no guarda nada)
  form.querySelectorAll("[data-probar-boton]").forEach((boton) => {
    boton.addEventListener("click", async () => {
      const que = boton.dataset.probarBoton;
      const caja = form.querySelector(`[data-resultado="${que}"]`);
      const datos = {};
      ["anthropic_key", "meta_app_id", "meta_app_secret", "phone_number_id", "whatsapp_token"].forEach((n) => {
        const c = form.elements[n];
        if (c) datos[n] = c.value.trim();
      });
      const texto = boton.textContent;
      boton.disabled = true;
      boton.textContent = "Probando…";
      try {
        const r = await fetch(form.dataset.probar.replace("QUE", que), {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF": csrf },
          body: JSON.stringify(datos),
        });
        const chequeos = await r.json();
        caja.replaceChildren(listaChequeos(Array.isArray(chequeos) ? chequeos : [{ estado: "falla", titulo: "No se pudo probar", detalle: chequeos.error || "Vuelve a cargar la página." }]));
      } catch {
        caja.replaceChildren(listaChequeos([{ estado: "atencion", titulo: "Sin conexión", detalle: "Revisa tu internet y vuelve a probar." }]));
      } finally {
        boton.disabled = false;
        boton.textContent = texto;
      }
    });
  });

  function listaChequeos(chequeos) {
    const iconos = { ok: "✓", atencion: "!", falla: "×", pendiente: "…" };
    const ul = document.createElement("ul");
    ul.className = "chequeos";
    chequeos.forEach((ch) => {
      const li = document.createElement("li");
      li.className = ch.estado;
      const icono = document.createElement("span");
      icono.className = "icono";
      icono.setAttribute("aria-hidden", "true");
      icono.textContent = iconos[ch.estado] || "…";
      const cuerpo = document.createElement("div");
      const titulo = document.createElement("strong");
      titulo.textContent = ch.titulo;
      const detalle = document.createElement("p");
      detalle.textContent = ch.detalle;
      cuerpo.append(titulo, detalle);
      li.append(icono, cuerpo);
      ul.append(li);
    });
    return ul;
  }

  // Estado del webhook: pregunta cada 4 segundos mientras el paso está a la vista
  function vigilarWebhook(caja) {
    if (sondeo) return;
    const revisar = async () => {
      try {
        const r = await fetch(form.dataset.webhook, { headers: { Accept: "application/json" } });
        const estado = await r.json();
        const [punto, texto] = caja.children;
        punto.className = "punto " + (estado.conectado ? "ok" : "pendiente");
        texto.textContent = estado.conectado ? "Conectado. " + estado.detalle : estado.detalle || "Esperando a Meta…";
        if (estado.conectado) detenerSondeo();
      } catch { /* se reintenta en el siguiente ciclo */ }
    };
    revisar();
    sondeo = setInterval(revisar, 4000);
  }

  function detenerSondeo() {
    clearInterval(sondeo);
    sondeo = null;
  }

  mostrar(actual);
}
