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

# 🎨 PREMIUM CSS: "Glow & Glassmorphism" Lüks Tasarım Katmanı
st.markdown('''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        /* Kenar çubuklarını ve Streamlit elementlerini gizleme */
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }
        
        /* Arka Plan: Deep Space Black */
        .stApp { background-color: #060708 !important; }
        .block-container { padding: 1.5rem 1rem !important; max-width: 440px !important; }
        
        /* Modern ve Ortalanmış Başlık */
        .ana-baslik {
            font-family: 'SF Pro Display', '-apple-system', BlinkMacSystemFont, sans-serif;
            font-weight: 800;
            font-size: 26px;
            letter-spacing: -0.5px;
            text-align: center;
            color: #f5f5f7;
            margin-top: 10px;
            margin-bottom: 2px;
        }
        .alt-baslik {
            font-family: '-apple-system', sans-serif;
            font-size: 13px;
            text-align: center;
            color: #6c727a;
            margin-bottom: 25px;
        }
        
        /* ✨ GLASSMORPHISM & NEON GLOW PANEL MİMARİSİ */
        .glass-panel {
            background: rgba(17, 19, 24, 0.75) !important;
            backdrop-filter: blur(20px) !important;
            -webkit-backdrop-filter: blur(20px) !important;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 24px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 0 30px rgba(0, 230, 118, 0.05), 0 10px 30px rgba(0,0,0,0.5);
        }
        
        /* İstasyon Detay Metinleri */
        .istasyon-isim { font-size: 22px; font-weight: 700; color: #f5f5f7; margin: 0 0 6px 0; letter-spacing: -0.3px; }
        .mesafe-text { 
            font-size: 15px; 
            font-weight: 700; 
            color: #00e676; 
            margin: 0 0 6px 0; 
            text-transform: uppercase; 
            letter-spacing: 0.5px;
            text-shadow: 0 0 10px rgba(0, 230, 118, 0.3);
        }
        .detay-text { font-size: 13px; color: #9aa2ae; margin: 0; }
        .adres-text { font-size: 12px; color: #6c727a; margin-top: 12px; line-height: 1.4; border-top: 1px solid rgba(255, 255, 255, 0.06); padding-top: 12px; }
        
        /* Panel İçi İnce Ayrım Çizgisi */
        .panel-bolucu {
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            margin: 18px 0;
        }
        
        /* Yaşam Alanları Tasarımı */
        .panel-alt-baslik { font-size: 13px; font-weight: 600; color: #f5f5f7; margin-bottom: 12px; letter-spacing: 0.2px; }
        .avantaj-item { font-size: 12px; color: #9aa2ae; margin-bottom: 8px; display: flex; justify-content: space-between; }
        .avantaj-badge { color: #00e676; font-weight: 600; }
        
        /* Canlı Durum Değişiklik Uyarısı */
        .canli-uyari-kart {
            background: rgba(255, 69, 58, 0.1);
            backdrop-filter: blur(10px);
            border: 1px solid #ff453a;
            padding: 12px 16px;
            border-radius: 16px;
            color: #ff453a;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 15px;
            text-align: center;
            box-shadow: 0 0 20px rgba(255, 69, 58, 0.1);
        }

        /* Streamlit Expander (Menzil Paneli) Düzenlemesi */
        .streamlit-expanderHeader {
            background-color: rgba(17, 19, 24, 0.5) !important;
            backdrop-filter: blur(10px) !important;
            border: 1px solid rgba(255, 255, 255, 0.05) !important;
            border-radius: 16px !important;
            padding: 10px 15px !important;
        }
        
        /* Premium Buton Mimarisi */
        .stButton>button { 
            border-radius: 14px; 
            height: 48px; 
            font-weight: 600; 
            background-color: rgba(26, 29, 36, 0.8); 
            color: #f5f5f7; 
            border: 1px solid rgba(255, 255, 255, 0.05);
            width: 100%;
            transition: all 0.2s ease;
        }
        .stButton>button:hover { border-color: #00e676; color: #00e676; box-shadow: 0 0 15px rgba(0, 230, 118, 0.15); }
        
        /* Navigasyon Link Butonu */
        .nav-link-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            border-radius: 14px; 
            height: 48px; 
            font-weight: 600; 
            background-color: rgba(26, 29, 36, 0.8); 
            color: #f5f5f7 !important; 
            border: 1px solid rgba(255, 255, 255, 0.05);
            box-sizing: border-box;
            font-size: 14px;
            transition: all 0.2s ease;
        }
        .nav-link-btn:hover { border-color: #00e676; color: #00e676 !important; box-shadow: 0 0 15px rgba(0, 230, 118, 0.15); }

        /* Hızlı Bildirim Buton Düzenlemeleri */
        .rapor-calisiyor>button { border-color: #00e676 !important; color: #00e676 !important; background: transparent !important; }
        .rapor-calisiyor>button:hover { background-color: rgba(0, 230, 118, 0.08) !important; }
        
        .rapor-arizali>button { border-color: #ff453a !important; color: #ff453a !important; background: transparent !important; }
        .rapor-arizali>button:hover { background-color: rgba(255, 69, 58, 0.08) !important; }
    </style>
''', unsafe_allow_html=True)

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
    clean_id = "".join(c for c in istasyon_id if c.isalnum() or c in (' ', '_', '-')).rstrip()
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
    
    username = kullanici.strip() if kullanici and kullanici.strip() else "Anonim Sürücü"
    note = yorum_metni.strip() if yorum_metni and yorum_metni.strip() else f"İstasyon durumu bildirildi: {durum}"
    
    yeni_yorum = {
        "kullanici": username, "yorum": note, "durum": durum,
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

# --- 📁 ÇEVRİMDIŞI ÖNBELLEK ---
if "offline_istasyonlar" not in st.session_state:
    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            st.session_state.offline_istasyonlar = json.load(f)
    except FileNotFoundError:
        st.error("Veri dosyası bulunamadı.")
        st.stop()

istasyonlar_verisi = st.session_state.offline_istasyonlar

# --- 🚀 MOBİL BAŞLIK ALANI ---
st.markdown('<div class="ana-baslik">⚡ ŞarjBul</div>', unsafe_allow_html=True)
st.markdown('<div class="alt-baslik">En yakın aktif şarj rotanız</div>', unsafe_allow_html=True)

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

# ==========================================
# 🚗 AKILLI ARAÇ SEÇİM MENÜSÜ
# ==========================================
with st.expander("📱 Araç / Menzil Ayarı", expanded=False):
    ARAC_KATALOGU = {
        "Tesla Model Y Long Range": {"batarya": 75.0, "tuketim": 16.9},
        "Togg T10X Uzun Menzil": {"batarya": 88.5, "tuketim": 16.9},
        "BYD Atto 3": {"batarya": 60.4, "tuketim": 16.0},
        "Renault Megane E-Tech": {"batarya": 60.0, "tuketim": 15.5},
        "MG4 Electric Long Range": {"batarya": 64.0, "tuketim": 16.6},
        "Özel Araç (Manuel Giriş)": {"batarya": 60.0, "tuketim": 17.0}
    }
    
    secilen_arac = st.selectbox("Model", list(ARAC_KATALOGU.keys()), label_visibility="collapsed")
    varsayilan_degerler = ARAC_KATALOGU[secilen_arac]
    
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1: batarya = st.number_input("Kapasite", value=varsayilan_degerler["batarya"])
    with col_b2: sarj_yuzdesi = st.slider("Şarj %", min_value=1, max_value=100, value=30)
    with col_b3: tuketim = st.number_input("Tüketim", value=varsayilan_degerler["tuketim"])
        
maks_menzil = ((batarya * (sarj_yuzdesi / 100.0)) / tuketim) * 100.0
st.markdown("<div style='margin-bottom:15px;'></div>", unsafe_allow_html=True)

# ==========================================
# 🧠 MUTLAK EN YAKIN AKTİF İSTASYONU BULMA
# ==========================================
en_uygun_istasyon = None
en_yakin_mesafe = float('inf')

for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    if km <= maks_menzil and km < en_yakin_mesafe:
        if not istasyon_arizali_mi(ist["isim"]):
            en_yakin_mesafe = km
            en_uygun_istasyon = ist.copy()
            en_uygun_istasyon["Mesafe"] = round(km, 1)

# ==========================================
# 🎯 GLOW & GLASSMORPHISM ENTEGRE PANEL
# ==========================================
if en_uygun_istasyon:
    
    # Canlı Durum Değişiklik Kontrolü
    if "nav_başlatıldı" in st.session_state and st.session_state["nav_başlatıldı"] == en_uygun_istasyon['isim']:
        if istasyon_arizali_mi(en_uygun_istasyon['isim']):
            st.markdown(f'<div class="canli-uyari-kart">Yoldaki İstasyonun Durumu Değişti! İstasyon arızalı bildirildi.</div>', unsafe_allow_html=True)

    # PANEL BAŞLANGICI
    st.markdown(f"""
    <div class="glass-panel">
        <div class="mesafe-text">✦ {en_uygun_istasyon['Mesafe']} km uzaklıkta</div>
        <div class="istasyon-isim">{en_uygun_istasyon['isim']}</div>
        <div class="detay-text">Şarj Hızı: {en_uygun_istasyon['hiz']}</div>
        <div class="adres-text">{en_uygun_istasyon['adres']}</div>
        <div class="panel-bolucu"></div>
        <div class="panel-alt-baslik">Yakındaki Yaşam Alanları</div>
        <div class="avantaj-item"><span>Kahve Dünyası (Dinlenme)</span><span class="avantaj-badge">120m</span></div>
        <div class="avantaj-item"><span>Migros Jet (Alışveriş)</span><span class="avantaj-badge">250m</span></div>
        <div class="avantaj-item"><span>ŞarjBul Sürücü Avantajı</span><span class="avantaj-badge">%15 İndirim</span></div>
    </div>
    """, unsafe_allow_html=True)
    
    # Eylem Butonları
    c1, c2 = st.columns(2)
    
    with c1:
        g_link = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={en_uygun_istasyon['enlem']},{en_uygun_istasyon['boylam']}&travelmode=driving"
        if st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn">Navigasyonu Başlat</a>', unsafe_allow_html=True):
            st.session_state["nav_başlatıldı"] = en_uygun_istasyon['isim']
        
    with c2:
        with st.popover("Durum Bildir"):
            st.write("Tek Dokunuşla Hızlı Bildir")
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                st.markdown('<div class="rapor-calisiyor">', unsafe_allow_html=True)
                if st.button("Sorunsuz", key="btn_ok"):
                    if yorum_gonder(en_uygun_istasyon['isim'], "Anonim Sürücü", "", "Sorunsuz / Boş"): st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
                
            with col_btn2:
                st.markdown('<div class="rapor-arizali">', unsafe_allow_html=True)
                if st.button("Arızalı", key="btn_fail"):
                    if yorum_gonder(en_uygun_istasyon['isim'], "Anonim Sürücü", "", "Arızalı / Kapalı"): st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown("---")
            st.caption("Detay Eklemek İster Misiniz?")
            nick = st.text_input("Kullanıcı Adı", max_chars=12, key="inp_nick")
            yorum_txt = st.text_input("Arıza Notu", key="inp_txt")
            if st.button("Detaylı Gönder", key="btn_detail"):
                if yorum_gonder(en_uygun_istasyon['isim'], nick, yorum_txt, "Durum Güncellemesi"): st.rerun()
            
            st.markdown("---")
            yorumlar = yorumlari_getir(en_uygun_istasyon['isim'])
            if yorumlar:
                for y in sorted(yorumlar, key=lambda x: x.get('tarih', ''), reverse=True)[:2]:
                    zaman_etiketi = zaman_oncesi(y.get('tarih', ''))
                    st.markdown(f"**{y['kullanici']}** ({y['durum']}) • *{zaman_etiketi}*")
                    st.caption(f"> {y['yorum']}")
else:
    st.warning("Menzilinize uygun aktif bir istasyon bulunamadı.")
