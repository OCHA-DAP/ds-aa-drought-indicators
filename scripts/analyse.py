"""Per-country and pooled statistics: which indicators explain drought impact?

Reads tables/<ISO3>.csv from build_tables.py. For each country, scope (aoi/nat) and the main
season: single-indicator and combined regressions of the production anomaly (R², leave-one-out
R²), AUC for the binary impact seasons, and the hot/normal-biomass quadrant. Then pooled
(country-demeaned, standardised) regressions across countries.
Output: results/results.json, results/summary_table.csv.
"""
import json, os, sys
import numpy as np, pandas as pd
from scipy import stats
from itertools import product

S = sys.argv[1]; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(f"{ROOT}/data/config/countries.json")); CFG.pop("_notes", None)
OUT = f"{S}/results"; os.makedirs(OUT, exist_ok=True)
IND = {"t_dt": "temperature (detrended)", "z_dt": "biomass zFPARc (detrended)", "rain": "rainfall (ASAP/CHIRPS)", "era5": "rainfall (ERA5)",
       "wsi": "water balance (WSI)", "spi": "SPI-3", "asi": "FAO ASI (% cropland stressed)", "mvhi": "FAO mean VHI"}
SIGN = {"t_dt": -1, "z_dt": +1, "rain": +1, "era5": +1, "wsi": +1, "spi": +1, "asi": -1, "mvhi": +1}  # sign of expected relation with production
COMBOS = [("t_dt", "z_dt"), ("t_dt", "rain"), ("t_dt", "asi"), ("z_dt", "rain"), ("t_dt", "z_dt", "rain"), ("t_dt", "mvhi")]

def zs(s): return (s - s.mean()) / s.std()
def ols(y, X):
    X = np.column_stack([np.ones(len(y))] + X); b = np.linalg.lstsq(X, y, rcond=None)[0]; yhat = X @ b
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum(); n, k = X.shape
    s2 = ((y - yhat) ** 2).sum() / max(n - k, 1); se = np.sqrt(np.diag(s2 * np.linalg.pinv(X.T @ X))); p = 2 * (1 - stats.t.cdf(np.abs(b / np.where(se == 0, np.nan, se)), max(n - k, 1)))
    return b, p, r2
def loo(y, Xc):
    n = len(y); pred = np.zeros(n)
    for i in range(n):
        m = np.ones(n, bool); m[i] = False; Xtr = np.column_stack([np.ones(m.sum())] + [c[m] for c in Xc]); b = np.linalg.lstsq(Xtr, y[m], rcond=None)[0]
        pred[i] = np.array([1] + [c[i] for c in Xc]) @ b
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
def auc(score, lab):
    pos = score[lab == 1]; neg = score[lab == 0]
    if len(pos) == 0 or len(neg) == 0: return np.nan
    return float(np.mean([1.0 if p > q else 0.5 if p == q else 0.0 for p, q in product(pos, neg)]))

R = {}; rows = []; pooled = []
for iso, c in CFG.items():
    f = f"{S}/tables/{iso}.csv"
    if not os.path.exists(f): continue
    T = pd.read_csv(f, index_col=0); main = c["seasons"][0]["name"]
    R[iso] = {"name": c["name"], "season": c["seasons"][0]["label"], "scopes": {}}
    for scope in ["aoi", "nat"]:
        cols = {k: (f"{k}_{main}_{scope}" if k in ("t_dt", "z_dt", "rain", "wsi", "spi") else f"{k}_{scope}") for k in IND}
        cols = {k: v for k, v in cols.items() if v in T.columns}
        if "t_dt" not in cols: continue
        d = T[list(cols.values()) + ["prod_anom", "impact", "impact_cerf", "impact_emdat", "impact_plus_undated"] + (["bad_year"] if "bad_year" in T else [])].copy()
        d.columns = list(cols.keys()) + ["prod_anom", "impact", "impact_cerf", "impact_emdat", "impact_plus_undated"] + (["bad_year"] if "bad_year" in T else [])
        d = d.loc[2001:2024]
        res = {"n": int(d.prod_anom.notna().sum()), "single": {}, "combo": {}, "auc": {}, "quad": {}}
        dp = d.dropna(subset=["prod_anom"])
        for k in cols:
            x = dp[k]; ok = x.notna()
            if ok.sum() < 12: continue
            y = dp.prod_anom[ok].values; X = zs(x[ok]).values
            b, p, r2 = ols(y, [X]); r = stats.pearsonr(X, y)[0]
            res["single"][k] = dict(r=round(r, 2), r2=round(r2, 3), loo=round(loo(y, [X]), 3), coef=round(b[1], 2), p=round(p[1], 3), n=int(ok.sum()), sign_ok=bool(np.sign(r) == SIGN[k]))
        for combo in COMBOS:
            if not all(k in cols for k in combo): continue
            ok = dp[list(combo)].notna().all(axis=1)
            if ok.sum() < 12: continue
            y = dp.prod_anom[ok].values; Xc = [zs(dp[k][ok]).values for k in combo]
            b, p, r2 = ols(y, Xc)
            res["combo"]["+".join(combo)] = dict(r2=round(r2, 3), loo=round(loo(y, Xc), 3), coefs=[round(v, 2) for v in b[1:]], p=[round(v, 3) for v in p[1:]])
        for tgt in ["impact", "impact_cerf", "impact_emdat", "impact_plus_undated", "bad_year"]:
            if tgt not in d: continue
            lab = d[tgt].values.astype(int)
            if lab.sum() < 2 or (lab == 0).sum() < 2: continue
            a = {}
            for k in cols:
                x = d[k]; ok = x.notna().values
                if ok.sum() < 12: continue
                a[k] = round(auc((-SIGN[k]) * zs(x[ok]).values, lab[ok]), 3)
            ok = d.prod_anom.notna().values; a["production"] = round(auc(-d.prod_anom[ok].values, lab[ok]), 3)
            if "t_dt" in cols and "z_dt" in cols:
                ok = d[["t_dt", "z_dt"]].notna().all(axis=1).values; a["temp+biomass (sum)"] = round(auc((zs(d.t_dt[ok]) - zs(d.z_dt[ok])).values, lab[ok]), 3)
            res["auc"][tgt] = dict(n_pos=int(lab.sum()), pos_years=[int(y) for y in d.index[lab == 1]], auc=a)
        if "z_dt" in cols:
            hot = d.t_dt > d.t_dt.median(); low = d.z_dt < d.z_dt.median()
            for hn, hm in [("hot", hot), ("cool", ~hot)]:
                for ln, lm in [("low biomass", low), ("high biomass", ~low)]:
                    m = hm & lm & d.prod_anom.notna()
                    res["quad"][f"{hn} / {ln}"] = dict(n=int(m.sum()), prod_mean=round(float(d.prod_anom[m].mean()), 1) if m.sum() else None, impact_rate=round(float(d.impact[m].mean()), 2) if m.sum() else None, years=[int(y) for y in d.index[m]])
        R[iso]["scopes"][scope] = res
        rows.append(dict(iso3=iso, scope=scope, n=res["n"], **{f"r2_{k}": v["r2"] for k, v in res["single"].items()}, **{f"loo_{k}": v["loo"] for k, v in res["single"].items()},
                         **{f"auc_{k}": v for k, v in res["auc"].get("impact", {}).get("auc", {}).items()}, n_impact=res["auc"].get("impact", {}).get("n_pos")))
        if scope == "nat":
            dd = dp.copy()
            for k in cols: dd[k] = zs(dd[k])
            dd["prod_z"] = zs(dd.prod_anom); dd["iso3"] = iso; pooled.append(dd)
# ---------- pooled (country-demeaned already via z-scoring within country)
P = pd.concat(pooled); pool = {}
for k in IND:
    if k not in P: continue
    ok = P[[k, "prod_z"]].notna().all(axis=1)
    if ok.sum() < 30: continue
    y = P.prod_z[ok].values; X = P[k][ok].values; b, p, r2 = ols(y, [X])
    pool[k] = dict(n=int(ok.sum()), n_countries=int(P.iso3[ok].nunique()), r=round(stats.pearsonr(X, y)[0], 3), r2=round(r2, 3), coef=round(b[1], 3), p=round(p[1], 4), loo=round(loo(y, [X]), 3))
for combo in COMBOS:
    if not all(k in P for k in combo): continue
    ok = P[list(combo) + ["prod_z"]].notna().all(axis=1)
    y = P.prod_z[ok].values; Xc = [P[k][ok].values for k in combo]; b, p, r2 = ols(y, Xc)
    pool["+".join(combo)] = dict(n=int(ok.sum()), r2=round(r2, 3), coefs=[round(v, 3) for v in b[1:]], p=[round(v, 4) for v in p[1:]], loo=round(loo(y, Xc), 3))
# pooled AUC on impact seasons
pa = {}
lab = P.impact.values.astype(int)
for k in IND:
    if k not in P: continue
    ok = P[k].notna().values; pa[k] = round(auc((-SIGN[k]) * P[k][ok].values, lab[ok]), 3)
pa["production"] = round(auc(-P.prod_z.values, lab), 3); pa["n_pos"] = int(lab.sum()); pa["n"] = int(len(lab))
R["_pooled"] = dict(regression=pool, auc_impact=pa)
json.dump(R, open(f"{OUT}/results.json", "w"), indent=1, default=float)
pd.DataFrame(rows).to_csv(f"{OUT}/summary_table.csv", index=False)
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
print(pd.DataFrame(rows)[[c for c in pd.DataFrame(rows).columns if c.startswith(("iso3", "scope", "n", "r2_", "loo_t", "loo_z", "auc_t", "auc_z", "auc_prod", "n_impact"))]].round(2).to_string())
print("\nPOOLED regression (prod z ~ indicator z):"); [print(f"  {k:22s} {v}") for k, v in pool.items()]
print("POOLED AUC:", pa)
