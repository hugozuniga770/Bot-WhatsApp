// Coexistencia (v3.4.2): abre el registro de Meta para el WhatsApp Business del negocio.
// Documentación de Meta, «Onboarding WhatsApp Business app users» (09/11/2026):
// FB.login con featureType "whatsapp_business_app_onboarding" y sessionInfoVersion "3".
//
// El código que devuelve FB.login vence en segundos, así que se manda al bot apenas llega
// (esperando como mucho 3 s el aviso de Meta con el id de la cuenta de WhatsApp). Si ese aviso
// no llega, el bot busca la cuenta con el token (C-22). Todo lo que avisa Meta se muestra en
// pantalla para poder ver qué pasó.
(() => {
  const caja = document.getElementById("coexistencia");
  if (!caja) return;
  const boton = document.getElementById("boton-coexistencia");
  const estado = document.getElementById("estado-coexistencia");
  const lista = document.getElementById("pasos-coexistencia");
  const { appId, configId, version, finalizar, csrf } = caja.dataset;
  let codigo = null;
  let sesion = null;
  let enviado = false;
  let espera = null;
  const eventos = [];

  const decir = (texto) => { estado.textContent = texto; };

  function mostrarPasos(pasos) {
    lista.replaceChildren(...(pasos || []).map((p) => {
      const li = document.createElement("li");
      li.className = p.estado;
      const icono = document.createElement("span");
      icono.className = "icono";
      icono.setAttribute("aria-hidden", "true");
      icono.textContent = p.estado === "ok" ? "✓" : p.estado === "falla" ? "×" : "!";
      const div = document.createElement("div");
      const titulo = document.createElement("strong");
      titulo.textContent = p.titulo;
      const detalle = document.createElement("p");
      detalle.textContent = p.detalle;
      div.append(titulo, detalle);
      li.append(icono, div);
      return li;
    }));
  }

  async function enviar() {
    if (enviado || !codigo) return;
    enviado = true;
    clearTimeout(espera);
    decir("Conectando con el bot… no cierres esta página.");
    try {
      const r = await fetch(finalizar, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF": csrf, Accept: "application/json" },
        body: JSON.stringify({ code: codigo, waba_id: (sesion && sesion.waba_id) || "",
                               phone_number_id: (sesion && sesion.phone_number_id) || "", eventos }),
      });
      const datos = await r.json();
      decir(datos.mensaje || "Listo.");
      mostrarPasos(datos.pasos);
      if (datos.ok) setTimeout(() => location.reload(), 5000);
      else boton.disabled = false;
    } catch {
      decir("No se pudo avisar al bot. Recarga la página y mira la Actividad.");
      boton.disabled = false;
    }
  }

  window.addEventListener("message", (evento) => {
    let origen;
    try { origen = new URL(evento.origin).hostname; } catch { return; }
    if (origen !== "facebook.com" && !origen.endsWith(".facebook.com")) return;
    let datos;
    try { datos = typeof evento.data === "string" ? JSON.parse(evento.data) : evento.data; } catch { return; }
    if (!datos || datos.type !== "WA_EMBEDDED_SIGNUP") return;
    const nombre = String(datos.event || "sin nombre");
    const d = datos.data || {};
    // Meta avisa los errores como CANCEL con error_message (documentación de implementación, 09/11/2026)
    const detalle = d.error_message ? `${d.error_code || ""} ${d.error_message}`.trim() : (d.current_step || "");
    eventos.push(nombre + (detalle ? ` (${String(detalle).slice(0, 120)})` : ""));
    if (nombre.startsWith("FINISH")) {
      sesion = d;
      if (codigo) enviar();
    } else if (nombre === "CANCEL" && d.error_message) {
      decir("Meta mostró un error: " + d.error_message + ". No se cambió nada.");
    } else if (nombre === "CANCEL") {
      decir("Se cerró el registro de Meta antes de terminar" + (d.current_step ? ` (paso: ${d.current_step})` : "") + ". No se cambió nada.");
    } else if (nombre === "ERROR") {
      decir("Meta mostró un error: " + (datos.data?.error_message || "sin detalle") + ". No se cambió nada.");
    }
  });

  function cargarSdk() {
    return new Promise((listo, error) => {
      if (window.FB) return listo();
      window.fbAsyncInit = () => {
        window.FB.init({ appId, autoLogAppEvents: true, xfbml: false, version });
        listo();
      };
      const s = document.createElement("script");
      s.src = "https://connect.facebook.net/es_LA/sdk.js";
      s.async = true;
      s.crossOrigin = "anonymous";
      s.onerror = () => error(new Error("sdk"));
      document.head.appendChild(s);
    });
  }

  // El SDK se carga al abrir la página: así la ventana de Meta se abre en el mismo toque y
  // Chrome no la bloquea como ventana emergente (v3.4.2, C-23).
  let sdkListo = false;
  if (appId && configId) {
    cargarSdk().then(() => { sdkListo = true; }).catch(() => decir("No se pudo cargar el registro de Meta. Revisa la conexión y recarga la página."));
  }

  boton.addEventListener("click", () => {
    if (!appId || !configId) return;
    if (!sdkListo || !window.FB) {
      decir("Todavía se está cargando el registro de Meta. Espera unos segundos y vuelve a tocar.");
      return;
    }
    boton.disabled = true;
    codigo = null; sesion = null; enviado = false; eventos.length = 0;
    lista.replaceChildren();
    decir("Se abrió la ventana de Meta. Si no la ves, búscala detrás de esta (Alt+Tab).");
    window.FB.login((respuesta) => {
      if (respuesta.authResponse && respuesta.authResponse.code) {
        codigo = respuesta.authResponse.code;
        if (sesion) enviar();
        else {
          decir(eventos.length ? "Meta terminó. Conectando…" :
                "Meta devolvió el código sin mostrar el registro. Igual se intenta conectar…");
          espera = setTimeout(enviar, 3000);  // no se espera más: el código vence a los 30 s
        }
      } else {
        decir("Se cerró el registro de Meta sin terminar" + (eventos.length ? ` (Meta avisó: ${eventos.join(", ")})` : "") + ". No se cambió nada.");
        boton.disabled = false;
      }
    }, {
      config_id: configId,
      response_type: "code",
      override_default_response_type: true,
      extras: { setup: {}, featureType: "whatsapp_business_app_onboarding", sessionInfoVersion: "3" },
    });
  });
})();
