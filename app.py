import streamlit as st
import pandas as pd
import json
import math

# Sayfa Yapılandırması
st.set_page_config(page_title="⚡ ŞarjBul - Türkiye", page_icon="⚡", layout="wide")

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

# --- 📁 VERİ YÜKLEME ---
# Kazıdığımız (scraper ile çektiğimiz) gerçek verileri okuyoruz
try:
    with open("istasyonlar.json", "r", encoding="utf-8") as f:
        istasyonlar_verisi = json.load(f)
except FileNotFoundError:
    st.error("⚠️ 'istasyonlar.json' dosyası bulunamadı! Lütfen önce scraper.py kodunu çalıştırın.")
    st.stop()

# --- 🎨 SOL MENÜ (SIDEBAR) ---
st.sidebar.header("📍 Konum & Filtre Ayarları")

st.sidebar.subheader("Mevcut Konumunuz")
# Başlangıç konumu olarak İzmir koordinatları girilmiştir, değiştirebilirsin
user_lat = st.sidebar.number_input("Enlem (Latitude)", value=38.4192, format="%.4f")
user_lon = st.sidebar.number_input("Boylam (Longitude)", value=27.1287, format="%.4f")

st.sidebar.markdown("---")
st.sidebar.subheader("Filtreleme")

# Mesafe Sınırı Slider'ı
max_mesafe = st.sidebar.slider("Maksimum Mesafe (KM)", min_value=1, max_value=500, value=50)

# Şarj Hızı Seçimi
hiz_secenekleri = ["Standart (AC)", "Hızlı (DC)", "Ultra Hızlı (DC)"]
secilen_hizlar = st.sidebar.multiselect("Şarj Hızı Seçin", hiz_secenekleri, default=hiz_secenekleri)

# --- 🚀 ANA SAYFA ---
st.title("⚡ ŞarjBul Türkiye")
st.subheader("En Yakın Elektrikli Araç Şarj İstasyonları")

# Kullanıcıya olan mesafeleri hesaplama ve filtreleme
mesafeli_liste = []
for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    if km <= max_mesafe and ist["hiz"] in secilen_hizlar:
        ist_kopyasi = ist.copy()
        ist_kopyasi["Mesafe (km)"] = round(km, 2)
        ist_kopyasi["latitude"] = ist["enlem"]
        ist_kopyasi["longitude"] = ist["boylam"]
        mesafeli_liste.append(ist_kopyasi)

# Eğer filtrelere uygun sonuç varsa ekranda göster
if mesafeli_liste:
    df_filtrelenmis = pd.DataFrame(mesafeli_liste).sort_values(by="Mesafe (km)")
    
    # Üst Bilgi Kartları
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric(label="Filtrelere Uygun İstasyon Sayısı", value=f"{len(df_filtrelenmis)} Adet")
    with col_m2:
        en_yakin_mesafe = df_filtrelenmis.iloc[0]["Mesafe (km)"]
        st.metric(label="En Yakın İstasyon Mesafesi", value=f"{en_yakin_mesafe} km")
        
    st.markdown("---")
    
    # Ekranda Yan Yana İki Panel (Sol: Harita, Sağ: Detaylar)
    sol_panel, sag_panel = st.columns([2, 1])
    
    with sol_panel:
        st.subheader("🗺️ İnteraktif Harita")
        st.map(df_filtrelenmis[["latitude", "longitude"]])
        
    with sag_panel:
        st.subheader("📋 En Yakın İstasyon Listesi")
        for index, row in df_filtrelenmis.head(5).iterrows():
            with st.expander(f"🚗 {row['isim']} ({row['Mesafe (km)']} km)"):
                st.caption(f"⚡ Hız: {row['hiz']}")
                st.write(f"📍 {row['adres']}")
                harita_linki = f"https://www.google.com/maps/search/?api=1&query={row['latitude']},{row['longitude']}"
                st.markdown(f"[🗺️ Google Maps Yol Tarifi]({harita_linki})")
else:
    st.warning("⚠️ Belirttiğiniz kriterlere uygun şarj istasyonu bulunamadı. Lütfen sol menüden mesafeyi artırın.")
