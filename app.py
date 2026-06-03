import streamlit as st
import pandas as pd
import json
import math
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime

# --- 📱 MOBİL VE KULLANICI DOSTU SAYFA AYARLARI ---
st.set_page_config(
    page_title="⚡ ŞarjBul", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Arayüzü daha modern ve temiz yapmak için özel CSS dokunuşları
st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        .block-container {
            padding: 1rem !important;
        }
        .stButton>button {
            width: 100%;
            border-radius: 8px;
        }
        div.stDataFrame {
            width: 100%;
        }
    </style>
""", unsafe_allow_html=True)

# İki nokta arası mesafe hesaplama
def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# OSRM Rota Hesaplayıcı
def rota_koordinatlarini_al(start_lat, start_lon, end_lat, end_lon):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get("routes"):
                coords = data["routes"][0]["geometry"]["coordinates"]
                return [[lat, lon] for lon, lat in coords]
    except:
        pass
    return None

# Firebase Veri Tabanı Bağlantısı
FIREBASE_DB_URL = "https://elektriklisarj-27adb-default-rtdb.europe-west1.firebasedatabase.app/"

def yorum_gonder(istasyon_id, kullanici, yorum_metni, durum):
    if kullanici and yorum_metni:
        clean_id = "".join(c for c in istasyon_id if c.isalnum() or c in (' ', '_', '-')).rstrip()
        url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
        yeni_yorum = {
            "kullanici": kullanici,
            "yorum": yorum_metni,
            "durum": durum,
            "tarih": datetime.now().strftime("%d.%m %H:%M")
        }
        try:
            requests.post(url, json=yeni_yorum, timeout=3)
            return True
        except:
            pass
    return False

def yorumlari_getir(istasyon_id):
    clean_id = "".join(c for c in istasyon_id if c.isalnum() or c in (' ', '_', '-')).rstrip()
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
    try:
        res = requests.get(url, timeout=3)
        if res.status_code == 200 and res.json():
            return res.json().values()
    except:
        pass
    return []

# --- 📁 VERİ YÜKLEME ---
try:
    with open("istasyonlar.json", "r", encoding="utf-8") as f:
        istasyonlar_verisi = json.load(f)
except FileNotFoundError:
    st.error("⚠️ Veri dosyası bulunamadı!")
    st.stop()

# --- 📍 SOL MENÜ (Gerekli Ayarlar) ---
st.sidebar.header("⚙️ Ayarlar")
user_lat = st.sidebar.number_input("Enlem", value=38.4192, format="%.4f")
user_lon = st.sidebar.number_input("Boylam", value=27.1287, format="%.4f")
max_mesafe = st.sidebar.slider("Arama Çapı (KM)", min_value=5, max_value=200, value=50)

hiz_secenekleri = ["Standart (AC)", "Hızlı (DC)", "Ultra Hızlı (DC)"]
secilen_hizlar = st.sidebar.multiselect("Şarj Hızı", hiz_secenekleri, default=hiz_secenekleri)

# --- 🚀 ANA SAYFA ---
st.title("⚡ ŞarjBul")

# Kolaylaştırılmış Menzil Paneli
st.write("### 🚗 Menzil Filtresi")
col_b1, col_b2, col_b3 = st.columns(3)
with col_b1:
    batarya = st.number_input("Batarya (kWh)", min_value=10, max_value=120, value=60)
with col_b2:
    sarj_yuzdesi = st.slider("Mevcut Şarj %", min_value=1, max_value=100, value=40)
with col_b3:
    tuketim = st.number_input("Tüketim (kWh/100km)", min_value=10.0, max_value=25.0, value=17.0)

kalan_enerji = batarya * (sarj_yuzdesi / 100.0)
maks_menzil = (kalan_enerji / tuketim) * 100.0
st.info(f"🔋 **Gidebileceğiniz kalan menzil: {maks_menzil:.1f} km**")

# Hafıza Yönetimi
if "secilen_istasyon" not in st.session_state:
    st.session_state.secilen_istasyon = None

# İstasyon Filtreleme
mesafeli_liste = []
for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    if km <= max_mesafe and ist["hiz"] in secilen_hizlar:
        ist_kopyasi = ist.copy()
        ist_kopyasi["Mesafe (km)"] = round(km, 1)
        ist_kopyasi["Ulasilabilir"] = km <= maks_menzil
        ist_kopyasi["renk"] = "blue" if km <= maks_menzil else "red"
        mesafeli_liste.append(ist_kopyasi)

if mesafeli_liste:
    df_filtrelenmis = pd.DataFrame(mesafeli_liste).sort_values(by="Mesafe (km)")
    
    st.markdown("---")
    
    # İKİ PANEL (Sol: Harita, Sağ: Liste)
    sol_panel, sag_panel = st.columns([1.8, 1.2])
    
    with sol_panel:
        st.write("### 🗺️ Harita")
        m = folium.Map(location=[user_lat, user_lon], zoom_start=12, tiles="Cartodb dark_matter")
        
        # Kullanıcı Pini
        folium.Marker([user_lat, user_lon], popup="Buradasınız", icon=folium.Icon(color="green", icon="user", prefix="fa")).add_to(m)
        
        # İstasyon Pinleri
        for _, row in df_filtrelenmis.iterrows():
            folium.CircleMarker(
                location=[row['enlem'], row['boylam']],
                radius=6, color=row['renk'], fill=True, fill_color=row['renk'], fill_opacity=0.7,
                popup=f"{row['isim']} ({row['Mesafe (km)']} km)"
            ).add_to(m)
            
        # Rota Çizimi
        if st.session_state.secilen_istasyon:
            slat, slon = st.session_state.secilen_istasyon
            rota = rota_koordinatlarini_al(user_lat, user_lon, slat, slon)
            if rota:
                folium.PolyLine(locations=rota, color="#00FFCC", weight=5, opacity=0.8).add_to(m)
                folium.Marker([slat, slon], icon=folium.Icon(color="white", icon="flag", prefix="fa")).add_to(m)
                
        st_folium(m, width="100%", height=450, key="map")
        
    with sag_panel:
        st.write(f"### 📋 İstasyonlar ({len(df_filtrelenmis)} Adet)")
        
        # En yakın 5 istasyonu sade listeleme
        for index, row in df_filtrelenmis.head(5).iterrows():
            emoji = "🔵" if row['Ulasilabilir'] else "🔴"
            with st.expander(f"{emoji} {row['isim']} ({row['Mesafe (km)']} km)"):
                st.write(f"ℹ️ **Adres:** {row['adres']}")
                st.write(f"⚡ **Hız/Tip:** {row['hiz']}")
                
                # Eylemler için sade butonlar
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🗺️ Rotayı Göster", key=f"r_{index}"):
                        st.session_state.secilen_istasyon = (row['enlem'], row['boylam'])
                        st.rerun()
                with c2:
                    g_link = f"https://www.google.com/maps/dir/?api=1&destination={row['enlem']},{row['boylam']}"
                    st.markdown(f"[<button style='width:100%; border:none; padding:6px; border-radius:8px; background-color:#2e2e2e; color:white; cursor:pointer;'>↗️ Google Maps</button>]({g_link})", unsafe_allow_html=True)
                
                # 💬 Sosyal Alanı Sadeleştirme (İç içe expander ile gizledik)
                with st.container():
                    st.markdown("---")
                    with st.expander("💬 Sürücü Yorumları & Durum Bildir bildir"):
                        nick = st.text_input("Nick", key=f"n_{index}", max_chars=12)
                        yorum_txt = st.text_input("Durum nedir?", key=f"t_{index}", placeholder="Örn: Çalışıyor, boş.")
                        durum = st.radio("Durum", ["Çalışıyor 👍", "Arızalı 👎"], key=f"d_{index}", horizontal=True)
                        
                        if st.button("Gönder", key=f"s_{index}"):
                            if yorum_gonder(row['isim'], nick, yorum_txt, durum):
                                st.success("Yayınlandı!")
                                st.rerun()
                        
                        # Geçmiş yorumları oku
                        yorumlar = yorumlari_getir(row['isim'])
                        if yorumlar:
                            for y in yorumlar:
                                st.markdown(f"**{y['kullanici']}** ({y['durum']}): {y['yorum']}")
                        else:
                            st.caption("Yorum yok.")
else:
    st.warning("İstasyon bulunamadı.")
