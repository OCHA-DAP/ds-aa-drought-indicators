"""Render the Pages site: the consolidated report at pages/indicators-vs-impact/ (summary matrix from
results/summary.json, per-country heatmaps, subnational panel and GDHY tables, literature, design notes) and one
page per country. Plain HTML + inline SVG, team template. Text partials: pages/_intro.html, _reading.html,
_literature.html, _closing.html."""
import html, json, os, sys
import numpy as np, pandas as pd

S = sys.argv[1]; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = json.load(open(f"{S}/results/results.json")); SUM = json.load(open(f"{S}/results/summary.json"))
PAN = json.load(open(f"{S}/results/panel.json")); GD = json.load(open(f"{S}/results/gdhy.json")); CFG = json.load(open(f"{ROOT}/data/config/countries.json")); CFG.pop("_notes", None)
DATING = pd.read_csv(f"{S}/tables/impact_dating.csv")
PAGES = f"{ROOT}/pages"; PRODUCT = "indicators-vs-impact"; PROD = f"{PAGES}/{PRODUCT}"; os.makedirs(PROD, exist_ok=True)
esc = html.escape
IND = {"t_dt": "Temperature", "z_dt": "Biomass (zFPARc)", "rain": "Rainfall (CHIRPS/ASAP)", "era5": "Rainfall (ERA5)", "wsi": "Water balance", "spi": "SPI-3", "asi": "FAO ASI", "mvhi": "FAO mean VHI"}
SHORT = {"t_dt": "Temp.", "z_dt": "zFPARc", "rain": "Rain CHIRPS", "era5": "Rain ERA5", "wsi": "WSI", "spi": "SPI-3", "asi": "ASI", "mvhi": "VHI"}
ORDER = ["t_dt", "z_dt", "asi", "mvhi", "rain", "era5", "spi", "wsi"]
INK = "#1f2324"; MUTED = "#5e6a6b"; FAINT = "#7e8e8f"; GRID = "#e2e8e8"; ACC = "#1e795f"; RED = "#9d372b"; BLUE = "#1862d8"
CSS = open(f"{ROOT}/pages/assets/page.css").read()
countries = [k for k in CFG if k in R]

def lerp(c1, c2, f):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))
def col_pos(v, lim):  # 0..lim -> white..green; negative -> light red
    if v is None or v != v: return "#f5f7f7"
    return lerp("#ffffff", "#1e795f", min(1, v / lim)) if v > 0 else lerp("#ffffff", "#e7b5af", min(1, -v / lim))

def heatmap(metric, title, tid, lim, fmt, scope="nat", target="impact"):
    cw, ch = 74, 26; lx = 150; ty = 34; W = lx + cw * len(ORDER) + 20; H = ty + ch * len(countries) + 20
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" font-family="Roboto,system-ui,sans-serif" role="img" aria-labelledby="{tid}"><title id="{tid}">{esc(title)}</title>']
    for j, k in enumerate(ORDER):
        x = lx + j * cw + cw / 2
        o.append(f'<text x="{x}" y="{ty - 10}" text-anchor="middle" font-size="10" fill="{MUTED}">{esc(SHORT[k])}</text>')
    for i, iso in enumerate(countries):
        y = ty + i * ch; sc = R[iso]["scopes"].get(scope) or R[iso]["scopes"].get("nat")
        o.append(f'<text x="{lx - 8}" y="{y + ch / 2 + 4}" text-anchor="end" font-size="11" fill="{INK}">{esc(CFG[iso]["name"])}</text>')
        for j, k in enumerate(ORDER):
            x = lx + j * cw
            if metric == "loo": v = sc["single"].get(k, {}).get("loo")
            elif metric == "r2": v = sc["single"].get(k, {}).get("r2")
            else: v = sc["auc"].get(target, {}).get("auc", {}).get(k); v = None if v is None else v - 0.5
            if v is None: o.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="3" fill="#fff" stroke="{GRID}"/>'); continue
            tip = esc("%s — %s: %s" % (CFG[iso]["name"], IND[k], fmt(v)))
            o.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="3" fill="{col_pos(v, lim)}"><title>{tip}</title></rect>')
            o.append(f'<text x="{x + cw / 2}" y="{y + ch / 2 + 3.5}" text-anchor="middle" font-size="10" fill="{INK}">{fmt(v)}</text>')
    o.append("</svg>"); return "\n".join(o)

def page(title, body, back="../", back_label="Drought indicators vs impact"):
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@700&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<a class="home-link" href="{back}">← {esc(back_label)}</a>
<div class="wrap">{body}</div></body></html>"""

def fmt2(v): return f"{v:+.2f}"
def fmtauc(v): return f"{v + 0.5:.2f}"

# ---------------- country pages
for iso in countries:
    c = CFG[iso]; r = R[iso]; T = pd.read_csv(f"{S}/tables/{iso}.csv", index_col=0)
    parts = [f"<h1>{esc(c['name'])}: which indicators track drought impact?</h1>",
             f"<p class='sub'>{esc(c['framework'])}. Main season used here: {esc(c['seasons'][0]['label'])}. Production target: {esc(', '.join(c['staples']))} (FAOSTAT, national, % from 2001–2024 trend).</p>"]
    for scope in ["aoi", "nat"]:
        sc = r["scopes"].get(scope)
        if not sc: continue
        parts.append(f"<h2>{'Framework area' if scope == 'aoi' else 'National mean of ASAP units'}</h2>")
        parts.append("<div class='tblwrap'><table><tr><th>Indicator</th><th class='num'>r with production</th><th class='num'>R²</th><th class='num'>Leave-one-out R²</th><th>p</th><th class='num'>AUC, impact seasons</th><th class='num'>AUC, CERF-dated</th><th class='num'>AUC, EM-DAT</th>" + ("<th class='num'>AUC, framework bad years</th>" if "bad_year" in sc["auc"] else "") + "</tr>")
        for k in ORDER:
            s = sc["single"].get(k)
            if not s: continue
            a = sc["auc"]
            def ga(t): v = a.get(t, {}).get("auc", {}).get(k); return "—" if v is None else f"{v:.2f}"
            parts.append(f"<tr><td>{esc(IND[k])}</td><td class='num'>{s['r']:+.2f}</td><td class='num'>{s['r2']:.2f}</td><td class='num'>{s['loo']:+.2f}</td><td><span class='tag {'sig' if s['p'] < 0.05 else 'ns'}'>{s['p']:.3f}</span></td><td class='num'>{ga('impact')}</td><td class='num'>{ga('impact_cerf')}</td><td class='num'>{ga('impact_emdat')}</td>" + (f"<td class='num'>{ga('bad_year')}</td>" if "bad_year" in a else "") + "</tr>")
        parts.append("</table></div>")
        if sc["combo"]:
            parts.append("<div class='tblwrap'><table><tr><th>Combination</th><th class='num'>R²</th><th class='num'>Leave-one-out R²</th><th>Coefficients (z per sd)</th></tr>")
            for k, v in sc["combo"].items():
                lab = esc(" + ".join(IND[x] for x in k.split("+"))); co = esc(", ".join("%+.2f (p %.3f)" % (c, pp) for c, pp in zip(v["coefs"], v["p"])))
                parts.append(f"<tr><td>{lab}</td><td class='num'>{v['r2']:.2f}</td><td class='num'>{v['loo']:+.2f}</td><td>{co}</td></tr>")
            parts.append("</table></div>")
        if sc["quad"]:
            parts.append("<h3>Hot vs cool, low vs high biomass (median splits)</h3><div class='tblwrap'><table><tr><th>Quadrant</th><th class='num'>Seasons</th><th class='num'>Mean production anomaly</th><th class='num'>Impact-season rate</th><th>Seasons</th></tr>")
            for k, v in sc["quad"].items():
                pm = "" if v["prod_mean"] is None else "%+.1f%%" % v["prod_mean"]; ir = "" if v["impact_rate"] is None else "%.0f%%" % (100 * v["impact_rate"]); yrs = esc(", ".join(map(str, v["years"])))
                parts.append(f"<tr><td>{esc(k)}</td><td class='num'>{v['n']}</td><td class='num'>{pm}</td><td class='num'>{ir}</td><td>{yrs}</td></tr>")
            parts.append("</table></div>")
        a = sc["auc"].get("impact")
        if a: parts.append("<p>Impact seasons (%d): %s.</p>" % (a["n_pos"], esc(", ".join(map(str, a["pos_years"])))))
    d = DATING[DATING.iso3 == iso]
    parts.append("<h2>How impact records were dated to seasons</h2><div class='tblwrap'><table><tr><th>Record</th><th>Period</th><th class='num'>Season</th><th>Rule</th></tr>")
    for x in d.itertuples():
        en = esc(str(x.end)) if pd.notna(x.end) else ""; se = "" if pd.isna(x.season) else str(int(x.season))
        parts.append(f"<tr><td>{esc(x.record)}</td><td>{esc(str(x.start))} → {en}</td><td class='num'>{se}</td><td>{esc(x.basis)}</td></tr>")
    parts.append("</table></div>")
    parts.append("<h2>Season table</h2><div class='tblwrap'>" + T.round(2).to_html(border=0, classes="data") + "</div>")
    os.makedirs(f"{PROD}/{iso.lower()}", exist_ok=True)
    open(f"{PROD}/{iso.lower()}/index.html", "w").write(page(f"{c['name']} — drought indicators vs impact", "\n".join(parts)))

# ---------------- report
PIND = ["t_dt", "z_dt", "asi", "mvhi", "rain", "spi", "wsi"]   # panel indicators (no ERA5 at unit level)
def lerpc(v, lim):
    if v is None or v != v: return "#f5f7f7"
    return lerp("#ffffff", "#1e795f", min(1, v / lim)) if v > 0 else lerp("#ffffff", "#e7b5af", min(1, -v / lim))
def cell(v, lim, fmt="%+.2f", flip=1):
    if v is None or v != v: return '<td class="num" style="background:#f5f7f7">–</td>'
    return '<td class="num" style="background:%s">%s</td>' % (lerpc(v * flip, lim), fmt % v)
SIGNP = {"t_dt": -1, "asi": -1}
def rcell(v, k, lim=0.7): return cell(v, lim, flip=SIGNP.get(k, 1))
NAMES = {**IND, "t_dt+asi": "Temperature + ASI", "t_dt+mvhi": "Temperature + VHI", "t_dt+z_dt": "Temperature + biomass", "t_dt+rain": "Temperature + rainfall"}

def summary_matrix():
    C = SUM["columns"]; rows = SUM["rows"]; keys = list(C)
    o = ['<div class="tblwrap"><table class="data"><tr><th>Indicator</th>']
    for c in keys: o.append('<th class="num">%s<br><span style="font-weight:400;color:#5e6a6b">%s</span></th>' % (esc(C[c]["label"]), esc(C[c]["metric"])))
    o.append("</tr>")
    for k, r in rows.items():
        o.append("<tr><td>%s</td>" % esc(NAMES.get(k, k)))
        for c in keys:
            v = r.get(c)
            if v is None or v != v: o.append(cell(None, 1))
            elif C[c]["kind"] == "binary": o.append('<td class="num" style="background:%s">%.2f</td>' % (lerpc(v - 0.5, 0.3), v))   # coloured by distance from chance
            else: o.append(cell(v, 0.2 if c == "faostat" else 0.05, "%.2f" if c == "faostat" else "%.3f"))
        o.append("</tr>")
    o.append("</table></div>")
    o.append("<p class='meta'>Columns: " + " ".join("<strong>%s</strong>: %s" % (esc(C[c]["label"]), esc(C[c].get("note", ""))) for c in keys) + "</p>")
    return "".join(o)

NOTES = {"AFG": "wheat, provinces, calendar year", "BFA": "millet + sorghum, provinces, main season", "ETH": "5 cereals, zones, Meher (56 of 95 zone names matched)",
         "KEN": "maize, districts to 2012 then counties", "GTM": "maize Primera, departments; production only", "SLV": "maize, departments; annual to 2012, Primera from 2013",
         "MRT": "sorghum + millet + maize, wilayas", "NER": "millet + sorghum, departments (69 of 90 matched)"}
def tab_panel():
    o = ['<div class="tblwrap"><table class="data"><tr><th>Country</th><th>FEWS NET series</th><th class="num">Units</th><th class="num">Obs.</th><th>Years</th>'] + [f'<th class="num">{SHORT[k]}</th>' for k in PIND] + ["</tr>"]
    for iso in CFG:
        if iso not in PAN: continue
        r = PAN[iso]; sc = r["scopes"]["all"]["target"]; t = sc["log_yield_w"]["single"] or sc["log_prod_w"]["single"]; tag = "" if sc["log_yield_w"]["single"] else " (production)"
        o.append(f'<tr><td>{esc(CFG[iso]["name"])}{tag}</td><td>{esc(NOTES.get(iso, ""))}</td><td class="num">{r["n_units"]}</td><td class="num">{r["n_obs"]}</td><td>{r["years"][0]}–{r["years"][1]}</td>')
        for k in PIND: o.append(cell(t.get(k, {}).get("loyo"), 0.3))
        o.append("</tr>")
    p = PAN["_pooled"]["log_yield_w"]["single"]
    o.append('<tr><td><strong>Pooled</strong></td><td>seven countries with yield</td><td class="num">%d</td><td class="num">%d</td><td>2001–2025</td>' % (sum(PAN[i]["n_units"] for i in PAN if i != "_pooled"), p["t_dt"]["n"]))
    for k in PIND: o.append(cell(p.get(k, {}).get("loyo"), 0.3))
    o.append("</tr></table></div>"); return "".join(o)
def tab_aoi():
    o = ['<div class="tblwrap"><table class="data"><tr><th>Country</th><th>Framework area</th><th class="num">Units</th><th class="num">Obs.</th>'] + [f'<th class="num">{SHORT[k]}</th>' for k in PIND] + ["</tr>"]
    for iso in CFG:
        a = PAN.get(iso, {}).get("scopes", {}).get("aoi")
        if not a: continue
        t = a["target"]["log_yield_w"]["single"] or a["target"]["log_prod_w"]["single"]; names = CFG[iso].get("aoi") or CFG[iso].get("aoi_asap") or []
        o.append(f'<tr><td>{esc(CFG[iso]["name"])}</td><td>{esc(", ".join(names[:6]) + (" …" if len(names) > 6 else ""))}</td><td class="num">{a["n_units"]}</td><td class="num">{a["n_obs"]}</td>')
        for k in PIND: o.append(cell(t.get(k, {}).get("loyo"), 0.3))
        o.append("</tr>")
    o.append("</table></div>"); return "".join(o)
def tab_agg(slot):
    o = ['<div class="tblwrap"><table class="data"><tr><th>Country</th><th class="num">Years</th><th class="num">r with FAOSTAT</th>'] + [f'<th class="num">{SHORT[k]}</th>' for k in PIND] + ["</tr>"]
    for iso in CFG:
        if iso not in PAN or "year_aggregate" not in PAN[iso]: continue
        a = PAN[iso]["year_aggregate"]; sng = a.get(slot, {}); rf = a.get("r_faostat")
        o.append(f'<tr><td>{esc(CFG[iso]["name"])}</td><td class="num">{a["n_years"]}</td>{cell(rf, 1.0)}')
        for k in PIND: o.append(rcell(sng.get(k, {}).get("r"), k))
        o.append("</tr>")
    o.append("</table></div>"); return "".join(o)
def tab_gdhy():
    o = ['<div class="tblwrap"><table class="data"><tr><th>Country, crop</th><th class="num">Cells</th><th class="num">r with FAOSTAT</th>'] + [f'<th class="num">{SHORT[k]}</th>' for k in PIND] + ['<th>Best admin-1 LOYO</th></tr>']
    for iso in CFG:
        for crop, c in GD.get(iso, {}).get("crops", {}).items():
            if "national" not in c: continue
            n = c["national"]; o.append(f'<tr><td>{esc(CFG[iso]["name"])}, {crop}</td><td class="num">{c["cells"]}</td>{cell(n["r_faostat"], 1.0)}')
            for k in PIND: o.append(rcell(n["ind"].get(k), k))
            a = c.get("admin1", {}); best = max(a.items(), key=lambda kv: kv[1]["loyo"]) if a else None
            o.append("<td>%s</td></tr>" % (f"{SHORT[best[0]]} {best[1]['loyo']:+.2f}" if best else "–"))
    o.append("</table></div>"); return "".join(o)

P = R["_pooled"]; body = [open(f"{ROOT}/pages/_intro.html").read()]
body.append("<h2>Summary: indicators against ground truths</h2>")
body.append("<p>The primary output. Rows are indicators (and the combinations tested), columns are ground truths. Continuous "
            "targets get an out-of-sample R² (leave-one-out for the national series, leave-one-year-out for the subnational panels); binary targets "
            "get an AUC computed from within-country (positive, negative) season pairs, 0.5 being chance. All pooled across countries with every series "
            "standardised within its country or unit, so only year-to-year variation is compared. Green is better; the colour scale differs by column.</p>")
body.append(summary_matrix())
body.append("""<h2>What was tested</h2>
<ul>
  <li><strong>Indicators</strong>, all from the JRC ASAP per-admin export (one consistent route, 2001 onward): temperature (ECMWF reanalysis,
      cropland), rainfall (CHIRPS), SPI-3, water satisfaction index (WSI), cumulative-FPAR anomaly (zFPARc). Plus ERA5 monthly rainfall from the
      team database and FAO GIEWS ASIS at admin 1: the Agricultural Stress Index (share of cropland under stress) and mean VHI. Temperature and
      biomass are detrended per unit, so "hot" means hotter than that year would be expected to be.</li>
  <li><strong>Season and area.</strong> Each country's main growing season; indicators averaged over the framework area and over all ASAP
      units (country pages show both); biomass, WSI and SPI-3 over the last 60 percent of the season, where the trigger windows sit.</li>
  <li><strong>Ground truths.</strong> (1) National production of the country's staples, FAOSTAT, percent departure from a 2001 to 2024 trend.
      (2) Seasons with a CERF drought allocation dated to that season by the CERF supplement's rainfall-deficit period, or an EM-DAT drought event
      that follows it. (3) The bad years each framework documents (five countries). (4) Official province or district yields from the FEWS NET
      Data Warehouse, eight countries, within-unit. (5) The same restricted to framework-area units. (6) GDHY gridded maize and wheat yields at
      admin 1, 2001 to 2016, as a secondary check.</li>
</ul>""")
body.append("<h2>By country: national production and the binary records</h2>")
body.append("<figure>" + heatmap("loo", "Leave-one-out R² of each indicator against the national staple production anomaly, main season, national mean", "h1", 0.4, fmt2) +
            "<figcaption><strong>Figure 1.</strong> Leave-one-out R² against the FAOSTAT production anomaly, national mean of ASAP units. Negative means worse than predicting the mean.</figcaption></figure>")
body.append("<figure>" + heatmap("auc", "AUC of each indicator for ranking the impact seasons (CERF-dated and EM-DAT)", "h2", 0.4, fmtauc) +
            "<figcaption><strong>Figure 2.</strong> AUC for ranking CERF and EM-DAT drought seasons above the others. Blank where a country has no negative or no positive seasons.</figcaption></figure>")
body.append("<figure>" + heatmap("auc", "AUC of each indicator for ranking the framework-documented bad years", "h3", 0.4, fmtauc, target="bad_year") +
            "<figcaption><strong>Figure 3.</strong> AUC for ranking the bad years documented in each framework; only five frameworks list them.</figcaption></figure>")
body.append("<h3>Pooled regressions on national production (each series standardised within its country)</h3><div class='tblwrap'><table><tr><th>Indicator</th><th class='num'>n season-years</th><th class='num'>r</th><th class='num'>R²</th><th class='num'>Leave-one-out R²</th><th>p</th></tr>")
for k in ORDER:
    v = P["regression"].get(k)
    if not v: continue
    body.append(f"<tr><td>{esc(IND[k])}</td><td class='num'>{v['n']}</td><td class='num'>{v['r']:+.2f}</td><td class='num'>{v['r2']:.2f}</td><td class='num'>{v['loo']:+.2f}</td><td><span class='tag {'sig' if v['p'] < 0.05 else 'ns'}'>{v['p']:.4f}</span></td></tr>")
body.append("</table></div><div class='tblwrap'><table><tr><th>Combination</th><th class='num'>R²</th><th class='num'>Leave-one-out R²</th><th>Coefficients</th></tr>")
for k, v in P["regression"].items():
    if "+" not in k: continue
    lab = esc(" + ".join(IND[x] for x in k.split("+"))); co = esc(", ".join("%+.2f (p %.4f)" % (c, pp) for c, pp in zip(v["coefs"], v["p"])))
    body.append(f"<tr><td>{lab}</td><td class='num'>{v['r2']:.2f}</td><td class='num'>{v['loo']:+.2f}</td><td>{co}</td></tr>")
body.append("</table></div>")
body.append("""<h2>By country: official subnational yields (FEWS NET Data Warehouse)</h2>
<p>Official government production statistics compiled by FEWS NET, at the finest level with a usable series. Each unit's log yield and each
   indicator (ASAP unit statistics, FAO ASI and VHI at admin 1) are detrended and standardised within the unit. Leave-one-year-out R² holds out
   all units of a year together, the honest test for a trigger that has to call a new year. Green means the indicator predicts something out of
   sample.</p>""")
body.append(tab_panel())
body.append("""<p>Only Afghanistan (temperature 0.14, SPI-3 and ASI 0.10) and Niger (water balance 0.12, temperature 0.10) show out-of-sample
   skill at the unit level; Burkina Faso, where the national temperature signal is clear, shows none at province level with any indicator.
   Pooled, every coefficient has the expected sign and is significant (n above 4,300), but explained variance is small. The ranking matches the
   national study: VHI and ASI first, then water balance and temperature, the NDVI-only biomass anomaly last.</p>
<h3>Framework-area units only</h3>
<p>Restricting to units inside each framework's area changes the picture where that area is small and drought-prone: Burkina Faso's four
   trigger provinces and Afghanistan's five framework provinces show real unit-level skill, led by water balance and ASI with temperature a step
   behind. The large Ethiopian and Kenyan areas show nothing, and dominate the pooled framework-area column of the summary table.</p>""")
body.append(tab_aoi())
body.append("""<h3>Aggregated back to the national year</h3>
<p>Averaging the within-unit standardised series over all units of a year gives a national series built from the official subnational
   statistics. The second column is its agreement with the FAOSTAT anomaly used above; the rest is its correlation with the national mean of
   each indicator, green when the sign is the expected one. Yield first, then production.</p>""")
body.append(tab_agg("single")); body.append(tab_agg("single_prod"))
body.append("""<p>The two sources agree closely (r 0.83 to 0.90) in Afghanistan, Burkina Faso, Niger and Mauritania, moderately in Ethiopia and
   Kenya, poorly in El Salvador, and Guatemala has only ten years. Where they agree the national ranking reappears: Afghanistan temperature −0.73
   with aggregated yield and VHI, ASI, water balance and temperature all around 0.7 with aggregated production; Niger water balance 0.64,
   temperature −0.59, VHI 0.59; Mauritania VHI 0.70 and temperature −0.61 on production; Burkina Faso temperature −0.48 on production against
   −0.56 with FAOSTAT. The biomass anomaly is never above 0.6 and often has the wrong sign. Ethiopia (temperature with the wrong sign), Kenya,
   Guatemala and El Salvador show nothing consistent.</p>
<h2>A second yield dataset: GDHY</h2>
<p>The Global Dataset of Historical Yields (Iizumi and Sakai 2020, <a href="https://doi.org/10.1038/s41597-020-0433-7">doi:10.1038/s41597-020-0433-7</a>)
   gives 0.5-degree maize, wheat, rice and soybean yields for 1981 to 2016 and is the dataset several of the global studies below use. Two limits
   here: no millet or sorghum, so the Sahel staples are not covered; and it blends national statistics with satellite NDVI, so agreement with
   vegetation indicators is partly circular. National and admin-1 means, detrended 1996 to 2016, analysed 2001 to 2016.</p>""")
body.append(tab_gdhy())
body.append("""<p>GDHY agrees only weakly with FAOSTAT in these countries (r 0.5 to 0.6 in Kenya, Guatemala and Mauritania, near zero or negative
   elsewhere) and Honduras and El Salvador have five cells each. Where usable it points the same way (Mauritanian maize follows temperature −0.66
   and rainfall and water balance 0.7; Ethiopian wheat temperature −0.70, ASI and VHI 0.7; Kenyan maize and wheat ASI and VHI 0.45 to 0.65). At
   admin 1 the pooled panel explains almost nothing, and its best indicator is the circular one. GDHY neither contradicts nor strengthens the
   result.</p>""")
body.append(open(f"{ROOT}/pages/_reading.html").read())
body.append(open(f"{ROOT}/pages/_literature.html").read())
body.append(open(f"{ROOT}/pages/_closing.html").read())
body.append("<h2>Country pages</h2><p>Each page shows both scopes (framework area and national), all binary targets, the quadrant split, how impact records were dated, and the season table.</p><div class='grid'>" +
            "".join("<a class='k' href='%s/'><h2>%s</h2><p>%s</p><span class='foot'><em>/%s/</em></span></a>" % (iso.lower(), esc(CFG[iso]["name"]), esc(CFG[iso]["framework"]), iso.lower()) for iso in countries) + "</div>")
open(f"{PROD}/index.html", "w").write(page("Drought indicators vs impact", "\n".join(body), back="../", back_label="Drought AA indicators"))
# the former /robustness/ page now redirects to the consolidated report
os.makedirs(f"{PAGES}/robustness", exist_ok=True)
open(f"{PAGES}/robustness/index.html", "w").write('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=../indicators-vs-impact/"><title>Moved</title></head><body><p>This page was folded into <a href="../indicators-vs-impact/">the consolidated report</a>.</p></body></html>')
print("site written:", countries)
