"""Subnational panel: official yield/production statistics (FEWS NET Data Warehouse
cropproductionfacts) per admin unit and season-year, against the ASAP indicators for the
same unit (tables/units/<ISO3>.csv from build_tables.py) and FAO ASIS ASI/VHI at admin 1.

Per country: within-unit regressions (each series demeaned and linearly detrended per unit,
then standardised) of the log-yield anomaly and production anomaly on each indicator and on
combinations, with leave-one-YEAR-out R² (all units of a year held out together). Pooled across
countries. Output: results/panel.json, results/panel_table.csv.
"""
import difflib, json, os, re, sys, unicodedata
import numpy as np, pandas as pd

S = sys.argv[1]; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{S}/results"; os.makedirs(OUT, exist_ok=True)
CFG = json.load(open(f"{ROOT}/data/config/countries.json")); CFG.pop("_notes", None)
def norm(s): return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower())

# FDW selection per country: staple products, season name, production system, admin level of the unit, and how to link to ASAP
FDW = {
    "AFG": dict(products=["Wheat Grain"], season="Calendar year", level="admin_1"),
    "BFA": dict(products=["Millet", "Sorghum"], season="Main", level="admin_2"),
    "ETH": dict(products=["Maize (Corn)", "Sorghum", "Mixed Teff", "Wheat Grain", "Barley (Unspecified)"], season="Meher", level="admin_2"),
    "KEN": dict(products=["Maize Grain (White)"], season="Annual harvest", level="county"),   # admin_2 districts to 2012, admin_1 counties from 2013
    "GTM": dict(products=["Maize Grain (White)", "Maize (Corn)"], season="Primera", level="admin_1"),
    "SLV": dict(products=["Maize Grain (White)"], season=["Annual", "Primera"], eras={"Annual": (2001, 2012), "Primera": (2013, 2025)}, level="admin_1"),  # reporting changed in 2013; each era is its own unit series
    "MRT": dict(products=["Sorghum", "Millet", "Maize (Corn)"], season="Main", level="admin_1", asap_to_admin1=True),
    "NER": dict(products=["Millet", "Sorghum"], season="Main season", level="admin_2"),
}
IND = ["t_dt", "z_dt", "rain", "wsi", "spi", "asi", "mvhi"]
MIN_YEARS = 8   # per unit series (Guatemala's Primera series have 9-10 years)
SIGN = {"t_dt": -1, "z_dt": 1, "rain": 1, "wsi": 1, "spi": 1, "asi": -1, "mvhi": 1}
COMBOS = [("t_dt", "z_dt"), ("t_dt", "rain"), ("t_dt", "asi"), ("t_dt", "mvhi"), ("z_dt", "rain")]
ADM2 = pd.read_csv(f"{S}/adm2_parent.csv")

def ols(y, X):
    X = np.column_stack([np.ones(len(y))] + X); b = np.linalg.lstsq(X, y, rcond=None)[0]; yhat = X @ b
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum(); n, k = X.shape
    s2 = ((y - yhat) ** 2).sum() / max(n - k, 1); se = np.sqrt(np.diag(s2 * np.linalg.pinv(X.T @ X)))
    from scipy import stats
    p = 2 * (1 - stats.t.cdf(np.abs(b / np.where(se == 0, np.nan, se)), max(n - k, 1)))
    return b, p, r2
def loyo(y, Xc, years):
    pred = np.zeros(len(y))
    for yr in np.unique(years):
        m = years != yr; Xtr = np.column_stack([np.ones(m.sum())] + [c[m] for c in Xc]); b = np.linalg.lstsq(Xtr, y[m], rcond=None)[0]
        Xte = np.column_stack([np.ones((~m).sum())] + [c[~m] for c in Xc]); pred[~m] = Xte @ b
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
def detrend_std(g, col):
    """Within-unit: remove a linear trend in year, then standardise. Needs >= 10 points."""
    x = g[col]; ok = x.notna()
    if ok.sum() < MIN_YEARS: return x * np.nan
    b = np.polyfit(g.year[ok], x[ok], 1); r = x - np.polyval(b, g.year); return (r - r[ok].mean()) / r[ok].std()

def match_map(src_names, dst_names, cutoff=0.85):
    dn = {norm(d): d for d in dst_names}; out = {}
    for s in src_names:
        n = norm(s)
        if n in dn: out[s] = dn[n]; continue
        c = difflib.get_close_matches(n, list(dn), n=1, cutoff=cutoff)
        if c: out[s] = dn[c[0]]
    return out

def rd(f): return pd.read_csv(f, engine="python", on_bad_lines="skip", encoding="latin-1")

R = {}; rows = []; pooled = []
for iso, spec in FDW.items():
    f = f"{S}/fdw/{iso}.csv"
    if not os.path.exists(f): continue
    d = pd.read_csv(f, low_memory=False); d["year"] = pd.to_numeric(d["season_year"].astype(str).str.extract(r"(\d{4})")[0], errors="coerce")
    seasons = spec["season"] if isinstance(spec["season"], list) else [spec["season"]]
    d = d[d["product"].isin(spec["products"]) & d.season_name.isin(seasons) & d.year.between(2001, 2025)].copy()
    if spec.get("eras"):
        keep_m = np.zeros(len(d), bool)
        for sname, (y0, y1) in spec["eras"].items(): keep_m |= ((d.season_name == sname) & d.year.between(y0, y1)).values
        d = d[keep_m].copy(); d["era"] = d.season_name
    if spec["level"] == "county":
        d["unit"] = np.where(d.year >= 2013, d.admin_1, d.admin_2); d["parent"] = d.admin_1
    else:
        d["unit"] = d[spec["level"]]; d["parent"] = d.admin_1
    d["geo"] = d["unit"]
    if "era" in d: d["unit"] = d["unit"] + " [" + d["era"] + "]"
    d = d[d.unit.notna() & d.value.notna()]
    # production systems: use the 'All (PS)' row where one exists for a unit-year-product-indicator, else sum the systems
    key = ["unit", "geo", "parent", "year", "product", "indicator"]
    has_all = d[d.crop_production_system == "All (PS)"].groupby(key).value.sum().rename("v_all")
    others = d[d.crop_production_system != "All (PS)"].groupby(key).value.sum().rename("v_sum")
    v = pd.concat([has_all, others], axis=1).reset_index(); v["value"] = v.v_all.fillna(v.v_sum)
    piv = v.pivot_table(index=["unit", "geo", "parent", "year"], columns="indicator", values="value", aggfunc="sum").reset_index()
    for c in ["Quantity Produced", "Area Harvested", "Area Planted", "Yield"]:
        if c not in piv: piv[c] = np.nan
    # crop-weighted yield: production / harvested area, falling back to planted area, then to the production-weighted reported yield
    area = piv["Area Harvested"].where(piv["Area Harvested"] > 0, piv["Area Planted"])
    yw = v[v.indicator.isin(["Yield", "Quantity Produced"])].pivot_table(index=["unit", "parent", "year", "product"], columns="indicator", values="value").reset_index()
    if "Yield" in yw and "Quantity Produced" in yw:
        yw["w"] = yw["Yield"] * yw["Quantity Produced"]; ywm = yw.groupby(["unit", "parent", "year"]).apply(lambda g: g.w.sum() / g["Quantity Produced"].sum() if g["Quantity Produced"].sum() > 0 else np.nan).rename("yield_rep").reset_index()
        piv = piv.merge(ywm, on=["unit", "parent", "year"], how="left")
    else: piv["yield_rep"] = np.nan
    piv["yield"] = (piv["Quantity Produced"] / area).where(area > 0, piv["yield_rep"])
    piv = piv[piv["Quantity Produced"] > 0]; piv["yield"] = piv["yield"].where(piv["yield"] > 0)   # Guatemala reports production without area for most years
    piv["log_yield"] = np.log(piv["yield"]); piv["log_prod"] = np.log(piv["Quantity Produced"])
    # ---- ASAP unit features
    U = pd.read_csv(f"{S}/tables/units/{iso}.csv")
    if spec.get("asap_to_admin1"):
        a2 = ADM2[ADM2.iso3 == iso]; par = match_map(U.region_name.unique(), a2.adm2.unique())
        p2a1 = dict(zip(a2.adm2, a2.adm1)); U["region_name"] = U.region_name.map(lambda n: p2a1.get(par.get(n), None)); U = U[U.region_name.notna()]
        U = U.groupby(["region_name", "year"])[[c for c in U.columns if c not in ("region_id", "region_name", "year")]].mean().reset_index()
    mm = match_map(piv.geo.unique(), U.region_name.unique())
    piv["asap_name"] = piv.geo.map(mm); P = piv[piv.asap_name.notna()].merge(U, left_on=["asap_name", "year"], right_on=["region_name", "year"], how="inner")
    # ---- ASIS admin-1 ASI / VHI by parent
    try:
        asi = rd(f"{S}/asis/{iso}_ASI_AnnualSummary_Season1_data.csv"); vhi = rd(f"{S}/asis/{iso}_Mean-VHI_AnnualSummary_Season1_data.csv")
        for nm, dd in [("asi", asi), ("mvhi", vhi)]:
            dd = dd[dd.CROP_MASK.astype(str).str.contains("Crop") & (dd.PROVINCE != "ALL")].copy(); dd["YEAR"] = pd.to_numeric(dd.YEAR, errors="coerce"); dd["DATA"] = pd.to_numeric(dd.DATA, errors="coerce")
            pm = match_map(P.parent.dropna().unique(), dd.PROVINCE.unique()); dd["parent"] = dd.PROVINCE
            x = dd.groupby(["parent", "YEAR"]).DATA.mean().reset_index().rename(columns={"YEAR": "year", "DATA": nm})
            P["asis_parent"] = P.parent.map(pm); P = P.merge(x, left_on=["asis_parent", "year"], right_on=["parent", "year"], how="left", suffixes=("", "_asis")).drop(columns=["parent_asis"], errors="ignore")
    except Exception as ex: print(iso, "ASIS join failed", repr(ex)[:80])
    # ---- within-unit detrend + standardise
    cols = [c for c in IND if c in P] ; keep = []
    for u, g in P.groupby("unit"):
        g = g.sort_values("year").copy()
        if g.log_prod.notna().sum() < MIN_YEARS: continue
        for c in cols + ["log_yield", "log_prod"]: g[c + "_w"] = detrend_std(g, c)
        keep.append(g)
    if not keep: print(iso, f"no units with >={MIN_YEARS} years"); continue
    P = pd.concat(keep); P["iso3"] = iso
    aoi_units = None
    if CFG[iso].get("aoi") or CFG[iso].get("aoi_asap"):
        targets = CFG[iso].get("aoi_asap") or CFG[iso]["aoi"]
        if spec["level"] == "admin_2" or spec["level"] == "county":
            aoi_units = P[P.parent.isin(match_map(P.parent.dropna().unique(), targets).keys()) | P.unit.isin(match_map(P.unit.unique(), targets).keys())].unit.unique()
        else: aoi_units = P[P.unit.isin(match_map(P.unit.unique(), targets).keys())].unit.unique()
    res = {"n_units": int(P.unit.nunique()), "n_obs": int(len(P)), "years": [int(P.year.min()), int(P.year.max())], "matched_units": int(len(mm)), "fdw_units": int(piv.geo.nunique()), "scopes": {}}
    for scope, sub in [("all", P), ("aoi", P[P.unit.isin(aoi_units)] if aoi_units is not None and len(aoi_units) else None)]:
        if sub is None or len(sub) < 40: continue
        sc = {"n_units": int(sub.unit.nunique()), "n_obs": int(len(sub)), "target": {}}
        for tgt in ["log_yield_w", "log_prod_w"]:
            t = {"single": {}, "combo": {}}
            for k in cols:
                m = sub[[k + "_w", tgt]].notna().all(axis=1)
                if m.sum() < 40: continue
                y = sub[tgt][m].values; X = sub[k + "_w"][m].values; yrs = sub.year[m].values
                b, p, r2 = ols(y, [X]); t["single"][k] = dict(r=round(float(np.corrcoef(X, y)[0, 1]), 3), r2=round(r2, 3), loyo=round(loyo(y, [X], yrs), 3), coef=round(b[1], 3), p=round(p[1], 4), n=int(m.sum()), sign_ok=bool(np.sign(b[1]) == SIGN[k]))
            for combo in COMBOS:
                if not all(k in cols for k in combo): continue
                m = sub[[k + "_w" for k in combo] + [tgt]].notna().all(axis=1)
                if m.sum() < 40: continue
                y = sub[tgt][m].values; Xc = [sub[k + "_w"][m].values for k in combo]; yrs = sub.year[m].values; b, p, r2 = ols(y, Xc)
                t["combo"]["+".join(combo)] = dict(r2=round(r2, 3), loyo=round(loyo(y, Xc, yrs), 3), coefs=[round(v, 3) for v in b[1:]], p=[round(v, 4) for v in p[1:]], n=int(m.sum()))
            # quadrant: hot vs cool, low vs high biomass (within-unit z), mean yield anomaly (%)
            if "t_dt" in cols and "z_dt" in cols:
                m = sub[["t_dt_w", "z_dt_w", tgt]].notna().all(axis=1); q = {}
                hot = sub.t_dt_w > 0; low = sub.z_dt_w < 0
                for hn, hm in [("hot", hot), ("cool", ~hot)]:
                    for ln, lm in [("low biomass", low), ("high biomass", ~low)]:
                        mm2 = m & hm & lm; q[f"{hn} / {ln}"] = dict(n=int(mm2.sum()), mean=round(float(sub[tgt][mm2].mean()), 2) if mm2.sum() else None)
                t["quad"] = q
            sc["target"][tgt] = t
        res["scopes"][scope] = sc
    # ---- year aggregate: average the within-unit standardised series over units each year (what the official
    # subnational statistics say nationally) and regress like the national study; compare with the FAOSTAT anomaly
    Y = P.groupby("year")[[c + "_w" for c in cols + ["log_yield", "log_prod"]]].mean(); Y["n_units"] = P.groupby("year").size(); Y = Y[Y.n_units >= max(3, 0.3 * P.unit.nunique())]
    agg = {"n_years": int(len(Y)), "single": {}}
    try:
        nat = pd.read_csv(f"{S}/tables/{iso}.csv").set_index("year")
        j = Y.join(nat["prod_anom"], how="inner"); agg["r_faostat"] = round(float(np.corrcoef(j.log_prod_w, j.prod_anom)[0, 1]), 3) if len(j) >= 8 else None; agg["n_faostat"] = int(len(j))
    except Exception: pass
    agg["single_prod"] = {}
    for tgt, slot in [("log_yield_w", "single"), ("log_prod_w", "single_prod")]:
        for k in cols:
            m = Y[[k + "_w", tgt]].notna().all(axis=1)
            if m.sum() < 8: continue
            y = Y[tgt][m].values; X = Y[k + "_w"][m].values; b, p, r2 = ols(y, [X])
            agg[slot][k] = dict(r=round(float(np.corrcoef(X, y)[0, 1]), 3), loyo=round(loyo(y, [X], Y.index[m].values), 3), p=round(p[1], 4), n=int(m.sum()))
    res["year_aggregate"] = agg
    R[iso] = res
    s1 = res["scopes"]["all"]["target"]["log_yield_w"]["single"]
    print(f"   year-aggregate ({agg['n_years']} y, r with FAOSTAT {agg.get('r_faostat')}): " + ", ".join(f"{k} r{v['r']:+.2f}/loyo{v['loyo']:+.2f}" for k, v in agg["single"].items()) + "\n   year-aggregate production: " + ", ".join(f"{k} r{v['r']:+.2f}/loyo{v['loyo']:+.2f}" for k, v in agg["single_prod"].items()))
    print(f"{iso}: units {res['n_units']} ({res['matched_units']}/{res['fdw_units']} matched) obs {res['n_obs']} {res['years']} | yield LOYO: " + ", ".join(f"{k} {v['loyo']:+.2f}" for k, v in s1.items()))
    rows.append(dict(iso3=iso, units=res["n_units"], obs=res["n_obs"], **{f"loyo_{k}": v["loyo"] for k, v in s1.items()}, **{f"r_{k}": v["r"] for k, v in s1.items()}))
    P["in_aoi"] = P.unit.isin(aoi_units) if aoi_units is not None else False
    pooled.append(P[["iso3", "unit", "year", "in_aoi", "log_yield_w", "log_prod_w"] + [k + "_w" for k in cols]])
PP = pd.concat(pooled); pool = {}; PP.to_csv(f"{OUT}/panel_units.csv", index=False)   # unit-year panel for summary.py
for tgt in ["log_yield_w", "log_prod_w"]:
    pool[tgt] = {"single": {}, "combo": {}}
    for k in IND:
        c = k + "_w"
        if c not in PP: continue
        m = PP[[c, tgt]].notna().all(axis=1); y = PP[tgt][m].values; X = PP[c][m].values; yrs = PP.year[m].values; b, p, r2 = ols(y, [X])
        pool[tgt]["single"][k] = dict(n=int(m.sum()), n_countries=int(PP.iso3[m].nunique()), r=round(float(np.corrcoef(X, y)[0, 1]), 3), r2=round(r2, 3), loyo=round(loyo(y, [X], yrs), 3), coef=round(b[1], 3), p=round(p[1], 5))
    for combo in COMBOS:
        cs = [k + "_w" for k in combo]
        if not all(c in PP for c in cs): continue
        m = PP[cs + [tgt]].notna().all(axis=1); y = PP[tgt][m].values; Xc = [PP[c][m].values for c in cs]; yrs = PP.year[m].values; b, p, r2 = ols(y, Xc)
        pool[tgt]["combo"]["+".join(combo)] = dict(n=int(m.sum()), r2=round(r2, 3), loyo=round(loyo(y, Xc, yrs), 3), coefs=[round(v, 3) for v in b[1:]], p=[round(v, 5) for v in p[1:]])
R["_pooled"] = pool
json.dump(R, open(f"{OUT}/panel.json", "w"), indent=1, default=float); pd.DataFrame(rows).to_csv(f"{OUT}/panel_table.csv", index=False)
print("\nPOOLED yield:", {k: (v["r"], v["loyo"], v["n"]) for k, v in pool["log_yield_w"]["single"].items()})
print("POOLED yield combos:", {k: (v["loyo"], v["coefs"]) for k, v in pool["log_yield_w"]["combo"].items()})
print("POOLED production:", {k: (v["r"], v["loyo"]) for k, v in pool["log_prod_w"]["single"].items()})
