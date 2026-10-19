// Interfaz de la demo. Toda la lógica vive en riskrag.js (motor) y credit.js (modelo ONNX).

import { RiskRag, CREDIT_TYPES, CATEGORIES, GUARANTEES, EXAMPLES, InputRejected } from "./riskrag.js";
import { CreditScorer } from "./credit.js";

const ORT_VERSION = "1.22.0";
const ORT_BASE = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;
const ORT_SRI = "sha384-epp8GDQUoLKx5qHa6SoDHKv7fSHILsEYk4uEsHdPRBztXEIVWCe/lhhrQJUBMZcf";

const $ = (sel) => document.querySelector(sel);
const out = $("#out");
let rag = null;
let scorer = null;
let scorerLoading = null;

const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ------------------------------------------------------------ Markdown mínimo (salida de los handlers) */

function inline(t) {
  return esc(t)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/(^|[\s(])_(.+?)_(?=[\s).,;:]|$)/g, "$1<em>$2</em>");
}

function markdown(md) {
  const html = [];
  let list = [];
  const flush = () => { if (list.length) { html.push(`<ul>${list.join("")}</ul>`); list = []; } };
  for (const line of md.split("\n")) {
    if (line.startsWith("- ")) list.push(`<li>${inline(line.slice(2))}</li>`);
    else if (line.startsWith("### ")) { flush(); html.push(`<h3>${inline(line.slice(4))}</h3>`); }
    else if (line.trim()) { flush(); html.push(`<p>${inline(line)}</p>`); }
    else flush();
  }
  flush();
  return `<div class="md">${html.join("")}</div>`;
}

/* ------------------------------------------------------------ Pestañas */

const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(tab, focus = false) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
  }
  if (focus) tab.focus();
  if (tab.id === "tab-score") ensureScorer();
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => selectTab(t));
  t.addEventListener("keydown", (e) => {
    const dir = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (dir) { e.preventDefault(); selectTab(tabs[(i + dir + tabs.length) % tabs.length], true); }
  });
});

/* ------------------------------------------------------------ Pregunta */

const FLAG_TEXT = {
  override_es: "intento de anular las instrucciones", override_en: "intento de anular las instrucciones",
  role_hijack: "intento de cambiar el rol del asistente", prompt_leak_es: "intento de revelar el prompt del sistema",
  prompt_leak_en: "intento de revelar el prompt del sistema", prompt_leak_rules: "intento de revelar las reglas internas",
  jailbreak: "intento de saltarse las restricciones", tool_abuse: "intento de forzar una herramienta",
  exfiltration: "intento de enviar datos a un destino externo", fake_system: "etiquetas falsas de sistema",
  data_dump: "pedido de volcar datos de personas",
};
function flagChip(flag) {
  const [kind, name] = flag.split(":");
  let text = flag, cls = "warn";
  if (kind === "injection") { text = FLAG_TEXT[name] || name; cls = "bad"; }
  else if (kind === "suspicious") text = `señal sospechosa: ${FLAG_TEXT[name] || name}`;
  else if (kind === "pii") text = `dato personal enmascarado (${name})`;
  else if (flag === "output:no_citations") text = "la respuesta no tenía citas válidas";
  else if (flag === "output:low_faithfulness") text = "la respuesta no tenía respaldo suficiente";
  return `<li class="chip ${cls}">${esc(text)}</li>`;
}

/** Oración citada resaltada dentro del fragmento fuente (mejor esfuerzo). */
function highlight(passage, answer) {
  const sentence = answer.split(new RegExp(`\\[${passage.key}\\]`))[0].split(/\[C\d+\]/).pop().trim();
  const body = passage.text.replaceAll("<", "‹").replaceAll(">", "›");
  const i = sentence ? body.indexOf(sentence) : -1;
  if (i < 0) return esc(body);
  return `${esc(body.slice(0, i))}<mark>${esc(sentence)}</mark>${esc(body.slice(i + sentence.length))}`;
}

function renderAnswer(question, result) {
  const a = result.answer;
  const blocked = result.intent === "bloqueado";
  const withCites = esc(a.answer).replace(/\[(C\d+)\]/g, (m, k) => `<button class="cite" type="button" data-src="${k}" aria-label="Ver fuente ${k.slice(1)}">${k.slice(1)}</button>`);
  const stateCls = blocked ? "state bad" : a.abstained ? "state" : "";
  const chips = [`<li class="chip">Intención <b>${esc(result.intent)}</b></li>`];
  if (result.tool) chips.push(`<li class="chip">Herramienta <code>${esc(result.tool)}</code></li>`);
  const deterministic = /clasificar_deudor|calcular_provision/.test(result.tool || "");
  chips.push(blocked
    ? `<li class="chip bad"><b>Bloqueada</b> antes de buscar</li>`
    : a.abstained ? `<li class="chip warn"><b>Se abstuvo</b></li>`
    : deterministic ? `<li class="chip ok"><b>Cálculo determinista</b></li>`
    : result.tool === "glosario" ? `<li class="chip ok"><b>Definición del glosario</b></li>`
    : `<li class="chip ok"><b>Con sustento</b></li>`);
  if (a.passages.length) chips.push(`<li class="chip">${a.passages.length} fuente${a.passages.length > 1 ? "s" : ""} citada${a.passages.length > 1 ? "s" : ""}</li>`);
  chips.push(...a.security_flags.map(flagChip));

  const sources = a.passages.length
    ? `<section class="sources"><h3>Fuentes citadas</h3><ol>${a.passages.map((p) => `
        <li class="src" id="src-${p.key}"><header><span><span class="k">${p.key.slice(1)}</span>${esc(p.label)}</span><span class="score">relevancia ${p.score.toFixed(2)}</span></header>
        <blockquote>${highlight(p, a.answer)}</blockquote></li>`).join("")}</ol></section>`
    : "";

  let extra = "";
  if (result.intent === "prediccion") {
    extra = `<div class="sec-note">Esta consulta pide una probabilidad de default. En esta página se calcula con el modelo ONNX.<br><button class="primary" type="button" id="go-score">Abrir el score de default</button></div>`;
  }
  out.innerHTML = `
    <p class="asked">Consulta: <q>${esc(a.question || question)}</q></p>
    <p class="answer-text ${stateCls}">${withCites}</p>
    <ul class="trace" aria-label="Cómo se resolvió">${chips.join("")}</ul>
    ${sources}${extra}`;
  const go = $("#go-score");
  if (go) go.addEventListener("click", () => selectTab($("#tab-score"), true));
}

out.addEventListener("click", (e) => {
  const btn = e.target.closest(".cite");
  if (!btn) return;
  const el = document.getElementById(`src-${btn.dataset.src}`);
  if (!el) return;
  el.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
  el.classList.remove("flash");
  void el.offsetWidth;
  el.classList.add("flash");
});

function showOutput(html) {
  out.innerHTML = html;
  if (matchMedia("(max-width: 900px)").matches) out.scrollIntoView({ block: "start" });
}

function ask(question) {
  if (!rag) return;
  if (!question.trim()) { showOutput(`<p class="empty-title">Escribe una pregunta o elige un caso.</p>`); return; }
  try {
    renderAnswer(question, rag.agentRun(question));
  } catch (err) {
    if (err instanceof InputRejected) {
      showOutput(`<p class="answer-text state bad">${esc(err.message)}</p>`);
    } else throw err;
  }
  if (matchMedia("(max-width: 900px)").matches) out.scrollIntoView({ block: "start" });
}

/* ------------------------------------------------------------ Formularios */

function fillSelect(sel, items) {
  sel.innerHTML = items.map((x) => `<option>${esc(x)}</option>`).join("");
}

function setupForms() {
  fillSelect($("#c-type"), Object.keys(CREDIT_TYPES));
  fillSelect($("#p-type"), Object.keys(CREDIT_TYPES));
  fillSelect($("#p-cat"), CATEGORIES);
  fillSelect($("#p-guar"), Object.keys(GUARANTEES));
  $("#c-type").value = "Consumo no revolvente";
  $("#p-type").value = "Microempresas";
  $("#p-cat").value = "Dudoso";

  const NONE = /### Categoría: None/;
  $("#form-classify").addEventListener("submit", (e) => {
    e.preventDefault();
    const md = rag.classify($("#c-type").value, $("#c-days").valueAsNumber)
      .replace(NONE, "### Sin categoría solo por atraso");
    showOutput(markdown(md));
  });
  $("#form-provision").addEventListener("submit", (e) => {
    e.preventDefault();
    const covered = $("#p-covered").value === "" ? null : $("#p-covered").valueAsNumber;
    showOutput(markdown(rag.provision($("#p-type").value, $("#p-cat").value, $("#p-amount").valueAsNumber, covered, $("#p-guar").value)));
  });
  $("#form-ask").addEventListener("submit", (e) => { e.preventDefault(); ask($("#q").value); });
  $("#q").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ask($("#q").value); }
  });

  const tags = { 4: "ataque de inyección", 5: "fuera del corpus" };
  $("#examples").innerHTML = EXAMPLES.map((q, i) =>
    `<li><button type="button" data-q="${esc(q)}">${esc(q)}${tags[i] ? `<span class="tag">${tags[i]}</span>` : ""}</button></li>`).join("");
  $("#examples").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-q]");
    if (!b) return;
    $("#q").value = b.dataset.q;
    ask(b.dataset.q);
  });
}

/* ------------------------------------------------------------ Score de default (ONNX) */

function loadScript(src, integrity) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src; s.integrity = integrity; s.crossOrigin = "anonymous";
    s.onload = resolve; s.onerror = () => reject(new Error("No se pudo cargar onnxruntime-web."));
    document.head.appendChild(s);
  });
}

const SAMPLE = {
  revolving_utilization_unsecured: 0.9, age: 35, number_of_time_30_59_days_past_due: 1, debt_ratio: 0.8,
  monthly_income: 3000, number_open_credit_lines: 6, number_of_times_90_days_late: 0,
  number_real_estate_loans: 0, number_of_time_60_89_days_past_due: 0, number_dependents: 3,
};

function buildScoreForm(meta) {
  $("#score-fields").innerHTML = meta.features.map((f) => {
    const attrs = [f.min !== null ? `min="${f.min}"` : "", f.max !== null ? `max="${f.max}"` : ""].join(" ");
    const val = SAMPLE[f.name] ?? f.median;
    return `<div><label for="f-${f.name}" title="${esc(f.description)}">${esc(f.label)}</label>
      <input id="f-${f.name}" name="${f.name}" type="number" inputmode="decimal" step="any" ${attrs} value="${val}" required></div>`;
  }).join("");
}

function ensureScorer() {
  if (scorer || scorerLoading) return scorerLoading;
  const state = $("#score-state"), btn = $("#btn-score");
  btn.disabled = true;
  state.textContent = "Descargando el motor ONNX (una sola vez)…";
  scorerLoading = (async () => {
    const [meta, modelBuf] = await Promise.all([
      fetch("models/credit_default.meta.json").then((r) => r.json()),
      fetch("models/credit_default.onnx").then((r) => r.arrayBuffer()),
    ]);
    buildScoreForm(meta);
    if (!window.ort) await loadScript(`${ORT_BASE}ort.wasm.min.js`, ORT_SRI);
    window.ort.env.wasm.wasmPaths = ORT_BASE;
    window.ort.env.wasm.numThreads = 1; // sin cabeceras de aislamiento en GitHub Pages
    scorer = await CreditScorer.load(window.ort, { model: new Uint8Array(modelBuf), meta });
    state.textContent = "Modelo listo.";
    btn.disabled = false;
  })().catch((err) => {
    scorerLoading = null;
    state.textContent = `${err.message} Revisa tu conexión e inténtalo de nuevo.`;
    btn.disabled = false;
  });
  return scorerLoading;
}

const pct = (x) => (x * 100).toFixed(1);
const BAND_TEXT = { bajo: "riesgo bajo", medio: "riesgo medio", alto: "riesgo alto" };

function renderScore(r) {
  const maxImpact = Math.max(...r.factors.map((f) => Math.abs(f.impact)), 0.001);
  const below = r.probability < r.threshold;
  const marker = Math.min(r.probability * 100, 100);
  out.innerHTML = `
    <p class="asked">Modelo XGBoost en ONNX, ejecutado en este navegador.</p>
    <div class="big"><span class="p">${pct(r.probability)}<small>%</small></span>
      <span class="chip ${r.risk_band === "bajo" ? "ok" : r.risk_band === "alto" ? "bad" : "warn"}"><b>${BAND_TEXT[r.risk_band]}</b></span></div>
    <p class="verdict">Probabilidad de incumplir en 2 años. ${below ? "Está por debajo" : "Supera"} el umbral de mínimo costo de ${pct(r.threshold)}%, así que la regla del modelo sería <strong>${r.decision}</strong>.</p>
    <div class="meter" role="img" aria-label="Posición de ${pct(r.probability)}% en la escala de riesgo"><i style="left:${marker}%"></i></div>
    <div class="meter-scale" aria-hidden="true"><span>0%</span><span>10%</span><span>30%</span><span>100%</span></div>
    <h2 class="mini">Qué empuja el resultado</h2>
    <ul class="factors">${r.factors.map((f) => {
      const w = (Math.abs(f.impact) / maxImpact) * 50;
      return `<li class="${f.impact > 0 ? "up" : "down"}"><span>${esc(f.label)}</span>
        <span class="bar"><b style="width:${w}%"></b></span>
        <span class="v">${f.impact > 0 ? "+" : "−"}${(Math.abs(f.impact) * 100).toFixed(1)} pts</span></li>`;
    }).join("")}</ul>
    <p class="fine" style="margin-top:1.25rem">Los puntos indican cuánto bajaría la probabilidad si esa variable tomara la mediana de entrenamiento. Es una aproximación por oclusión, no valores SHAP. Modelo de portafolio: no usar para decidir sobre personas reales.</p>`;
  if (matchMedia("(max-width: 900px)").matches) out.scrollIntoView({ block: "start" });
}

$("#form-score").addEventListener("submit", async (e) => {
  e.preventDefault();
  await ensureScorer();
  if (!scorer) return;
  const values = {};
  for (const f of scorer.features) values[f.name] = document.getElementById(`f-${f.name}`).valueAsNumber;
  const errors = scorer.validate(values);
  if (errors.length) { showOutput(`<p class="answer-text state bad">${errors.map(esc).join("<br>")}</p>`); return; }
  renderScore(await scorer.score(values));
});

/* ------------------------------------------------------------ Arranque */

function renderEval(ev) {
  if (!ev) return;
  const names = {
    recall_at_5: "Recall@5 de recuperación", mrr: "MRR", intent_accuracy: "Exactitud de intención",
    key_facts_coverage: "Cobertura de datos clave", citation_accuracy: "Exactitud de citas",
    abstention_accuracy: "Abstención correcta", faithfulness: "Fidelidad a la fuente",
    adversarial_containment: "Ataques contenidos",
  };
  const rows = Object.entries(ev.metrics).map(([k, v]) =>
    `<tr><td>${esc(names[k] || k)}</td><td>${v.toFixed(3)}</td><td>${ev.thresholds[k] !== undefined ? `mín. ${ev.thresholds[k]}` : ""}</td></tr>`).join("");
  const box = $("#eval");
  box.innerHTML = `<table><caption>Evaluación automática en cada cambio</caption><thead><tr><th scope="col">Métrica</th><th scope="col">Valor</th><th scope="col">Umbral</th></tr></thead><tbody>${rows}</tbody></table>`;
  box.hidden = false;
}

async function boot() {
  setupForms();
  try {
    const res = await fetch("data/kb.json");
    const kb = await res.json();
    rag = new RiskRag(kb);
    $("#load-state").textContent = `Índice listo: ${kb.meta.n_chunks} fragmentos, sin servidor.`;
    $("#btn-ask").disabled = false;
    renderEval(kb.meta.eval);
    $("#built").textContent = `Índice generado el ${kb.meta.built_at}.`;
  } catch (err) {
    $("#load-state").textContent = "No se pudo cargar el índice. Recarga la página.";
    console.error(err);
  }
}
boot();
