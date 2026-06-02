import streamlit as st
import pandas as pd
import json
import math
import requests
import folium
from streamlit_folium import st_folium

# --- 📱 MOBİL VE PWA AYARLARI ---
st.set_page_config(
    page_title="⚡ ŞarjBul - Türkiye", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
    </style>
""", unsafe_allow_html=True)

# Mesafe Hesaplama Formülü
def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# OSRM API Kullanarak İki Nokta Arası Rota Koordinatlarını Çeken Fonksiyon
def rota_koordinatlarini_al(start_lat, start_lon, end_lat, end_lon):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("routes"):
                # OSRM GeoJSON formatında [Boylam, Enlem] döner, Folium için bunu [Enlem, Boylam] yapacağız
                coords = data["routes"][0]["geometry"]["coordinates"]
                return [[lat, lon] for lon, lat in coords]
    except Exception:
        pass
    return None

# --- 📁 VERİ YÜKLEME ---
try:
    with open("istasyonlar.json", "r", encoding="utf-8") as f:
        istasyonlar_verisi = json.load(f)
except FileNotFoundError:
    st.error("⚠️ 'istasyonlar.json' dosyası bulunamadı!")
    st.stop()

# --- 🎨 SOL MENÜ (SIDEBAR) ---
st.sidebar.header("📍 Konum & Filtre Ayarları")
user_lat = st.sidebar.number_input("Enlem (Latitude)", value=38.4192, format="%.4f")
user_lon = st.sidebar.number_input("Boylam (Longitude)", value=27.1287, format="%.4f")
max_mesafe = st.sidebar.slider("Maksimum Arama Mesafesi (KM)", min_value=1, max_value=500, value=50)

hiz_secenekleri = ["Standart (AC)", "Hızlı (DC)", "Ultra Hızlı (DC)"]
secilen_hizlar = st.sidebar.multiselect("Şarj Hızı Seçin", hiz_secenekleri, default=hiz_secenekleri)

# --- 🚀 ANA SAYFA ---
st.title("⚡ ŞarjBul Türkiye")

# --- 🔋 ARAÇ VE MENZİL DURUMU PANELİ ---
st.subheader("🚗 Araç Menzil Durumu")
col_b1, col_b2, col_b3 = st.columns(3)
with col_b1:
    batarya = st.number_input("Batarya Kapasitesi (kWh)", min_value=10, max_value=150, value=60, step=5)
with col_b2:
    sarj_yuzdesi = st.slider("Mevcut Şarj Yüzdesi (%)", min_value=1, max_value=100, value=40)
with col_b3:
    tuketim = st.number_input("Ortalama Tüketim (kWh/100km)", min_value=10.0, max_value=30.0, value=17.0, step=0.5)

kalan_enerji = batarya * (sarj_yuzdesi / 100.0)
maks_menzil = (kalan_enerji / tuketim) * 100.0
st.info(f"🔋 **Mevcut Şarjınızla Gidebileceğiniz Maksimum Menzil: {maks_menzil:.1f} km**")
st.markdown("---")

# Tıklanan rotayı hafızada tutmak için Streamlit Session State kullanıyoruz
if "secilen_istasyon_koordinat" not in st.session_state:
    st.session_state.secilen_istasyon_koordinat = None

# Filtreleme İşlemleri
mesafeli_liste = []
for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    if km <= max_mesafe and ist["hiz"] in secilen_hizlar:
        ist_kopyasi = ist.copy()
        ist_kopyasi["Mesafe (km)"] = round(km, 2)
        ist_kopyasi["Menzil Durumu"] = "Ulaşılabilir ✅" if km <= maks_menzil else "Menzil Dışı ❌"
        ist_kopyasi["renk"] = "blue" if km <= maks_menzil else "red"
        mesafeli_liste.append(ist_kopyasi)

if mesafeli_liste:
    df_filtrelenmis = pd.DataFrame(mesafeli_liste).sort_values(by="Mesafe (km)")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric(label="Filtrelere Uygun İstasyon Sayısı", value=f"{len(df_filtrelenmis)} Adet")
    with col_m2:
        en_yakin_mesafe = df_filtrelenmis.iloc[0]["Mesafe (km)"]
        st.metric(label="En Yakın İstasyon Mesafesi", value=f"{en_yakin_mesafe} km")
        
    st.markdown("---")
    
    # EKRAN DÜZENİ (Sol: Harita, Sağ: Liste)
    sol_panel, sag_panel = st.columns([2, 1])
    
    with sag_panel:
        st.subheader("📋 İstasyon Listesi")
        for index, row in df_filtrelenmis.head(10).iterrows():
            durum_emoji = "✅" if "Ulaşılabilir" in row['Menzil Durumu'] else "❌"
            with st.expander(f"{durum_emoji} {row['isim']} ({row['Mesafe (km)']} km)"):
                st.write(f"**Menzil Durumu:** {row['Menzil Durumu']}")
                st.caption(f"⚡ Hız: {row['hiz']}")
                st.write(f"📍 {row['adres']}")
                
                # 🛠️ YENİ: Uygulama içi Rota Butonu
                if st.button("🗺️ Haritada Rotayı Çiz", key=f"btn_{index}"):
                    st.session_state.secilen_istasyon_koordinat = (row['enlem'], row['boylam'])
                    st.rerun()
                    
                harita_linki = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={row['enlem']},{row['boylam']}"
                st.markdown(f"[↗️ Dışarıda Aç (Google Maps)]({harita_linki})")
                
    with sol_panel:
        st.subheader("🗺️ İnteraktif Navigasyon Haritası")
        st.caption("🔵 Mavi: Menzil Dahili | 🔴 Kırmızı: Menzil Dışı | 🟢 Yeşil Ev: Sizin Konumunuz")
        
        # 🎨 Premium Görünüm İçin Haritayı Oluşturuyoruz (Cartodb Dark Matter - Gece Modu)
        m = folium.Map(location=[user_lat, user_lon], zoom_start=11, tiles="Cartodb dark_matter")
        
        # Kullanıcının Kendi Konumuna Yeşil Ev İkonu Koyuyoruz
        folium.Marker(
            [user_lat, user_lon],
            popup="Sizin Konumunuz",
            icon=folium.Icon(color="green", icon="home", prefix="fa")
        ).add_to(m)
        
        # İstasyon Pinlerini Haritaya Ekleme
        for _, row in df_filtrelenmis.iterrows():
            folium.CircleMarker(
                location=[row['enlem'], row['boylam']],
                radius=6,
                color=row['renk'],
                fill=True,
                fill_color=row['renk'],
                fill_opacity=0.7,
                popup=f"{row['isim']} ({row['Mesafe (km)']} km)"
            ).add_to(m)
            
        # 🗺️ Eğer Kullanıcı Bir İstasyona Tıkladıysa Rotayı Çiziyoruz
        if st.session_state.secilen_istasyon_koordinat:
            dest_lat, dest_lon = st.session_state.secilen_istasyon_koordinat
            rota_noktalari = rota_koordinatlarini_al(user_lat, user_lon, dest_lat, dest_lon)
            
            if rota_noktalari:
                # Haritaya kalın, parlayan bir rota çizgisi ekliyoruz
                folium.PolyLine(
                    locations=rota_noktalari,
                    color="#00FFCC",  # Neon Turkuaz Rota Çizgisi
                    weight=5,
                    opacity=0.8
                ).add_to(m)
                
                # Hedef istasyonun üzerine özel bir bitiş bayrağı pini koyuyoruz
                folium.Marker(
                    [dest_lat, dest_lon],
                    icon=folium.Icon(color="white", icon="flag", prefix="fa")
                ).add_to(m)
                
        # Haritayı Ekrana Çizdir
        st_folium(m, width="100%", height=500, key="main_map")
else:
    st.warning("⚠️ Belirttiğiniz kriterlere uygun şarj istasyonu bulunamadı.")
