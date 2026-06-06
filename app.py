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

# 🎨 PREMIUM CSS: "Executive White & Navy" Hatasızlaştırma Katmanı
st.markdown('''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        /* Standart Streamlit elementlerini gizleme */
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }
        
        /* Arka Plan: Clean Luxury Light Gray/White */
        .stApp { background-color: #f8f9fa !important; }
        .block-container { padding: 2rem 1rem !important; max-width: 440px !important; }
        
        /* 🏛️ BAŞLIK İÇİN LÜKS TABLO MİMARİSİ */
        .title-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 25px;
            border: 2px solid #0f172a;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
        }
        .title-cell {
            background-color: #0f172a;
            color: #ffffff !important;
            font-family: 'Inter', '-apple-system', sans-serif;
            font-weight: 800;
            font-size: 24px;
            letter-spacing: 0.5px;
            text-align: center;
            padding: 14px;
            text-transform: uppercase;
        }
        .subtitle-cell {
            background-color: #ffffff;
            color: #475569 !important;
            font-family: 'Inter', '-apple-system', sans-serif;
            font-size: 13px;
            font-weight: 500;
            text-align: center;
            padding: 10px;
            border-top: 1px solid #e2e8f0;
            letter-spacing: 0.2px;
        }
        
        /* Tema Çakışmasını Önleyen Global Input Renk Sabitleyicileri */
        .stSelectbox label p, .stSlider label p, .stNumberInput label p, .stTextInput label p {
            color: #0f172a !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #e2e8f0 !important;
        }
        input {
            color: #0f172a !important;
            background-color: #ffffff !important;
        }
        
        /* 💳 EXECUTIVE WHITE & NAVY KART MİMARİSİ */
        .premium-card {
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-top: 5px solid #0f172a !important;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
            margin-bottom: 20px;
        }
        
        /* Kart İçi Tipografi */
        .istasyon-isim { font-size: 20px; font-weight: 700; color: #0f172a !important; margin: 0 0 6px 0; letter-spacing: -0.3px; }
        .mesafe-text { font-size: 14px; font-weight: 700; color: #1e40af !important; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px; }
        .detay-text { font-size: 13px; color: #475569 !important; margin: 0; font-weight: 500; }
        .adres-text { font-size: 12px; color: #64748b !important; margin-top: 14px; line-height: 1.5; border-top: 1px solid #f1f5f9; padding-top: 14px; }
        
        /* Ayrım Çizgisi ve Alt Alanlar */
        .panel-bolucu { border-top: 1px solid #f1f5f9; margin: 18px 0; }
        .panel-alt-baslik { font-size: 13px; font-weight: 700; color: #0f172a !important; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.3px; }
        .avantaj-item { font-size: 12px; color: #475569 !important; margin-bottom: 8px; display: flex; justify-content: space-between; font-weight: 500; }
        .avantaj-badge { color: #1e40af !important; font-weight: 700; }
        
        /* Canlı Durum Değişiklik Uyarısı (Kurumsal Alarm) */
        .canli-uyari-kart {
            background: #fef2f2 !important;
            border: 1px solid #ef4444 !important;
            padding: 12px 16px;
            border-radius: 12px;
            color: #991b1b !important;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 15px;
            text-align: center;
        }

        /* Streamlit Elementlerinin Kurumsal Adaptasyonu */
        .streamlit-expanderHeader {
            background-color: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 12px !important;
            padding: 12px 16px !important;
            color: #0f172a !important;
            font-weight: 600 !important;
        }
        
        /* Lacivert Buton Tasarımları */
        .stButton>button { 
            border-radius: 10px; 
            height: 46px; 
            font-weight: 600; 
            background-color: #0f172a; 
            color: #ffffff !important; 
            border: 1px solid #0f172a;
            width: 100%;
            transition: all 0.2s ease;
        }
        .stButton>button:hover { background-color: #1e3a8a; border-color: #1e3a8a; color: #ffffff !important; box-shadow: 0 4px 12px rgba(30, 58, 138, 0.15); }
        
        /* Navigasyon Link Butonu */
        .nav-link-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            border-radius: 10px; 
            height: 46px; 
            font-weight: 600; 
            background-color: #0f172a; 
            color: #ffffff !important; 
            border: 1px solid #0f172a;
            box-sizing: border-box;
            font-size: 14px;
            transition: all 0.2s ease;
        }
        .nav-link-btn:hover { background-color: #1e3a8a; border-color: #1e3a8a; color: #ffffff !important; box-shadow: 0 4px 12px rgba(30, 58, 138, 0.15); }

        /* Hızlı Durum Bildirim Butonları */
        .rapor-calisiyor>button { border-color: #2563eb !important; color: #2563eb !important; background: #eff6ff !important; }
        .rapor-calisiyor>button:hover { background-color: #dbeafe !important; }
        
        .rapor-arizali>button { border-color: #dc2626 !important; color: #dc2626 !important; background: #fef2f2 !important; }
        .rapor-arizali>button:hover { background-color: #fee2e2 !important; }
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

# ==========================================
# 🏛️ TABLO İÇİNDE BAŞLIK ALANI
# ==========================================
st.markdown('''
    <table class="title-table">
        <tr>
            <td class="title-cell">ŞarjBul</td>
        </tr>
        <tr>
            <td class="subtitle-cell">En yakın aktif şarj rotanız</td>
        </tr>
    </table>
''', unsafe_allow_html=True)

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

# ⚠️ Tema Bağımsız Durum Bildirim Paneli (Eğer GPS Bekleniyorsa)
if not user_lat or not user_lon:
    st.markdown("""
    <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; border-left: 5px solid #2563eb; padding: 16px; border-radius: 12px; margin-top: 10px; margin-bottom: 20px;">
        <div style="color: #1e40af; font-weight: 700; font-size: 14px; margin-bottom: 4px; text-transform: uppercase;">Konum İzini Bekleniyor</div>
        <div style="color: #1e3a8a; font-size: 13px; font-weight: 500; line-height: 1.4;">
            En yakın istasyonu hesaplayabilmemiz için lütfen tarayıcınızın veya telefonunuzun üst kısmında çıkan konum erişim talebini onaylayın.
        </div>
    </div>
    <div style='text-align:center; color:#64748b; font-size:12px; margin-top:10px; line-height:1.4;'>
        Not: Eğer Instagram, X veya WhatsApp içerisinden giriş yaptıysanız, uygulama içi tarayıcılar GPS iznini engelleyebilir. Lütfen bağlantıyı kopyalayıp doğrudan Safari veya Chrome üzerinde açın.
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ==========================================
# 🚗 AKILLI ARAÇ SEÇİM MENÜSÜ
# ==========================================
with st.expander("Araç ve Menzil Ayarları", expanded=False):
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
# 🎯 EXECUTIVE WHITE & NAVY ENTEGRE PANEL
# ==========================================
if en_uygun_istasyon:
    
    if "nav_başlatıldı" in st.session_state and st.session_state["nav_başlatıldı"] == en_uygun_istasyon['isim']:
        if istasyon_arizali_mi(en_uygun_istasyon['isim']):
            st.markdown(f'<div class="canli-uyari-kart">Yoldaki istasyonun durumu değişti! İstasyon arızalı bildirildi.</div>', unsafe_allow_html=True)

    # PREMIUM BEYAZ VE LACİVERT PANEL BAŞLANGICI
    st.markdown(f"""
    <div class="premium-card">
        <div class="mesafe-text">{en_uygun_istasyon['Mesafe']} km uzaklıkta</div>
        <div class="istasyon-isim">{en_uygun_istasyon['isim']}</div>
        <div class="detay-text">Şarj Hızı: {en_uygun_istasyon['hiz']}</div>
        <div class="adres-text">{en_uygun_istasyon['adres']}</div>
        <div class="panel-bolucu"></div>
        <div class="panel-alt-baslik">Yakındaki Yaşam Alanları</div>
        <div class="avantaj-item"><span>Kahve Dünyası (Dinlenme)</span><span class="avantaj-badge">120m</span></div>
        <div class="avantaj-item"><span>Migros Jet (Alışveriş)</span><span class="avantaj-badge">250m</span></div>
        <div class="avantaj-item"><span>Sürücü Avantajı</span><span class="avantaj-badge">%15 İndirim</span></div>
    </div>
    """, unsafe_allow_html=True)
    
    # Eylem Butonları
    c1, c2 = st.columns(2)
    
    with c1:
        # Evrensel Google Maps Yönlendirme API Linki
        g_link = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={en_uygun_istasyon['enlem']},{en_uygun_istasyon['boylam']}&travelmode=driving"
        if st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn">Navigasyonu Başlat</a>', unsafe_allow_html=True):
            st.session_state["nav_başlatıldı"] = en_uygun_istasyon['isim']
        
    with c2:
        with st.popover("Durum Bildir"):
            st.write("Tek dokunuşla hızlı bildirim gönderin")
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
            st.caption("Detay eklemek ister misiniz?")
            nick = st.text_input("Kullanıcı Adı", max_chars=12, key="inp_nick")
            yorum_txt = st.text_input("Durum Notu", key="inp_txt")
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
    # ⚠️ Tema Bağımsız İstasyon Bulunamadı Kartı
    st.markdown("""
    <div style="background-color: #fff1f2; border: 1px solid #fecdd3; border-left: 5px solid #e11d48; padding: 16px; border-radius: 12px; margin-top: 10px;">
        <div style="color: #9f1239; font-weight: 700; font-size: 14px; margin-bottom: 4px; text-transform: uppercase;">Menzil Aşımı / İstasyon Bulunamadı</div>
        <div style="color: #4c0519; font-size: 13px; font-weight: 500; line-height: 1.4;">
            Mevcut şarj yüzdeniz ve konumunuza göre ulaşılabilecek aktif bir şarj istasyonu bulunamadı. Lütfen yukarıdaki panelden şarj yüzdenizi veya araç modelinizi güncelleyin.
        </div>
    </div>
    """, unsafe_allow_html=True)
