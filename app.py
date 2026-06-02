import streamlit as st
import pandas as pd
import json
import math

# Sayfa Yapılandırması
# --- 📱 MOBİL VE PWA AYARLARI ---
st.set_page_config(
    page_title="⚡ ŞarjBul - Türkiye", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="collapsed"  # Mobilde yan menüyü gizleyerek ekranı genişletir
)

# Telefonlarda tarayıcı çubuğunu gizlemek ve tam ekran uygulama hissi vermek için HTML enjekte ediyoruz
st.markdown("""
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        /* Mobil cihazlarda haritanın ve butonların daha rahat tıklanması için boşlukları optimize ediyoruz */
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

# --- 📁 VERİ YÜKLEME ---
try:
    with open("istasyonlar.json", "r", encoding="utf-8") as f:
        istasyonlar_verisi = json.load(f)
except FileNotFoundError:
    st.error("⚠️ 'istasyonlar.json' dosyası bulunamadı! Lütfen önce scraper.py kodunu çalıştırın.")
    st.stop()

# --- 🎨 SOL MENÜ (SIDEBAR) ---
st.sidebar.header("📍 Konum & Filtre Ayarları")

st.sidebar.subheader("Mevcut Konumunuz")
user_lat = st.sidebar.number_input("Enlem (Latitude)", value=38.4192, format="%.4f")
user_lon = st.sidebar.number_input("Boylam (Longitude)", value=27.1287, format="%.4f")

st.sidebar.markdown("---")
st.sidebar.subheader("Filtreleme")

# Mesafe Sınırı Slider'ı
max_mesafe = st.sidebar.slider("Maksimum Arama Mesafesi (KM)", min_value=1, max_value=500, value=50)

# Şarj Hızı Seçimi
hiz_secenekleri = ["Standart (AC)", "Hızlı (DC)", "Ultra Hızlı (DC)"]
secilen_hizlar = st.sidebar.multiselect("Şarj Hızı Seçin", hiz_secenekleri, default=hiz_secenekleri)

# --- 🚀 ANA SAYFA ---
st.title("⚡ ŞarjBul Türkiye")

# --- 🔋 YENİ: ARAÇ VE MENZİL DURUMU PANELİ ---
st.subheader("🚗 Araç Menzil Durumu")
col_b1, col_b2, col_b3 = st.columns(3)

with col_b1:
    batarya = st.number_input("Batarya Kapasitesi (kWh)", min_value=10, max_value=150, value=60, step=5)
with col_b2:
    sarj_yuzdesi = st.slider("Mevcut Şarj Yüzdesi (%)", min_value=1, max_value=100, value=40)
with col_b3:
    tuketim = st.number_input("Ortalama Tüketim (kWh/100km)", min_value=10.0, max_value=30.0, value=17.0, step=0.5)

# Matematiksel Menzil Hesaplama Formülü
kalan_enerji = batarya * (sarj_yuzdesi / 100.0)
maks_menzil = (kalan_enerji / tuketim) * 100.0

st.info(f"🔋 **Mevcut Şarjınızla Gidebileceğiniz Maksimum Menzil: {maks_menzil:.1f} km**")
st.markdown("---")

# Kullanıcıya olan mesafeleri hesaplama ve filtreleme
mesafeli_liste = []
for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    if km <= max_mesafe and ist["hiz"] in secilen_hizlar:
        ist_kopyasi = ist.copy()
        ist_kopyasi["Mesafe (km)"] = round(km, 2)
        ist_kopyasi["latitude"] = ist["enlem"]
        ist_kopyasi["longitude"] = ist["boylam"]
        
        # 🚨 MENZİL KONTROLÜ: İstasyon menzil içinde mi dışında mı?
        if km <= maks_menzil:
            ist_kopyasi["Menzil Durumu"] = "Ulaşılabilir ✅"
            ist_kopyasi["renk"] = "#0000FF" # Güvenli istasyonlar MAVİ pin
        else:
            ist_kopyasi["Menzil Durumu"] = "Menzil Dışı ❌"
            ist_kopyasi["renk"] = "#FF0000" # Ulaşılamaz istasyonlar KIRMIZI pin
            
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
        st.caption("🔵 Mavi: Menziliniz Dahilinde | 🔴 Kırmızı: Mevcut Şarjınız Yetmiyor")
        # Yeni renk parametresini haritaya ekliyoruz
        st.map(df_filtrelenmis[["latitude", "longitude", "renk"]], color="renk")
        
    with sag_panel:
        st.subheader("📋 İstasyon Listesi")
        for index, row in df_filtrelenmis.head(10).iterrows():
            # Başlık kısmına menzil durumunu da ekledik
            durum_emoji = "✅" if "Ulaşılabilir" in row['Menzil Durumu'] else "❌"
            with st.expander(f"{durum_emoji} {row['isim']} ({row['Mesafe (km)']} km)"):
                st.write(f"**Menzil Durumu:** {row['Menzil Durumu']}")
                st.caption(f"⚡ Hız: {row['hiz']}")
                st.write(f"📍 {row['adres']}")
                harita_linki = f"https://www.google.com/maps/search/?api=1&query={row['latitude']},{row['longitude']}"
                st.markdown(f"[🗺️ Google Maps Yol Tarifi]({harita_linki})")
else:
    st.warning("⚠️ Belirttiğiniz kriterlere uygun şarj istasyonu bulunamadı. Lütfen sol menüden mesafeyi artırın.")
