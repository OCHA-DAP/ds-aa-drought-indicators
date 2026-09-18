#!/usr/bin/env bash
# Fetch the six ASAP indicator series used here for one country: fetch_asap.sh <ISO3> <country_id> <level> <outdir>
# Indicators: zFPARc crop/rangeland (240), temperature (140), rainfall (10), WSI (160), SPI-3 (40); growing-cycle class set.
# See data/config/asap_ids.json for the country_id gotcha. Large countries take minutes per series; be polite.
set -u; iso=$1; cid=$2; lvl=$3; out=$4; mkdir -p "$out"
B="https://agricultural-production-hotspots.ec.europa.eu/export/rum/export.php"
for spec in "zfparc_crop 240 1 1 3" "zfparc_range 240 2 1 3" "temp_crop 140 1 1 4" "rain_crop 10 1 1 4" "wsi_crop 160 1 1 5" "spi3_crop 40 1 1 4"; do
  read -r name vid cls csid sid <<< "$spec"; f="$out/${iso}_$name.csv"
  curl -s -A "Mozilla/5.0 (OCHA-CHD data science)" --max-time 1500 "$B?gaul_level=$lvl&country_id=$cid&variable_id=$vid&class_id=$cls&classesset_id=$csid&sensor_id=$sid" -o "$f"
  echo "$iso $name: $(wc -l < "$f") rows, country=$(sed -n '2p' "$f" | cut -d, -f2)"; sleep 3
done
