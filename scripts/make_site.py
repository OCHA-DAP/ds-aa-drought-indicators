"""Render the Pages site from results/results.json and tables/: landing page with the
cross-country summary and one page per country. Plain HTML + inline SVG, team template."""
import html, json, os, sys
import numpy as np, pandas as pd

S = sys.argv[1]; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = json.load(open(f"{S}/results/results.json")); CFG = json.load(open(f"{ROOT}/data/config/countries.json")); CFG.pop("_notes", None)
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

def heatmap(metric, title, tid, lim, fmt, scope="nat"):
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
            else: v = sc["auc"].get("impact", {}).get("auc", {}).get(k); v = None if v is None else v - 0.5
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

# ---------------- landing: summary
P = R["_pooled"]
body = [open(f"{ROOT}/pages/_landing_intro.html").read() if os.path.exists(f"{ROOT}/pages/_landing_intro.html") else "<h1>Drought indicators vs impact</h1>"]
body.append("<h2>Cross-country summary</h2>")
body.append("<figure>" + heatmap("loo", "Leave-one-out R² of each indicator against the national staple production anomaly, main season, national mean", "h1", 0.4, fmt2) + "<figcaption><strong>Figure 1.</strong> Leave-one-out R² of each single indicator against the national staple production anomaly (main growing season, national mean of ASAP units). Green = the indicator predicts production out of sample; red = worse than the mean. Hover for values.</figcaption></figure>")
body.append("<figure>" + heatmap("auc", "AUC of each indicator for ranking the impact seasons (CERF-dated and EM-DAT)", "h2", 0.4, fmtauc) + "<figcaption><strong>Figure 2.</strong> AUC for ranking the impact seasons (CERF drought allocations dated to their deficit season, plus EM-DAT drought events): 0.5 is chance. Hover for values.</figcaption></figure>")
body.append("<h3>Pooled across countries (each series standardised within its country)</h3><div class='tblwrap'><table><tr><th>Indicator</th><th class='num'>n season-years</th><th class='num'>r</th><th class='num'>R²</th><th class='num'>Leave-one-out R²</th><th>p</th><th class='num'>AUC, impact seasons</th></tr>")
for k in ORDER:
    v = P["regression"].get(k)
    if not v: continue
    body.append(f"<tr><td>{esc(IND[k])}</td><td class='num'>{v['n']}</td><td class='num'>{v['r']:+.2f}</td><td class='num'>{v['r2']:.2f}</td><td class='num'>{v['loo']:+.2f}</td><td><span class='tag {'sig' if v['p'] < 0.05 else 'ns'}'>{v['p']:.4f}</span></td><td class='num'>{P['auc_impact'].get(k, float('nan')):.2f}</td></tr>")
body.append("</table></div><div class='tblwrap'><table><tr><th>Combination</th><th class='num'>R²</th><th class='num'>Leave-one-out R²</th><th>Coefficients</th></tr>")
for k, v in P["regression"].items():
    if "+" not in k: continue
    lab = esc(" + ".join(IND[x] for x in k.split("+"))); co = esc(", ".join("%+.2f (p %.4f)" % (c, pp) for c, pp in zip(v["coefs"], v["p"])))
    body.append(f"<tr><td>{lab}</td><td class='num'>{v['r2']:.2f}</td><td class='num'>{v['loo']:+.2f}</td><td>{co}</td></tr>")
body.append("</table></div>")
body.append("<h2>Countries</h2><div class='grid'>" + "".join("<a class='k' href='%s/'><h2>%s</h2><p>%s</p><span class='foot'><em>/%s/</em></span></a>" % (iso.lower(), esc(CFG[iso]["name"]), esc(CFG[iso]["framework"]), iso.lower()) for iso in countries) + "</div>")
if os.path.exists(f"{ROOT}/pages/_landing_outro.html"): body.append(open(f"{ROOT}/pages/_landing_outro.html").read())
open(f"{PROD}/index.html", "w").write(page("Drought indicators vs impact", "\n".join(body), back="../", back_label="Drought AA indicators"))
print("site written:", countries)
