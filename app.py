import streamlit as st
import pandas as pd
import json
import math
import requests
from datetime import datetime
from streamlit_js_eval import get_geolocation

# --- 📱 MOBİL VE MİNİMALİST SAYFA AYARLARI ---
st.set_page_config(
    page_title="Elektirikli Şarj Bul", 
    page_icon="⚡", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# 🎨 PREMIUM CSS: "Midnight Cyber" Lüks Gece Sürüşü Renk Paleti
st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        /* Kenar çubuklarını ve Streamlit elementlerini gizleme */
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        
        /* Arka Plan: Ultra Deep Black (#08090a) */
        .stApp { background-color: #08090a !important; }
        .block-container { padding: 2rem 1rem !important; max-width: 480px !important; }
        
        /* Modern ve Ortalanmış Başlık - Apple Silver (#f5f5f7) */
        .ana-baslik {
            font-family: 'SF Pro Display', '-apple-system', BlinkMacSystemFont, sans-serif;
            font-weight: 800;
            font-size: 32px;
            letter-spacing: -0.5px;
            text-align: center;
            color: #f5f5f7;
            margin-bottom: 5px;
        }
        .alt-baslik {
            font-family: '-apple-system', sans-serif;
            font-size: 14px;
            text-align: center;
            color: #6c727a;
            margin-bottom: 25px;
        }
        
        /* Cyber Slate Blue Premium Kart Tasarımı (#111318) */
        .oneri-kart { 
            background: #111318; 
            padding: 24px; 
            border-radius: 16px; 
            border: 1px solid #1f242e;
            margin-bottom: 20px; 
            box-shadow: 0 4px 24px rgba(0,0,0,0.4);
        }
        .istasyon-isim { font-size: 20px; font-weight: 700; color: #f5f5f7; margin: 0 0 8px 0; }
        
        /* Neon Cyber Green (#00e676) */
        .mesafe-text { font-size: 16px; font-weight: 600; color: #00e676; margin: 0 0 4px 0; }
        .detay-text { font-size: 14px; color: #9aa2ae; margin: 0; }
        .adres-text { font-size: 12px; color: #6c727a; margin-top: 8px; line-height: 1.4; }
        
        /* Canlı Durum Değişiklik Uyarısı */
        .canli-uyari-kart {
            background: #221214;
            border: 1px solid #ff453a;
            padding: 12px 16px;
            border-radius: 12px;
            color: #ff453a;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 15px;
            text-align: center;
        }
        
        /* Yaşam Alanı & Avantajlar Katmanı */
        .avantaj-konteyner {
            background: #111318;
            border-radius: 12px;
            padding: 16px;
            border: 1px solid #1f242e;
            margin-top: 15px;
        }
        .avantaj-baslik { font-size: 14px; font-weight: 600; color: #f5f5f7; margin-bottom: 10px; }
        .avantaj-item { font-size: 12px; color: #9aa2ae; margin-bottom: 6px; display: flex; justify-content: space-between; }
        .avantaj-badge { color: #00e676; font-weight: 600; }

        /* Buton Mimarisi */
        .stButton>button { 
            border-radius: 12px; 
            height: 46px; 
            font-weight: 600; 
            background-color: #111318; 
            color: #f5f5f7; 
            border: 1px solid #1f242e;
            width: 100%;
            transition: all 0.2s ease;
        }
        .stButton>button:hover { border-color: #00e676; color: #00e676; background-color: #151922; }
        
        /* Navigasyon Link Butonu */
        .nav-link-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            border-radius: 12px; 
            height: 46px; 
            font-weight: 600; 
            background-color: #111318; 
            color: #f5f5f7 !important; 
            border: 1px solid #1f242e;
            box-sizing: border-box;
            font-size: 14px;
            transition: all 0.2s ease;
        }
        .nav-link-btn:hover { border-color: #00e676; color: #00e676 !important; background-color: #151922; }
    </style>
""", unsafe_allow_html=True)

# İki Nokta Arası Mesafe Hesaplama
def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def zaman_oncesi(tarih_str):
    try:
        eski_zaman = datetime.strptime(tarih_str, "%d.%m %H:%M")
        simdi = datetime.now()
        eski_zaman = eski_zaman.replace(year=simdi.year)
        fark = simdi - eski_zaman
        saniye = fark.total_seconds()
        if saniye < 0: return "Az önce"
        dakika = int(saniye / 60)
        saat = int(dakika / 60)
        gun = int(saat / 24)
        if dakika < 1: return "Az önce"
        elif dakika < 60: return f"{dakika} dakika önce"
        elif saat < 24: return f"{saat} saat önce"
        else: return f"{gun} gün önce"
    except: return tarih_str

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

# --- 📁 ÇEVRİMDIŞI ÖNBELLEK (OFFLINE CACHE) ---
if "offline_istasyonlar" not in st.session_state:
    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            st.session_state.offline_istasyonlar = json.load(f)
    except FileNotFoundError:
        st.error("Veri dosyası bulunamadı.")
        st.stop()

istasyonlar_verisi = st.session_state.offline_istasyonlar

# --- 🚀 BAŞLIK ALANI ---
st.markdown('<div class="ana-baslik">Elektirikli Şarj Bul</div>', unsafe_allow_html=True)
st.markdown('<div class="alt-baslik">Konumunuza en yakın aktif istasyon listelenir.</div>', unsafe_allow_html=True)

# ==========================================
# 📡 GPS ENTEGRASYONU VE GÜVENLİK DUVARI
# ==========================================
user_lat, user_lon = None, None

try:
    konum_verisi = get_geolocation()
    if konum_verisi and 'coords' in konum_verisi:
        user_lat = konum_verisi['coords'].get('latitude')
        user_lon = konum_verisi['coords'].get('longitude')
        st.session_state["last_valid_lat"] = user_lat
        st.session_state["last_valid_lon"] = user_lon
except Exception:
    pass

if not user_lat or not user_lon:
    user_lat = st.session_state.get("last_valid_lat")
    user_lon = st.session_state.get("last_valid_lon")

if not user_lat or not user_lon:
    st.info("Konumunuza en yakın istasyonu bulabilmemiz için lütfen çıkan panelden konum izni verin.")
    st.markdown("""
        <div style='text-align:center; color:#6c727a; font-size:12px; margin-top:20px; line-height:1.4;'>
            Not: Eğer Instagram, X veya WhatsApp içerisinden giriş yaptıysanız, uygulama içi tarayıcılar GPS iznini engelleyebilir. Lütfen bağlantıyı kopyalayıp doğrudan Safari veya Chrome üzerinde açın.
        </div>
    """, unsafe_allow_html=True)
    st.stop()

# MENZİL HESAPLAMA (Minimalist Panel)
with st.expander("Menzil Durumu", expanded=False):
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1: batarya = st.number_input("Batarya (kWh)", value=60)
    with col_b2: sarj_yuzdesi = st.slider("Şarj %", min_value=1, max_value=100, value=30)
    with col_b3: tuketim = st.number_input("Tüketim", value=17.0)
maks_menzil = ((batarya * (sarj_yuzdesi / 100.0)) / tuketim) * 100.0

# ==========================================
# 🧠 TÜM TÜRKİYE'DE MUTLAK EN YAKIN AKTİF İSTASYONU BULMA
# ==========================================
en_uygun_istasyon = None
en_yakin_mesafe = float('inf')

for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    
    if km <= maks_menzil:
        if km < en_yakin_mesafe:
            if not istasyon_arizali_mi(ist["isim"]):
                en_yakin_mesafe = km
                en_uygun_istasyon = ist.copy()
                en_uygun_istasyon["Mesafe"] = round(km, 1)

# ==========================================
# 🎯 REY-BAN / APPLE SADELİĞİNDE TEK ÖNERİ KATMANI
# ==========================================
if en_uygun_istasyon:
    
    # Canlı Durum Değişiklik Kontrolü
    if "nav_başlatıldı" in st.session_state and st.session_state["nav_başlatıldı"] == en_uygun_istasyon['isim']:
        if istasyon_arizali_mi(en_uygun_istasyon['isim']):
            st.markdown("""
                <div class="canli-uyari-kart">
                    Yoldaki İstasyonun Durumu Değişti! İstasyon arızalı veya kapalı olarak bildirildi.
                </div>
            """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="oneri-kart">
        <div class="istasyon-isim">{en_uygun_istasyon['isim']}</div>
        <div class="mesafe-text">{en_uygun_istasyon['Mesafe']} km uzaklıkta</div>
        <div class="detay-text">Şarj Hızı: {en_uygun_istasyon['hiz']}</div>
        <div class="adres-text">{en_uygun_istasyon['adres']}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Eylem Alanı
    c1, c2 = st.columns(2)
    
    with c1:
        g_link = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={en_uygun_istasyon['enlem']},{en_uygun_istasyon['boylam']}&travelmode=driving"
        if st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn" id="nav_btn">Navigasyonu Başlat</a>', unsafe_allow_html=True):
            st.session_state["nav_başlatıldı"] = en_uygun_istasyon['isim']
        
    with c2:
        with st.popover("Durum Bildir"):
            st.write("İstasyon Durumu")
            nick = st.text_input("Kullanıcı Adı", max_chars=12)
            yorum_txt = st.text_input("Mevcut Durum")
            durum = st.radio("İstasyon Durumu", ["Sorunsuz / Boş", "Arızalı / Kapalı"], horizontal=True)
            if st.button("Gönder"):
                if yorum_gonder(en_uygun_istasyon['isim'], nick, yorum_txt, durum):
                    st.rerun()
            
            st.markdown("---")
            
            # Dinamik Zaman Damgalı Son Yorumlar
            yorumlar = yorumlari_getir(en_uygun_istasyon['isim'])
            if yorumlar:
                for y in sorted(yorumlar, key=lambda x: x.get('tarih', ''), reverse=True)[:3]:
                    zaman_etiketi = zaman_oncesi(y.get('tarih', ''))
                    st.markdown(f"**{y['kullanici']}** ({y['durum']}) • *{zaman_etiketi}*")
                    st.caption(f"> {y['yorum']}")
            else:
                st.caption("Bildirim bulunmuyor.")

    # YAŞAM ALANI & AVANTAJLAR KATMANI
    st.markdown(f"""
    <div class="avantaj-konteyner">
        <div class="avantaj-baslik">Şarj Süresince Yakınlardaki Yaşam Alanları</div>
        <div class="avantaj-item">
            <span>Kahve Dünyası (Dinlenme Alanı)</span>
            <span class="avantaj-badge">120m yürüme</span>
        </div>
        <div class="avantaj-item">
            <span>Migros Jet (Alışveriş)</span>
            <span class="avantaj-badge">250m yürüme</span>
        </div>
        <div class="avantaj-item">
            <span>ŞarjBul Kullanıcılarına Özel Restoran İndirimi</span>
            <span class="avantaj-badge">%15 İndirim</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

else:
    st.warning("Menzilinize uygun aktif bir istasyon bulunamadı.")
