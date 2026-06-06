import streamlit as st
import pandas as pd
import json
import math
import requests
from streamlit_js_eval import get_geolocation

# --- 📱 SAYFA AYARLARI ---
st.set_page_config(page_title="ŞarjBul", layout="centered")

# 🎨 CSS
st.markdown('''
    <style>
        [data-testid="stSidebar"] { display: none !important; }
        .premium-card { background: #ffffff; border: 1px solid #e2e8f0; border-top: 5px solid #0f172a; border-radius: 14px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
        .istasyon-isim { font-size: 18px; font-weight: 700; color: #0f172a; }
        .mesafe-text { font-size: 13px; font-weight: 700; color: #1e40af; text-transform: uppercase; }
        .nav-link-btn { display: block; text-align: center; padding: 12px; background: #0f172a; color: white; border-radius: 8px; text-decoration: none; font-weight: 600; margin-top: 10px; }
    </style>
''', unsafe_allow_html=True)

def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

# --- 📁 VERİ YÜKLEME ---
if "istasyonlar" not in st.session_state:
    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            st.session_state.istasyonlar = json.load(f)
    except:
        st.error("Veri dosyası okunamadı!")
        st.stop()

# --- 📍 KONUM ---
if "user_coords" not in st.session_state:
    st.session_state.user_coords = (38.4192, 27.1287) # İzmir Varsayılan

loc = get_geolocation()
if loc and 'coords' in loc:
    st.session_state.user_coords = (loc['coords']['latitude'], loc['coords']['longitude'])

# --- 🏛️ ARAYÜZ ---
st.markdown("### ⚡ ŞARJBUL")

with st.expander("Araç ve Menzil Ayarları"):
    menzil_limit = st.slider("Maksimum Menzil (km)", 10, 500, 100)

# --- 🧠 HESAPLAMA ---
u_lat, u_lon = st.session_state.user_coords
en_yakin = None
min_mesafe = float('inf')

for ist in st.session_state.istasyonlar:
    # Geliştirici modunda gördüğümüz anahtarları kullanıyoruz
    i_lat = ist.get("enlem")
    i_lon = ist.get("boylam")
    
    if i_lat is not None and i_lon is not None:
        km = mesafe_hesapla(u_lat, u_lon, float(i_lat), float(i_lon))
        if km < min_mesafe:
            min_mesafe = km
            en_yakin = ist
            en_yakin["Mesafe"] = round(km, 1)

# --- 🎯 SONUÇ ---
if en_yakin and min_mesafe <= menzil_limit:
    st.markdown(f"""
    <div class="premium-card">
        <div class="mesafe-text">📍 {en_yakin["Mesafe"]} km uzaklıkta</div>
        <div class="istasyon-isim">{en_yakin.get("isim")}</div>
        <div style="font-size:12px; color:#64748b;">Adres: {en_yakin.get("adres")}</div>
        <div style="font-size:12px; color:#64748b;">Güç: {en_yakin.get("hiz")}</div>
    </div>
    """, unsafe_allow_html=True)
    
    g_link = f"https://www.google.com/maps/dir/?api=1&origin={u_lat},{u_lon}&destination={en_yakin.get('enlem')},{en_yakin.get('boylam')}"
    st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn">🗺️ Navigasyonu Başlat</a>', unsafe_allow_html=True)
else:
    st.warning("Yakınlarda menziliniz dahilinde uygun istasyon bulunamadı.")
