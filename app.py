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

# 🎨 PREMIUM CSS: Esnek ve Kilitlenmeyen Mobil Arayüz Tasarımı
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
            margin-top: 10px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.02);
        }
        
        .premium-card.warning-card {
            border-top: 5px solid #ea580c !important;
        }
        
        .istasyon-isim { font-size: 18px; font-weight: 700; color: #0f172a !important; }
        .mesafe-text { font-size: 13px; font-weight: 700; color: #1e40af !important; text-transform: uppercase; }
        .mesafe-text.warning-text { color: #ea580c !important; }
        
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
            margin-top: 10px;
        }
        .nav-link-btn.warning-btn {
            background-color: #ea580c !important;
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

@st.cache_data(ttl=30)
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

# --- 📁 VERİ MODELİ KORUMASI ---
if "offline_istasyonlar" not in st.session_state:
    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            st.session_state.offline_istasyonlar = json.load(f)
    except:
        st.error("istasyonlar.json dosyası yüklenemedi.")
        st.stop()

# ==========================================
# 🔄 LIFECYCLE VE STATE YÖNETİMİ (Kilitlenmeyi Önleyen Alan)
# ==========================================
if "user_coords" not in st.session_state:
    # Telefon GPS'i yanıt verene kadar arayüzün boş kalmaması için varsayılan merkez konum
    st.session_state.user_coords = (38.4192, 27.1287) 
    st.session_state.gps_loaded = False

# Arka planda sessizce cihazın GPS'ini sorgula
try:
    konum_verisi = get_geolocation()
    if isinstance(konum_verisi, dict) and 'coords' in konum_verisi:
        coords = konum_verisi.get('coords', {})
        if coords:
            live_lat = coords.get('latitude')
            live_lon = coords.get('longitude')
            if live_lat and live_lon:
                current_coords = (live_lat, live_lon)
                if st.session_state.user_coords != current_coords:
                    st.session_state.user_coords = current_coords
                    st.session_state.gps_loaded = True
                    st.rerun()
except Exception:
    pass

# ==========================================
# 🏛️ LOGO VE BAŞLIK
# ==========================================
st.markdown('<table class="title-table"><tr><td class="title-cell">ŞarjBul</td></tr><tr><td class="subtitle-cell">En yakın aktif şarj rotanız</td></tr></table>', unsafe_allow_html=True)

# GPS durumuna göre kullanıcıyı bilgilendiren küçük şık bir badge
if st.session_state.gps_loaded:
    st.caption("🟢 Canlı Mobil GPS Aktif")
else:
    st.caption("🟡 Konum aranıyor (Varsayılan Merkez Gösteriliyor)...")

# ==========================================
# 🚗 ARAÇ SEÇİMİ VE MENZİL HESABI
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

maks_menzil = ((batarya * (sarj_yuzdesi / 100.0)) / tuketim) * 100.0

# ==========================================
# 🧠 MATRİS HESAPLAMA (Hata Toleranslı Ana Algoritma)
# ==========================================
en_yakin_istasyon = None
en_yakin_mesafe = float('inf')
aktif_arizali_set = arizali_istasyon_setini_getir()

u_lat, u_lon = st.session_state.user_coords

for ist in st.session_state.offline_istasyonlar:
    # JSON anahtar kelime varyasyonlarına karşı tam koruma koruması
    i_lat = ist.get("enlem") or ist.get("lat") or ist.get("latitude")
    i_lon = ist.get("boylam") or ist.get("lon") or ist.get("lng") or ist.get("longitude")
    
    if i_lat is None or i_lon is None:
        continue
        
    km = mesafe_hesapla(u_lat, u_lon, float(i_lat), float(i_lon))
    
    # İstasyon ismi okuma koruması
    i_isim = ist.get("isim") or ist.get("name") or "Şarj İstasyonu"
    clean_id = "".join(c for c in i_isim if c.isalnum() or c in (' ', '_', '-')).rstrip()
    
    if clean_id not in aktif_arizali_set:
        if km < en_yakin_mesafe:
            en_yakin_mesafe = km
            en_yakin_istasyon = ist.copy()
            en_yakin_istasyon["Mesafe_KM"] = round(km, 1)

# ==========================================
# 🎯 AKILLI VE KESİNTİSİZ SONUÇ EKRANI
# ==========================================
if en_yakin_istasyon:
    km_uzaklik = en_yakin_istasyon["Mesafe_KM"]
    ist_isim = en_yakin_istasyon.get("isim") or en_yakin_istasyon.get("name") or "Bilinmeyen İstasyon"
    ist_hiz = en_yakin_istasyon.get("hiz") or en_yakin_istasyon.get("speed") or "Bilinmiyor"
    ist_adres = en_yakin_istasyon.get("adres") or en_yakin_istasyon.get("address") or "Adres Bilgisi Yok"
    
    # Menzil kontrolü
    menzil_yeterli = km_uzaklik <= maks_menzil
    
    if menzil_yeterli:
        # Standart Premium Görünüm (Menzil İçi)
        st.markdown(f"""
        <div class="premium-card">
            <div class="mesafe-text">📍 {km_uzaklik} km uzaklıkta</div>
            <div class="istasyon-isim" style="margin-top:5px;">{ist_isim}</div>
            <div style="font-size:13px; color:#475569; margin-top:5px;">⚡ Güç/Hız: {ist_hiz}</div>
            <div class="adres-text">{ist_adres}</div>
        </div>
        """, unsafe_allow_html=True)
        
        g_link = f"https://www.google.com/maps/dir/?api=1&origin={u_lat},{u_lon}&destination={i_lat},{i_lon}&travelmode=driving"
        st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn">🗺️ Navigasyonu Başlat</a>', unsafe_allow_html=True)
    else:
        # Turuncu İkazlı Görünüm (Menzil Dışı ama İstasyon Görünüyor!)
        st.markdown(f"""
        <div class="premium-card warning-card">
            <div class="mesafe-text warning-text">⚠️ MENZİLİNİZİN DIŞINDA ({km_uzaklik} km)</div>
            <div style="font-size:11px; color:#ea580c; font-weight:600; margin-top:2px;">Mevcut bataryanız ile tahmini menziliniz: {round(maks_menzil, 1)} km</div>
            <div class="istasyon-isim" style="margin-top:8px;">{ist_isim}</div>
            <div style="font-size:13px; color:#475569; margin-top:5px;">⚡ Güç/Hız: {ist_hiz}</div>
            <div class="adres-text">{ist_adres}</div>
        </div>
        """, unsafe_allow_html=True)
        
        g_link = f"https://www.google.com/maps/dir/?api=1&origin={u_lat},{u_lon}&destination={i_lat},{i_lon}&travelmode=driving"
        st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn warning-btn">🗺️ Menzili Göze Al ve Rotala</a>', unsafe_allow_html=True)
else:
    st.info("ℹ️ Sistemde listelenebilecek aktif bir şarj istasyonu kaydı bulunamadı.")
