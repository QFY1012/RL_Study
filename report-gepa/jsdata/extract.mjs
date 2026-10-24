// Tables a story's JS carries inline: what its build bundled from the data files.
//
//   node extract.mjs <out_dir> <file.js>...
//
// Walks each file's syntax tree (acorn) and takes, outermost first:
//   objects  an array of at least MIN_ROWS object literals, columns the keys (a nested object one level as "field.key")
//   arrays   an array of at least MIN_ROWS arrays of one length, at least MIN_COLUMNS; the build dropped the header, columns are c0, c1...
//   columns  an object of at least MIN_COLUMNS arrays of one length, at least MIN_ROWS
//   text     a string of csv or tsv text (the build inlined the file as it was)
// A JSON.parse of a string literal is parsed and searched the same way. Only literals
// count: a row with a function, a variable or a computed key is not data.
// Each table goes to <out_dir>/<file>__<where>.csv (.tsv for tsv text), where is the
// variable and keys it sits under; stdout gets one json line per table.

import fs from "fs";
import path from "path";
import * as acorn from "acorn";
import * as walk from "acorn-walk";

const MIN_ROWS = 50;
const MIN_COLUMNS = 3;
const FAIL = Symbol("not a literal");

function value(n) {
  switch (n.type) {
    case "Literal":
      return n.regex ? FAIL : n.value;
    case "TemplateLiteral":
      return n.expressions.length ? FAIL : n.quasis[0].value.cooked;
    case "ArrayExpression": {
      const out = [];
      for (const e of n.elements) {
        const v = e === null ? null : value(e);
        if (v === FAIL) return FAIL;
        out.push(v);
      }
      return out;
    }
    case "ObjectExpression": {
      const out = {};
      for (const p of n.properties) {
        if (p.type !== "Property" || p.computed || p.kind !== "init" || p.method) return FAIL;
        const k = p.key.type === "Identifier" ? p.key.name : p.key.value;
        const v = value(p.value);
        if (v === FAIL) return FAIL;
        out[k] = v;
      }
      return out;
    }
    case "UnaryExpression": {
      if (n.operator === "void") return null;
      const v = value(n.argument);
      if (typeof v !== "number") return FAIL;
      return { "-": -v, "+": v, "!": !v }[n.operator] ?? FAIL;
    }
    case "Identifier":
      return { undefined: null, NaN: NaN, Infinity: Infinity }[n.name] ?? FAIL;
    default:
      return FAIL;
  }
}

const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

function flat(row) {
  const out = {};
  for (const [k, v] of Object.entries(row)) {
    if (isObject(v)) for (const [k2, v2] of Object.entries(v)) out[`${k}.${k2}`] = v2;
    else out[k] = v;
  }
  return out;
}

function table(v) {
  if (Array.isArray(v) && v.length >= MIN_ROWS) {
    if (v.every(isObject)) {
      const rows = v.map(flat);
      const header = [...new Set(rows.flatMap(Object.keys))];
      return header.length >= MIN_COLUMNS ? { kind: "objects", header, rows: rows.map((r) => header.map((k) => r[k])) } : null;
    }
    const n = Array.isArray(v[0]) ? v[0].length : 0;
    if (n >= MIN_COLUMNS && v.every((r) => Array.isArray(r) && r.length === n))
      return { kind: "arrays", header: [...Array(n).keys()].map((i) => `c${i}`), rows: v };
  }
  if (isObject(v)) {
    const cols = Object.entries(v);
    const n = cols.length && Array.isArray(cols[0][1]) ? cols[0][1].length : 0;
    if (cols.length >= MIN_COLUMNS && n >= MIN_ROWS && cols.every(([, c]) => Array.isArray(c) && c.length === n))
      return { kind: "columns", header: cols.map(([k]) => k), rows: [...Array(n).keys()].map((i) => cols.map(([, c]) => c[i])) };
  }
  return null;
}

function delimited(s) {
  if (typeof s !== "string" || s.length < 1000) return null;
  const lines = s.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < MIN_ROWS + 1) return null;
  for (const d of ["\t", ","]) {
    const n = lines[0].split(d).length;
    if (n >= MIN_COLUMNS && lines.filter((l) => l.split(d).length === n).length >= 0.9 * lines.length) return d;
  }
  return null;
}

// Tables inside a parsed JSON value, outermost first, with the keys leading to each.
function* search(v, where) {
  const t = table(v);
  if (t) return yield { where, ...t };
  if (typeof v === "string" && delimited(v)) return yield { where, kind: "text", text: v, delimiter: delimited(v) };
  if (Array.isArray(v)) for (const [i, x] of v.entries()) yield* search(x, [...where, String(i)]);
  else if (isObject(v)) for (const [k, x] of Object.entries(v)) yield* search(x, [...where, k]);
}

function where(ancestors) {
  const names = [];
  for (const [i, a] of ancestors.entries()) {
    const child = ancestors[i + 1];
    if (a.type === "VariableDeclarator" && a.id.type === "Identifier") names.push(a.id.name);
    else if (a.type === "Property" && child === a.value && !a.computed) names.push(a.key.name ?? String(a.key.value));
    else if (a.type === "AssignmentExpression" && child === a.right)
      names.push(a.left.type === "Identifier" ? a.left.name : a.left.property?.name ?? "set");
    else if (a.type === "ExportDefaultDeclaration") names.push("default");
  }
  return names;
}

function cell(v) {
  if (v === null || v === undefined) return "";
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

function parse(src) {
  try {
    return acorn.parse(src, { ecmaVersion: "latest", sourceType: "module" });
  } catch {
    return acorn.parse(src, { ecmaVersion: "latest", sourceType: "script" });
  }
}

function extract(file) {
  const src = fs.readFileSync(file, "utf8");
  const found = []; // {start, end, where, ...table}
  walk.fullAncestor(parse(src), (n, _s, ancestors) => {
    const at = { start: n.start, end: n.end };
    if (n.type === "CallExpression" && n.callee.type === "MemberExpression" && n.callee.object.name === "JSON"
        && n.callee.property.name === "parse" && n.arguments.length === 1) {
      const s = value(n.arguments[0]);
      if (typeof s !== "string") return;
      let v;
      try { v = JSON.parse(s); } catch { return; }
      for (const t of search(v, [...where(ancestors), "json"])) found.push({ ...at, ...t });
    } else if (n.type === "ArrayExpression" || n.type === "ObjectExpression") {
      if (n.type === "ArrayExpression" ? n.elements.length < MIN_ROWS : n.properties.length < MIN_COLUMNS) return;
      const v = value(n);
      const t = v === FAIL ? null : table(v);
      if (t) found.push({ ...at, where: where(ancestors), ...t });
    } else if (n.type === "Literal" || n.type === "TemplateLiteral") {
      const s = value(n);
      const d = delimited(s);
      if (d) found.push({ ...at, where: where(ancestors), kind: "text", text: s, delimiter: d });
    }
  });
  // the walk visits children first; a table inside another one is part of it
  return found.filter((t) => !found.some((o) => o !== t && o.start <= t.start && t.end <= o.end && (o.end - o.start) > (t.end - t.start)));
}

const [out, ...files] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const used = new Set();
for (const file of files) {
  let tables;
  try {
    tables = extract(file);
  } catch (e) {
    console.log(JSON.stringify({ js: path.basename(file), error: String(e.message).slice(0, 120) }));
    continue;
  }
  for (const t of tables) {
    const ext = t.kind === "text" && t.delimiter === "\t" ? "tsv" : "csv";
    const base = `${path.basename(file)}__${t.where.join(".") || "inline"}`.replace(/[^\w.-]+/g, "_");
    let name = `${base}.${ext}`;
    for (let i = 2; used.has(name); i++) name = `${base}-${i}.${ext}`;
    used.add(name);
    const body = t.kind === "text" ? t.text : [t.header, ...t.rows].map((r) => r.map(cell).join(",")).join("\n") + "\n";
    fs.writeFileSync(path.join(out, name), body);
    const rows = t.kind === "text" ? t.text.split(/\r?\n/).filter((l) => l.trim()).length - 1 : t.rows.length;
    const header = t.kind === "text" ? t.text.split(/\r?\n/)[0].split(t.delimiter) : t.header;
    console.log(JSON.stringify({ js: path.basename(file), file: name, where: t.where.join("."), kind: t.kind, rows, columns: header.length,
                                 header: header.slice(0, 12) }));
  }
}
