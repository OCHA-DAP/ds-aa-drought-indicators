# ds-aa-drought-indicators

Do temperature, rainfall, water balance and vegetation indicators predict drought **impact**
across the countries where OCHA has a drought anticipatory-action framework? A cross-country
backtest of the indicators behind our triggers against national staple production (FAOSTAT),
CERF drought allocations (dated to their rainfall-deficit season by `ds-cerf-supplement`) and
EM-DAT drought events, 2001–2024.

**Site:** https://ocha-dap.github.io/ds-aa-drought-indicators/

Grew out of the Burkina Faso finding (`ds-aa-bfa-drought`, Sept 2026) that growing-season
temperature explained cereal-production shortfalls and CERF seasons far better than the ASAP
biomass anomaly the framework triggers on.

## Countries

Endorsed and in-development drought frameworks in the team KB: AFG, BFA, ETH, KEN, GTM, HND,
SLV, MRT, NER, TCD. Per-country settings (main growing season as dekads, framework area of
interest, FAOSTAT staples, framework-documented bad years) are in `data/config/countries.json`.

## Data

| Layer | Source | How |
|---|---|---|
| Temperature, rainfall, SPI-3, water balance (WSI), cumulative-FPAR anomaly (zFPARc) | JRC ASAP per-admin indicator statistics export (`export/rum/export.php`) | `scripts/fetch_asap.sh`. **Gotcha:** `country_id` is *not* `asap0_id` — it is the rank of the country's ISO3 code in ASAP's full GAUL0 list (AFG=1, BFA=17, ETH=61, MRT=129, NER=137…). Level 2 (provinces) exists only for some countries; the export returns a header-only file otherwise. `data/config/asap_ids.json` records the ids found by probing. |
| ERA5 monthly precipitation (admin 0/1/2) | team prod Postgres `public.era5` raster stats | one query, see `scripts/build_tables.py` docstring |
| FAO ASI (% cropland stressed, annual) and mean VHI, admin 1 | FAO GIEWS ASIS country csv endpoints (`giews/earthobservation/asis/data/country/<ISO3>/MAP_ASI/DATA/…`) | `scripts/fetch_asis.sh` |
| Production | FAOSTAT bulk `Production_Crops_Livestock_E_All_Data_(Normalized)` | staples per country summed, % from 2001–2024 linear trend |
| CERF drought allocations | dev Postgres `aa.cerf_allocation` ⋈ `aa.cerf_supplement` (valid deficit period) | dated seasons = overlap with the main season; undated ones kept as a sensitivity |
| EM-DAT drought events | team blob snapshot via `ocha_stratus.emdat` | dated to the last main season whose midpoint precedes the event start |

## Pipeline

```bash
uv sync
# 1. raw pulls into a scratch dir $S (see scripts/fetch_*.sh and the build_tables docstring)
uv run python scripts/build_tables.py $S      # tables/<ISO3>.csv, tables/impact_dating.csv
uv run python scripts/analyse.py $S           # results/results.json, results/summary_table.csv
uv run python scripts/make_site.py $S         # pages/ (landing + one page per country)
```

## Method in one paragraph

Per country and main growing season: indicator means over the season (biomass, WSI and SPI-3
over its last 60 %), aggregated over the framework area and over all ASAP units; temperature
detrended per unit with a Theil-Sen slope over 1991–2025, biomass over 2001–2025. Targets: the
production anomaly (continuous) and impact seasons (binary). Statistics: OLS on standardised
predictors with leave-one-out R², AUC for the binary target, and a pooled regression across
countries with each series standardised within its country. Caveats and the per-country
dating tables are on the site.
