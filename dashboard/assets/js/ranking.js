// The ranking and the selection, ported line for line from src/moria/rank.py (geomean, view_scores, select,
// largest_remainder), so that the what-if in How ranking works can be trusted: at Moria's own settings it must reproduce the
// real shortlist and queue exactly (checked on load, and in the repo's tests). The what-if never changes Moria.

export const VIEWS = ["early_warning", "strategic"];
export const COMPONENTS = { early_warning: ["strength", "novelty", "lead", "pathway"], strategic: ["strength", "breadth", "impact", "pathway"] };

/** The weighted geometric mean of the components present, iterating the weights in their configured order. */
export function geomean(parts, weights, order, floor) {
  const used = [];
  for (const k of order) {
    const w = weights[k];
    if (k in parts && w > 0) used.push([k, w]);
  }
  if (!used.length) return floor;
  let total = 0;
  for (const [, w] of used) total += w;
  let s = 0;
  for (const [k, w] of used) s += w * Math.log(Math.max(parts[k], floor));
  return Math.exp(s / total);
}

export function largestRemainder(size, shares) {
  const raw = {}, caps = {};
  for (const [k, v] of Object.entries(shares)) {
    raw[k] = size * v;
    caps[k] = Math.floor(raw[k]);
  }
  let left = size - Object.values(caps).reduce((a, b) => a + b, 0);
  const keys = Object.keys(raw).sort((a, b) => -(raw[a] - caps[a]) + (raw[b] - caps[b]) || (a < b ? -1 : a > b ? 1 : 0));
  for (const k of keys.slice(0, Math.max(0, left))) caps[k] += 1;
  return caps;
}

/** A settings object from the bundle's config: deep copies, so a what-if never touches the bundle. */
export function settingsFrom(config) {
  const r = config.rank, q = config.queue;
  return {
    floor: r.floor,
    shortlist: r.shortlist,
    weights: { early_warning: { ...r.weights.early_warning }, strategic: { ...r.weights.strategic } },
    weights_order: r.weights_order || { early_warning: ["strength", "novelty", "lead", "pathway"], strategic: ["strength", "breadth", "impact", "pathway"] },
    type_weight: { ...r.type_weight },
    flag_penalty: { ...r.flag_penalty },
    dossier_penalty: { ...(q.dossier_penalty || {}) },
    size: q.size,
    views: { ...q.views },
    rings: { ...q.rings },
    source_max: q.source_max,
    third_order_max: q.third_order_max,
  };
}

/** Each view's score for a candidate under the settings (pathway and impact absent: the suggestions are not used).
 * In the queue (`inQueue`), the dossier's own checks lower it too, as queue.py does; a held candidate (a document
 * weak signal whose sources have no baseline yet) is in neither view. */
export function scores(c, s, inQueue = false) {
  const parts = { strength: c.strength_pct, novelty: c.novelty, lead: c.lead, breadth: c.breadth };
  let flag = 1;
  for (const f of c.flags) if (f in s.flag_penalty) flag *= s.flag_penalty[f];
  if (inQueue) for (const f of c.dossier_flags || []) if (f in (s.dossier_penalty || {})) flag *= s.dossier_penalty[f];
  const factor = c.factors.scope * s.type_weight[c.type] * flag * c.factors.context;
  const out = {};
  for (const view of VIEWS) {
    if (!c.views.includes(view) || c.held) {
      out[view] = null;
      continue;
    }
    const comps = {};
    for (const k of COMPONENTS[view]) if (k in parts) comps[k] = parts[k];
    out[view] = geomean(comps, s.weights[view], s.weights_order[view], s.floor) * factor;
  }
  return out;
}

/** Picks under the quotas, as rank.select: the views alternate by their shares; each ring held to its quota, each
 * source to the cap, one per redundancy group; then a ring's unused places (pass 2), then the source cap relaxed. */
export function select(rows, size, s, thirdOrder = false) {
  const ringCap = largestRemainder(size, s.rings);
  const sourceCap = Math.max(1, Math.floor(size * s.source_max));
  const thirdCap = Math.floor(size * s.third_order_max);
  const rankings = {};
  for (const v of VIEWS) {
    rankings[v] = rows.filter((r) => r.score[v] != null).sort((a, b) => b.score[v] - a.score[v] || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  }
  const picks = [], used = new Set(), groups = new Set(), rings = {}, sources = {};
  let thirds = 0;
  for (const stage of [1, 2, 3]) {
    const pos = { early_warning: 0, strategic: 0 };
    const done = new Set(VIEWS.filter((v) => !rankings[v].length || (s.views[v] || 0) <= 0));
    while (picks.length < size && done.size < VIEWS.length) {
      const taken = { early_warning: 0, strategic: 0 };
      for (const p of picks) taken[p.view] += 1;
      let view = null, best = null;
      for (const [i, v] of VIEWS.entries()) {
        if (done.has(v)) continue;
        const key = (taken[v] + 1) / s.views[v];
        if (best == null || key < best[0] || (key === best[0] && i < best[1])) {
          best = [key, i];
          view = v;
        }
      }
      const ranking = rankings[view];
      let chosen = null;
      while (pos[view] < ranking.length) {
        const r = ranking[pos[view]];
        pos[view] += 1;
        if (used.has(r.id) || (r.redundancy_group && groups.has(r.redundancy_group))) continue;
        if (stage === 1 && (rings[r.ring] || 0) >= (ringCap[r.ring] || 0)) continue;
        if (stage < 3 && (sources[r.source] || 0) >= sourceCap) continue;
        if (thirdOrder && r.order === "3" && thirds >= thirdCap) continue;
        chosen = r;
        break;
      }
      if (!chosen) {
        done.add(view);
        continue;
      }
      used.add(chosen.id);
      if (chosen.redundancy_group) groups.add(chosen.redundancy_group);
      rings[chosen.ring] = (rings[chosen.ring] || 0) + 1;
      sources[chosen.source] = (sources[chosen.source] || 0) + 1;
      if (thirdOrder && chosen.order === "3") thirds += 1;
      picks.push({ id: chosen.id, rank: picks.length + 1, view, pass: stage });
    }
    if (picks.length >= size) break;
  }
  return picks;
}

/** The lowest order of each signal's pathways a person confirmed (the third-order cap reads these). */
export function confirmedOrders(register) {
  const out = {};
  for (const s of register || []) {
    const orders = ((s.review || {}).pathways || []).filter((p) => p.confirmed).map((p) => p.order);
    if (orders.length) out[s.signal_id] = String(Math.min(...orders));
  }
  return out;
}

/** The whole what-if: every candidate scored, the shortlist picked from all, the queue from the shortlist. */
export function whatIf(candidates, s, register) {
  const orders = confirmedOrders(register);
  const rows = candidates.map((c) => ({ id: c.id, ring: c.ring, source: c.source, redundancy_group: c.redundancy_group, order: orders[c.id] || null, score: scores(c, s) }));
  const shortlist = select(rows, s.shortlist, s);
  const inShort = new Set(shortlist.map((p) => p.id));
  const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
  // the queue's scores also weigh the dossiers' checks (queue.dossier_penalty)
  const queueRows = candidates.filter((c) => inShort.has(c.id)).map((c) => ({ ...byId[c.id], score: scores(c, s, true) }));
  const queue = select(queueRows, s.size, s, true);
  return { rows, byId, shortlist, queue };
}
