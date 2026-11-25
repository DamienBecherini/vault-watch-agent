// @ts-check
/* vault-watch: what a run sets for its own steps (an engine, a model, an effort, for that run alone), shown as lines
   and cards with their fields to change them, and what an action costs with the engine of its step. */

import { dollars, esc, tip } from "./util.js";
import { api, info, onSubscription } from "./api.js";
import { lang, T } from "./texts.js";
import { modelName } from "./settings.js";

// A check's estimate as the interface will start it: in another language than English, its leads are explained in
// it, which the model writes on top (verify.EXPLAIN_SHARE)
export const est = (o, key) => lang !== "en" && o[`${key}_explained`] != null ? o[`${key}_explained`] : o[key];
// What an action costs: the estimate (Claude API prices) on the API only; nothing on a subscription or a local model;
// another provider's prices are its own.
export const cost = usd => onSubscription() ? T.subscription : info?.billing === "none" ? T.local
  : info?.engine && info.engine !== "api" ? T.provider : usd;

// --- What a run sets for its own steps: an engine, a model, an effort, for that run alone -----------------------
// The Settings give each step its engine, model and effort; a page that starts a run shows them and lets the reader
// change them for that run only (config.run_steps on the server). Forgotten when another screen is opened.
export const OWN = {};      // {step: {engine, model, effort}}
export let STEPS = null;    // how each step would run now, with OWN laid over the Settings (/api/steps)
export const MODE_STEP = { fix: "fix", translation: "fix-translation", compact: "compact", add: "add" };  // the step that proposes, per kind of run
export const stepsQuery = () => Object.keys(OWN).length ? `?steps=${encodeURIComponent(JSON.stringify(OWN))}` : "";
export const loadSteps = async () => { STEPS = await api(`/api/steps${stepsQuery()}`); };
export const stepNow = step => STEPS?.steps.find(s => s.step === step);
export const ownFor = steps => Object.fromEntries(Object.entries(OWN).filter(([step]) => steps.includes(step)));
// What an action costs with the engine of its step: its estimate on the Claude API only
export const costOf = (step, usd) => {
  const s = stepNow(step);
  return !s ? cost(usd) : s.billing === "subscription" ? T.subscription : s.billing === "none" ? T.local : s.engine !== "api" ? T.provider : usd;
};
// The same as HTML: on a subscription, what the estimate is worth at list price, struck through, beside it
export const costHtml = (step, usd) => {
  const said = costOf(step, usd);
  return said === T.subscription && /\d/.test(usd || "")  // on a subscription (the step's, or the engine's when steps are not loaded)
    ? `<s class="worth" title="${esc(T.verif.listPriceTip)}">${esc(usd)}</s> ${esc(said)}` : esc(said);
};
export const billedStep = step => costOf(step, "$") === "$";
// How a step is paid, in the page's language: its chip's class and word
const payOf = s => s.billing === "subscription" ? ["free", T.perStep.chipSubscription] : s.billing === "none" ? ["free", T.perStep.chipLocal]
  : s.engine !== "api" ? ["", T.perStep.chipProvider] : ["bill", T.perStep.chipBilled];
// The engine's name without its English parenthesis (« Claude Code (subscription) »): how it is paid is said apart
const engineName = s => s.engine_label.replace(/\s*\([^)]*\)$/, "");
// One line per step: what runs it, and the fields to change it for this run
export function stepLine(step, name = "") {
  const s = stepNow(step);
  if (!s) return "";
  return `<div class="step-line small" data-step-line="${step}">
    <span class="muted">${name ? `${esc(name)}${T.colon}` : ""}${esc(engineName(s))} · ${esc(s.model ? modelName(s.model) : "?")} · ${T.perStep.effort(s.effort)} · ${payOf(s)[1]}</span>
    ${OWN[step] ? `<span class="badge attention">${T.perStep.once}</span>` : ""}
    ${STEPS.forced ? "" : `<button type="button" class="small-button" data-step-edit="${step}" data-closed="${OWN[step] ? T.perStep.edit : T.perStep.change}">${OWN[step] ? T.perStep.edit : T.perStep.change}</button>`}
    ${OWN[step] && !STEPS.forced ? `<button type="button" class="small-button" data-step-reset="${step}">${T.perStep.reset}</button>` : ""}
    <span class="step-fields" data-step-fields="${step}" hidden>
      <select data-f="engine" aria-label="${T.perStep.engine}">${STEPS.engines.map(e => `<option value="${esc(e.name)}"${e.name === s.engine ? " selected" : ""}>${esc(T.perStep.engineNames[e.name] || e.label)}</option>`).join("")}</select>
      <input type="text" data-f="model" list="models-${step}" value="${esc(s.model)}" placeholder="${esc(T.perStep.modelOfRole)}" aria-label="${T.perStep.model}" spellcheck="false">
      <datalist id="models-${step}"></datalist>
      <select data-f="effort" aria-label="${T.perStep.effortLabel}">${STEPS.efforts.map(e => `<option value="${e}"${e === s.effort ? " selected" : ""}>${T.perStep.effort(e)}</option>`).join("")}</select>
      <button type="button" class="small-button" data-step-ok="${step}">${T.perStep.apply}</button>
    </span></div>`;
}
// One card per step of a run (the bar of a check): its number and name, what it does (on a phone, in a « ? »), what
// runs it as chips, and the same fields as stepLine to change it for this run (bindSteps)
export function stepCard(step, n, name, what = "") {
  const s = stepNow(step);
  if (!s) return "";
  const pay = payOf(s);
  return `<div class="step-card${OWN[step] ? " changed" : ""}" data-step-line="${step}">
    <div class="step-head"><b>${n} · ${esc(name)}</b>${what ? `<span class="narrow-only">${tip(what)}</span>` : ""}
      ${STEPS.forced ? "" : `<button type="button" class="small-button" data-step-edit="${step}" data-closed="${OWN[step] ? T.perStep.edit : T.perStep.changeShort}">${OWN[step] ? T.perStep.edit : T.perStep.changeShort}</button>`}</div>
    ${what ? `<div class="step-what wide-only">${esc(what)}</div>` : ""}
    <div class="chips"><span class="chip">${esc(engineName(s))}</span><span class="chip">${esc(s.model ? modelName(s.model) : "?")}</span><span class="chip">${T.perStep.effort(s.effort)}</span><span class="chip ${pay[0]}">${pay[1]}</span></div>
    ${OWN[step] ? `<div class="step-once">${T.perStep.once}${STEPS.forced ? "" : ` · <button type="button" class="link-button" data-step-reset="${step}">${T.perStep.reset}</button>`}</div>` : ""}
    <span class="step-fields" data-step-fields="${step}" hidden>
      <select data-f="engine" aria-label="${T.perStep.engine}">${STEPS.engines.map(e => `<option value="${esc(e.name)}"${e.name === s.engine ? " selected" : ""}>${esc(T.perStep.engineNames[e.name] || e.label)}</option>`).join("")}</select>
      <input type="text" data-f="model" list="models-${step}" value="${esc(s.model)}" placeholder="${esc(T.perStep.modelOfRole)}" aria-label="${T.perStep.model}" spellcheck="false">
      <datalist id="models-${step}"></datalist>
      <select data-f="effort" aria-label="${T.perStep.effortLabel}">${STEPS.efforts.map(e => `<option value="${e}"${e === s.effort ? " selected" : ""}>${T.perStep.effort(e)}</option>`).join("")}</select>
      <button type="button" class="small-button primary" data-step-ok="${step}">${T.perStep.applyOnce}</button>
    </span></div>`;
}
// The buttons of the lines above, inside `root`; `redraw` draws the screen again once a choice is made
export function bindSteps(root, redraw) {
  const fields = step => root.querySelector(`[data-step-fields="${step}"]`);
  const models = async step => {  // the models the chosen engine offers, as suggestions: any id can be typed
    const f = fields(step), engine = f.querySelector("[data-f=engine]").value;
    const claude = engine === "api" || engine === "claude-code";
    const r = await api(`/api/models${claude ? "" : `?engine=${encodeURIComponent(engine)}`}`).catch(() => ({ models: [] }));
    f.querySelector("datalist").innerHTML = (r.models || []).map(m => `<option value="${esc(m.id)}">${esc(m.name || m.id)}</option>`).join("");
  };
  root.querySelectorAll("[data-step-edit]").forEach(b => b.onclick = () => {
    const f = fields(b.dataset.stepEdit);
    f.hidden = !f.hidden;
    b.textContent = f.hidden ? b.dataset.closed : T.perStep.cancel;  // the button says what it does now
    if (!f.hidden) models(b.dataset.stepEdit);
  });
  root.querySelectorAll("[data-step-fields]").forEach(f => f.querySelector("[data-f=engine]").onchange = () => {
    f.querySelector("[data-f=model]").value = "";  // another engine: its usual model, unless one is typed
    models(f.dataset.stepFields);
  });
  root.querySelectorAll("[data-step-ok]").forEach(b => b.onclick = async () => {
    const f = fields(b.dataset.stepOk), value = name => f.querySelector(`[data-f=${name}]`).value.trim();
    OWN[b.dataset.stepOk] = Object.fromEntries([["engine", value("engine")], ["model", value("model")], ["effort", value("effort")]].filter(([, v]) => v));
    await loadSteps();
    redraw();
  });
  root.querySelectorAll("[data-step-reset]").forEach(b => b.onclick = async () => {
    delete OWN[b.dataset.stepReset];
    await loadSteps();
    redraw();
  });
}
// What a check cost: billed, or what its calls on a subscription are worth at list price, struck through (nothing is
// billed); a check that calls no model is free
export const costTag = (cost, unbilled, free) => {
  const V = T.verif;
  const worth = unbilled > 0 ? `<span class="worth" title="${esc(V.listPriceTip)}"><s>${dollars(unbilled)}</s> <span class="sub-tag">${V.onSubscription}</span></span>` : "";
  if (cost > 0) return `${dollars(cost)}${worth ? ` + ${worth}` : ""}`;
  return worth || (free ? V.free : dollars(0));
};
