"""Render pages/robustness/index.html: literature context, the subnational official-statistics panel
(results/panel.json), and the GDHY gridded-yield cross-check (results/gdhy.json)."""
import html, json, os, sys
S = sys.argv[1]; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAN = json.load(open(f"{S}/results/panel.json")); GD = json.load(open(f"{S}/results/gdhy.json")); NAT = json.load(open(f"{S}/results/results.json"))
CFG = json.load(open(f"{ROOT}/data/config/countries.json")); CFG.pop("_notes", None)
OUT = f"{ROOT}/pages/robustness"; os.makedirs(OUT, exist_ok=True); esc = html.escape
CSS = open(f"{ROOT}/pages/assets/page.css").read()
IND = ["t_dt", "z_dt", "asi", "mvhi", "rain", "spi", "wsi"]; SHORT = {"t_dt": "Temp.", "z_dt": "zFPARc", "asi": "ASI", "mvhi": "VHI", "rain": "Rain", "spi": "SPI-3", "wsi": "WSI"}
SIGN = {"t_dt": -1, "asi": -1}
def lerp(c1, c2, f):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))
def col(v, lim):
    if v is None or v != v: return "#f5f7f7"
    return lerp("#ffffff", "#1e795f", min(1, v / lim)) if v > 0 else lerp("#ffffff", "#e7b5af", min(1, -v / lim))
def cell(v, lim, fmt="%+.2f", flip=1):
    if v is None or v != v: return '<td class="num" style="background:#f5f7f7">–</td>'
    return '<td class="num" style="background:%s">%s</td>' % (col(v * flip, lim), fmt % v)
def rcell(v, k, lim=0.7):   # correlation coloured by whether it has the expected sign
    return cell(v, lim, flip=SIGN.get(k, 1))

NOTES = {"AFG": "wheat, provinces, calendar year", "BFA": "millet + sorghum, provinces, main season", "ETH": "5 cereals, zones, Meher (56 of 95 zone names matched to ASAP)",
         "KEN": "maize, districts to 2012 then counties", "GTM": "maize Primera, departments; production only (no area reported)", "SLV": "maize, departments; annual series to 2012, Primera from 2013 (kept as separate series)",
         "MRT": "sorghum + millet + maize, wilayas (ASAP moughataas averaged up)", "NER": "millet + sorghum, departments (69 of 90 matched)"}

# ---------- table A: within-unit panel
def tabA():
    o = ['<div class="tblwrap"><table class="data"><tr><th>Country</th><th>FEWS NET series</th><th class="num">Units</th><th class="num">Obs.</th><th>Years</th>'] + [f'<th class="num">{SHORT[k]}</th>' for k in IND] + ["</tr>"]
    for iso in CFG:
        if iso not in PAN: continue
        r = PAN[iso]; sc = r["scopes"]["all"]["target"]; t = sc["log_yield_w"]["single"] or sc["log_prod_w"]["single"]; tag = "" if sc["log_yield_w"]["single"] else " (production)"
        o.append(f'<tr><td>{esc(CFG[iso]["name"])}{tag}</td><td>{esc(NOTES.get(iso, ""))}</td><td class="num">{r["n_units"]}</td><td class="num">{r["n_obs"]}</td><td>{r["years"][0]}–{r["years"][1]}</td>')
        for k in IND: o.append(cell(t.get(k, {}).get("loyo"), 0.3))
        o.append("</tr>")
    p = PAN["_pooled"]["log_yield_w"]["single"]
    o.append('<tr><td><strong>Pooled</strong></td><td>seven countries with yield, within-unit standardised</td><td class="num">%d</td><td class="num">%d</td><td>2001–2025</td>' % (sum(PAN[i]["n_units"] for i in PAN if i != "_pooled"), p["t_dt"]["n"]))
    for k in IND: o.append(cell(p.get(k, {}).get("loyo"), 0.3))
    o.append("</tr></table></div>"); return "".join(o)

def tabPooled():
    p = PAN["_pooled"]["log_yield_w"]; o = ['<div class="tblwrap"><table class="data"><tr><th>Predictor(s)</th><th class="num">r</th><th class="num">Coefficient(s)</th><th class="num">LOYO R²</th><th class="num">n</th></tr>']
    for k in IND:
        v = p["single"].get(k)
        if not v: continue
        o.append(f'<tr><td>{esc(SHORT[k])}</td><td class="num">{v["r"]:+.2f}</td><td class="num">{v["coef"]:+.3f}</td>{cell(v["loyo"], 0.1, "%.3f")}<td class="num">{v["n"]}</td></tr>')
    for k, v in p["combo"].items():
        o.append(f'<tr><td>{esc(" + ".join(SHORT[x] for x in k.split("+")))}</td><td class="num">–</td><td class="num">{", ".join("%+.3f" % c for c in v["coefs"])}</td>{cell(v["loyo"], 0.1, "%.3f")}<td class="num">{v["n"]}</td></tr>')
    o.append("</table></div>"); return "".join(o)

def tabAgg(slot, label):
    o = [f'<div class="tblwrap"><table class="data"><tr><th>Country</th><th class="num">Years</th><th class="num">r with FAOSTAT</th>'] + [f'<th class="num">{SHORT[k]}</th>' for k in IND] + ["</tr>"]
    for iso in CFG:
        if iso not in PAN or "year_aggregate" not in PAN[iso]: continue
        a = PAN[iso]["year_aggregate"]; s = a.get(slot, {})
        rf = a.get("r_faostat"); o.append(f'<tr><td>{esc(CFG[iso]["name"])}</td><td class="num">{a["n_years"]}</td>{cell(rf, 1.0) if rf is not None else "<td class=num>–</td>"}')
        for k in IND: o.append(rcell(s.get(k, {}).get("r"), k))
        o.append("</tr>")
    o.append("</table></div>"); return "".join(o)

def tabGD():
    o = ['<div class="tblwrap"><table class="data"><tr><th>Country, crop</th><th class="num">Cells</th><th class="num">r with FAOSTAT</th>'] + [f'<th class="num">{SHORT[k]}</th>' for k in IND] + ['<th>Best admin-1 LOYO</th></tr>']
    for iso in CFG:
        for crop, c in GD.get(iso, {}).get("crops", {}).items():
            if "national" not in c: continue
            n = c["national"]; rf = n["r_faostat"]
            o.append(f'<tr><td>{esc(CFG[iso]["name"])}, {crop}</td><td class="num">{c["cells"]}</td>{cell(rf, 1.0) if rf is not None else "<td class=num>–</td>"}')
            for k in IND: o.append(rcell(n["ind"].get(k), k))
            a = c.get("admin1", {}); best = max(a.items(), key=lambda kv: kv[1]["loyo"]) if a else None
            o.append("<td>%s</td></tr>" % (f"{SHORT[best[0]]} {best[1]['loyo']:+.2f}" if best else "–"))
    p = GD["_pooled"]; o.append('<tr><td><strong>Pooled admin-1 panel, LOYO R²</strong></td><td class="num">–</td><td class="num">–</td>' + "".join(cell(p.get(k, {}).get("loyo"), 0.1, "%.3f") for k in IND) + "<td>–</td></tr>")
    o.append("</table></div>"); return "".join(o)

def tabAOI():
    o = ['<div class="tblwrap"><table class="data"><tr><th>Country</th><th>Framework area</th><th class="num">Units</th><th class="num">Obs.</th>'] + [f'<th class="num">{SHORT[k]}</th>' for k in IND] + ["</tr>"]
    for iso in CFG:
        a = PAN.get(iso, {}).get("scopes", {}).get("aoi")
        if not a: continue
        t = a["target"]["log_yield_w"]["single"] or a["target"]["log_prod_w"]["single"]
        o.append(f'<tr><td>{esc(CFG[iso]["name"])}</td><td>{esc(", ".join((CFG[iso].get("aoi") or CFG[iso].get("aoi_asap") or [])[:6]) + (" …" if len(CFG[iso].get("aoi") or CFG[iso].get("aoi_asap") or []) > 6 else ""))}</td><td class="num">{a["n_units"]}</td><td class="num">{a["n_obs"]}</td>')
        for k in IND: o.append(cell(t.get(k, {}).get("loyo"), 0.3))
        o.append("</tr>")
    o.append("</table></div>"); return "".join(o)

# national headline numbers for the intro
pn = NAT["_pooled"]["nat"]["single"] if "_pooled" in NAT and "nat" in NAT["_pooled"] else None

body = f"""
<h1>How robust is the temperature finding? Literature, subnational yields and a second yield dataset</h1>
<p class="sub">Follow-up to <a href="../indicators-vs-impact/">Do temperature, rainfall and vegetation indicators predict drought impact?</a>
   Three checks: what the crop-climate literature says, whether the national result survives at the level of
   provinces and districts with official government production statistics (FEWS NET Data Warehouse), and whether a
   gridded yield dataset (GDHY) tells the same story.</p>

<div class="callout">
  <p><strong>Bottom line.</strong> The direction of the finding is well supported by the literature: statistical
     crop-climate studies for Africa and the Sahel consistently find that growing-season temperature explains as much
     or more of yield variation as rainfall, and that heat and drought damage are entangled. The subnational check
     both confirms and qualifies it. Aggregated to the national year, the official subnational statistics reproduce
     the national ranking in Afghanistan, Niger and Mauritania (temperature, water balance and VHI at the top, the
     biomass anomaly at the bottom) and weakly in Burkina Faso, and again show nothing in Ethiopia, Kenya and Central
     America. But <em>within</em> individual provinces and districts, every indicator explains very little of the
     year-to-year variation in official yields: pooled over 4,800 unit-years the best single indicator (VHI) reaches
     a leave-one-year-out R² of 0.04 and temperature 0.02, with all signs as expected and all coefficients
     significant. Official subnational yield series are noisy, and the relationships that are visible nationally
     are averages over that noise. GDHY, the gridded yield dataset, agrees too weakly with FAOSTAT in these countries
     (r 0.2 to 0.6, no millet or sorghum) to serve as an independent target. So: temperature deserves a place
     beside rainfall and vegetation indicators in trigger design, in the Sahel and Afghanistan in particular,
     but no indicator in this set, temperature included, predicts which province will have a bad year.</p>
</div>

<h2>1. What the literature says</h2>
<p>The result that surprised us, temperature outperforming rainfall and satellite vegetation as a predictor of
   staple-production shortfalls, is the mainstream finding of the statistical crop-climate literature for the
   tropics and Africa. The closest studies:</p>
<ul>
  <li><strong>Schlenker and Lobell (2010)</strong>, <em>Robust negative impacts of climate change on African
      agriculture</em>, Environmental Research Letters 5, 014010. Panel regressions of FAO national yields on
      growing-season weather for maize, sorghum, millet, groundnut and cassava across sub-Saharan Africa. Temperature,
      not precipitation, is the dominant driver of yield variation and of projected losses; the precipitation
      coefficients are small and often insignificant once temperature is in the model.
      <a href="https://doi.org/10.1088/1748-9326/5/1/014010">doi:10.1088/1748-9326/5/1/014010</a></li>
  <li><strong>Lobell, Bänziger, Magorokosho and Vivek (2011)</strong>, <em>Nonlinear heat effects on African maize as
      evidenced by historical yield trials</em>, Nature Climate Change 1, 42–45. Twenty thousand maize trials: each
      degree-day above 30 °C cut yield by about 1 percent under good rainfall and 1.7 percent under drought. Heat
      hurts most when the crop is also water-stressed, which is the interaction our hot-and-low-biomass quadrant
      picks up. <a href="https://doi.org/10.1038/nclimate1043">doi:10.1038/nclimate1043</a></li>
  <li><strong>Sultan et al. (2013)</strong>, <em>Assessing climate change impacts on sorghum and millet yields in the
      Sudanian and Sahelian savannas of West Africa</em>, Environmental Research Letters 8, 014040. Crop-model
      simulations across 35 stations: the yield response to warming is negative for all varieties regardless of the
      direction of rainfall change, so temperature dominates the Sahel signal. Directly relevant to Burkina Faso,
      Niger, Mauritania and Chad. <a href="https://doi.org/10.1088/1748-9326/8/1/014040">doi:10.1088/1748-9326/8/1/014040</a></li>
  <li><strong>Lobell and Burke (2008)</strong>, <em>Why are agricultural impacts of climate change so uncertain? The
      importance of temperature relative to precipitation</em>, Environmental Research Letters 3, 034007. Shows that
      for most crops and regions, uncertainty in the temperature response matters more than uncertainty in rainfall,
      and that statistical models attribute more yield variance to temperature.
      <a href="https://doi.org/10.1088/1748-9326/3/3/034007">doi:10.1088/1748-9326/3/3/034007</a></li>
  <li><strong>Ray, Gerber, MacDonald and West (2015)</strong>, <em>Climate variation explains a third of global crop
      yield variability</em>, Nature Communications 6, 5989. Gridded analysis: climate explains roughly a third of
      global yield variability, with large regional differences and both temperature and precipitation mattering.
      Consistent with our finding that a large share of the variance is not climatic at all, and that national
      production diverges from the framework area's weather in some countries.
      <a href="https://doi.org/10.1038/ncomms6989">doi:10.1038/ncomms6989</a></li>
  <li><strong>Vogel et al. (2019)</strong>, <em>The effects of climate extremes on global agricultural yields</em>,
      Environmental Research Letters 14, 054010. Random-forest models on GDHY yields: climate extremes explain 18 to
      43 percent of the interannual variance of maize, soybean, rice and spring-wheat yields, with temperature
      extremes carrying more weight than precipitation extremes in most regions, and hot-dry compound years the
      most damaging. <a href="https://doi.org/10.1088/1748-9326/ab154b">doi:10.1088/1748-9326/ab154b</a></li>
  <li><strong>Lesk, Rowhani and Ramankutty (2016)</strong>, <em>Influence of extreme weather disasters on global crop
      production</em>, Nature 529, 84–87. Using EM-DAT disasters against FAO production: droughts and extreme heat
      each cut national cereal production by about 9 to 10 percent; floods and cold had no measurable effect.
      Supports treating heat as an impact driver in its own right rather than a covariate of drought.
      <a href="https://doi.org/10.1038/nature16467">doi:10.1038/nature16467</a></li>
  <li><strong>Rojas, Vrieling and Rembold (2011)</strong>, <em>Assessing drought probability for agricultural areas in
      Africa with coarse resolution remote sensing imagery</em>, Remote Sensing of Environment 115, 343–352, and the
      FAO ASIS methodology built on it. The Agricultural Stress Index is derived from the Vegetation Health Index,
      which is an equal-weight blend of a vegetation condition index (NDVI) and a <em>temperature condition index</em>
      (land-surface temperature, after Kogan 1995). This is why ASI and VHI track temperature so closely in our
      results and outperform the NDVI-only zFPARc: they already contain half of the heat signal.
      <a href="https://doi.org/10.1016/j.rse.2010.09.006">doi:10.1016/j.rse.2010.09.006</a></li>
  <li><strong>Rembold et al. (2019)</strong>, <em>ASAP: a new global early warning system to detect anomaly hot spots of
      agricultural production for food security analysis</em>, Agricultural Systems 168, 247–257. Describes the
      warning system two of our frameworks trigger on; its indicators are rainfall, water balance and FPAR-based
      biomass, and temperature is provided as context rather than used in the warning classification.
      <a href="https://doi.org/10.1016/j.agsy.2018.07.002">doi:10.1016/j.agsy.2018.07.002</a></li>
</ul>
<p>Two literature caveats apply to us as much as to those studies. First, temperature and rainfall are negatively
   correlated in the Sahel growing season (dry years are hot years because of reduced cloud and evaporative
   cooling), so part of what "temperature" captures is the rainfall deficit measured more precisely, as the
   Burkina Faso water-balance comparison suggested. Second, the literature works with national or gridded
   yields, where aggregation averages out local noise; the subnational check below shows how much that matters.</p>

<h2>2. Subnational check: official production statistics per province</h2>
<p>Source: the FEWS NET Data Warehouse crop-production facts (official government statistics compiled by FEWS NET
   and its partners), for the staples and main season of each country, at the finest administrative level with a
   usable series. Yield is production over harvested area, falling back to planted area and then to the reported
   yield where area is missing; Guatemala reports production only. Chad has no series in the warehouse and Honduras
   only a national series to 2009, so both drop out. Each unit's log yield, log production and each indicator
   (the same ASAP unit statistics as the main study, FAO ASI and VHI at admin 1) are detrended linearly and
   standardised <em>within the unit</em>, so only year-to-year departures from the unit's own trend are compared.
   Leave-one-year-out R² holds out all units of a year together, which is the honest test for a trigger that has to
   call a new year.</p>

<h3>2a. Within-unit relationships</h3>
<p>Leave-one-year-out R² of the within-unit yield anomaly on each single indicator, all units. Green means the
   indicator predicts something out of sample; near zero or negative means it does not.</p>
{tabA()}
<p>Only Afghanistan (temperature 0.14, SPI and ASI 0.10) and Niger (water balance 0.12, temperature 0.10) show any
   out-of-sample skill at the unit level. Burkina Faso, where the national temperature signal was strongest, shows
   none at province level with any indicator. Pooled across the countries every coefficient has the expected
   sign and is significant at any conventional level (n above 4,300), but the explained variance is small:</p>
{tabPooled()}
<p>Two things are going on. Official subnational statistics carry substantial non-climatic noise (estimation
   methods, revisions, area-versus-yield attribution), which puts a low ceiling on any predictor. And the
   indicators are averaged over an administrative unit and a season, while damage depends on timing within the
   season and on where within the unit the crops are. The pooled ranking nevertheless matches the national study:
   VHI and ASI first, then water balance and temperature, with the NDVI-only biomass anomaly last.</p>
<p>Restricting the panel to the units inside each framework's area of interest changes the picture where the area
   is small and drought-prone. In Burkina Faso's four trigger provinces water balance reaches a leave-one-year-out
   R² of 0.25, SPI-3 and rainfall 0.15, temperature 0.12; in Afghanistan's five framework provinces ASI reaches
   0.33, VHI 0.26 and temperature 0.19. The large framework areas in Ethiopia and Kenya show nothing, as
   nationally. So the indicators do carry unit-level skill where the framework area was chosen for its exposure,
   and there the water-balance and ASIS indicators lead, with temperature a step behind.</p>
{tabAOI()}

<h3>2b. Aggregated back to the national year</h3>
<p>Averaging the within-unit standardised series over all units of a year gives a national series built from the
   official subnational statistics. Its correlation with the FAOSTAT production anomaly used in the main study
   (second column) shows how well the two sources agree; the remaining columns are its correlation with the
   national mean of each indicator (coloured green when the sign is the expected one). Yield first, then
   production.</p>
{tabAgg("single", "yield")}
{tabAgg("single_prod", "production")}
<p>The two statistical sources agree closely (r 0.83 to 0.90) in Afghanistan, Burkina Faso, Niger and Mauritania,
   moderately in Ethiopia and Kenya (0.64 and 0.71), poorly in El Salvador (0.37), and Guatemala has only ten
   years of production and no overlap to test. Where they agree, the ranking from the main study reappears: in Afghanistan temperature correlates
   −0.73 with aggregated yield and VHI, ASI, water balance and temperature all around 0.7 with aggregated
   production; in Niger water balance (0.64), temperature (−0.59) and VHI (0.59) lead; in Mauritania VHI (0.70)
   and temperature (−0.61) on production. In Burkina Faso the aggregated official statistics give temperature
   −0.48 on production, close to the −0.56 that FAOSTAT gave, with rainfall and VHI similar. The biomass anomaly
   is never above 0.6 and often has the wrong sign. Ethiopia (where temperature even carries the wrong sign,
   +0.35 on yield), Kenya, Guatemala and El Salvador show nothing consistent, as in the main study.</p>

<h2>3. A second yield dataset: GDHY</h2>
<p>The Global Dataset of Historical Yields (Iizumi and Sakai 2020, Scientific Data 7, 97;
   <a href="https://doi.org/10.1038/s41597-020-0433-7">doi:10.1038/s41597-020-0433-7</a>) gives 0.5-degree yields for
   maize, wheat, rice and soybean, 1981 to 2016. It is the dataset Vogel et al. (2019) used. Two limits for our
   purpose: it has no millet or sorghum, so the Sahel staples are not covered and only minor maize is available
   there; and it is built by blending national statistics with satellite NDVI, so agreement with vegetation
   indicators is partly circular. Cells were assigned to CODAB admin-1 units by their centre, national and admin-1
   mean yields detrended on 1996 to 2016 and analysed on 2001 to 2016.</p>
{tabGD()}
<p>GDHY agrees only weakly with FAOSTAT in these countries (r 0.5 to 0.6 in Kenya, Guatemala and Mauritania, near
   zero or negative in Niger, El Salvador and Ethiopian wheat), and Honduras and El Salvador have only five
   cells each. Where it is usable it points the same way: Mauritanian maize follows temperature (−0.66), rainfall
   and water balance (0.7); Ethiopian wheat follows temperature (−0.70), ASI and VHI (0.7) even though it does not
   follow FAOSTAT; Kenyan maize and wheat follow ASI and VHI (0.45 to 0.65) more than temperature. At admin 1 the
   pooled panel again explains almost nothing (best single indicator zFPARc, LOYO R² 0.02, which is the circular
   one). GDHY is not an independent check here; it neither contradicts nor strengthens the result.</p>

<h2>4. What this means for the conclusions</h2>
<ul>
  <li><strong>Holds:</strong> at the scale of a country-season, growing-season temperature is among the best
      predictors of staple-production shortfalls in Afghanistan, Niger, Mauritania and Burkina Faso, with a second
      independent production dataset, and the NDVI-only biomass anomaly is consistently the weakest. This matches
      the peer-reviewed literature on African and Sahelian crops.</li>
  <li><strong>Holds, and is now better understood:</strong> FAO ASI and VHI beat the ASAP biomass anomaly because
      VHI contains a land-surface-temperature term. Frameworks that want a single satellite indicator with a heat
      component already have one.</li>
  <li><strong>Qualified:</strong> none of the indicators, temperature included, predicts which province or district
      will have a bad year, at least as measured by official yield statistics. Triggers defined on a handful of
      admin-2 units should not be expected to have much skill against locally reported outcomes, whatever
      indicator they use; the evidence for skill is at the scale of a region or country.</li>
  <li><strong>Unchanged:</strong> Ethiopia, Kenya and the Dry Corridor show no usable relationship with any
      indicator in any of the three datasets, which points to targets (national totals, bimodal seasons, Meher
      versus Belg, subsistence versus commercial areas) rather than to the indicators.</li>
  <li><strong>Still to do:</strong> a subnational impact target that is not a yield statistic (IPC phase 3+
      population by admin unit, which the team database holds from 2017, or FEWS NET classifications) would test the
      provincial question with less measurement noise, over a shorter record.</li>
</ul>

<h2>Data notes</h2>
<ul>
  <li>FEWS NET Data Warehouse: <code>https://fdw.fews.net/api/cropproductionfacts/?country_code=&lt;ISO2&gt;&amp;format=csv</code>,
      pulled 18 September 2026. Rows with status "Missing Historic Data" or "Not Available" have no value; where a
      unit-year-product has an "All (PS)" production-system row it is used, otherwise the systems are summed.
      Series: {"; ".join(f"{CFG[i]['name']}: {NOTES[i]}" for i in NOTES)}.</li>
  <li>Unit matching to ASAP names is by normalised string with a fuzzy fallback; unmatched units are dropped
      (counts in the table). Kenya's districts (to 2012) and counties (from 2013) are separate series, as are
      El Salvador's two reporting eras, each detrended on its own.</li>
  <li>Minimum series length per unit: 8 years. Leave-one-year-out removes every unit of the held-out year.</li>
  <li>GDHY v1.2 and v1.3 from PANGAEA (<a href="https://doi.org/10.1594/PANGAEA.909132">doi:10.1594/PANGAEA.909132</a>);
      cells with at least 15 years of data; national mean unweighted over cells.</li>
  <li>Code: <code>scripts/panel.py</code>, <code>scripts/gdhy.py</code>, <code>scripts/make_robustness.py</code> in
      <a href="https://github.com/OCHA-DAP/ds-aa-drought-indicators">OCHA-DAP/ds-aa-drought-indicators</a>;
      results in <code>data/processed/panel.json</code> and <code>gdhy.json</code>.</li>
</ul>
<p class="meta">OCHA Centre for Humanitarian Data, September 2026.</p>
"""
open(f"{OUT}/index.html", "w").write(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Robustness of the temperature finding</title>
<meta name="description" content="Literature, subnational official yields and a gridded yield dataset as checks on the cross-country drought indicator study.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@700&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<a class="home-link" href="../">← Drought AA indicators</a>
<div class="wrap">{body}</div></body></html>""")
print("wrote", f"{OUT}/index.html")
