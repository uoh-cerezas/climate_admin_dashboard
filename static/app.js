const esc = value => String(value ?? "—").replace(/[&<>\"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const input = (label, name, value, type = "text", attrs = "") =>
  `<label>${esc(label)}<input name="${esc(name)}" type="${type}" value="${esc(value)}" ${attrs}></label>`;

const update = payload => fetch("api/config", {
  method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(payload)
}).then(response => response.json().then(body => {
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}));

const renderEditable = data => {
  const email = data.email.editable;
  const emailForm = document.getElementById("email-form");
  emailForm.innerHTML = `<label><input name="enabled" type="checkbox" ${email.enabled ? "checked" : ""}> Envío habilitado</label>` +
    input("Hora de envío", "send_hour", email.send_hour, "number", "min=0 max=23") +
    input("Minutos", "send_minute", email.send_minute, "number", "min=0 max=59") +
    `<button type="submit">Guardar correo</button>`;
  emailForm.addEventListener("submit", event => {
    event.preventDefault();
    const values = new FormData(emailForm);
    update({ email: {
      enabled: values.get("enabled") === "on",
      send_hour: Number(values.get("send_hour")), send_minute: Number(values.get("send_minute"))
    } }).then(() => window.location.reload()).catch(error => alert(error.message));
  });

  document.getElementById("sites").innerHTML = Object.entries(data.email.sites || {}).map(([site, info]) =>
    `<label class="site"><strong>${esc(site)}</strong><span class="site-toggle"><input name="enabled" data-site="${esc(site)}" type="checkbox" ${info.enabled ? "checked" : ""}> Enviar correo</span><span>Para</span><input name="to" data-site="${esc(site)}" value="${esc(info.to === "—" ? "" : info.to)}" placeholder="correo1@dominio.cl; correo2@dominio.cl" ${info.enabled ? "" : "disabled"}></label>`
  ).join("") || "<span>No hay campos configurados.</span>";
  if (Object.keys(data.email.sites || {}).length) {
    const globalCc = document.createElement("label");
    globalCc.className = "global-cc";
    globalCc.innerHTML = `CC global (igual para todos los campos)<input id="global-cc" value="${esc(data.email.global_cc || "")}" placeholder="correo1@dominio.cl; correo2@dominio.cl">`;
    document.getElementById("sites").prepend(globalCc);
    const save = document.createElement("button"); save.textContent = "Guardar destinatarios"; save.type = "button"; save.className = "save-sites";
    document.querySelectorAll("#sites input[name=enabled]").forEach(toggle => toggle.addEventListener("change", event => {
      const recipient = document.querySelector(`#sites input[name=to][data-site="${CSS.escape(event.target.dataset.site)}"]`);
      if (recipient) recipient.disabled = !event.target.checked;
    }));
    save.addEventListener("click", () => {
      const sites = {};
      document.querySelectorAll("#sites input[name=to][data-site]").forEach(field => { sites[field.dataset.site] ||= {}; sites[field.dataset.site].to = field.value; });
      document.querySelectorAll("#sites input[name=enabled]").forEach(field => { sites[field.dataset.site].enabled = field.checked; });
      update({ sites, global_cc: document.getElementById("global-cc").value }).then(() => window.location.reload()).catch(error => alert(error.message));
    });
    document.getElementById("sites").append(save);
  }
};

const renderSchedule = data => {
  const schedule = document.getElementById("schedule");
  const start = data.pipeline.schedule["Inicio del período"];
  schedule.innerHTML = `<div class="read-row"><span>Inicio del período</span><strong>${esc(start)}</strong></div>` +
    `<form id="schedule-end-form" class="end-date-form"><label>Fin del período<input name="end" type="date" value="${esc(data.pipeline.schedule_editable.end)}" required></label><p class="hint">El período debe finalizar el día 2 del mes (por ejemplo, 2 de agosto o 2 de septiembre).</p><button type="submit">Guardar fecha final</button></form>`;
  const form = document.getElementById("schedule-end-form");
  form.addEventListener("submit", event => {
    event.preventDefault();
    update({ schedule: { end: new FormData(form).get("end") } }).then(() => window.location.reload()).catch(error => alert(error.message));
  });
};

fetch("api/config", { headers: { Accept: "application/json" } })
  .then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
  .then(data => {
    const validation = document.getElementById("validation");
    const errors = data.validation?.errors || [];
    const warnings = data.validation?.warnings || [];
    validation.classList.toggle("invalid", errors.length > 0);
    validation.textContent = errors.length ? `Configuración inválida: ${errors.join(" · ")}` :
      (warnings.length ? `Configuración válida con advertencias: ${warnings.join(" · ")}` : "Configuración válida");
    renderSchedule(data);
    renderEditable(data);
  })
  .catch(error => {
    const node = document.getElementById("validation");
    node.classList.add("invalid"); node.textContent = `No se pudo leer la configuración: ${error.message}`;
  });

