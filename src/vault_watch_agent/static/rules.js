// What may be ticked on the page of a check: the leads sent to a run, and among them those dug deeper.
// One rule: a lead dug deeper is always a lead ticked. Pure functions on {ticked, dug} (two Sets of lead lines), no
// page: app.js reads the boxes, applies one of these, then sets the boxes; tests/test_rules.py runs them with node.
const LeadRules = {
  // The state made consistent: a lead dug deeper and not ticked is no longer dug
  settle({ ticked, dug }) {
    return { ticked: new Set(ticked), dug: new Set([...dug].filter(lead => ticked.has(lead))) };
  },
  // A lead ticked or unticked: unticked, it is no longer dug deeper either
  tick({ ticked, dug }, lead, on) {
    const t = new Set(ticked), d = new Set(dug);
    if (on) t.add(lead); else { t.delete(lead); d.delete(lead); }
    return { ticked: t, dug: d };
  },
  // A lead dug deeper or not (its box on its line, or its button in its card): dug, it is ticked too
  dig({ ticked, dug }, lead, on) {
    const t = new Set(ticked), d = new Set(dug);
    if (on) { d.add(lead); t.add(lead); } else d.delete(lead);
    return { ticked: t, dug: d };
  },
  // Several leads ticked or unticked at once (a card, the whole page)
  tickAll(state, leads, on) {
    return leads.reduce((s, lead) => LeadRules.tick(s, lead, on), state);
  },
  // « Dig every lead ticked » or « dig nothing », over `leads` (a card, or the whole run): only a ticked lead is dug
  digTicked({ ticked, dug }, leads, on) {
    const d = new Set(dug);
    leads.forEach(lead => { if (on && ticked.has(lead)) d.add(lead); else d.delete(lead); });
    return { ticked: new Set(ticked), dug: d };
  },
};
if (typeof module !== "undefined") module.exports = LeadRules;  // node, for the tests
