import streamlit as st
import pandas as pd
import json
import math
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime

# --- 📱 MOBIL VE PREMIUM TASARIM AYARLARI ---
st.set_page_config(
    page_title="⚡ ŞarjBul Pro", 
    page_icon="⚡", 
    layout="centered", # Ekranı daraltarak mobil/kapalı mimari hissi verir
    initial_sidebar_state="collapsed"
)

# Arayüzü tamamen sadeleştiren modern CSS dokunuşları
st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        .block-container { padding: 1rem !important; max-width: 600px !important; }
        .stButton>button { border-radius: 12px; height: 45px; font-weight: bold; }
        .card { background-color: #1e1e1e; padding: 15px; border-radius: 12px; margin-bottom: 10px; border-left: 5px solid #00FFCC; }
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

# OSRM Hızlı Rota Motoru (Sislenme problemini önlemek için optimize edildi)
@st.cache_data(show_spinner=False)
def rota_koordinatlarini_al(start_lat, start_lon, end_lat, end_lon):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=2)
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
            "kullanici": kullanici, "yorum": yorum_metni, "durum": durum,
            "tarih": datetime.now().strftime("%d.%m %H:%M")
        }
        try: requests.post(url, json=yeni_yorum, timeout=2); return True
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

# --- ⚙️ ARKA PLAN AYARLARI (GİZLİ MENÜ) ---
user_lat = st.sidebar.number_input("Enlem", value=38.4192, format="%.4f")
user_lon = st.sidebar.number_input("Boylam", value=27.1287, format="%.4f")
max_mesafe = st.sidebar.slider("Arama Çapı (KM)", min_value=5, max_value=200, value=50)
hiz_secenekleri = ["Standart (AC)", "Hızlı (DC)", "Ultra Hızlı (DC)"]
secilen_hizlar = st.sidebar.multiselect("Şarj Hızı", hiz_secenekleri, default=hiz_secenekleri)

# --- 🚀 ANA EKRAN BAŞLANGICI ---
st.title("⚡ ŞarjBul Türkiye")

# 🚗 MENZİL DURUM KATMANI
with st.expander("🔋 Araç ve Menzil Ayarları", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        batarya = st.number_input("Batarya Kapasitesi (kWh)", value=60, step=5)
        tuketim = st.number_input("Ortalama Tüketim (kWh/100km)", value=17.0, step=1.0)
    with col2:
        sarj_yuzdesi = st.slider("Mevcut Şarj %", min_value=1, max_value=100, value=40)
    
    kalan_enerji = batarya * (sarj_yuzdesi / 100.0)
    maks_menzil = (kalan_enerji / tuketim) * 100.0
    st.info(f"📍 **Mevcut şarj ile maksimum menziliniz: {maks_menzil:.1f} km**")

# Eylem Hafızası (Session State)
if "aktif_istasyon" not in st.session_state:
    st.session_state.aktif_istasyon = None

# İstasyonları Hesaplama ve Filtreleme
uygun_istasyonlar = []
for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    if km <= max_mesafe and ist["hiz"] in secilen_hizlar:
        ist_kopyasi = ist.copy()
        ist_kopyasi["Mesafe"] = round(km, 1)
        ist_kopyasi["Menzil_Yeterli"] = km <= maks_menzil
        uygun_istasyonlar.append(ist_kopyasi)

df = pd.DataFrame(uygun_istasyonlar).sort_values(by="Mesafe")

# ==========================================
# 🗺️ KAPALI MİMARİ: DİNAMİK HARİTA KATMANI
# ==========================================
# Kullanıcı bir emir verene kadar bu katman tamamen gizlidir!
if st.session_state.aktif_istasyon:
    st.write("### 🗺️ Canlı Navigasyon Ekranı")
    
    ist_isim, ilat, ilon, ikm = st.session_state.aktif_istasyon
    
    # Haritayı tam hedefe odaklanmış olarak başlatıyoruz
    m = folium.Map(location=[(user_lat + ilat)/2, (user_lon + ilon)/2], zoom_start=12, tiles="Cartodb dark_matter")
    
    # Kullanıcı ve Hedef Pinleri
    folium.Marker([user_lat, user_lon], popup="Buradasınız", icon=folium.Icon(color="green", icon="user", prefix="fa")).add_to(m)
    folium.Marker([ilat, ilon], popup=ist_isim, icon=folium.Icon(color="blue", icon="flash", prefix="fa")).add_to(m)
    
    # Anlık Rota Çizimi
    rota = rota_koordinatlarini_al(user_lat, user_lon, ilat, ilon)
    if rota:
        folium.PolyLine(locations=rota, color="#00FFCC", weight=6, opacity=0.9).add_to(m)
        
    # Haritayı ekrana bas (Donma ve sislenmeyi engellemek için özelleştirilmiş key)
    st_folium(m, width="100%", height=350, key=f"map_{ist_isim}")
    
    if st.button("❌ Haritayı Kapat ve Listeye Dön"):
        st.session_state.aktif_istasyon = None
        st.rerun()
    st.markdown("---")

# --- 📋 KULLANICI DOSTU SADE İSTASYON LİSTESİ ---
st.write(f"### 📍 Yakındaki İstasyonlar ({len(df.head(5))} Adet)")

for index, row in df.head(5).iterrows():
    emoji = "🟢 Ulaşılabilir" if row['Menzil_Yeterli'] else "🔴 Menzil Yetersiz"
    
    # Şık, kapalı kart tasarımı
    with st.container():
        st.markdown(f"""
        <div class="card">
            <h4>{row['isim']}</h4>
            <p style='margin: 0; color: #bbbbbb;'>⚡ Hız: {row['hiz']} | 📏 Mesafe: {row['Mesafe']} km</p>
            <p style='margin: 5px 0 0 0; font-size: 13px; color: {'#00FFCC' if row['Menzil_Yeterli'] else '#FF5555'};'><strong>{emoji}</strong></p>
        </div>
        """, unsafe_allow_html=True)
        
        # Kartın hemen altındaki temiz kontrol butonları
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("🗺️ Rotayı Çiz", key=f"route_{index}"):
                # Kullanıcı emir verdi: Harita katmanını tetikliyoruz
                st.session_state.aktif_istasyon = (row['isim'], row['enlem'], row['boylam'], row['Mesafe'])
                st.rerun()
        with c2:
            g_link = f"http://googleusercontent.com/maps.google.com/3{row['enlem']},{row['boylam']}"
            st.markdown(f"[<button style='width:100%; border:none; padding:10px; border-radius:12px; background-color:#2e2e2e; color:white; font-weight:bold; height:45px; cursor:pointer;'>↗️ Google</button>]({g_link})", unsafe_allow_html=True)
        with c3:
            with st.popover("💬 Durum"):
                st.write("💬 **Durum Bildir**")
                nick = st.text_input("Nick", key=f"n_{index}", max_chars=12)
                yorum_txt = st.text_input("Yorum", key=f"t_{index}")
                durum = st.radio("Durum", ["Çalışıyor 👍", "Arızalı 👎"], key=f"d_{index}", horizontal=True)
                if st.button("Gönder", key=f"s_{index}"):
                    if yorum_gonder(row['isim'], nick, yorum_txt, durum):
                        st.success("Paylaşıldı!")
                        st.rerun()
                
                st.markdown("---")
                st.write("📢 **Son Bildirimler:**")
                yorumlar = yorumlari_getir(row['isim'])
                if yorumlar:
                    for y in yorumlar:
                        st.markdown(f"**{y['kullanici']}** ({y['durum']}): {y['yorum']}")
                else:
                    st.caption("Bildirim yok.")
