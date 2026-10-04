"""Dashboard Area Terbakar & Estimasi Karbon - Provinsi Riau 2023-2025.

Membaca data hasil praproses di folder data/ (lihat preprocess.py).
Jika folder data/ belum ada, otomatis memakai DATA DEMO agar tampilan bisa dicoba.
"""
import json
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

DATA = Path(__file__).parent / "dashboard_data"
st.set_page_config(page_title="Kebakaran Hutan Riau", page_icon="🔥", layout="wide")


# ---------- Data ----------
def demo_data():
    """Data palsu hanya untuk mencoba tampilan."""
    import random

    from shapely.geometry import Point, mapping

    random.seed(1)
    riau = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [[
            [100.0, -1.0], [103.8, -1.0], [103.8, 2.5], [100.0, 2.5], [100.0, -1.0]]]}}]}
    burns, rows = {}, []
    for year, n in zip([2023, 2024, 2025], [60, 25, 40]):
        feats = []
        for _ in range(n):
            p = Point(random.uniform(100.5, 103.2), random.uniform(-0.8, 2.0)).buffer(random.uniform(0.01, 0.06))
            feats.append({"type": "Feature", "properties": {}, "geometry": mapping(p)})
        burns[year] = {"type": "FeatureCollection", "features": feats}
        peat = n * random.uniform(300, 500)
        non = n * random.uniform(150, 300)
        rows.append({"tahun": year, "luas_total_ha": peat + non, "luas_gambut_ha": peat,
                     "luas_non_gambut_ha": non, "emisi_total_tco2": peat * 900 + non * 600})
    return riau, None, burns, pd.DataFrame(rows), True


@st.cache_data
def load_data():
    if not (DATA / "summary.csv").exists():
        return demo_data()
    read = lambda name: json.loads((DATA / name).read_text(encoding="utf-8"))
    summary = pd.read_csv(DATA / "summary.csv")
    burns = {int(y): read(f"burn_{y}.geojson") for y in summary["tahun"]}
    return read("riau_provinsi.geojson"), read("riau_kabupaten.geojson"), burns, summary, False


riau, kabupaten, burns, summary, is_demo = load_data()
years = sorted(summary["tahun"].astype(int).tolist())

# ---------- Header & filter ----------
left, right = st.columns([4, 1])
left.title("🔥 Area Terbakar Provinsi Riau")
left.caption("Hasil identifikasi model deep learning pada citra Landsat, 2023–2025")
choice = right.selectbox("Tahun", ["Semua tahun"] + years, index=len(years))
if is_demo:
    st.warning("Menampilkan DATA DEMO. Jalankan preprocess.py untuk memakai data asli.")

sel_years = years if choice == "Semua tahun" else [int(choice)]
sel = summary[summary["tahun"].isin(sel_years)]

# ---------- Scorecard ----------
total = sel["luas_total_ha"].sum()
peat = sel["luas_gambut_ha"].sum()
carbon = sel["emisi_total_tco2"].sum()

c1, c2, c3 = st.columns(3)
c1.metric("Luas total terbakar", f"{total:,.0f} ha")
c2.metric("Estimasi emisi karbon", f"{carbon / 1e6:,.2f} juta ton CO₂")
c3.metric("Terbakar di lahan gambut", f"{(peat / total * 100 if total else 0):.1f} %",
          f"{peat:,.0f} ha", delta_color="off")

# ---------- Peta ----------
m = folium.Map(location=[0.6, 101.9], zoom_start=7, tiles="OpenStreetMap")
if kabupaten:   # batas kabupaten/kota (tipis) dengan nama saat kursor diarahkan
    folium.GeoJson(kabupaten, name="Kabupaten/kota",
                   style_function=lambda _: {"color": "#888", "weight": 0.8, "fillOpacity": 0.0},
                   tooltip=folium.GeoJsonTooltip(fields=["kabupaten"], aliases=["Kab/Kota:"])).add_to(m)
folium.GeoJson(riau, name="Provinsi Riau",   # batas provinsi (tebal)
               style_function=lambda _: {"color": "#222", "weight": 2.2, "fillOpacity": 0.0}).add_to(m)
for y in sel_years:
    folium.GeoJson(burns[y], name=f"Terbakar {y}",
                   style_function=lambda _: {"color": "#d62728", "weight": 0.5,
                                             "fillColor": "#d62728", "fillOpacity": 0.7}).add_to(m)
st_folium(m, height=520, use_container_width=True, returned_objects=[])

# ---------- Tabel ----------
st.subheader("Ringkasan")
table = summary.rename(columns={
    "tahun": "Tahun", "luas_total_ha": "Luas total (ha)", "luas_gambut_ha": "Gambut (ha)",
    "luas_non_gambut_ha": "Non-gambut (ha)", "emisi_vegetasi_tco2": "Emisi vegetasi (ton CO₂)",
    "emisi_gambut_tco2": "Emisi gambut (ton CO₂)", "emisi_total_tco2": "Emisi total (ton CO₂)"})
for c in table.columns.drop("Tahun"):
    table[c] = table[c].map("{:,.0f}".format)
st.dataframe(table, hide_index=True, width="stretch")
st.download_button("Unduh CSV", summary.to_csv(index=False), "ringkasan_kebakaran_riau.csv", "text/csv")

# ---------- Metodologi ----------
with st.expander("Metodologi & keterbatasan"):
    st.markdown("""
- **Model**: model terbaik dari perbandingan U-Net, U-Net++, DeepLabv3+, dan ResUNet (dilatih dengan label BRIN 2019–2021).
- **Emisi karbon** (ton CO₂) = Luas terbakar × Fuel load × Combustion factor × Emission factor, dihitung terpisah untuk vegetasi dan gambut.
- **Luas terbakar** adalah luas unik: event yang saling tumpang tindih tidak dihitung ganda.
- **Keterbatasan**: area tertutup awan pada Landsat tidak dapat diidentifikasi sehingga luas dapat *underestimate*.
""")
