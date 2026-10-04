"""Jalankan SEKALI di laptop: TIFF per-event + CSV emisi + shapefile Riau -> folder dashboard_data/.

Struktur input (otomatis terdeteksi):
  Data/HasilIdentifikasiKebakaran_<TAHUN>/BurnedArea_event*.tif   (nilai 1 = terbakar)
  Data/HasilIdentifikasiKebakaran_<TAHUN>/Emisi_CO2_<TAHUN>_TOTAL.csv
  BatasRiau/BatasRiau.shp

Tahun baru (2023, 2025) cukup ditaruh dengan pola folder yang sama, lalu jalankan ulang:
  python preprocess.py
"""
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape
from shapely.ops import unary_union

BASE = Path(__file__).parent
RAW = BASE / "Data"
OUT = BASE / "dashboard_data"
RIAU_SHP = BASE / "BatasRiau" / "BatasRiau.shp"
BURN_VALUE = 1
SIMPLIFY_M = 10          # toleransi penyederhanaan (meter); naikkan bila file terlalu besar
KAB_COL = "WADMKK"       # kolom nama kabupaten/kota pada shapefile

OUT.mkdir(exist_ok=True)

# ---- Batas Riau (shapefile tanpa .prj -> koordinatnya sudah derajat, WGS84) ----
kab = gpd.read_file(RIAU_SHP)
if kab.crs is None:
    kab = kab.set_crs(4326)
kab = kab.to_crs(4326)
kab["geometry"] = kab.geometry.simplify(0.001)   # ~100 m, cukup untuk batas di peta
kab[[KAB_COL, "geometry"]].rename(columns={KAB_COL: "kabupaten"}).to_file(
    OUT / "riau_kabupaten.geojson", driver="GeoJSON")
gpd.GeoDataFrame(geometry=[kab.geometry.union_all()], crs=4326).to_file(
    OUT / "riau_provinsi.geojson", driver="GeoJSON")

# ---- Per tahun ----
rows = []
for folder in sorted(RAW.glob("HasilIdentifikasiKebakaran_*")):
    year = int(re.search(r"(\d{4})$", folder.name).group(1))
    tifs = sorted(folder.glob("*.tif"))
    polys, crs = [], None
    for t in tifs:
        with rasterio.open(t) as src:
            crs = src.crs
            arr = src.read(1)
            if not (arr == BURN_VALUE).any():
                continue
            polys += [shape(g) for g, _ in shapes(arr, mask=(arr == BURN_VALUE), transform=src.transform)]
    merged = unary_union(polys)          # gabungkan event yang saling tumpang tindih
    gdf = gpd.GeoDataFrame(geometry=[merged], crs=crs)
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_M)
    gdf.to_crs(4326).to_file(OUT / f"burn_{year}.geojson", driver="GeoJSON")

    tot = pd.read_csv(next(folder.glob("Emisi_CO2_*_TOTAL.csv"))).iloc[0]
    rows.append({
        "tahun": year,
        "luas_total_ha": tot["area_terbakar_unik_ha"],
        "luas_gambut_ha": tot["area_gambut_ha"],
        "luas_non_gambut_ha": tot["area_nongambut_ha"],
        "emisi_vegetasi_tco2": tot["emisi_vegetasi_tCO2"],
        "emisi_gambut_tco2": tot["emisi_gambut_tCO2"],
        "emisi_total_tco2": tot["emisi_total_tCO2"],
    })
    print(year, f"{len(tifs)} TIFF | luas CSV {tot['area_terbakar_unik_ha']:,.0f} ha | "
                f"luas dari poligon {gdf.to_crs(32647).area.sum() / 1e4:,.0f} ha")

pd.DataFrame(rows).to_csv(OUT / "summary.csv", index=False)
print("Selesai ->", OUT)
