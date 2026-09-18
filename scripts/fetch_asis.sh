#!/usr/bin/env bash
# Fetch FAO GIEWS ASIS country csvs: fetch_asis.sh <ISO3> <outdir>
set -u; iso=$1; out=$2; mkdir -p "$out"; B="https://www.fao.org/giews/earthobservation/asis/data/country"
for f in "MAP_ASI/DATA/ASI_AnnualSummary_Season1_data.csv" "MAP_ASI/DATA/ASI_AnnualSummary_Season2_data.csv" "MAP_ASI/DATA/Mean-VHI_AnnualSummary_Season1_data.csv" "MAP_ASI/DATA/Mean-VHI_AnnualSummary_Season2_data.csv" "MAP_ASI/DATA/ASI_Dekad_Season1_data.csv" "MAP_NDVI_ANOMALY/DATA/vhi_adm1_dekad_data.csv"; do
  o="$out/${iso}_$(basename "$f")"; code=$(curl -s -L -A "Mozilla/5.0" --max-time 120 -o "$o" -w "%{http_code}" "$B/$iso/$f"); [ "$code" = "200" ] || rm -f "$o"; echo "$iso $(basename "$f") $code"
done
