"""The primary output: one matrix of indicators (rows) against ground truths (columns), pooled across countries.
Continuous targets get an out-of-sample R² (leave-one-out for the national series, leave-one-year-out for the
panels); binary targets get an AUC computed from within-country (positive, negative) season pairs only, so countries
are never compared with each other and a country with no negatives or no positives contributes nothing.
Inputs: results/results.json (analyse.py), results/panel.json + panel_units.csv (panel.py), results/gdhy.json (gdhy.py),
tables/<ISO3>.csv. Output: results/summary.json, results/summary_matrix.csv."""
import json, os, re, sys
import numpy as np, pandas as pd
from itertools import product
S = sys.argv[1]; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(f"{ROOT}/data/config/countries.json")); CFG.pop("_notes", None)
R = json.load(open(f"{S}/results/results.json")); PAN = json.load(open(f"{S}/results/panel.json")); GD = json.load(open(f"{S}/results/gdhy.json"))
PU = pd.read_csv(f"{S}/results/panel_units.csv")
IND = ["t_dt", "z_dt", "asi", "mvhi", "rain", "era5", "spi", "wsi"]; SIGN = {"t_dt": -1, "asi": -1}
COMBOS = [("t_dt", "asi"), ("t_dt", "mvhi"), ("t_dt", "z_dt"), ("t_dt", "rain")]
def zs(s): return (s - s.mean()) / s.std()
def loyo(y, Xc, years):
    pred = np.zeros(len(y))
    for yr in np.unique(years):
        m = years != yr; Xtr = np.column_stack([np.ones(m.sum())] + [c[m] for c in Xc]); b = np.linalg.lstsq(Xtr, y[m], rcond=None)[0]
        pred[~m] = np.column_stack([np.ones((~m).sum())] + [c[~m] for c in Xc]) @ b
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()

# ---- national season tables, within-country standardised, oriented so that higher = worse
nat = []
for iso in CFG:
    f = f"{S}/tables/{iso}.csv"
    if not os.path.exists(f): continue
    T = pd.read_csv(f); d = pd.DataFrame({"iso3": iso, "year": T.year})
    for k in IND:
        c = [x for x in T.columns if re.match(rf"^{k}_[A-Za-z]+_nat$", x) or x == f"{k}_nat"]
        if c: d[k] = SIGN.get(k, 1) * -1 * zs(T[c[0]])   # higher = worse (hotter, less rain, more stress)
    for t in ["impact", "bad_year", "impact_cerf", "impact_emdat"]:
        if t in T: d[t] = T[t]
    nat.append(d)
N = pd.concat(nat)
def pooled_auc(score_col_or_series, target):
    """AUC over (positive, negative) pairs formed within each country."""
    wins = 0.0; pairs = 0; used = []
    sc = N[score_col_or_series] if isinstance(score_col_or_series, str) else score_col_or_series
    for iso, g in N.assign(_s=sc.values).groupby("iso3"):
        g = g[g[["_s", target]].notna().all(axis=1)]; pos = g._s[g[target] == 1].values; neg = g._s[g[target] == 0].values
        if len(pos) == 0 or len(neg) == 0: continue
        used.append(iso)
        for p, q in product(pos, neg): wins += 1.0 if p > q else 0.5 if p == q else 0.0; pairs += 1
    return (round(wins / pairs, 3) if pairs else None), pairs, used

cols = {
    "faostat": {"label": "National staple production (FAOSTAT)", "metric": "LOO R²", "kind": "continuous", "n": R["_pooled"]["regression"]["t_dt"]["n"], "note": "240 country-seasons, 10 countries; each series standardised within its country; leave-one-season-out."},
    "impact": {"label": "Impact seasons: CERF drought allocation or EM-DAT event", "metric": "AUC", "kind": "binary"},
    "bad_year": {"label": "Framework-documented bad years", "metric": "AUC", "kind": "binary"},
    "fdw_all": {"label": "Official subnational yield, all units (FEWS NET DW)", "metric": "LOYO R²", "kind": "continuous", "n": PAN["_pooled"]["log_yield_w"]["single"]["t_dt"]["n"], "note": "~4,800 unit-years in 7 countries (Guatemala has no yield); within-unit detrended; leave-one-year-out."},
    "fdw_aoi": {"label": "Official subnational yield, framework-area units only", "metric": "LOYO R²", "kind": "continuous"},
    "gdhy": {"label": "GDHY gridded maize/wheat yield, admin 1 (secondary)", "metric": "LOYO R²", "kind": "continuous", "n": GD["_pooled"]["t_dt"]["n"], "note": "2001–2016, maize and wheat only, partly circular with NDVI."},
}
rows = {}
A = PU[PU.in_aoi == True]; cols["fdw_aoi"]["n"] = int(A.log_yield_w.notna().sum()); cols["fdw_aoi"]["note"] = "%d unit-years in %s." % (cols["fdw_aoi"]["n"], ", ".join(sorted(A.iso3.unique())))
def panel_loyo(D, ks):
    cs = [k + "_w" for k in ks]
    if not all(c in D for c in cs): return None
    m = D[cs + ["log_yield_w"]].notna().all(axis=1)
    if m.sum() < 40: return None
    return round(loyo(D.log_yield_w[m].values, [D[c][m].values for c in cs], D.year[m].values), 3)
for k in IND:
    r = {"faostat": R["_pooled"]["regression"].get(k, {}).get("loo")}
    if k in N: 
        for t in ["impact", "bad_year"]: r[t], _, _ = pooled_auc(k, t)
    else: r["impact"] = r["bad_year"] = None
    r["fdw_all"] = PAN["_pooled"]["log_yield_w"]["single"].get(k, {}).get("loyo"); r["fdw_aoi"] = panel_loyo(A, [k]); r["gdhy"] = GD["_pooled"].get(k, {}).get("loyo")
    rows[k] = r
for combo in COMBOS:
    key = "+".join(combo); r = {"faostat": R["_pooled"]["regression"].get(key, {}).get("loo")}
    if all(k in N for k in combo):
        sc = N[list(combo)].sum(axis=1)
        for t in ["impact", "bad_year"]: r[t], _, _ = pooled_auc(sc, t)
    else: r["impact"] = r["bad_year"] = None
    r["fdw_all"] = PAN["_pooled"]["log_yield_w"]["combo"].get(key, {}).get("loyo"); r["fdw_aoi"] = panel_loyo(A, combo); r["gdhy"] = GD["_pooled"].get(key, {}).get("loyo")
    rows[key] = r
for t in ["impact", "bad_year"]:
    _, pairs, used = pooled_auc("t_dt", t); cols[t]["n"] = pairs; cols[t]["note"] = "%d within-country (positive, negative) season pairs from %s; positives: %d seasons." % (pairs, ", ".join(used), int(N[N.iso3.isin(used)][t].sum()))
json.dump({"columns": cols, "rows": rows}, open(f"{S}/results/summary.json", "w"), indent=1)
M = pd.DataFrame(rows).T[list(cols)]; M.to_csv(f"{S}/results/summary_matrix.csv"); print(M.to_string())
for t in ["impact", "bad_year"]: print(t, cols[t]["note"])
