/* @ds-bundle: {"format":4,"namespace":"DienstPilot","components":[{"name":"ShiftChip"},{"name":"RosterCell"},{"name":"RosterGrid"},{"name":"Button"},{"name":"Field"},{"name":"Checkbox"},{"name":"Switch"},{"name":"Segmented"},{"name":"Suggestion"},{"name":"RuleMessage"},{"name":"EnvBadge"}]} */
(function () {
  "use strict";

  /* ---------- i18n: shift types and letters ---------- */
  var SHIFTS = {
    frueh:        { de: { l: "F", n: "Früh" },         en: { l: "E", n: "Early" } },
    spaet:        { de: { l: "S", n: "Spät" },         en: { l: "L", n: "Late" } },
    nacht:        { de: { l: "N", n: "Nacht" },        en: { l: "N", n: "Night" } },
    bereitschaft: { de: { l: "B", n: "Bereitschaft" }, en: { l: "O", n: "On-call" } },
    frei:         { de: { l: "U", n: "Urlaub" },       en: { l: "V", n: "Leave" } }
  };
  var ALIAS = { F: "frueh", E: "frueh", S: "spaet", L: "spaet", N: "nacht", B: "bereitschaft", O: "bereitschaft", U: "frei", V: "frei" };
  var T = {
    de: { granted: "Wunsch erfüllt", missed: "Wunsch nicht erfüllt", violation: "Regelverstoß", gap: "Lücke", gapOf: "Lücke: {s} unbesetzt", leave: "Urlaub",
          suggested: "Vorschlag", why: "Warum?", hideWhy: "Begründung ausblenden", accept: "Übernehmen", dismiss: "Verwerfen", env: "Demo-Umgebung, synthetische Daten",
          coverage: "Besetzung", staffed: "Vollständig besetzt", hours: "Std.", physician: "Ärztin / Arzt", aiNote: "Die KI schlägt nur vor. Entscheiden müssen Sie.", fix: "Korrektur ansehen",
          on: "An", off: "Aus", today: "heute", weekend: "Wochenende", cell: "{name}, {day}: {what}" },
    en: { granted: "Wish granted", missed: "Wish not granted", violation: "Rule violation", gap: "Gap", gapOf: "Gap: {s} unstaffed", leave: "Leave",
          suggested: "Suggestion", why: "Why?", hideWhy: "Hide reasoning", accept: "Accept", dismiss: "Dismiss", env: "Demo environment, synthetic data",
          coverage: "Coverage", staffed: "Fully staffed", hours: "hrs", physician: "Physician", aiNote: "The AI only proposes. You decide.", fix: "See correction",
          on: "On", off: "Off", today: "today", weekend: "weekend", cell: "{name}, {day}: {what}" }
  };
  function lang(l) { return l === "en" ? "en" : "de"; }
  function fmt(s, o) { return s.replace(/\{(\w+)\}/g, function (_, k) { return o[k] == null ? "" : o[k]; }); }
  function shiftKey(s) { if (!s) return null; return SHIFTS[s] ? s : (ALIAS[String(s).toUpperCase()] || null); }
  function shiftInfo(s, l) { var k = shiftKey(s); return k ? { key: k, letter: SHIFTS[k][lang(l)].l, name: SHIFTS[k][lang(l)].n } : null; }

  /* ---------- tiny DOM helper ---------- */
  var SVGNS = "http://www.w3.org/2000/svg";
  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.slice(0, 2) === "on" && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (var i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }
  function append(el, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { append(el, x); }); return; }
    el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  }
  /* ---------- Icons: Lucide (lucide-static 1.52.0, ISC), outline, 1.75px absolute stroke ----------
     Same names and geometry as lucide-react / lucide-react-native:
     <CircleAlert size={16} strokeWidth={1.75} absoluteStrokeWidth />. */
  var LUCIDE = {"check":[["path",{"d":"M20 6 9 17l-5-5"}]],"circle-slash-2":[["circle",{"cx":"12","cy":"12","r":"10"}],["path",{"d":"M22 2 2 22"}]],"circle-alert":[["circle",{"cx":"12","cy":"12","r":"10"}],["line",{"x1":"12","x2":"12","y1":"8","y2":"12"}],["line",{"x1":"12","x2":"12.01","y1":"16","y2":"16"}]],"pencil-line":[["path",{"d":"M13 21h8"}],["path",{"d":"m15 5 4 4"}],["path",{"d":"M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"}]],"circle-question-mark":[["circle",{"cx":"12","cy":"12","r":"10"}],["path",{"d":"M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"}],["path",{"d":"M12 17h.01"}]],"x":[["path",{"d":"M18 6 6 18"}],["path",{"d":"m6 6 12 12"}]],"chevron-down":[["path",{"d":"m6 9 6 6 6-6"}]],"flask-conical":[["path",{"d":"M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2"}],["path",{"d":"M6.453 15h11.094"}],["path",{"d":"M8.5 2h7"}]]};
  var STROKE = 1.75; // px on screen, at every size (absoluteStrokeWidth)
  function icon(name, size, extraClass) {
    var node = LUCIDE[name];
    if (!node) throw new Error("DienstPilot: icon not in the set: " + name);
    size = size || 16;
    var s = document.createElementNS(SVGNS, "svg");
    var a = { xmlns: SVGNS, width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      "stroke-width": String(Math.round(STROKE * 24 / size * 1000) / 1000), "stroke-linecap": "round", "stroke-linejoin": "round",
      "class": "lucide lucide-" + name + " dp-icon" + (extraClass ? " " + extraClass : ""), "aria-hidden": "true", focusable: "false" };
    for (var k in a) s.setAttribute(k, a[k]);
    node.forEach(function (n) { var e = document.createElementNS(SVGNS, n[0]); for (var k in n[1]) e.setAttribute(k, n[1][k]); s.appendChild(e); });
    return s;
  }
  var uid = 0; function nextId(p) { uid += 1; return (p || "dp") + "-" + uid; }

  /* ---------- ShiftChip ---------- */
  function ShiftChip(o) {
    o = o || {};
    var s = shiftInfo(o.shift || o.type, o.lang);
    if (!s) throw new Error("ShiftChip: unknown shift " + (o.shift || o.type));
    var size = o.size === "lg" ? " dp-chip--lg" : o.size === "sm" ? " dp-chip--sm" : "";
    var chip = h("span", { class: "dp-chip dp-shift--" + s.key + size, role: o.label || o.time ? null : "img", "aria-label": o.label || o.time ? null : s.name, title: s.name },
      s.key === "frei" ? h("span", { "aria-hidden": "true", text: s.letter }) : h("span", { "aria-hidden": "true", text: s.letter }));
    if (!o.label && !o.time) return chip;
    return h("span", { class: "dp-chiplabel dp-root" }, chip,
      h("span", { class: "dp-chiplabel-text" },
        h("span", { class: "label", text: o.label === true ? s.name : (o.label || s.name) }),
        o.time ? h("span", { class: "num-small", style: "color:var(--ink-muted)", text: o.time }) : null));
  }

  /* ---------- RosterCell ---------- */
  // states: shift, wish ("granted"|"missed"), violation (bool|string), gap (shift key it lacks), leave (bool), suggested (bool), selected
  function cellLabel(o, l) {
    var t = T[l], parts = [];
    var s = shiftInfo(o.shift, l);
    if (o.leave) parts.push(t.leave);
    else if (o.gap) parts.push(fmt(t.gapOf, { s: (shiftInfo(o.gap, l) || {}).name || "" }));
    else if (s) parts.push((o.suggested ? t.suggested + ": " : "") + s.name);
    else parts.push("–");
    if (o.wish === "granted") parts.push(t.granted);
    if (o.wish === "missed") parts.push(t.missed);
    if (o.violation) parts.push(t.violation + (typeof o.violation === "string" ? ": " + o.violation : ""));
    return parts.join(", ");
  }
  function RosterCell(o) {
    o = o || {};
    var l = lang(o.lang);
    var s = o.leave ? shiftInfo("frei", l) : o.gap ? shiftInfo(o.gap, l) : shiftInfo(o.shift, l);
    var cls = ["dp-cell"];
    if (s && !o.gap && !o.leave && !o.suggested) cls.push("has-shift");
    if (s) cls.push("dp-shift--" + s.key);
    if (o.leave) cls.push("is-leave");
    if (o.gap) cls.push("is-gap");
    if (o.suggested) cls.push("is-suggested");
    if (o.violation) cls.push("is-violation");
    if (o.selected) cls.push("is-selected");
    var label = cellLabel(o, l);
    var el = h("div", { class: cls.join(" "), role: o.interactive ? "button" : null, tabindex: o.interactive ? "0" : null, title: label, "aria-label": label },
      s ? h("span", { class: "dp-letter grid-letter", "aria-hidden": "true", text: s.letter }) : null,
      o.wish === "granted" ? h("span", { class: "dp-mark dp-mark--granted", "aria-hidden": "true" }, icon("check", 12)) : null,
      o.wish === "missed" ? h("span", { class: "dp-mark dp-mark--missed", "aria-hidden": "true" }, icon("circle-slash-2", 12)) : null,
      o.violation ? h("span", { class: "dp-bang", "aria-hidden": "true" }, icon("circle-alert", 14)) : null);
    if (o.onClick) el.addEventListener("click", o.onClick);
    return el;
  }

  /* ---------- RosterGrid ---------- */
  // days: [{d: 14, wd: "Mo", weekend?, today?}], rows: [{name, role?, hours?, cells: [cellOpts|null]}], coverage?: [string | {gap: "S"} | null]
  function RosterGrid(o) {
    o = o || {};
    var l = lang(o.lang), t = T[l], days = o.days || [];
    var head = h("tr", null, h("th", { class: "dp-rowhead label", scope: "col", text: o.rowLabel || t.physician }),
      days.map(function (d) {
        return h("th", { scope: "col", class: [d.weekend ? "is-weekend" : "", d.today ? "is-today" : ""].join(" ").trim() || null, style: "width:var(--cell-w)", "aria-label": d.wd + " " + d.d + (d.today ? ", " + t.today : "") },
          h("span", { class: "dp-day num-small" }, h("span", { text: d.wd }), h("b", { text: String(d.d) })));
      }),
      h("th", { class: "dp-total num-small", scope: "col", text: t.hours }));
    var body = (o.rows || []).map(function (r) {
      return h("tr", null,
        h("th", { class: "dp-rowhead grid-name", scope: "row" }, r.name, r.role ? h("small", { text: r.role }) : null),
        days.map(function (d, i) {
          var c = (r.cells || [])[i];
          var opts = Object.assign({ lang: l, interactive: o.interactive }, typeof c === "string" ? { shift: c } : (c || {}));
          var td = h("td", { class: [d.weekend ? "is-weekend-col" : "", d.today ? "is-today-col" : ""].join(" ").trim() || null });
          td.appendChild(RosterCell(opts));
          return td;
        }),
        h("td", { class: "dp-total num-small", text: r.hours == null ? "" : String(r.hours) }));
    });
    var foot = o.coverage ? h("tfoot", null, h("tr", null,
      h("th", { class: "dp-rowhead label", scope: "row", text: t.coverage }),
      days.map(function (d, i) {
        var c = o.coverage[i];
        var td = h("td", { class: d.weekend ? "is-weekend-col" : null });
        if (c && typeof c === "object" && c.gap) td.appendChild(RosterCell({ lang: l, gap: c.gap }));
        else if (c === "ok" || c === true) td.appendChild(h("div", { class: "dp-cell dp-cov", role: "img", "aria-label": t.staffed, title: t.staffed }, icon("check", 16)));
        else td.appendChild(h("div", { class: "dp-cell dp-cov num-small", text: c == null ? "" : String(c) }));
        return td;
      }),
      h("td", { class: "dp-total" }))) : null;
    var table = h("table", { class: "dp-grid", role: "grid", "aria-label": o.caption || null }, h("thead", null, head), h("tbody", null, body), foot);
    var sheet = h("div", { class: "dp-sheet dp-root" }, table);
    if (o.legend !== false) sheet.appendChild(Legend({ lang: l }));
    return sheet;
  }
  function Legend(o) {
    var l = lang(o && o.lang), t = T[l];
    function item(cell, text) { return h("span", { class: "dp-legend-item caption" }, RosterCell(Object.assign({ lang: l }, cell)), h("span", { text: text })); }
    return h("div", { class: "dp-legend", role: "note" },
      ["frueh", "spaet", "nacht", "bereitschaft"].map(function (k) { var s = shiftInfo(k, l); return item({ shift: k }, s.name); }),
      item({ leave: true }, t.leave),
      item({ shift: "frueh", wish: "granted" }, t.granted),
      item({ shift: "spaet", wish: "missed" }, t.missed),
      item({ shift: "frueh", violation: true }, t.violation),
      item({ gap: "spaet" }, t.gap),
      item({ shift: "spaet", suggested: true }, t.suggested));
  }

  /* ---------- Button ---------- */
  function Button(o) {
    o = o || {};
    var v = o.variant || "secondary";
    var cls = "dp-btn dp-btn--" + v + (o.size === "lg" ? " dp-btn--lg" : "") + (o.block ? " dp-btn--block" : "") + " " + (o.size === "lg" ? "body-strong" : "label");
    return h(o.href ? "a" : "button", { class: cls, type: o.href ? null : (o.type || "button"), href: o.href || null, disabled: o.disabled || null, "aria-expanded": o.expanded == null ? null : String(o.expanded), "aria-controls": o.controls || null, onClick: o.onClick },
      o.icon ? icon(o.icon, o.size === "lg" ? 20 : 16) : null, o.label != null ? h("span", { text: o.label }) : null);
  }

  /* ---------- Form controls ---------- */
  function Field(o) {
    o = o || {};
    var id = o.id || nextId("field"), hintId = id + "-hint", errId = id + "-err";
    var describedBy = [o.hint ? hintId : null, o.error ? errId : null].filter(Boolean).join(" ") || null;
    if (o.error && !o.fix && window.console) console.warn("DienstPilot.Field: every error needs `fix`, saying how to correct it.", o.label);
    var control;
    if (o.options) {
      control = h("select", { class: "dp-input", id: id, "aria-describedby": describedBy, "aria-invalid": o.error ? "true" : null },
        o.options.map(function (op) { var v = typeof op === "string" ? { value: op, label: op } : op; return h("option", { value: v.value, selected: v.value === o.value || null, text: v.label }); }));
    } else if (o.multiline) {
      control = h("textarea", { class: "dp-input", id: id, placeholder: o.placeholder || null, "aria-describedby": describedBy, "aria-invalid": o.error ? "true" : null });
      if (o.value) control.value = o.value;
    } else {
      control = h("input", { class: "dp-input" + (o.numeric ? " dp-tnum" : ""), id: id, type: o.type || "text", value: o.value || null, placeholder: o.placeholder || null, inputmode: o.numeric ? "numeric" : null, "aria-describedby": describedBy, "aria-invalid": o.error ? "true" : null });
    }
    if (o.options) control = h("span", { class: "dp-select" }, control, icon("chevron-down", 16, "dp-select-icon"));
    return h("div", { class: "dp-field" + (o.error ? " is-invalid" : "") },
      h("label", { class: "dp-field-label label", for: id, text: o.label }),
      control,
      o.hint ? h("span", { class: "dp-field-hint caption", id: hintId, text: o.hint }) : null,
      o.error ? h("span", { class: "dp-field-error caption", id: errId }, icon("circle-alert", 16),
        h("span", null, h("strong", { text: o.error }), o.fix ? [" ", o.fix] : null)) : null);
  }
  function Checkbox(o) {
    o = o || {};
    return h("label", { class: "dp-check" },
      h("input", { type: "checkbox", checked: o.checked || null, name: o.name || null, onChange: o.onChange }),
      h("span", { class: "dp-check-box", "aria-hidden": "true" }, icon("check", 16)),
      h("span", { class: "body" }, o.label, o.hint ? h("span", { class: "caption", style: "display:block;color:var(--ink-muted)", text: o.hint }) : null));
  }
  function Switch(o) {
    o = o || {};
    var l = lang(o.lang), t = T[l];
    var state = h("span", { class: "dp-switch-state caption", "aria-hidden": "true", text: o.checked ? t.on : t.off });
    var input = h("input", { type: "checkbox", role: "switch", checked: o.checked || null });
    input.addEventListener("change", function () { state.textContent = input.checked ? t.on : t.off; if (o.onChange) o.onChange(input.checked); });
    return h("label", { class: "dp-switch" }, h("span", { class: "body", text: o.label }), h("span", { style: "display:inline-flex;align-items:center;gap:var(--space-2)" }, state, input, h("span", { class: "dp-switch-track", "aria-hidden": "true" })));
  }
  function Segmented(o) {
    o = o || {};
    var name = o.name || nextId("seg");
    return h("div", { class: "dp-seg", role: "radiogroup", "aria-label": o.label || null },
      (o.options || []).map(function (op) {
        var v = typeof op === "string" ? { value: op, label: op } : op;
        return h("label", null, h("input", { type: "radio", name: name, value: v.value, checked: v.value === o.value || null, onChange: o.onChange ? function () { o.onChange(v.value); } : null }), h("span", { class: "label", text: v.label }));
      }));
  }

  /* ---------- Suggestion ---------- */
  // { lang, text, reasons: [{text, source?}], note?, accept?, dismiss?, inline?, open? }
  function Suggestion(o) {
    o = o || {};
    var l = lang(o.lang), t = T[l];
    var whyId = nextId("why");
    var whyPanel = h("div", { class: "dp-sugg-why", id: whyId, hidden: o.open ? null : true },
      h("ul", { class: "body" }, (o.reasons || []).map(function (r) {
        return h("li", null, r.text, r.source ? [" ", h("cite", { class: "caption", text: "(" + r.source + ")" })] : null);
      })),
      h("span", { class: "dp-sugg-note caption", text: o.note || t.aiNote }));
    var whyBtn = Button({ variant: "quiet", icon: "circle-question-mark", label: o.open ? t.hideWhy : t.why, expanded: !!o.open, controls: whyId });
    whyBtn.classList.add("dp-sugg-why-btn");
    whyBtn.addEventListener("click", function () {
      var open = whyPanel.hasAttribute("hidden");
      if (open) whyPanel.removeAttribute("hidden"); else whyPanel.setAttribute("hidden", "");
      whyBtn.setAttribute("aria-expanded", String(open));
      whyBtn.querySelector("span:last-child").textContent = open ? t.hideWhy : t.why;
    });
    var tag = h("span", { class: "dp-sugg-tag label" }, icon("pencil-line", 16), h("span", { text: t.suggested }));
    if (o.inline) {
      var dismissBtn = Button({ variant: "quiet", icon: "x" }); dismissBtn.classList.add("dp-iconbtn"); dismissBtn.setAttribute("aria-label", t.dismiss);
      var whyInline = Button({ variant: "link", icon: "circle-question-mark", label: t.why });
      if (o.onWhy) whyInline.addEventListener("click", o.onWhy);
      return h("span", { class: "dp-sugg dp-sugg--inline dp-root", role: "group", "aria-label": t.suggested }, h("span", { class: "label", text: o.text }), whyInline, dismissBtn);
    }
    return h("section", { class: "dp-sugg dp-root", "aria-label": t.suggested },
      tag,
      h("p", { class: "dp-sugg-body body" }, o.text),
      h("div", { class: "dp-sugg-actions" },
        Button({ variant: "primary", label: o.accept || t.accept, onClick: o.onAccept }),
        Button({ variant: "quiet", label: o.dismiss || t.dismiss, onClick: o.onDismiss }),
        whyBtn),
      whyPanel);
  }

  /* ---------- RuleMessage (C2) ---------- */
  function RuleMessage(o) {
    o = o || {};
    var l = lang(o.lang), t = T[l];
    if (!o.detail && window.console) console.warn("DienstPilot.RuleMessage: every error needs `detail`, saying how to fix it.", o.title);
    return h("div", { class: "dp-rule dp-root", role: "alert" },
      h("span", { class: "dp-rule-icon", "aria-hidden": "true" }, icon("circle-alert", 20)),
      h("span", { class: "dp-rule-text" },
        h("strong", { class: "body-strong", text: o.title }),
        o.detail ? h("span", { class: "body", text: o.detail }) : null),
      o.fix !== false ? h("span", { class: "dp-rule-actions" }, Button({ variant: "secondary", label: o.fix || t.fix, onClick: o.onFix })) : null);
  }

  /* ---------- EnvBadge ---------- */
  function EnvBadge(o) {
    o = o || {};
    var l = lang(o.lang);
    return h(o.bar ? "div" : "span", { class: "dp-env caption" + (o.bar ? " dp-env--bar" : ""), role: "status" },
      icon("flask-conical", 16), h("span", { text: T[l].env }));
  }

  var api = { ShiftChip: ShiftChip, RosterCell: RosterCell, RosterGrid: RosterGrid, Legend: Legend, Button: Button, Field: Field, Checkbox: Checkbox, Switch: Switch,
    Segmented: Segmented, Suggestion: Suggestion, RuleMessage: RuleMessage, EnvBadge: EnvBadge, icon: icon, ICONS: Object.keys(LUCIDE), shiftInfo: shiftInfo, SHIFTS: SHIFTS, strings: T };
  window.DienstPilot = Object.assign(window.DienstPilot || {}, api);
})();
