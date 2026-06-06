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

# 🎨 PREMIUM CSS
st.markdown('''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }
        
        .stApp { background-color: #f8f9fa !important; }
        .block-container { padding: 1rem !important; max-width: 440px !important; }
        
        .title-table { width: 100%; border-collapse: collapse; margin-bottom: 15px; border: 2px solid #0f172a; border-radius: 8px; overflow: hidden; }
        .title-cell { background-color: #0f172a; color: #ffffff !important; font-family: '-apple-system', sans-serif; font-weight: 800; font-size: 22px; text-align: center; padding: 12px; text-transform: uppercase; }
        .subtitle-cell { background-color: #ffffff; color: #475569 !important; font-size: 12px; text-align: center; padding: 8px; border-top: 1px solid #e2e8f0; }
        
        .premium-card { background: #ffffff !important; border: 1px solid #e2e8f0 !important; border-top: 5px solid #0f172a !important; border-radius: 14px; padding: 20px; margin-top: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.02); }
        .premium-card.warning-card { border-top: 5px solid #ea580c !important; }
        
        .istasyon-isim { font-size: 18px; font-weight: 700; color: #0f172a !important; }
        .mesafe-text { font-size: 13px; font-weight: 700; color: #1e40af !important; text-transform: uppercase; }
        .mesafe-text.warning-text { color: #ea580c !important; }
        
        .adres-text { font-size: 12px; color: #64748b !important; margin-top: 10px; padding-top: 10px; border-top: 1px solid #f1f5f9; }
        
        .nav-link-btn { display: flex; align-items: center; justify-content: center; text-decoration: none; border-radius: 8px; height: 44px; font-weight: 600; background-color: #0f172a; color: #ffffff !important; font-size: 13px; width: 100%; margin-top: 10px; }
        .nav-link-btn.warning-btn { background-color: #ea580c !important; }
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

# Esnek Veri Okuyucu: Artık iç içe (nested) verileri de tarıyor
def esnek_deger_oku(sozluk, olasi_anahtarlar):
    if not isinstance(sozluk, dict): return None
    # 1. Seviye Tarama (Doğrudan anahtarlar)
    for k, v in sozluk.items():
        if str(k).lower() in olasi_anahtarlar:
            return v
    # 2. Seviye Tarama (Alt objelerin içi, örn: "location": {"lat": 38.0})
    for k, v in sozluk.items():
        if isinstance(v, dict):
            for alt_k, alt_v in v.items():
                if str(alt_k).lower() in olasi_anahtarlar:
                    return alt_v
    return None

# --- 📁 AKILLI VERİ MODELİ KORUMASI (FIREBASE DESTEKLİ) ---
if "offline_istasyonlar" not in st.session_state:
    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
            istasyonlar = []
            if isinstance(raw_data, list):
                istasyonlar = raw_data
            elif isinstance(raw_data, dict):
                # Firebase formatını düzleştirme: {"-Nxyz": {istasyon_verisi}, "-Nabc": {istasyon_verisi}}
                for key, value in raw_data.items():
                    if isinstance(value, dict):
                        value["_firebase_id"] = key  # ID'yi kaybetmemek için ekliyoruz
                        istasyonlar.append(value)
                    elif isinstance(value, list):
                        istasyonlar.extend(value)
                
                if not istasyonlar and raw_data.keys():
                    istasyonlar = [raw_data]
            
            st.session_state.offline_istasyonlar = istasyonlar
    except Exception as e:
        st.error(f"istasyonlar.json dosyası yüklenemedi. Hata: {str(e)}")
        st.stop()

# ==========================================
# 🔄 LIFECYCLE VE STATE YÖNETİMİ
# ==========================================
if "user_coords" not in st.session_state:
    st.session_state.user_coords = (38.4192, 27.1287) 
    st.session_state.gps_loaded = False

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
# 🧠 MATRİS HESAPLAMA
# ==========================================
en_yakin_istasyon = None
en_yakin_mesafe = float('inf')
aktif_arizali_set = arizali_istasyon_setini_getir()

u_lat, u_lon = st.session_state.user_coords

for ist in st.session_state.offline_istasyonlar:
    raw_lat = esnek_deger_oku(ist, ["enlem", "lat", "latitude", "y", "koordinat_x"])
    raw_lon = esnek_deger_oku(ist, ["boylam", "lon", "lng", "longitude", "x", "koordinat_y"])
    
    if raw_lat is None or raw_lon is None:
        continue
        
    try:
        if isinstance(raw_lat, str): raw_lat = raw_lat.replace(',', '.')
        if isinstance(raw_lon, str): raw_lon = raw_lon.replace(',', '.')
        i_lat, i_lon = float(raw_lat), float(raw_lon)
    except (ValueError, TypeError):
        continue
        
    km = mesafe_hesapla(u_lat, u_lon, i_lat, i_lon)
    
    i_isim = esnek_deger_oku(ist, ["isim", "name", "title", "ad", "şirket", "sirket", "firma"]) or "Şarj İstasyonu"
    clean_id = "".join(c for c in str(i_isim) if c.isalnum() or c in (' ', '_', '-')).rstrip()
    
    if clean_id not in aktif_arizali_set:
        if km < en_yakin_mesafe:
            en_yakin_mesafe = km
            en_yakin_istasyon = ist.copy()
            en_yakin_istasyon["Safe_Lat"] = i_lat
            en_yakin_istasyon["Safe_Lon"] = i_lon
            en_yakin_istasyon["Safe_Isim"] = str(i_isim)
            en_yakin_istasyon["Mesafe_KM"] = round(km, 1)

# ==========================================
# 🎯 SONUÇ EKRANI
# ==========================================
if en_yakin_istasyon:
    km_uzaklik = en_yakin_istasyon["Mesafe_KM"]
    ist_isim = en_yakin_istasyon["Safe_Isim"]
    ist_hiz = esnek_deger_oku(en_yakin_istasyon, ["hiz", "speed", "güç", "guc", "kw"]) or "Bilinmiyor"
    ist_adres = esnek_deger_oku(en_yakin_istasyon, ["adres", "address", "lokasyon", "ilce"]) or "Adres Bilgisi Yok"
    
    hedef_lat = en_yakin_istasyon["Safe_Lat"]
    hedef_lon = en_yakin_istasyon["Safe_Lon"]
    
    menzil_yeterli = km_uzaklik <= maks_menzil
    g_link = f"https://www.google.com/maps/dir/?api=1&origin={u_lat},{u_lon}&destination={hedef_lat},{hedef_lon}&travelmode=driving"
    
    if menzil_yeterli:
        st.markdown(f"""
        <div class="premium-card">
            <div class="mesafe-text">📍 {km_uzaklik} km uzaklıkta</div>
            <div class="istasyon-isim" style="margin-top:5px;">{ist_isim}</div>
            <div style="font-size:13px; color:#475569; margin-top:5px;">⚡ Güç/Hız: {ist_hiz}</div>
            <div class="adres-text">{ist_adres}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn">🗺️ Navigasyonu Başlat</a>', unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="premium-card warning-card">
            <div class="mesafe-text warning-text">⚠️ MENZİLİNİZİN DIŞINDA ({km_uzaklik} km)</div>
            <div style="font-size:11px; color:#ea580c; font-weight:600; margin-top:2px;">Mevcut bataryanız ile tahmini menziliniz: {round(maks_menzil, 1)} km</div>
            <div class="istasyon-isim" style="margin-top:8px;">{ist_isim}</div>
            <div style="font-size:13px; color:#475569; margin-top:5px;">⚡ Güç/Hız: {ist_hiz}</div>
            <div class="adres-text">{ist_adres}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn warning-btn">🗺️ Menzili Göze Al ve Rotala</a>', unsafe_allow_html=True)
else:
    toplam_kayit = len(st.session_state.offline_istasyonlar)
    st.info(f"ℹ️ Veritabanında toplam **{toplam_kayit}** kayıt bulundu ancak hiçbiri şarj istasyonu formatında işlenemedi.")
    
    # KOD YİNE ÇALIŞMAZSA SORUNU ŞIP DİYE ÇÖZMENİ SAĞLAYACAK DEBUG PANELİ
    if toplam_kayit > 0:
        with st.expander("🛠️ Geliştirici Modu (JSON Verisi Nasıl Görünüyor?)"):
            st.markdown("Aşağıdaki veri, uygulamanın `istasyonlar.json` içinden okuyabildiği **ilk kayıttır**. Enlem ve boylam değerlerinin hangi isimle yazıldığını buradan teyit edebilirsin:")
            st.json(st.session_state.offline_istasyonlar[:1])
