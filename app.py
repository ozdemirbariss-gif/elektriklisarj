import streamlit as st
import pandas as pd
import json
import math
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime

# --- 📱 MOBİL VE MİNİMALİST SAYFA AYARLARI ---
st.set_page_config(
    page_title="Elektrikli Şarj Bul", 
    page_icon="⚡", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# 🎨 Gelişmiş CSS: Tamamen ortalanmış, emojisiz, premium tipografi ve kart tasarımı
st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        /* Sidebar'ı tamamen görünmez yapıyoruz */
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        
        .block-container { padding: 2rem 1rem !important; max-width: 480px !important; }
        
        /* Modern ve Ortalanmış Başlık */
        .ana-baslik {
            font-family: 'SF Pro Display', '-apple-system', BlinkMacSystemFont, sans-serif;
            font-weight: 800;
            font-size: 32px;
            letter-spacing: -0.5px;
            text-align: center;
            color: #ffffff;
            margin-bottom: 5px;
        }
        .alt-baslik {
            font-family: '-apple-system', sans-serif;
            font-size: 14px;
            text-align: center;
            color: #888888;
            margin-bottom: 25px;
        }
        
        /* Premium Kart Tasarımı */
        .oneri-kart { 
            background: #161618; 
            padding: 24px; 
            border-radius: 16px; 
            border: 1px solid #2c2c2e;
            margin-bottom: 20px; 
        }
        .istasyon-isim { font-size: 20px; font-weight: 700; color: #ffffff; margin: 0 0 8px 0; }
        .mesafe-text { font-size: 16px; font-weight: 600; color: #34c759; margin: 0 0 4px 0; }
        .detay-text { font-size: 14px; color: #aeaeac; margin: 0; }
        .adres-text { font-size: 12px; color: #636366; margin-top: 8px; line-height: 1.4; }
        
        /* Buton Sadeleştirmeleri */
        .stButton>button { 
            border-radius: 12px; 
            height: 46px; 
            font-weight: 600; 
            background-color: #1c1c1e; 
            color: #ffffff; 
            border: 1px solid #2c2c2e;
        }
        .stButton>button:hover { border-color: #34c759; color: #34c759; }
    </style>
""", unsafe_allow_html=True)

# Mesafe Hesaplama
def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# OSRM Rota Motoru
@st.cache_data(show_spinner=False)
def rota_koordinatlarini_al(start_lat, start_lon, end_lat, end_lon):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data.get("routes"):
                return [[lat, lon] for lon, lat in data["routes"][0]["geometry"]["coordinates"]]
    except: pass
    return None

# Firebase Veri Tabanı Bağlantısı
FIREBASE_DB_URL = "https://elektriklisarj-27adb-default-rtdb.europe-west1.firebasedatabase.app/"

def yorum_gonder(istasyon_id, kullanici, yorum_metni, durum):
    if kullanici and yorum_metni:
        clean_id = "".join(c for c in istasyon_id if c.isalnum() or c in (' ', '_', '-')).rstrip()
        url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
        yeni_yorum = {
            "kullanici": kullanici, "yorum": yorum_metni, "durum": durum,
            "tarih": datetime.now().strftime("%d.%m %H:%M")
        }
        try: requests.post(url, json=yeni_yorum, timeout=2); return True
        except: pass
    return False

def istasyon_arizali_mi(istasyon_id):
    clean_id = "".join(c for c in istasyon_id if c.isalnum() or c in (' ', '_', '-')).rstrip()
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
    try:
        res = requests.get(url, timeout=2)
        if res.status_code == 200 and res.json():
            bildirimler = list(res.json().values())
            if "Arızalı" in bildirimler[-1].get("durum", ""):
                return True
    except: pass
    return False

def yorumlari_getir(istasyon_id):
    clean_id = "".join(c for c in istasyon_id if c.isalnum() or c in (' ', '_', '-')).rstrip()
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
    try:
        res = requests.get(url, timeout=2)
        if res.status_code == 200 and res.json(): return res.json().values()
    except: pass
    return []

# --- 📁 VERİ YÜKLEME ---
try:
    with open("istasyonlar.json", "r", encoding="utf-8") as f:
        istasyonlar_verisi = json.load(f)
except FileNotFoundError:
    st.error("Veri dosyası bulunamadı.")
    st.stop()

# --- 📍 SABİT KULLANICI KONUMU (Görünmez Arka Plan) ---
user_lat = 38.4192
user_lon = 27.1287

# --- 🚀 ANA EKRAN GEOMETRİSİ ---
st.markdown('<div class="ana-baslik">Elektirikli Şarj Bul</div>', unsafe_allow_html=True)
st.markdown('<div class="alt-baslik">Konumunuza en yakın aktif istasyon listelenir.</div>', unsafe_allow_html=True)

# MENZİL HESAPLAMA (Göz yormayan ince çizgiler)
with st.expander("Menzil Durumu", expanded=False):
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1: batarya = st.number_input("Batarya (kWh)", value=60)
    with col_b2: sarj_yuzdesi = st.slider("Şarj %", min_value=1, max_value=100, value=30)
    with col_b3: tuketim = st.number_input("Tüketim", value=17.0)
maks_menzil = ((batarya * (sarj_yuzdesi / 100.0)) / tuketim) * 100.0

if "harita_acik" not in st.session_state:
    st.session_state.harita_acik = False

# ==========================================
# 🧠 TÜM TÜRKİYE'DE EN YAKIN AKTİF İSTASYONU BULMA
# ==========================================
en_uygun_istasyon = None
en_yakin_mesafe = float('inf')

for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    
    # Çap sınırı yok; menzil yeten ve arızalı olmayan mutlak en yakın istasyon seçilir
    if km <= maks_menzil:
        if km < en_yakin_mesafe:
            if not istasyon_arizali_mi(ist["isim"]):
                en_yakin_mesafe = km
                en_uygun_istasyon = ist.copy()
                en_uygun_istasyon["Mesafe"] = round(km, 1)

# ==========================================
# 🎯 DİNAMİK KAPALI HARİTA KATMANI
# ==========================================
if en_uygun_istasyon:
    if st.session_state.harita_acik:
        m = folium.Map(location=[(user_lat + en_uygun_istasyon['enlem'])/2, (user_lon + en_uygun_istasyon['boylam'])/2], zoom_start=13, tiles="Cartodb dark_matter")
        folium.Marker([user_lat, user_lon], icon=folium.Icon(color="green", icon="user", prefix="fa")).add_to(m)
        folium.Marker([en_uygun_istasyon['enlem'], en_uygun_istasyon['boylam']], icon=folium.Icon(color="blue", icon="flash", prefix="fa")).add_to(m)
        
        rota = rota_koordinatlarini_al(user_lat, user_lon, en_uygun_istasyon['enlem'], en_uygun_istasyon['boylam'])
        if rota:
            folium.PolyLine(locations=rota, color="#00FFCC", weight=6, opacity=0.9).add_to(m)
            
        st_folium(m, width="100%", height=300, key=f"map_{en_uygun_istasyon['isim']}")
        
        if st.button("Haritayı Kapat"):
            st.session_state.harita_acik = False
            st.rerun()
        st.markdown("---")

    # 👑 PREMIUM TEK ÖNERİ KARTI
    st.markdown(f"""
    <div class="oneri-kart">
        <div class="istasyon-isim">{en_uygun_istasyon['isim']}</div>
        <div class="mesafe-text">{en_uygun_istasyon['Mesafe']} km uzaklıkta</div>
        <div class="detay-text">Şarj Hızı: {en_uygun_istasyon['hiz']}</div>
        <div class="adres-text">{en_uygun_istasyon['adres']}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Eylem Alanı
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Rotayı Çiz"):
            st.session_state.harita_acik = True
            st.rerun()
    with c2:
        g_link = f"http://googleusercontent.com/maps.google.com/5{en_uygun_istasyon['enlem']},{en_uygun_istasyon['boylam']}"
        st.markdown(f"[<button style='width:100%; border:none; padding:12px; border-radius:12px; background-color:#1c1c1e; color:white; font-weight:600; height:46px; cursor:pointer; border: 1px solid #2c2c2e;'>Google Maps</button>]({g_link})", unsafe_allow_html=True)
    with c3:
        with st.popover("Durum Bildir"):
            st.write("İstasyon Durumu")
            nick = st.text_input("Kullanıcı Adı", max_chars=12)
            yorum_txt = st.text_input("Mevcut Durum")
            durum = st.radio("İstasyon Durumu", ["Sorunsuz / Boş", "Arızalı / Kapalı"], horizontal=True)
            if st.button("Gönder"):
                if yorum_gonder(en_uygun_istasyon['isim'], nick, yorum_txt, durum):
                    st.rerun()
            
            st.markdown("---")
            yorumlar = yorumlari_getir(en_uygun_istasyon['isim'])
            if yorumlar:
                for y in sorted(yorumlar, key=lambda x: x.get('tarih', ''), reverse=True)[:3]:
                    st.markdown(f"**{y['kullanici']}** ({y['durum']}): {y['yorum']}")
            else:
                st.caption("Bildirim bulunmuyor.")
else:
    st.warning("Menzilinize uygun aktif bir istasyon bulunamadı.")
