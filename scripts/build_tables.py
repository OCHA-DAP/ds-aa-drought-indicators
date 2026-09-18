"""Build per-country season tables: predictors (ASAP, ERA5, FAO ASIS) and impact targets.

Inputs (scratch dir S, see README): asap_all/ asap_l2/ asap_bfa/ (ASAP indicator exports),
era5_precip.parquet (team DB raster stats), asis/ (FAO ASIS csvs), faostat_ten_staples.csv,
cerf_drought_all.csv, emdat_drought_all.csv, adm_names.csv, data/config/countries.json.
Output: tables/<ISO3>.csv (one row per season-year) and tables/impact_dating.csv.
"""
import json, os, re, sys, unicodedata
import numpy as np, pandas as pd
from scipy import stats

S = sys.argv[1]; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(f"{ROOT}/data/config/countries.json")); CFG.pop("_notes", None)
OUT = f"{S}/tables"; os.makedirs(OUT, exist_ok=True)
YRS = range(2001, 2026)

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)

import difflib
def match_names(targets, candidates):
    """Candidate names whose normalised form matches any target: exact, containment (>=5 chars) or
    close spelling (difflib ratio >= 0.85, e.g. Guidimakha/Guidimagha, Sar-e-Pul/Sar-E-Pul)."""
    out = []
    tn = [norm(t) for t in targets]
    for c in candidates:
        cn = norm(c)
        if any(cn == t or (len(t) >= 5 and (t in cn or cn in t)) or difflib.SequenceMatcher(None, cn, t).ratio() >= 0.85 for t in tn):
            out.append(c)
    return out

ADM2 = None
def units_in_aoi(iso, units, aoi_names, level2):
    """ASAP units (region_id) inside the framework AOI (admin-1 names). For level-2 exports, map each
    unit to its admin-1 parent through the CODAB admin-2 table by name, then filter on the parent."""
    global ADM2
    if ADM2 is None: ADM2 = pd.read_csv(f"{S}/adm2_parent.csv")
    if not level2:
        return units[units.region_name.isin(match_names(aoi_names, units.region_name))].region_id.tolist()
    a2 = ADM2[ADM2.iso3 == iso]
    if a2.empty: return []
    parents = {norm(r.adm2): r.adm1 for r in a2.itertuples()}
    keep = []
    for r in units.itertuples():
        n = norm(r.region_name); par = parents.get(n)
        if par is None:
            best = difflib.get_close_matches(n, list(parents), n=1, cutoff=0.85); par = parents[best[0]] if best else None
        if par and match_names(aoi_names, [par]): keep.append(r.region_id)
    return keep

def dekad_of(d): return (d.dt.month - 1) * 3 + np.minimum((d.dt.day - 1) // 10, 2) + 1

def load_asap(iso, ind):
    for path in [f"{S}/asap_bfa/{ind}.csv" if iso == "BFA" else None, f"{S}/asap_l2/{iso}_{ind}.csv", f"{S}/asap_all/{iso}_{ind}.csv"]:
        if path and os.path.exists(path) and os.path.getsize(path) > 500:
            d = pd.read_csv(path, dtype={"date": str})
            if len(d) < 5: continue
            d["date"] = pd.to_datetime(d["date"], format="%Y%m%d"); d["year"] = d.date.dt.year; d["dekad"] = dekad_of(d.date)
            return d[["region_id", "region_name", "year", "dekad", "value"]], path
    return None, None

def theil_detrend(g, col, y0, y1):
    f = g[g.year.between(y0, y1)].dropna(subset=[col])
    if len(f) < 10: return g[col] * np.nan
    sl = stats.theilslopes(f[col], f.year)
    return g[col] - sl[0] * (g.year - f.year.mean())

def season_mean(d, col, dk0, dk1, tail=None):
    """Mean over dekads dk0..dk1 (tail: only the last `tail` fraction of the window)."""
    if tail:
        n = dk1 - dk0 + 1; dk0 = dk1 - int(round(n * tail)) + 1
    return d[d.dekad.between(dk0, dk1)].groupby(["region_id", "year"])[col].mean()

adm = pd.read_csv(f"{S}/adm_names.csv")
era5 = pd.read_parquet(f"{S}/era5_precip.parquet"); era5["valid_date"] = pd.to_datetime(era5.valid_date); era5["year"] = era5.valid_date.dt.year; era5["month"] = era5.valid_date.dt.month
fao = pd.read_csv(f"{S}/faostat_ten_staples.csv")
cerf = pd.read_csv(f"{S}/cerf_drought_all.csv"); emd = pd.read_csv(f"{S}/emdat_drought_all.csv")
NAMES = {"AFG": "Afghanistan", "BFA": "Burkina Faso", "ETH": "Ethiopia", "KEN": "Kenya", "GTM": "Guatemala", "HND": "Honduras", "SLV": "El Salvador", "MRT": "Mauritania", "NER": "Niger", "TCD": "Chad"}

def assign_season(iso, start, end, seasons, mode="overlap"):
    """mode='overlap': season-year whose main-season window overlaps [start,end] most (CERF supplement
    valid periods are the deficit season itself). mode='impact': the last main season whose midpoint
    precedes the impact start (EM-DAT events and allocations are dated to when people were affected,
    normally the lean season after the failed harvest)."""
    main = seasons[0]; dk0, dk1 = main["dekads"]
    def win(y):
        m0 = (dk0 - 1) // 3 + 1; m1 = (dk1 - 1) // 3 + 1
        return pd.Timestamp(y, m0, 1), pd.Timestamp(y, m1, 28)
    if mode == "overlap":
        best = None
        for y in range(start.year - 1, end.year + 1):
            a, b = win(y); ov = (min(b, end) - max(a, start)).days
            if ov > 0 and (best is None or ov > best[1]): best = (y, ov)
        if best: return best[0], "overlap"
    for y in range(start.year, start.year - 3, -1):
        a, b = win(y); mid = a + (b - a) / 2
        if mid <= start + pd.Timedelta(days=31): return y, "last-season-before-impact"
    return None, "none"

dating_rows = []; summary = {}
for iso, c in CFG.items():
    seasons = c["seasons"]; main = seasons[0]
    # ---------- ASAP
    A = {}; src = {}
    for ind in ["temp_crop", "rain_crop", "zfparc_crop", "zfparc_range", "wsi_crop", "spi3_crop"]:
        d, p = load_asap(iso, ind); A[ind] = d; src[ind] = p
    if A["temp_crop"] is None: print(iso, "no ASAP temp — skipping"); continue
    units = A["temp_crop"][["region_id", "region_name"]].drop_duplicates()
    level2 = "asap_l2" in (src["temp_crop"] or "") or iso == "BFA"
    aoi_units = None
    if c.get("aoi_asap"): aoi_units = units[units.region_name.isin(c["aoi_asap"])].region_id.tolist()
    elif c.get("aoi"): aoi_units = units_in_aoi(iso, units, c["aoi"], level2)
    rows = {}
    for sname, s in [(x["name"], x) for x in seasons]:
        dk0, dk1 = s["dekads"]
        feats = {}
        feats["t"] = season_mean(A["temp_crop"], "value", dk0, dk1)
        feats["rain"] = season_mean(A["rain_crop"], "value", dk0, dk1)
        feats["wsi"] = season_mean(A["wsi_crop"], "value", dk0, dk1, tail=0.6) if A["wsi_crop"] is not None else None
        feats["spi"] = season_mean(A["spi3_crop"], "value", dk0, dk1, tail=0.6) if A["spi3_crop"] is not None else None
        zc = season_mean(A["zfparc_crop"], "value", dk0, dk1, tail=0.6) if A["zfparc_crop"] is not None else None
        zr = season_mean(A["zfparc_range"], "value", dk0, dk1, tail=0.6) if A["zfparc_range"] is not None else None
        feats["z"] = pd.concat([zc, zr], axis=1).mean(axis=1) if zc is not None or zr is not None else None
        F = pd.concat({k: v for k, v in feats.items() if v is not None}, axis=1).reset_index()
        # detrend per unit
        parts = []
        for rid, g in F.groupby("region_id"):
            g = g.sort_values("year").copy()
            g["t_dt"] = theil_detrend(g, "t", 1991, 2025) - g[g.year.between(1991, 2025)].t.mean() if "t" in g else np.nan
            if "z" in g: g["z_dt"] = theil_detrend(g, "z", 2001, 2025)
            parts.append(g)
        F = pd.concat(parts)
        for scope, sel in [("aoi", aoi_units), ("nat", None)]:
            if scope == "aoi" and not sel: continue
            g = F[F.region_id.isin(sel)] if sel else F
            m = g.groupby("year")[[k for k in ["t", "t_dt", "rain", "wsi", "spi", "z", "z_dt"] if k in g]].mean()
            m.columns = [f"{k}_{sname}_{scope}" for k in m.columns]
            rows[(sname, scope)] = m
    T = pd.concat(rows.values(), axis=1)
    # ---------- ERA5 precip (adm1 for AOI, adm0 national); seasonal mean of monthly means
    e = era5[era5.iso3 == iso]
    m0, m1 = (main["dekads"][0] - 1) // 3 + 1, (main["dekads"][1] - 1) // 3 + 1
    en = e[(e.adm_level == 0) & e.month.between(m0, m1)].groupby("year")["mean"].mean(); T["era5_nat"] = en
    if c.get("aoi"):
        a1 = adm[(adm.iso3 == iso) & adm.pcode.str.len().le(6)]
        pc = a1[a1.name.isin(match_names(c["aoi"], a1.name))].pcode.tolist()
        ea = e[(e.adm_level == 1) & e.pcode.isin(pc) & e.month.between(m0, m1)].groupby("year")["mean"].mean(); T["era5_aoi"] = ea
    # ---------- FAO ASIS: annual ASI (% cropland stressed) and mean VHI, season 1; adm1 rows
    def rd(f): return pd.read_csv(f, engine="python", on_bad_lines="skip", encoding="latin-1")
    try:
        asi = rd(f"{S}/asis/{iso}_ASI_AnnualSummary_Season1_data.csv"); vhi = rd(f"{S}/asis/{iso}_Mean-VHI_AnnualSummary_Season1_data.csv")
        for nm, d, col in [("asi", asi, "asi"), ("mvhi", vhi, "mvhi")]:
            d["YEAR"] = pd.to_numeric(d.YEAR, errors="coerce"); d["DATA"] = pd.to_numeric(d.DATA, errors="coerce"); d = d[d.CROP_MASK.str.contains("Crop", na=False)]
            T[f"{col}_nat"] = d[d.PROVINCE == "ALL"].groupby("YEAR").DATA.mean()
            if c.get("aoi"):
                pv = match_names(c["aoi"], [p for p in d.PROVINCE.unique() if p != "ALL"])
                if pv: T[f"{col}_aoi"] = d[d.PROVINCE.isin(pv)].groupby("YEAR").DATA.mean()
    except Exception as ex: print(iso, "ASIS failed", repr(ex)[:100])
    # ---------- production target
    fp = fao[(fao.Area == NAMES[iso]) & fao.Item.isin(c["staples"])].groupby("Year").Value.sum()
    fp = fp[(fp.index >= 2001) & (fp.index <= 2024)]
    b = np.polyfit(fp.index, fp.values, 1); T["prod_anom"] = pd.Series((fp.values - np.polyval(b, fp.index)) / np.polyval(b, fp.index) * 100, index=fp.index)
    # ---------- impact seasons
    imp = set(); imp_undated = set(); imp_emdat = set(); imp_cerf = set()
    for r in cerf[cerf.iso3 == iso].itertuples():
        if pd.notna(r.vys):
            st = pd.Timestamp(int(r.vys), int(r.vms), 1); en_ = pd.Timestamp(int(r.vye), int(r.vme), 28)
            y, how = assign_season(iso, st, en_, seasons); imp_cerf.add(y)
            dating_rows.append(dict(iso3=iso, record=f"CERF {int(r.year)} {r.win} ${r.musd}M", start=st.date(), end=en_.date(), season=y, basis=how))
        else:
            y, how = assign_season(iso, pd.Timestamp(int(r.year), 1, 1), pd.Timestamp(int(r.year), 1, 1), seasons, mode="impact"); imp_undated.add(y)
            dating_rows.append(dict(iso3=iso, record=f"CERF {int(r.year)} {r.win} ${r.musd}M (undated)", start=f"{int(r.year)}-01-01", end=None, season=y, basis="undated: " + how))
    for r in emd[emd.ISO == iso].itertuples():
        sy = int(r._3); sm = int(r._4) if pd.notna(r._4) else 1; ey = int(r._5) if pd.notna(r._5) else sy; em_ = int(r._6) if pd.notna(r._6) else 12
        st = pd.Timestamp(sy, sm, 1); en_ = pd.Timestamp(ey, min(em_, 12), 28)
        y, how = assign_season(iso, st, en_, seasons, mode="impact"); imp_emdat.add(y)
        dating_rows.append(dict(iso3=iso, record=f"EM-DAT {r._2} ({int(r._7) if pd.notna(r._7) else 'n/a'} affected)", start=st.date(), end=en_.date(), season=y, basis=how))
    imp = {y for y in imp_cerf | imp_emdat if y is not None}
    T["impact"] = [int(y in imp) for y in T.index]; T["impact_cerf"] = [int(y in imp_cerf) for y in T.index]; T["impact_emdat"] = [int(y in imp_emdat) for y in T.index]
    T["impact_plus_undated"] = [int(y in (imp | {u for u in imp_undated if u})) for y in T.index]
    if c.get("bad_years"): T["bad_year"] = [int(y in set(c["bad_years"])) for y in T.index]
    T = T.loc[[y for y in T.index if 2001 <= y <= 2025]]
    T.index.name = "year"; T.to_csv(f"{OUT}/{iso}.csv")
    summary[iso] = dict(asap_units=int(len(units)), aoi_units=len(aoi_units) if aoi_units else 0, aoi_names=[units.set_index('region_id').region_name[u] for u in (aoi_units or [])][:12], src=os.path.basename(src["temp_crop"] or ""), impact=sorted(imp), cerf=sorted(x for x in imp_cerf if x), emdat=sorted(x for x in imp_emdat if x), cols=len(T.columns))
    print(iso, summary[iso])
pd.DataFrame(dating_rows).to_csv(f"{OUT}/impact_dating.csv", index=False)
json.dump(summary, open(f"{OUT}/summary.json", "w"), indent=1, default=str)
