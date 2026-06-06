import streamlit as st
import pandas as pd
import json
import math
import requests
from datetime import datetime
from streamlit_js_eval import get_geolocation

# --- 📱 MOBİL VE PREMIUM SAYFA AYARLARI ---
st.set_page_config(
    page_title="ŞarjBul", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# 🎨 PREMIUM CSS: Mobil çökme ve kaymaları engelleyen temizlenmiş stil havuzu
st.markdown('''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }
        
        .stApp { background-color: #f8f9fa !important; }
        .block-container { padding: 1rem !important; max-width: 440px !important; }
        
        .title-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
            border: 2px solid #0f172a;
            border-radius: 8px;
            overflow: hidden;
        }
        .title-cell {
            background-color: #0f172a;
            color: #ffffff !important;
            font-family: '-apple-system', sans-serif;
            font-weight: 800;
            font-size: 22px;
            text-align: center;
            padding: 12px;
            text-transform: uppercase;
        }
        .subtitle-cell {
            background-color: #ffffff;
            color: #475569 !important;
            font-size: 12px;
            text-align: center;
            padding: 8px;
            border-top: 1px solid #e2e8f0;
        }
        
        .premium-card {
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-top: 5px solid #0f172a !important;
            border-radius: 14px;
            padding: 20px;
            margin-top: 15px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.02);
        }
        
        .istasyon-isim { font-size: 18px; font-weight: 700; color: #0f172a !important; }
        .mesafe-text { font-size: 13px; font-weight: 700; color: #1e40af !important; text-transform: uppercase; }
        .adres-text { font-size: 12px; color: #64748b !important; margin-top: 10px; padding-top: 10px; border-top: 1px solid #f1f5f9; }
        
        .nav-link-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            border-radius: 8px; 
            height: 44px; 
            font-weight: 600; 
            background-color: #0f172a; 
            color: #ffffff !important;
            font-size: 13px;
            width: 100%;
        }
    </style>
''', unsafe_allow_html=True)

def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

FIREBASE_DB_URL = "https://elektriklisarj-27adb-default-rtdb.europe-west1.firebasedatabase.app/"

@st.cache_data(ttl=20)
def arizali_istasyon_setini_getir():
    arizali_set = set()
    try:
        res = requests.get(f"{FIREBASE_DB_URL}yorumlar.json", timeout=1.5)
        if res.status_code == 200 and res.json():
            for clean_id, yorum_paketleri in res.json().items():
                if isinstance(yorum_paketleri, dict):
                    sirali = sorted(yorum_paketleri.values(), key=lambda x: x.get('tarih', ''))
                    if sirali and "Arızalı" in sirali[-1].get("durum", ""):
                        arizali_set.add(clean_id)
    except: pass
    return arizali_set

# --- 📁 VERİ YÜKLEME ---
if "offline_istasyonlar" not in st.session_state:
    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            st.session_state.offline_istasyonlar = json.load(f)
    except:
        st.error("istasyonlar.json bulunamadı.")
        st.stop()

# ==========================================
# 🏛️ ARAYÜZ BAŞLANGICI
# ==========================================
st.markdown('<table class="title-table"><tr><td class="title-cell">ŞarjBul</td></tr><tr><td class="subtitle-cell">En yakın aktif şarj rotanız</td></tr></table>', unsafe_allow_html=True)

# ==========================================
# 🚗 ARAÇ VE MENZİL AYARLARI
# ==========================================
with st.expander("Araç ve Menzil Ayarları", expanded=False):
    ARAC_KATALOGU = {
        "Tesla Model Y Long Range": {"batarya": 75.0, "tuketim": 16.9},
        "Togg T10X Uzun Menzil": {"batarya": 88.5, "tuketim": 16.9},
        "BYD Atto 3": {"batarya": 60.4, "tuketim": 16.0},
        "Özel Araç (Manuel)": {"batarya": 60.0, "tuketim": 17.0}
    }
    secilen_arac = st.selectbox("Model", list(ARAC_KATALOGU.keys()))
    vals = ARAC_KATALOGU[secilen_arac]
    
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1: batarya = st.number_input("Kapasite", value=vals["batarya"])
    with col_b2: sarj_yuzdesi = st.slider("Şarj %", 1, 100, 35)
    with col_b3: tuketim = st.number_input("Tüketim", value=vals["tuketim"])
    
    st.markdown("---")
    menzil_filtresi_aktif = st.checkbox("Menzil Filtresini Uygula", value=True)

maks_menzil = ((batarya * (sarj_yuzdesi / 100.0)) / tuketim) * 100.0

# ==========================================
# 📡 GÜVENLİ GPS VE FALLBACK YÖNETİMİ (Çökmeyi Önleyen Kritik Kısım)
# ==========================================
user_lat, user_lon = None, None

try:
    konum_verisi = get_geolocation()
    if isinstance(konum_verisi, dict) and 'coords' in konum_verisi:
        coords = konum_verisi.get('coords', {})
        if coords:
            user_lat = coords.get('latitude')
            user_lon = coords.get('longitude')
except Exception:
    pass

# GPS çalışmazsa devreye girecek kurtarma senaryosu
if not user_lat or not user_lon:
    st.warning("📍 Canlı konum alınamadı. Lütfen aşağıdan manuel konum seçin:")
    sehir_secimi = st.selectbox("Bulunduğunuz Bölge", ["İzmir Merkez", "Çeşme", "Alsancak", "İstanbul Anadolu", "İstanbul Avrupa"])
    
    # Koordinat havuzu (Uygulamanın durmasını engeller)
    koordinatlar = {
        "İzmir Merkez": (38.4192, 27.1287),
        "Çeşme": (38.3246, 26.3031),
        "Alsancak": (38.4374, 27.1424),
        "İstanbul Anadolu": (40.9922, 29.1244),
        "İstanbul Avrupa": (41.0422, 28.9844)
    }
    user_lat, user_lon = koordinatlar[sehir_secimi]

# ==========================================
# 🧠 İSTASYON HESAPLAMA VE FİLTRELEME
# ==========================================
en_uygun_istasyon = None
en_yakin_mesafe = float('inf')
aktif_arizali_set = arizali_istasyon_setini_getir()

for ist in st.session_state.offline_istasyonlar:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    
    if (not menzil_filtresi_aktif) or (km <= maks_menzil):
        if km < en_yakin_mesafe:
            clean_id = "".join(c for c in ist["isim"] if c.isalnum() or c in (' ', '_', '-')).rstrip()
            if clean_id not in aktif_arizali_set:
                en_yakin_mesafe = km
                en_uygun_istasyon = ist.copy()
                en_uygun_istasyon["Mesafe"] = round(km, 1)

# ==========================================
# 🎯 SONUÇ EKRANI
# ==========================================
if en_uygun_istasyon:
    st.markdown(f"""
    <div class="premium-card">
        <div class="mesafe-text">📍 {en_uygun_istasyon['Mesafe']} km uzaklıkta</div>
        <div class="istasyon-isim" style="margin-top:5px;">{en_uygun_istasyon['isim']}</div>
        <div style="font-size:13px; color:#475569; margin-top:5px;">⚡ Hız: {en_uygun_istasyon['hiz']}</div>
        <div class="adres-text">{en_uygun_istasyon['adres']}</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    g_link = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={en_uygun_istasyon['enlem']},{en_uygun_istasyon['boylam']}&travelmode=driving"
    st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn">🗺️ Navigasyonu Başlat</a>', unsafe_allow_html=True)
else:
    st.error("🚨 Belirtilen menzil dahilinde aktif bir şarj istasyonu bulunamadı. Lütfen expander panelinden menzil filtresini kapatın.")
