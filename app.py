import streamlit as st
import json
import math
import hashlib
import logging
import unicodedata
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import html
from streamlit_js_eval import get_geolocation
import sentry_sdk  # YENİ: Sentry eklendi

# --- 📱 MOBİL VE PREMIUM SAYFA AYARLARI ---
st.set_page_config(
    page_title="ŞarjBul",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 🚨 SENTRY HATA TAKİP (GRACEFUL INIT)
# ==========================================
try:
    if "sentry" in st.secrets and "dsn" in st.secrets["sentry"]:
        sentry_sdk.init(
            dsn=st.secrets["sentry"]["dsn"],
            traces_sample_rate=1.0,
        )
except Exception:
    pass  # Sentry secrets yoksa uygulama çökmeyecek, sessizce devam edecek

# ==========================================
# 🪵 LOGLAMA AYARI
# ==========================================
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ==========================================
# 🔐 FİREBASE BAĞLANTISI VE AUTH SABİTLERİ
# ==========================================
try:
    FIREBASE_DB_URL = st.secrets["firebase"]["db_url"]
    FIREBASE_API_KEY = st.secrets["firebase"]["api_key"] # Auth için gerekli
except (KeyError, FileNotFoundError):
    st.error("Firebase bağlantı bilgileri (db_url ve api_key) bulunamadı. Lütfen secrets.toml dosyasını kontrol edin.")
    st.stop()

# ==========================================
# 📐 UYGULAMA SABİTLERİ
# ==========================================
MAX_ISTASYON_SAYISI = 2        
OVERPASS_TIMEOUT_S  = 12.0     
FIREBASE_TIMEOUT_S  = 4.0      
YORUM_CACHE_TTL     = 30       
CEVRE_CACHE_TTL     = 86_400   
MAX_YAKIN_YER       = 5        
MAX_SON_YORUM       = 2
YOL_UZAMA_KATSAYISI = 1.25
YORUM_BEKLEME_SURESI = 30        

ARAC_KATALOGU: dict = {
    "Tesla Model Y Long Range": {"batarya": 75.0, "tuketim": 16.9},
    "Togg T10X Uzun Menzil":   {"batarya": 88.5, "tuketim": 16.9},
    "BYD Atto 3":               {"batarya": 60.4, "tuketim": 16.0},
    "Renault Megane E-Tech":    {"batarya": 60.0, "tuketim": 15.5},
    "Özel Araç (Manuel)":      {"batarya": 60.0, "tuketim": 17.0},
}

KATEGORI_EMOJILER: dict = {
    "cafe":        ("☕",  "Kafe"),
    "restaurant":  ("🍽️", "Restoran"),
    "fast_food":   ("🍔", "Fast Food"),
    "supermarket": ("🛒", "Süpermarket"),
    "convenience": ("🏪", "Market"),
    "fuel":        ("⛽", "Akaryakıt"),   
    "parking":     ("🅿️", "Otopark"),
    "hotel":       ("🏨", "Otel"),
    "mall":        ("🏬", "AVM"),
    "pharmacy":    ("💊", "Eczane"),
    "atm":         ("🏧", "ATM"),
    "toilets":     ("🚻", "Tuvalet"),
}

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter"
]
OVERPASS_HEADERS = {
    "User-Agent": "SarjBul/2.0",
    "Accept":     "application/json",
}

# 🎨 PREMIUM CSS (Sidebar engelleri kaldırıldı)
st.markdown('''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        [data-testid="stHeader"] { display: none !important; }
        .stApp { background-color: #f8f9fa !important; }
        .block-container { padding: 1.5rem 1rem !important; max-width: 440px !important; }
        .title-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; border: 2px solid #0f172a; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08); }
        .title-cell { background-color: #0f172a; color: #ffffff !important; font-family: 'Inter', sans-serif; font-weight: 800; font-size: 24px; text-align: center; padding: 14px; text-transform: uppercase; }
        .subtitle-cell { background-color: #ffffff; color: #475569 !important; font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 500; text-align: center; padding: 10px; border-top: 1px solid #e2e8f0; }
        .premium-card { background: #ffffff !important; border: 1px solid #e2e8f0 !important; border-top: 5px solid #0f172a !important; border-radius: 16px; padding: 24px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04); margin-bottom: 20px; }
        .istasyon-isim { font-size: 20px; font-weight: 700; color: #0f172a !important; margin: 0 0 6px 0; letter-spacing: -0.3px; }
        .mesafe-text { font-size: 14px; font-weight: 700; color: #1e40af !important; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px; }
        .detay-text { font-size: 13px; color: #475569 !important; margin: 0; font-weight: 500; }
        .adres-text { font-size: 12px; color: #64748b !important; margin-top: 14px; line-height: 1.5; border-top: 1px solid #f1f5f9; padding-top: 14px; }
        .panel-bolucu { border-top: 1px solid #f1f5f9; margin: 18px 0; }
        .panel-alt-baslik { font-size: 13px; font-weight: 700; color: #0f172a !important; margin-bottom: 12px; text-transform: uppercase; }
        .avantaj-item { font-size: 12px; color: #475569 !important; margin-bottom: 8px; display: flex; justify-content: space-between; font-weight: 500; }
        .avantaj-badge { color: #1e40af !important; font-weight: 700; }
        .nav-link-btn { display: flex; align-items: center; justify-content: center; text-decoration: none; border-radius: 10px; height: 46px; font-weight: 600; background-color: #0f172a; color: #ffffff !important; border: 1px solid #0f172a; font-size: 14px; }
        .stButton>button { border-radius: 10px; height: 46px; font-weight: 600; width: 100%; }
        .rapor-calisiyor>button { border-color: #2563eb !important; color: #2563eb !important; background: #eff6ff !important; }
        .rapor-arizali>button { border-color: #dc2626 !important; color: #dc2626 !important; background: #fef2f2 !important; }
    </style>
''', unsafe_allow_html=True)

# ==========================================
# 🛠️ YARDIMCI VE AUTH FONKSİYONLARI
# ==========================================
@st.cache_resource
def get_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "SarjBul/2.0"})
    return session

def guvenli_metin(metin: str) -> str:
    return html.escape(str(metin or "").strip())

def yorum_gonderilebilir_mi() -> bool:
    son = st.session_state.get("son_yorum_zamani")
    if son is None:
        return True
    return (datetime.now() - son).total_seconds() > YORUM_BEKLEME_SURESI

def clean_id_uret(isim: str) -> str:
    normalized = unicodedata.normalize("NFKD", isim)
    ascii_isim = normalized.encode("ascii", "ignore").decode("ascii").strip()
    safe = "".join(c for c in ascii_isim if c.isalnum() or c in (" ", "_", "-")).rstrip()
    return safe if safe else hashlib.md5(isim.encode()).hexdigest()[:12]

def mesafe_hesapla(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def yorum_tarihi_parse(tarih_str: str) -> datetime:
    try: return datetime.fromisoformat(tarih_str)
    except Exception: return datetime.min

# YENİ: REST API ile Firebase Authentication
def firebase_login(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    try:
        r = get_session().post(url, json={"email": email, "password": password, "returnSecureToken": True}, timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error("Auth hatası: %s", e)
    return None

# ==========================================
# 🗄️ DİNAMİK VERİ ÇEKİMİ (TTL + GRACEFUL FALLBACK)
# ==========================================
@st.cache_data(ttl=600)  # YENİ: 10 Dakika TTL (10 * 60 saniye)
def istasyonlari_yukle() -> list:
    url = f"{FIREBASE_DB_URL}istasyonlar.json"
    try:
        # 1. Aşama: Firebase'den canlı veri çekmeyi dene
        res = get_session().get(url, timeout=3.0)
        if res.status_code == 200 and res.json():
            veri = res.json()
            # Firebase dict yapısında dönerse listeye çeviriyoruz
            if isinstance(veri, dict):
                return list(veri.values())
            return veri
    except Exception as e:
        # Sentry loglaması
        sentry_sdk.capture_exception(e)
        logger.warning("Firebase'den istasyonlar çekilemedi, Graceful Fallback devrede: %s", e)
    
    # 2. Aşama (Graceful Fallback): Firebase çökerse veya timeout olursa lokal dosyayı oku
    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Fallback JSON dosyası da okunamadı: %s", e)
        return []

istasyonlar_verisi = istasyonlari_yukle()

# ==========================================
# 🎛️ SIDEBAR KONTROLLERİ VE AUTHENTICATION
# ==========================================
with st.sidebar:
    st.header("🔑 Giriş Yap")
    if "auth_token" not in st.session_state:
        email = st.text_input("E-posta")
        password = st.text_input("Şifre", type="password")
        if st.button("Giriş Yap", use_container_width=True):
            user_data = firebase_login(email, password)
            if user_data:
                st.session_state["auth_token"] = user_data["idToken"]
                st.session_state["auth_email"] = user_data["email"]
                st.success("Giriş başarılı!")
                st.rerun()
            else:
                st.error("Giriş başarısız. Lütfen bilgilerinizi kontrol edin.")
    else:
        st.success(f"Hoş geldiniz, {st.session_state.get('auth_email', 'Kullanıcı')}!")
        if st.button("Çıkış Yap", use_container_width=True):
            del st.session_state["auth_token"]
            del st.session_state["auth_email"]
            st.rerun()

    st.markdown("---")
    st.header("⚙️ Arama Ayarları")
    # YENİ: Çevre arama yarıçapı kullanıcı kontrolüne bırakıldı
    ayar_yaricap = st.slider("Çevresel Mekan Arama Yarıçapı (m)", min_value=100, max_value=800, value=400, step=100)
    
    st.markdown("---")
    st.info("Kullanıcı deneyimi için yan menüyü kapatabilirsiniz.")

# ==========================================
# 🌐 YORUM VE ÇEVRE VERİLERİ ÇEKİMİ
# ==========================================
@st.cache_data(ttl=YORUM_CACHE_TTL)
def arizali_istasyon_setini_getir() -> set:
    url = f"{FIREBASE_DB_URL}yorumlar.json"
    arizali_set = set()
    try:
        res = get_session().get(url, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code == 200 and res.json():
            for clean_id, pkts in res.json().items():
                if isinstance(pkts, dict):
                    sirali = sorted(pkts.values(), key=lambda x: yorum_tarihi_parse(x.get("tarih", "")))
                    if sum(1 for y in sirali[-5:] if "Arızalı" in y.get("durum", "")) >= 3:
                        arizali_set.add(clean_id)
    except Exception: pass
    return arizali_set

@st.cache_data(ttl=CEVRE_CACHE_TTL)
def yakin_cevre_getir(enlem: float, boylam: float, yaricap_m: int) -> list:
    sorgu = f"""
    [out:json][timeout:{int(OVERPASS_TIMEOUT_S)}];
    (
      node["amenity"~"cafe|restaurant|fast_food|parking|pharmacy|atm|toilets|fuel"](around:{yaricap_m},{enlem},{boylam});
      node["shop"~"supermarket|convenience|mall"](around:{yaricap_m},{enlem},{boylam});
      node["tourism"="hotel"](around:{yaricap_m},{enlem},{boylam});
    );
    out body;
    """
    for url in OVERPASS_URLS:
        try:
            res = requests.post(url, data={"data": sorgu}, headers=OVERPASS_HEADERS, timeout=OVERPASS_TIMEOUT_S)
            if res.status_code == 200:
                sonuclar = []
                for el in res.json().get("elements", []):
                    tags = el.get("tags", {})
                    amenity = tags.get("amenity", tags.get("shop", tags.get("tourism", "")))
                    if amenity in KATEGORI_EMOJILER:
                        km = mesafe_hesapla(enlem, boylam, el.get("lat", enlem), el.get("lon", boylam))
                        emoji, kat_adi = KATEGORI_EMOJILER[amenity]
                        sonuclar.append({"isim": guvenli_metin(tags.get("name") or kat_adi), "kategori": kat_adi, "emoji": emoji, "metre": int(km * 1000)})
                
                gorulmus, filtrelenmis = set(), []
                for s in sorted(sonuclar, key=lambda x: x["metre"]):
                    if s["kategori"] not in gorulmus:
                        gorulmus.add(s["kategori"])
                        filtrelenmis.append(s)
                    if len(filtrelenmis) >= MAX_YAKIN_YER: break
                return filtrelenmis
        except Exception: continue
    return []

def _cevre_getir_ist(ist: dict) -> list:
    return yakin_cevre_getir(ist["enlem"], ist["boylam"], ayar_yaricap)

def _paralel_cevre_getir(istasyon_listesi: list) -> list:
    with ThreadPoolExecutor(max_workers=max(1, len(istasyon_listesi))) as executor:
        return list(executor.map(_cevre_getir_ist, istasyon_listesi))

def yorum_gonder(istasyon_id: str, kullanici: str, yorum_metni: str, durum: str) -> bool:
    if not yorum_gonderilebilir_mi(): return False
    clean_id = clean_id_uret(istasyon_id)
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
    
    # Kullanıcı login olmuşsa mail adresinin ilk kısmını nick olarak al
    if "auth_email" in st.session_state and kullanici == "Anonim Sürücü":
        kullanici = st.session_state["auth_email"].split("@")[0]

    yeni_yorum = {"kullanici": guvenli_metin(kullanici), "yorum": guvenli_metin(yorum_metni), "durum": guvenli_metin(durum), "tarih": datetime.now().isoformat()}
    try:
        r = get_session().post(url, json=yeni_yorum, timeout=FIREBASE_TIMEOUT_S)
        if r.status_code in (200, 201):
            st.session_state["son_yorum_zamani"] = datetime.now()
            arizali_istasyon_setini_getir.clear()
            return True
    except Exception: pass
    return False

# ==========================================
# 🏛️ BAŞLIK VE KONUM
# ==========================================
st.markdown('''
    <table class="title-table">
        <tr><td class="title-cell">ŞarjBul</td></tr>
        <tr><td class="subtitle-cell">En yakın aktif şarj rotanız</td></tr>
    </table>
''', unsafe_allow_html=True)

if not istasyonlar_verisi:
    st.error("İstasyon verileri yüklenemedi. Ağ bağlantınızı kontrol edin.")
    st.stop()

user_lat, user_lon = None, None
try:
    konum_verisi = get_geolocation()
    if isinstance(konum_verisi, dict) and "coords" in konum_verisi:
        user_lat, user_lon = konum_verisi["coords"].get("latitude"), konum_verisi["coords"].get("longitude")
    if user_lat and user_lon:
        st.session_state["last_valid_lat"], st.session_state["last_valid_lon"] = user_lat, user_lon
except Exception: pass

user_lat = user_lat or st.session_state.get("last_valid_lat")
user_lon = user_lon or st.session_state.get("last_valid_lon")

if not user_lat or not user_lon:
    manuel = st.selectbox("Lütfen Mevcut Konumunuzu Seçin:", ["Seçiniz...", "İstanbul (Kadıköy)", "Ankara (Çankaya)", "İzmir (Alsancak)"])
    SABIT_K = {"İstanbul (Kadıköy)": (40.9901, 29.0284), "Ankara (Çankaya)": (39.9208, 32.8541), "İzmir (Alsancak)": (38.4374, 27.1422)}
    if manuel in SABIT_K:
        st.session_state["last_valid_lat"], st.session_state["last_valid_lon"] = SABIT_K[manuel]
        st.rerun()
    st.stop()

# ==========================================
# 🚗 ARAÇ SEÇİMİ VE FİLTRELEME
# ==========================================
with st.expander("Araç ve Menzil Ayarları", expanded=False):
    secilen_arac = st.selectbox("Model", list(ARAC_KATALOGU.keys()), label_visibility="collapsed")
    varsayilan = ARAC_KATALOGU[secilen_arac]
    c_b1, c_b2, c_b3 = st.columns(3)
    batarya = c_b1.number_input("Kapasite", value=varsayilan["batarya"])
    sarj_yuzdesi = c_b2.slider("Şarj %", min_value=1, max_value=100, value=30)
    tuketim = c_b3.number_input("Tüketim", value=varsayilan["tuketim"])
    guvenlik_marji = st.slider("Güvenlik Marjı (%)", min_value=10, max_value=50, value=25)
    menzil_filtresi = st.checkbox("Menzil Filtresini Uygula", value=True)

ham_menzil = (batarya * (sarj_yuzdesi / 100.0) / tuketim) * 100.0
guvenli_menzil = ham_menzil * (1 - guvenlik_marji / 100.0)

uygun_istasyonlar = []
aktif_arizali_set = arizali_istasyon_setini_getir()

for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    if (not menzil_filtresi) or (km <= guvenli_menzil):
        if clean_id_uret(ist["isim"]) not in aktif_arizali_set:
            ist_kopya = ist.copy()
            ist_kopya["Mesafe"] = round(km, 1)
            uygun_istasyonlar.append(ist_kopya)

en_yakin = sorted(uygun_istasyonlar, key=lambda x: x["Mesafe"])[:MAX_ISTASYON_SAYISI]

# ==========================================
# 🎯 SONUÇ EKRANI VE KARTLAR
# ==========================================
if en_yakin:
    cevre_sonuclari = _paralel_cevre_getir(en_yakin)
    
    for sira, (istasyon, yakin_yerler) in enumerate(zip(en_yakin, cevre_sonuclari)):
        etiket = "🥇 En Yakın İstasyon" if sira == 0 else f"#{sira + 1} Yedek İstasyon"
        
        yakin_html = ""
        if yakin_yerler:
            yakin_html = '<div class="panel-bolucu"></div><div class="panel-alt-baslik">Yakındaki Yerler</div>'
            for yer in yakin_yerler:
                yakin_html += f'<div class="avantaj-item"><span>{yer["emoji"]} {yer["isim"]}</span><span class="avantaj-badge">{yer["metre"]}m</span></div>'

        st.markdown(f"""
        <div class="premium-card">
            <div style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:8px;">{guvenli_metin(etiket)}</div>
            <div class="mesafe-text">{istasyon['Mesafe']} km uzaklıkta</div>
            <div class="istasyon-isim">{guvenli_metin(istasyon['isim'])}</div>
            <div class="detay-text">Şarj Hızı: {guvenli_metin(istasyon.get('hiz', 'Bilinmiyor'))}</div>
            <div class="adres-text">{guvenli_metin(istasyon.get('adres', ''))}</div>
            {yakin_html}
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            # Standart nav link düzeltmesi dahil
            g_link = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={istasyon['enlem']},{istasyon['boylam']}&travelmode=driving"
            st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn">Navigasyonu Başlat</a>', unsafe_allow_html=True)

        with c2:
            with st.popover("Durum Bildir"):
                # AUTHENTICATION KONTROLÜ
                if "auth_token" not in st.session_state:
                    st.warning("Durum bildirmek ve yorum yapmak için lütfen yan menüden giriş yapın.")
                else:
                    col_btn1, col_btn2 = st.columns(2)
                    ist_isim = istasyon.get("isim", "").strip()

                    with col_btn1:
                        st.markdown('<div class="rapor-calisiyor">', unsafe_allow_html=True)
                        if st.button("Sorunsuz", key=f"btn_ok_{sira}"):
                            if yorum_gonder(ist_isim, "Anonim Sürücü", "Sorunsuz / Boş", "Sorunsuz / Boş"): st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)

                    with col_btn2:
                        st.markdown('<div class="rapor-arizali">', unsafe_allow_html=True)
                        if st.button("Arızalı", key=f"btn_fail_{sira}"):
                            if yorum_gonder(ist_isim, "Anonim Sürücü", "Arızalı / Kapalı", "Arızalı / Kapalı"): st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown("---")
                    yorum_txt = st.text_input("Durum Notu", key=f"inp_txt_{sira}")
                    if st.button("Detaylı Gönder", key=f"btn_detail_{sira}"):
                        if yorum_gonder(ist_isim, "Anonim Sürücü", yorum_txt, "Durum Güncellemesi"): st.rerun()
else:
    st.warning("Mevcut şarj yüzdeniz ile ulaşılabilecek aktif bir istasyon bulunamadı. Lütfen menzil filtresini kapatın.")
