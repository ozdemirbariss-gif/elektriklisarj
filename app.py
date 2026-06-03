import streamlit as st
import pandas as pd
import json
import math
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime

# --- 📱 MOBİL VE HIZLI ODAKLI SAYFA AYARLARI ---
st.set_page_config(
    page_title="⚡ ŞarjBul - Anlık Öneri", 
    page_icon="⚡", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# Arayüzü tek bir kart odaklı yapan minimalist CSS
st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        .block-container { padding: 1rem !important; max-width: 500px !important; }
        .stButton>button { border-radius: 12px; height: 48px; font-weight: bold; }
        .oneri-kart { background: linear-gradient(145deg, #1e1e1e, #121212); padding: 20px; border-radius: 16px; border: 2px solid #00FFCC; box-shadow: 0 4px 15px rgba(0,255,204,0.1); margin-bottom: 15px; }
        .durum-badge { background-color: #00FFCC; color: #121212; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 12px; }
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
    """Veri tabanındaki son bildirime bakar, arızalıysa True döner"""
    clean_id = "".join(c for c in istasyon_id if c.isalnum() or c in (' ', '_', '-')).rstrip()
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
    try:
        res = requests.get(url, timeout=2)
        if res.status_code == 200 and res.json():
            # Son eklenen bildirimi kontrol et
            bildirimler = list(res.json().values())
            son_bildirim = bildirimler[-1]
            if "Arızalı" in son_bildirim.get("durum", ""):
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
    st.error("⚠️ Veri dosyası bulunamadı!")
    st.stop()

# --- ⚙️ GİZLİ AYARLAR (SIDEBAR) ---
user_lat = st.sidebar.number_input("Enlem", value=38.4192, format="%.4f")
user_lon = st.sidebar.number_input("Boylam", value=27.1287, format="%.4f")
max_mesafe = st.sidebar.slider("Maksimum Arama Çapı (KM)", min_value=5, max_value=300, value=100)
hiz_secenekleri = ["Standart (AC)", "Hızlı (DC)", "Ultra Hızlı (DC)"]
secilen_hizlar = st.sidebar.multiselect("Şarj Hızı", hiz_secenekleri, default=["Hızlı (DC)", "Ultra Hızlı (DC)"])

# --- 🚀 ANA EKRAN ---
st.title("⚡ ŞarjBul")
st.caption("Sizin için en yakın ve en uygun istasyon anlık hesaplanır.")

# MENZİL GİRDİSİ (Hafifletilmiş tek satır tasarım)
col_b1, col_b2, col_b3 = st.columns(3)
with col_b1: batarya = st.number_input("Batarya (kWh)", value=60)
with col_b2: sarj_yuzdesi = st.slider("Şarj %", min_value=1, max_value=100, value=30)
with col_b3: tuketim = st.number_input("Tüketim", value=17.0)

maks_menzil = ((batarya * (sarj_yuzdesi / 100.0)) / tuketim) * 100.0

if "harita_acik" not in st.session_state:
    st.session_state.harita_acik = False

# ==========================================
# 🧠 AKILLI EN YAKIN VE BOŞ İSTASYON SEÇİMİ
# ==========================================
en_uygun_istasyon = None
en_yakin_mesafe = float('inf')

for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    
    # 1. Kriter: Mesafe ve Hız filtrelerine uyuyor mu?
    if km <= max_mesafe and ist["hiz"] in secilen_hizlar:
        # 2. Kriter: Menzilimiz bu istasyona yetiyor mu?
        if km <= maks_menzil:
            # 3. Kriter: Şu anki mesafeden daha mı yakın?
            if km < en_yakin_mesafe:
                # 4. Kriter (Sosyal Kontrol): İstasyon veri tabanında "Arızalı" olarak işaretlenmiş mi?
                if not istasyon_arizali_mi(ist["isim"]):
                    en_yakin_mesafe = km
                    en_uygun_istasyon = ist.copy()
                    en_uygun_istasyon["Mesafe"] = round(km, 1)

st.markdown("---")

# ==========================================
# 🎯 TEK ÖNERİ KATMANI VE KULLANICI AKSİYONLARI
# ==========================================
if en_uygun_istasyon:
    # 🗺️ EMİR VERİLDİĞİNDE AÇILAN HARİTA KATMANI
    if st.session_state.harita_acik:
        st.write("### 🗺️ Rota Canlı Takip")
        m = folium.Map(location=[(user_lat + en_uygun_istasyon['enlem'])/2, (user_lon + en_uygun_istasyon['boylam'])/2], zoom_start=13, tiles="Cartodb dark_matter")
        folium.Marker([user_lat, user_lon], popup="Buradasınız", icon=folium.Icon(color="green", icon="user", prefix="fa")).add_to(m)
        folium.Marker([en_uygun_istasyon['enlem'], en_uygun_istasyon['boylam']], popup=en_uygun_istasyon['isim'], icon=folium.Icon(color="blue", icon="flash", prefix="fa")).add_to(m)
        
        rota = rota_koordinatlarini_al(user_lat, user_lon, en_uygun_istasyon['enlem'], en_uygun_istasyon['boylam'])
        if rota:
            folium.PolyLine(locations=rota, color="#00FFCC", weight=6, opacity=0.9).add_to(m)
            
        st_folium(m, width="100%", height=320, key=f"single_map_{en_uygun_istasyon['isim']}")
        
        if st.button("❌ Haritayı Kapat"):
            st.session_state.harita_acik = False
            st.rerun()
        st.markdown("---")

    # 👑 EN İDEAL TEK İSTASYON KARTI
    st.write("### 🌟 Önerilen En Uygun İstasyon")
    st.markdown(f"""
    <div class="oneri-kart">
        <span class="durum-badge">Aktif & Boş 👍</span>
        <h2 style='margin: 10px 0 5px 0; color: #fff;'>{en_uygun_istasyon['isim']}</h2>
        <p style='margin: 0; color: #00FFCC; font-size: 18px; font-weight: bold;'>📏 Mesafe: {en_uygun_istasyon['Mesafe']} km</p>
        <p style='margin: 5px 0 0 0; color: #bbbbbb; font-size: 14px;'>⚡ Hız: {en_uygun_istasyon['hiz']}</p>
        <p style='margin: 5px 0 0 0; color: #888888; font-size: 13px;'>📍 {en_uygun_istasyon['adres']}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sürücü Eylem Butonları
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🗺️ Rotayı Çiz"):
            st.session_state.harita_acik = True
            st.rerun()
    with c2:
        g_link = f"http://googleusercontent.com/maps.google.com/4{en_uygun_istasyon['enlem']},{en_uygun_istasyon['boylam']}"
        st.markdown(f"[<button style='width:100%; border:none; padding:12px; border-radius:12px; background-color:#2e2e2e; color:white; font-weight:bold; height:48px; cursor:pointer;'>↗️ Google</button>]({g_link})", unsafe_allow_html=True)
    with c3:
        with st.popover("💬 Durum Bildir"):
            st.write("💬 **İstasyon Durumu Paylaş**")
            nick = st.text_input("Nick", max_chars=12)
            yorum_txt = st.text_input("Yorum")
            durum = st.radio("Durum", ["Sorunsuz / Boş 👍", "Arızalı / Kapalı 👎"], horizontal=True)
            if st.button("Gönder"):
                if json_status := yorum_gonder(en_uygun_istasyon['isim'], nick, yorum_txt, durum):
                    st.success("Bildirildi!")
                    st.rerun()
            
            st.markdown("---")
            st.write("📢 **Son Bildirimler:**")
            yorumlar = yorumlari_getir(en_uygun_istasyon['isim'])
            if yorumlar:
                for y in yorumlar:
                    st.markdown(f"**{y['kullanici']}** ({y['durum']}): {y['yorum']}")
            else:
                st.caption("Bildirim yok.")
else:
    st.warning("⚠️ Belirttiğiniz kriterlere, menzilinize uygun ve aktif durumda olan bir istasyon bulunamadı. Lütfen arama çapını genişletin.")
