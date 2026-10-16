// The data in use. The public bundle is always loaded; a practice bundle (invented) or a private bundle (the
// analyst's own file, read in this tab only) can replace it. Nothing here is ever written anywhere.

export const state = {
  pub: null, // the public bundle (aggregates only)
  data: null, // the bundle in use
  mode: "public", // public | practice | private
  fileName: null,
  index: null,
  series: [], // the Mirrormere's chosen series: [{id, slot}]
  filter: null, // a filter handed from one level to another (a type tile to the candidates)
};

export function hasDetail() {
  return state.mode !== "public" && Array.isArray(state.data?.candidates);
}

export function setData(bundle, mode, fileName = null) {
  state.data = bundle;
  state.mode = mode;
  state.fileName = fileName;
  state.series = [];
  state.index = null;
}

export function candidateIndex() {
  if (!state.index && hasDetail()) state.index = Object.fromEntries(state.data.candidates.map((c) => [c.id, c]));
  return state.index || {};
}

export function candidate(id) {
  return candidateIndex()[id] || null;
}

export function seriesOf(c) {
  if (!c || !state.data?.series) return [];
  return (c.series || []).map((s) => ({ ...s, data: state.data.series[s.id] })).filter((s) => s.data);
}

export function dossierOf(id) {
  return state.data?.dossiers?.[id] || null;
}

/** Read a dropped or chosen file: JSON, or gzip-compressed JSON, decompressed by the browser itself. */
export async function readBundle(file) {
  const head = new Uint8Array(await file.slice(0, 2).arrayBuffer());
  let text;
  if (head[0] === 0x1f && head[1] === 0x8b) {
    if (typeof DecompressionStream === "undefined") throw new Error("This browser can't open .gz files; use a recent Chrome, Edge, Firefox or Safari.");
    text = await new Response(file.stream().pipeThrough(new DecompressionStream("gzip"))).text();
  } else {
    text = await file.text();
  }
  let b;
  try {
    b = JSON.parse(text);
  } catch {
    throw new Error("That file isn't a Moria dashboard file (it isn't JSON).");
  }
  if (!b || b.schema !== 1 || !["private", "practice"].includes(b.kind) || !Array.isArray(b.candidates)) {
    throw new Error("That file isn't a Moria dashboard bundle. Look for dashboard.json.gz under interpretation/dashboard/ in the bucket.");
  }
  return b;
}

export async function fetchJson(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
