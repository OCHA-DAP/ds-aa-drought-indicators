"""Secondary yield target: GDHY v1.2/v1.3 gridded 0.5° yields (Iizumi & Sakai 2020), maize and wheat, 1981-2016.
Cells are assigned to CODAB admin-1 polygons by centre. National and admin-1 mean yields (unweighted over cells
with data) are detrended and compared with (a) the FAOSTAT production anomaly, to validate the dataset, and
(b) the ASAP / ASIS indicators nationally and per admin-1 unit (within-unit detrended, leave-one-year-out R²).
Caveat: GDHY blends census statistics with satellite NDVI, so agreement with vegetation indices is partly circular.
Output: results/gdhy.json."""
import glob, json, os, re, sys, difflib, unicodedata
import numpy as np, pandas as pd, geopandas as gpd, xarray as xr
from shapely.geometry import Point
from ocha_stratus import codab
S = sys.argv[1]; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = f"{S}/results"
CFG = json.load(open(f"{ROOT}/data/config/countries.json")); CFG.pop("_notes", None)
LEVEL2 = {"BFA", "ETH", "MRT", "NER", "TCD"}
CROPS = {"maize": ["BFA", "ETH", "KEN", "GTM", "HND", "SLV", "NER", "TCD", "MRT"], "wheat": ["AFG", "ETH", "KEN"]}
IND = ["t_dt", "rain", "wsi", "spi", "z_dt", "asi", "mvhi"]; SIGN = {"t_dt": -1, "asi": -1}
def norm(s): return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower())
def match_map(src, dst, cutoff=0.85):
    dn = {norm(d): d for d in dst}; out = {}
    for s in src:
        n = norm(s)
        if n in dn: out[s] = dn[n]; continue
        c = difflib.get_close_matches(n, list(dn), n=1, cutoff=cutoff)
        if c: out[s] = dn[c[0]]
    return out
def namecol(g, lvl):
    for suf in ("EN", "FR", "ES", "PT", "AR"):
        c = f"ADM{lvl}_{suf}"
        if c in g and g[c].notna().any(): return c
    return [c for c in g.columns if c.startswith(f"ADM{lvl}_") and not c.endswith("PCODE")][0]
def ols(y, X):
    X = np.column_stack([np.ones(len(y))] + X); b = np.linalg.lstsq(X, y, rcond=None)[0]; return b
def loyo(y, Xc, years):
    pred = np.zeros(len(y))
    for yr in np.unique(years):
        m = years != yr; b = ols(y[m], [c[m] for c in Xc]); pred[~m] = np.column_stack([np.ones((~m).sum())] + [c[~m] for c in Xc]) @ b
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
def detrend_std(g, col, minn=10):
    x = g[col]; ok = x.notna()
    if ok.sum() < minn: return x * np.nan
    b = np.polyfit(g.year[ok], x[ok], 1); r = x - np.polyval(b, g.year); return (r - r[ok].mean()) / r[ok].std()

# ---- GDHY stack 1996-2016 (trend fitted on 21 years, analysed on 2001-2016)
YEARS = list(range(1996, 2017)); stack = {}
for crop in CROPS:
    arrs = []
    for y in YEARS:
        f = f"{S}/gdhy/{crop}/yield_{y}.nc4"
        d = xr.open_dataset(f)["var"]; d = d.assign_coords(lon=((d.lon + 180) % 360) - 180).sortby("lon"); arrs.append(d.expand_dims(year=[y]))
    stack[crop] = xr.concat(arrs, "year")
lon, lat = np.meshgrid(stack["maize"].lon.values, stack["maize"].lat.values)
cells = gpd.GeoDataFrame({"ilat": np.repeat(np.arange(lat.shape[0]), lat.shape[1]), "ilon": np.tile(np.arange(lat.shape[1]), lat.shape[0])},
                         geometry=[Point(x, y) for x, y in zip(lon.ravel(), lat.ravel())], crs="EPSG:4326")

R = {}; pooled = []
for iso in CFG:
    try: a1 = codab.load_codab_from_blob(iso.lower(), admin_level=1)
    except Exception as ex: print(iso, "no CODAB adm1", repr(ex)[:60]); continue
    n1 = namecol(a1, 1); a1 = a1[[n1, "geometry"]].rename(columns={n1: "adm1"})
    box = a1.total_bounds; sub = cells.cx[box[0]:box[2], box[1]:box[3]]
    j = gpd.sjoin(sub, a1, predicate="within", how="inner")
    res = {"crops": {}}
    U = pd.read_csv(f"{S}/tables/units/{iso}.csv")
    if iso in LEVEL2:   # ASAP units are admin 2: find each one's admin-1 parent through CODAB adm2
        a2 = codab.load_codab_from_blob(iso.lower(), admin_level=2); n2 = namecol(a2, 2); p1 = namecol(a2, 1)
        m2 = match_map(U.region_name.unique(), a2[n2].unique()); par = dict(zip(a2[n2], a2[p1]))
        U["adm1"] = U.region_name.map(lambda n: par.get(m2.get(n)))
    else:
        m1 = match_map(U.region_name.unique(), a1.adm1.unique()); U["adm1"] = U.region_name.map(m1)
    U = U[U.adm1.notna()]; feat = [c for c in U.columns if c in ("t_dt", "rain", "wsi", "spi", "z_dt")]
    U1 = U.groupby(["adm1", "year"])[feat].mean().reset_index()
    # ASIS at admin 1
    try:
        for nm, fn in [("asi", "ASI"), ("mvhi", "Mean-VHI")]:
            dd = pd.read_csv(f"{S}/asis/{iso}_{fn}_AnnualSummary_Season1_data.csv", engine="python", on_bad_lines="skip", encoding="latin-1")
            dd = dd[dd.CROP_MASK.astype(str).str.contains("Crop") & (dd.PROVINCE != "ALL")].copy(); dd["YEAR"] = pd.to_numeric(dd.YEAR, errors="coerce"); dd["DATA"] = pd.to_numeric(dd.DATA, errors="coerce")
            pm = match_map(U1.adm1.unique(), dd.PROVINCE.unique()); x = dd.groupby(["PROVINCE", "YEAR"]).DATA.mean().reset_index()
            x["adm1"] = x.PROVINCE.map({v: k for k, v in pm.items()}); x = x[x.adm1.notna()].rename(columns={"YEAR": "year", "DATA": nm})[["adm1", "year", nm]]
            U1 = U1.merge(x, on=["adm1", "year"], how="left")
    except Exception as ex: print(iso, "ASIS", repr(ex)[:60])
    nat = pd.read_csv(f"{S}/tables/{iso}.csv").set_index("year")
    natcols = {k: [c for c in nat.columns if re.match(rf"^{k}_[A-Za-z]+_nat$", c) or c == f"{k}_nat"] for k in IND}
    for crop, isos in CROPS.items():
        if iso not in isos: continue
        arr = stack[crop].values  # year, lat, lon
        v = arr[:, j.ilat.values, j.ilon.values]  # year x cells
        has = np.isfinite(v).sum(0) >= 15; v = v[:, has]; jj = j[has]
        if v.shape[1] < 5: res["crops"][crop] = {"cells": int(v.shape[1])}; continue
        natser = pd.Series(np.nanmean(v, 1), index=YEARS)
        cr = {"cells": int(v.shape[1])}
        # national: detrend 1996-2016, analyse 2001-2016
        b = np.polyfit(YEARS, np.log(natser.values), 1); an = (np.log(natser.values) - np.polyval(b, YEARS)) * 100
        an = pd.Series(an, index=YEARS).loc[2001:2016]; jn = nat.join(an.rename("gdhy"), how="inner")
        cr["national"] = {"n": int(len(jn)), "r_faostat": round(float(jn.gdhy.corr(jn.prod_anom)), 3) if jn.prod_anom.notna().sum() >= 8 else None,
                          "ind": {k: round(float(jn.gdhy.corr(jn[natcols[k][0]])), 3) for k in IND if natcols[k]}}
        # admin-1 panel
        g = pd.DataFrame(v, index=YEARS, columns=jj.adm1.values).T.groupby(level=0).mean().T   # years x adm1
        g = g.loc[2001:2016]; long = g.stack().rename("y").reset_index().rename(columns={"level_0": "year", "level_1": "adm1"})
        long["log_y"] = np.log(long.y); P = long.merge(U1, on=["adm1", "year"], how="inner"); keep = []
        for u, gg in P.groupby("adm1"):
            gg = gg.sort_values("year").copy()
            if len(gg) < 10: continue
            for c in ["log_y"] + [c for c in IND if c in gg]: gg[c + "_w"] = detrend_std(gg, c)
            keep.append(gg)
        if keep:
            P = pd.concat(keep); P["iso3"] = iso; P["crop"] = crop; sub = {}
            for k in IND:
                if k + "_w" not in P: continue
                m = P[[k + "_w", "log_y_w"]].notna().all(axis=1)
                if m.sum() < 40: continue
                y = P.log_y_w[m].values; X = P[k + "_w"][m].values
                sub[k] = dict(n=int(m.sum()), units=int(P.adm1[m].nunique()), r=round(float(np.corrcoef(X, y)[0, 1]), 3), loyo=round(loyo(y, [X], P.year[m].values), 3))
            cr["admin1"] = sub; pooled.append(P[["iso3", "crop", "adm1", "year", "log_y_w"] + [k + "_w" for k in IND if k + "_w" in P]])
        res["crops"][crop] = cr
        print(f"{iso} {crop}: cells {cr['cells']}, national r FAOSTAT {cr['national']['r_faostat']}, national r: " + ", ".join(f"{k} {v:+.2f}" for k, v in cr["national"]["ind"].items()) +
              (" | admin1 LOYO: " + ", ".join(f"{k} {v['loyo']:+.2f}" for k, v in cr["admin1"].items()) if cr.get("admin1") else ""))
    R[iso] = res
PP = pd.concat(pooled); pool = {}
for k in IND:
    c = k + "_w"
    if c not in PP: continue
    m = PP[[c, "log_y_w"]].notna().all(axis=1); y = PP.log_y_w[m].values; X = PP[c][m].values
    pool[k] = dict(n=int(m.sum()), n_countries=int(PP.iso3[m].nunique()), r=round(float(np.corrcoef(X, y)[0, 1]), 3), loyo=round(loyo(y, [X], PP.year[m].values), 3))
for combo in [("t_dt", "z_dt"), ("t_dt", "rain"), ("t_dt", "mvhi")]:
    cs = [k + "_w" for k in combo]; m = PP[cs + ["log_y_w"]].notna().all(axis=1); y = PP.log_y_w[m].values; Xc = [PP[c][m].values for c in cs]; b = ols(y, Xc)
    pool["+".join(combo)] = dict(n=int(m.sum()), loyo=round(loyo(y, Xc, PP.year[m].values), 3), coefs=[round(float(x), 3) for x in b[1:]])
R["_pooled"] = pool; json.dump(R, open(f"{OUT}/gdhy.json", "w"), indent=1, default=float)
print("POOLED admin-1 GDHY:", {k: (v.get("r"), v["loyo"], v["n"]) for k, v in pool.items()})
