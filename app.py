import streamlit as st
import json
import math
import hashlib
import logging
import unicodedata
import asyncio
import re
import requests
from datetime import datetime, timedelta
import html
from typing import Any, Dict, List, Optional, Tuple

from streamlit_js_eval import get_geolocation
import sentry_sdk

# --- 📱 MOBİL VE PREMIUM SAYFA AYARLARI ---
st.set_page_config(
    page_title="ŞarjBul",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 🪵 LOGLAMA AYARI
# ==========================================
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ==========================================
# 🚨 SENTRY HATA TAKİP (GRACEFUL INIT)
# ==========================================
def sentry_init() -> None:
    """Sentry secrets yoksa uygulama sessizce devam eder."""
    try:
        if "sentry" in st.secrets and "dsn" in st.secrets["sentry"]:
            sentry_sdk.init(
                dsn=st.secrets["sentry"]["dsn"],
                traces_sample_rate=float(st.secrets["sentry"].get("traces_sample_rate", 0.10)),
                send_default_pii=False,
            )
    except Exception as e:
        logger.warning("Sentry başlatılamadı: %s", e)

sentry_init()

# ==========================================
# 🔐 FİREBASE BAĞLANTISI VE AUTH SABİTLERİ
# ==========================================
def normalize_firebase_url(url: str) -> str:
    return str(url).strip().rstrip("/") + "/"

try:
    FIREBASE_DB_URL = normalize_firebase_url(st.secrets["firebase"]["db_url"])
    FIREBASE_API_KEY = st.secrets["firebase"]["api_key"]
except (KeyError, FileNotFoundError):
    st.error("Firebase bağlantı bilgileri (db_url ve api_key) bulunamadı. Lütfen secrets.toml dosyasını kontrol edin.")
    st.stop()

# ==========================================
# 📐 UYGULAMA SABİTLERİ
# ==========================================
MAX_ISTASYON_SAYISI       = 5
OVERPASS_TIMEOUT_S        = 12.0
FIREBASE_TIMEOUT_S        = 4.0
ISTASYON_CACHE_TTL        = 300       # 5 dakika
# [UX/Kod 4] 10 → 60 sn: write-on-invalidate stratejisiyle sıklaştırmak gereksiz
YORUM_CACHE_TTL           = 60
CEVRE_CACHE_TTL           = 21_600    # 6 saat
# [Gerçek Hata 2] Firebase ID token ömrü ~60 dk; 5 dk payda bırak
TOKEN_OMUR_DK             = 55
MAX_YAKIN_YER             = 5
MAX_SON_YORUM             = 2
YOL_UZAMA_KATSAYISI       = 1.25      # kuş uçuşu -> yaklaşık yol mesafesi
YORUM_BEKLEME_SURESI      = 30
ARIZA_GECERLILIK_SAATI    = 6
ARIZA_RISK_ESIGI          = 2
MAX_YORUM_KARAKTER        = 280

ARAC_KATALOGU: Dict[str, Dict[str, float]] = {
    "Tesla Model Y Long Range": {"batarya": 75.0, "tuketim": 16.9},
    "Togg T10X Uzun Menzil":   {"batarya": 88.5, "tuketim": 16.9},
    "BYD Atto 3":               {"batarya": 60.4, "tuketim": 16.0},
    "Renault Megane E-Tech":    {"batarya": 60.0, "tuketim": 15.5},
    "Özel Araç (Manuel)":       {"batarya": 60.0, "tuketim": 17.0},
}

KATEGORI_EMOJILER: Dict[str, Tuple[str, str]] = {
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
    "https://lz4.overpass-api.de/api/interpreter",
]
OVERPASS_HEADERS = {
    "User-Agent": "SarjBul/2.1 (+https://streamlit.io)",
    "Accept": "application/json",
}

# Hız filtresi için eşik haritası
HIZ_ESIK_MAP: Dict[str, float] = {
    "AC (≥7 kW)": 7.0,
    "DC (≥50 kW)": 50.0,
    "Hızlı DC (≥150 kW)": 150.0,
}

# ==========================================
# 🎨 PREMIUM CSS
# ==========================================
st.markdown('''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        :root {
            --sb-bg-main: #07111F;
            --sb-bg-card: #0F1B2D;
            --sb-bg-card-soft: #13233A;
            --sb-text-main: #F8FAFC;
            --sb-text-soft: #CBD5E1;
            --sb-text-muted: #94A3B8;
            --sb-line-soft: rgba(148, 163, 184, 0.14);
            --sb-primary: #38BDF8;
            --sb-primary-deep: #0284C7;
            --sb-success: #22C55E;
            --sb-warning: #F59E0B;
            --sb-danger: #EF4444;
            --sb-glow: rgba(56, 189, 248, 0.28);
        }

        [data-testid="stHeader"] { display: none !important; }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(56, 189, 248, 0.13), transparent 34%),
                radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.06), transparent 28%),
                linear-gradient(180deg, #07111F 0%, #0B1220 100%) !important;
            color: var(--sb-text-main) !important;
        }

        .block-container {
            padding: 1.15rem 0.9rem 5.5rem !important;
            max-width: 460px !important;
        }

        div[data-testid="stExpander"] {
            background: rgba(15, 27, 45, 0.78) !important;
            border: 1px solid rgba(148, 163, 184, 0.14) !important;
            border-radius: 18px !important;
            box-shadow: 0 14px 36px rgba(0, 0, 0, 0.20);
            overflow: hidden;
        }

        div[data-testid="stExpander"] details summary {
            color: #E2E8F0 !important;
            font-weight: 800 !important;
        }

        label, .stMarkdown, .stCaption, .stTextInput label, .stNumberInput label, .stSelectbox label, .stSlider label, .stMultiSelect label {
            color: #CBD5E1 !important;
        }

        .stCaption, .caption {
            color: #94A3B8 !important;
        }

        input, textarea {
            background-color: rgba(15, 27, 45, 0.92) !important;
            color: #F8FAFC !important;
            border-radius: 14px !important;
            border: 1px solid rgba(148, 163, 184, 0.20) !important;
        }

        .title-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 18px;
            border: 1px solid rgba(56, 189, 248, 0.24);
            border-radius: 24px;
            overflow: hidden;
            background:
                radial-gradient(circle at top right, rgba(56, 189, 248, 0.19), transparent 32%),
                linear-gradient(135deg, #0F1B2D 0%, #13233A 100%);
            box-shadow:
                0 22px 54px rgba(0, 0, 0, 0.30),
                inset 0 1px 0 rgba(255, 255, 255, 0.05);
        }

        .title-cell {
            background: transparent;
            color: #F8FAFC !important;
            font-family: 'Inter', sans-serif;
            font-weight: 950;
            font-size: 30px;
            text-align: left;
            padding: 22px 22px 4px;
            letter-spacing: -1px;
            text-transform: none;
        }

        .subtitle-cell {
            background: transparent;
            color: #94A3B8 !important;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            font-weight: 650;
            text-align: left;
            padding: 4px 22px 20px;
            border-top: none;
            line-height: 1.45;
        }

        .premium-card {
            background:
                radial-gradient(circle at top right, rgba(56, 189, 248, 0.10), transparent 34%),
                linear-gradient(180deg, #0F1B2D 0%, #0B1628 100%) !important;
            border: 1px solid rgba(148, 163, 184, 0.16) !important;
            border-top: 1px solid rgba(56, 189, 248, 0.35) !important;
            border-radius: 24px;
            padding: 22px;
            box-shadow:
                0 18px 44px rgba(0, 0, 0, 0.32),
                inset 0 1px 0 rgba(255, 255, 255, 0.04);
            margin-bottom: 18px;
        }

        .premium-card-risk {
            border-color: rgba(239, 68, 68, 0.36) !important;
            border-top-color: rgba(239, 68, 68, 0.48) !important;
            box-shadow:
                0 18px 44px rgba(127, 29, 29, 0.24),
                inset 0 1px 0 rgba(255, 255, 255, 0.04);
        }

        .kart-ust-satir {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 10px;
        }

        .kart-etiket {
            font-size: 11px;
            font-weight: 900;
            color: #94A3B8 !important;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 8px;
        }

        .istasyon-isim {
            font-size: 21px;
            font-weight: 900;
            color: #F8FAFC !important;
            margin: 2px 0 8px 0;
            letter-spacing: -0.45px;
            line-height: 1.18;
        }

        .mesafe-text {
            font-size: 28px;
            font-weight: 950;
            color: #38BDF8 !important;
            margin: 4px 0 8px 0;
            letter-spacing: -1px;
            text-transform: none;
            line-height: 1.08;
            text-shadow: 0 0 28px rgba(56, 189, 248, 0.16);
        }

        .mesafe-alt-text {
            font-size: 12px;
            color: #94A3B8 !important;
            margin: 0 0 12px 0;
            font-weight: 650;
        }

        .detay-text {
            font-size: 13px;
            color: #CBD5E1 !important;
            margin: 5px 0;
            font-weight: 650;
            line-height: 1.38;
        }

        .detay-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 7px;
            margin-top: 10px;
        }

        .detay-chip {
            display: inline-flex;
            align-items: center;
            border: 1px solid rgba(148, 163, 184, 0.16);
            background: rgba(19, 35, 58, 0.78);
            color: #CBD5E1 !important;
            padding: 7px 9px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 800;
            line-height: 1;
        }

        .adres-text {
            font-size: 12px;
            color: #94A3B8 !important;
            margin-top: 14px;
            line-height: 1.48;
            border-top: 1px solid rgba(148, 163, 184, 0.12);
            padding-top: 14px;
        }

        .panel-bolucu {
            border-top: 1px solid rgba(148, 163, 184, 0.12);
            margin: 18px 0;
        }

        .panel-alt-baslik {
            font-size: 12px;
            font-weight: 900;
            color: #E2E8F0 !important;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.7px;
        }

        .avantaj-item {
            font-size: 12px;
            color: #CBD5E1 !important;
            margin-bottom: 9px;
            display: flex;
            justify-content: space-between;
            gap: 12px;
            font-weight: 650;
            line-height: 1.35;
        }

        .avantaj-badge {
            color: #38BDF8 !important;
            font-weight: 900;
            white-space: nowrap;
        }

        .durum-badge {
            display: inline-flex;
            align-items: center;
            font-size: 11px;
            font-weight: 950;
            padding: 7px 10px;
            border-radius: 999px;
            margin-bottom: 8px;
            line-height: 1;
        }

        .durum-aktif {
            background: rgba(34, 197, 94, 0.12);
            color: #86EFAC;
            border: 1px solid rgba(34, 197, 94, 0.35);
        }

        .durum-riskli {
            background: rgba(239, 68, 68, 0.12);
            color: #FCA5A5;
            border: 1px solid rgba(239, 68, 68, 0.38);
        }

        .durum-belirsiz {
            background: rgba(245, 158, 11, 0.12);
            color: #FCD34D;
            border: 1px solid rgba(245, 158, 11, 0.32);
        }

        .nav-link-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            border-radius: 16px;
            min-height: 54px;
            font-weight: 950;
            background: linear-gradient(135deg, #38BDF8 0%, #0284C7 100%);
            color: #031525 !important;
            border: 1px solid rgba(125, 211, 252, 0.65);
            font-size: 15px;
            box-shadow: 0 12px 28px rgba(56, 189, 248, 0.25);
        }

        .nav-link-btn:hover {
            filter: brightness(1.05);
            text-decoration: none;
        }

        .stButton>button {
            border-radius: 16px;
            min-height: 54px;
            font-weight: 850;
            width: 100%;
            background: rgba(15, 27, 45, 0.86) !important;
            color: #E2E8F0 !important;
            border: 1px solid rgba(148, 163, 184, 0.18) !important;
        }

        .rapor-calisiyor>button {
            border-color: rgba(34, 197, 94, 0.45) !important;
            color: #86EFAC !important;
            background: rgba(34, 197, 94, 0.10) !important;
        }

        .rapor-arizali>button {
            border-color: rgba(239, 68, 68, 0.45) !important;
            color: #FCA5A5 !important;
            background: rgba(239, 68, 68, 0.10) !important;
        }

        .mini-note {
            font-size: 11px;
            color: #64748B !important;
            line-height: 1.45;
            margin-top: 11px;
        }

        div[data-testid="stAlert"] {
            border-radius: 18px !important;
            border: 1px solid rgba(148, 163, 184, 0.18) !important;
        }

        hr {
            border-color: rgba(148, 163, 184, 0.14) !important;
        }
    </style>
''', unsafe_allow_html=True)

# ==========================================
# 🛠️ YARDIMCI FONKSİYONLAR
# ==========================================
@st.cache_resource
def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "SarjBul/2.1",
        "Accept": "application/json",
    })
    return session


def guvenli_metin(metin: Any, max_len: Optional[int] = None) -> str:
    text = html.escape(str(metin or "").strip())
    if max_len is not None:
        text = text[:max_len]
    return text


def html_etiketlerini_temizle(metin: Any) -> str:
    """Adres alanına yanlışlıkla HTML gelirse ekranda kod gibi görünmesini engeller."""
    text = html.unescape(str(metin or "").strip())
    while "<" in text and ">" in text:
        start = text.find("<")
        end = text.find(">", start)
        if end == -1:
            break
        text = text[:start] + " " + text[end + 1:]
    return " ".join(text.split())


def adres_metni_getir(istasyon: Dict[str, Any]) -> str:
    adres = html_etiketlerini_temizle(istasyon.get("adres", ""))
    return adres or "Adres Bilgisi Yok"


def clean_id_uret(isim: str) -> str:
    raw = str(isim or "").strip()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_isim = normalized.encode("ascii", "ignore").decode("ascii").strip()
    safe = "".join(c for c in ascii_isim if c.isalnum() or c in (" ", "_", "-")).rstrip()
    safe = "_".join(safe.split())
    return safe[:80] if safe else hashlib.md5(raw.encode()).hexdigest()[:12]


def istasyon_id_getir(istasyon: Dict[str, Any]) -> str:
    """İstasyonda id yoksa KeyError vermeden stabil bir yedek anahtar üretir."""
    for alan in ("id", "station_id", "place_id", "uid", "firebase_key", "key"):
        deger = istasyon.get(alan)
        if deger not in (None, ""):
            return str(deger).strip()

    isim = str(istasyon.get("isim") or istasyon.get("name") or "bilinmeyen_istasyon").strip()
    enlem = str(istasyon.get("enlem") or istasyon.get("lat") or "").strip()
    boylam = str(istasyon.get("boylam") or istasyon.get("lon") or istasyon.get("lng") or "").strip()
    fallback = f"{isim}_{enlem}_{boylam}".strip("_")
    return fallback or "bilinmeyen_istasyon"


# [Gerçek Hata 2] Firebase ID token süresi kontrolü
def token_suresi_doldu_mu() -> bool:
    """
    auth_login_time'dan itibaren TOKEN_OMUR_DK dakika geçip geçmediğini kontrol eder.
    Firebase ID token ömrü 60 dk; 5 dk pay bırakarak 55. dakikada geçersiz sayarız.
    """
    login_time_str = st.session_state.get("auth_login_time")
    if not login_time_str:
        return True
    try:
        gecen_dk = (datetime.now() - datetime.fromisoformat(login_time_str)).total_seconds() / 60
        return gecen_dk > TOKEN_OMUR_DK
    except Exception:
        return True


def yorum_gonderilebilir_mi() -> Tuple[bool, int]:
    son = st.session_state.get("son_yorum_zamani")
    if son is None:
        return True, 0
    kalan = YORUM_BEKLEME_SURESI - int((datetime.now() - son).total_seconds())
    return kalan <= 0, max(0, kalan)


# [Gerçek Hata 3] Sunucu taraflı cooldown: sayfa yenilemede session_state sıfırlansa da
# Firebase verisindeki uid_hash'e göre son yorum zamanı kontrol edilir.
def sunucu_tarafli_cooldown_kontrol(
    tum_yorumlar: Dict[str, List[Dict[str, Any]]], uid_hash: str
) -> Tuple[bool, int]:
    """
    tum_yorumlar (zaten bellekte, cached) üzerinde uid_hash eşleşmesi arar.
    Bulunan en son yorum zamanına göre cooldown uygular.
    Döner: (gonderilebilir_mi, kalan_saniye)
    """
    if not uid_hash:
        return True, 0
    simdi = datetime.now()
    son_yorum_zamani: Optional[datetime] = None

    for yorumlar in tum_yorumlar.values():
        for y in yorumlar:
            if str(y.get("uid_hash", ""))[:16] == uid_hash[:16]:
                tarih = yorum_tarihi_parse(y.get("tarih", ""))
                if tarih != datetime.min:
                    if son_yorum_zamani is None or tarih > son_yorum_zamani:
                        son_yorum_zamani = tarih

    if son_yorum_zamani is None:
        return True, 0
    kalan = YORUM_BEKLEME_SURESI - int((simdi - son_yorum_zamani).total_seconds())
    return kalan <= 0, max(0, kalan)


def yorum_tarihi_parse(tarih_str: str) -> datetime:
    try:
        return datetime.fromisoformat(str(tarih_str).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.min


def mesafe_hesapla(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine kuş uçuşu mesafe, km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def tahmini_yol_mesafesi_km(kus_ucusu_km: float) -> float:
    return kus_ucusu_km * YOL_UZAMA_KATSAYISI


def konum_gecerli_mi(lat: Any, lon: Any) -> bool:
    try:
        lat_f, lon_f = float(lat), float(lon)
        return -90 <= lat_f <= 90 and -180 <= lon_f <= 180
    except Exception:
        return False


def istasyon_normalize_et(ist: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Firebase veya lokal JSON'dan gelen istasyonu doğrular ve güvenli tipe çevirir."""
    if not isinstance(ist, dict):
        return None
    try:
        isim = str(ist.get("isim", "")).strip()
        enlem = float(ist.get("enlem"))
        boylam = float(ist.get("boylam"))
        if not isim or not konum_gecerli_mi(enlem, boylam):
            return None

        yeni = dict(ist)
        yeni["isim"] = isim
        yeni["enlem"] = enlem
        yeni["boylam"] = boylam
        yeni.setdefault("hiz", "Bilinmiyor")
        yeni["adres"] = adres_metni_getir(yeni)
        yeni.setdefault("operator", yeni.get("operatör", "Bilinmiyor"))
        yeni.setdefault("soket", "Bilinmiyor")
        yeni.setdefault("fiyat", "Bilinmiyor")
        return yeni
    except Exception:
        return None


def ariza_skoru_hesapla(yorumlar: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Son saatler içindeki bildirime göre risk skoru üretir."""
    simdi = datetime.now()
    baslangic = simdi - timedelta(hours=ARIZA_GECERLILIK_SAATI)
    aktif_yorumlar = []

    for y in yorumlar:
        tarih = yorum_tarihi_parse(y.get("tarih", ""))
        if tarih >= baslangic:
            aktif_yorumlar.append(y)

    arizali = sum(1 for y in aktif_yorumlar if "Arızalı" in str(y.get("durum", "")))
    sorunsuz = sum(1 for y in aktif_yorumlar if "Sorunsuz" in str(y.get("durum", "")))
    skor = arizali - sorunsuz

    if skor >= ARIZA_RISK_ESIGI:
        durum = "riskli"
        etiket = f"⚠️ Kullanıcılar arıza bildirdi ({arizali}/{len(aktif_yorumlar)})"
    elif aktif_yorumlar:
        durum = "aktif"
        etiket = "✅ Son bildirimlere göre aktif"
    else:
        durum = "belirsiz"
        etiket = "ℹ️ Yakın zamanda bildirim yok"

    return {
        "skor": skor,
        "durum": durum,
        "etiket": etiket,
        "arizali": arizali,
        "sorunsuz": sorunsuz,
        "aktif_yorum_sayisi": len(aktif_yorumlar),
    }

# ==========================================
# 🔐 AUTH FONKSİYONLARI
# ==========================================
def firebase_login(email: str, password: str) -> Optional[Dict[str, Any]]:
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    try:
        r = get_session().post(
            url,
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json()
        logger.warning("Firebase auth başarısız: %s - %s", r.status_code, r.text[:200])
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.exception("Auth hatası")
    return None


# [Eksik Özellik: Kayıt akışı]
def firebase_register(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Firebase Authentication üzerinden yeni kullanıcı kaydı oluşturur."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    try:
        r = get_session().post(
            url,
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json()
        logger.warning("Firebase kayıt başarısız: %s - %s", r.status_code, r.text[:200])
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.exception("Kayıt hatası")
    return None


# [Eksik Özellik: Şifre sıfırlama]
def firebase_sifre_sifirla(email: str) -> Tuple[bool, str]:
    """Firebase Authentication üzerinden şifre sıfırlama e-postası gönderir."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_API_KEY}"
    try:
        r = get_session().post(
            url,
            json={"requestType": "PASSWORD_RESET", "email": email},
            timeout=5,
        )
        if r.status_code == 200:
            return True, "Şifre sıfırlama bağlantısı e-posta adresinize gönderildi."
        hata = r.json().get("error", {}).get("message", "Bilinmeyen hata")
        return False, f"Gönderilemedi: {hata}"
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.exception("Şifre sıfırlama hatası")
        return False, "Bağlantı hatası nedeniyle istek gönderilemedi."


def firebase_auth_params() -> Dict[str, str]:
    token = st.session_state.get("auth_token")
    return {"auth": token} if token else {}


def oturumu_temizle() -> None:
    for key in ("auth_token", "auth_email", "auth_uid", "auth_login_time"):
        st.session_state.pop(key, None)

# ==========================================
# 🗄️ DİNAMİK VERİ ÇEKİMİ
# ==========================================
@st.cache_data(ttl=ISTASYON_CACHE_TTL, show_spinner=False)
def istasyonlari_yukle() -> List[Dict[str, Any]]:
    url = f"{FIREBASE_DB_URL}istasyonlar.json"
    try:
        res = get_session().get(url, timeout=3.0)
        if res.status_code == 200:
            veri = res.json()
            if veri:
                ham_liste = list(veri.values()) if isinstance(veri, dict) else veri
                temiz_liste = []
                for item in ham_liste:
                    normalized = istasyon_normalize_et(item)
                    if normalized:
                        temiz_liste.append(normalized)
                    else:
                        logger.warning("Geçersiz istasyon verisi atlandı: %s", item)
                return temiz_liste
        logger.warning("Firebase istasyon cevabı başarısız/boş: %s", res.status_code)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.warning("Firebase'den istasyonlar çekilemedi, fallback devrede: %s", e)

    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            veri = json.load(f)
            ham_liste = list(veri.values()) if isinstance(veri, dict) else veri
            return [x for item in ham_liste if (x := istasyon_normalize_et(item))]
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error("Fallback JSON dosyası da okunamadı: %s", e)
        return []


@st.cache_data(ttl=YORUM_CACHE_TTL, show_spinner=False)
def tum_yorumlari_getir() -> Dict[str, List[Dict[str, Any]]]:
    url = f"{FIREBASE_DB_URL}yorumlar.json"
    sonuc: Dict[str, List[Dict[str, Any]]] = {}
    try:
        res = get_session().get(url, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code == 200 and res.json():
            for clean_id, pkts in res.json().items():
                if isinstance(pkts, dict):
                    yorumlar = [y for y in pkts.values() if isinstance(y, dict)]
                    sonuc[clean_id] = sorted(yorumlar, key=lambda x: yorum_tarihi_parse(x.get("tarih", "")), reverse=True)
        elif res.status_code not in (200, 404):
            logger.warning("Yorumlar alınamadı: %s - %s", res.status_code, res.text[:200])
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.exception("Yorum verisi çekilemedi")
    return sonuc


@st.cache_data(ttl=YORUM_CACHE_TTL, show_spinner=False)
def istasyon_yorumlari_getir(istasyon_id: str, limit: int = MAX_SON_YORUM) -> List[Dict[str, Any]]:
    clean_id = clean_id_uret(istasyon_id)
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
    try:
        res = get_session().get(url, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code == 200 and res.json():
            yorumlar = [y for y in res.json().values() if isinstance(y, dict)]
            return sorted(yorumlar, key=lambda x: yorum_tarihi_parse(x.get("tarih", "")), reverse=True)[:limit]
        if res.status_code not in (200, 404):
            logger.warning("İstasyon yorumları alınamadı: %s - %s", res.status_code, res.text[:200])
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.exception("İstasyon yorumları çekilemedi")
    return []


def yorum_gonder(istasyon_id: str, yorum_metni: str, durum: str) -> Tuple[bool, str]:
    # [Gerçek Hata 2] Token süresi kontrolü — oturum dolmuşsa anında temizle
    if token_suresi_doldu_mu():
        oturumu_temizle()
        return False, "Oturum süreniz dolmuş. Lütfen yeniden giriş yapın."

    # Client-side cooldown (session_state tabanlı)
    gonderilebilir, kalan = yorum_gonderilebilir_mi()
    if not gonderilebilir:
        return False, f"Çok sık bildirim yapıyorsunuz. {kalan} saniye sonra tekrar deneyin."

    token = st.session_state.get("auth_token")
    if not token:
        return False, "Durum bildirmek için giriş yapmalısınız."

    # [Gerçek Hata 3] Sunucu taraflı cooldown: sayfa yenilemede session sıfırlansa da engeller
    uid_hash = hashlib.sha256(str(st.session_state.get("auth_uid", "")).encode()).hexdigest()[:16]
    tum_yorumlar_snapshot = tum_yorumlari_getir()
    sunucu_ok, sunucu_kalan = sunucu_tarafli_cooldown_kontrol(tum_yorumlar_snapshot, uid_hash)
    if not sunucu_ok:
        return False, f"Çok sık bildirim yapıyorsunuz. {sunucu_kalan} saniye sonra tekrar deneyin."

    clean_id = clean_id_uret(istasyon_id)
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"

    # Privacy: e-posta prefix'i yerine anonim doğrulanmış kullanıcı etiketi.
    kullanici = "Doğrulanmış Sürücü"

    yeni_yorum = {
        "kullanici": kullanici,
        "yorum": guvenli_metin(yorum_metni or durum, MAX_YORUM_KARAKTER),
        "durum": guvenli_metin(durum, 60),
        "tarih": datetime.now().isoformat(timespec="seconds"),
        "uid_hash": uid_hash,
    }

    try:
        r = get_session().post(
            url,
            params={"auth": token},
            json=yeni_yorum,
            timeout=FIREBASE_TIMEOUT_S,
        )
        if r.status_code in (200, 201):
            st.session_state["son_yorum_zamani"] = datetime.now()
            tum_yorumlari_getir.clear()
            istasyon_yorumlari_getir.clear()
            return True, "Bildirim kaydedildi."

        if r.status_code in (401, 403):
            oturumu_temizle()
            return False, "Oturum süresi dolmuş olabilir. Lütfen yeniden giriş yapın."

        logger.warning("Yorum gönderilemedi: %s - %s", r.status_code, r.text[:200])
        return False, "Yorum gönderilemedi. Lütfen tekrar deneyin."
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.exception("Yorum gönderme hatası")
        return False, "Bağlantı hatası nedeniyle yorum gönderilemedi."

# ==========================================
# 🌐 OVERPASS / ÇEVRE VERİLERİ
# ==========================================
@st.cache_data(ttl=CEVRE_CACHE_TTL, show_spinner=False)
def yakin_cevre_getir(enlem: float, boylam: float, yaricap_m: int) -> Optional[List[Dict[str, Any]]]:
    """
    [UX/Kod 2] Dönüş tipi Optional:
      None  → tüm Overpass URL'leri başarısız (API hatası); çağıran uyarı gösterir.
      []    → istek başarılı ama yakında eşleşen yer bulunamadı.
    """
    sorgu = f"""
    [out:json][timeout:{int(OVERPASS_TIMEOUT_S)}];
    (
      nwr["amenity"~"cafe|restaurant|fast_food|parking|pharmacy|atm|toilets|fuel"](around:{yaricap_m},{enlem},{boylam});
      nwr["shop"~"supermarket|convenience|mall"](around:{yaricap_m},{enlem},{boylam});
      nwr["tourism"="hotel"](around:{yaricap_m},{enlem},{boylam});
    );
    out center tags;
    """

    for overpass_url in OVERPASS_URLS:
        try:
            res = get_session().post(
                overpass_url,
                data={"data": sorgu},
                headers=OVERPASS_HEADERS,
                timeout=OVERPASS_TIMEOUT_S,
            )
            if res.status_code != 200:
                logger.warning("Overpass başarısız: %s - %s", res.status_code, overpass_url)
                continue

            sonuclar: List[Dict[str, Any]] = []
            for el in res.json().get("elements", []):
                tags = el.get("tags", {}) or {}
                kategori_kodu = tags.get("amenity") or tags.get("shop") or tags.get("tourism") or ""
                if kategori_kodu not in KATEGORI_EMOJILER:
                    continue

                lat = el.get("lat") or el.get("center", {}).get("lat")
                lon = el.get("lon") or el.get("center", {}).get("lon")
                if lat is None or lon is None:
                    continue

                km = mesafe_hesapla(enlem, boylam, float(lat), float(lon))
                emoji, kat_adi = KATEGORI_EMOJILER[kategori_kodu]
                sonuclar.append({
                    "isim": guvenli_metin(tags.get("name") or kat_adi, 80),
                    "kategori": kat_adi,
                    "emoji": emoji,
                    "metre": int(km * 1000),
                })

            gorulmus_kategori, gorulmus_isim, filtrelenmis = set(), set(), []
            for s in sorted(sonuclar, key=lambda x: x["metre"]):
                isim_key = str(s["isim"]).lower()
                if s["kategori"] in gorulmus_kategori or isim_key in gorulmus_isim:
                    continue
                gorulmus_kategori.add(s["kategori"])
                gorulmus_isim.add(isim_key)
                filtrelenmis.append(s)
                if len(filtrelenmis) >= MAX_YAKIN_YER:
                    break
            return filtrelenmis   # Başarılı; boş liste bile olsa None değil

        except Exception as e:
            sentry_sdk.capture_exception(e)
            logger.warning("Overpass denemesi başarısız (%s): %s", overpass_url, e)
            continue

    return None  # Tüm URL'ler başarısız → API hatası


def _cevre_getir_ist(ist: Dict[str, Any], yaricap: int) -> Optional[List[Dict[str, Any]]]:
    return yakin_cevre_getir(ist["enlem"], ist["boylam"], yaricap)


# [UX/Kod 1] ThreadPoolExecutor → asyncio.to_thread + asyncio.gather
async def _paralel_cevre_getir_async(
    istasyon_listesi: List[Dict[str, Any]], yaricap: int
) -> List[Optional[List[Dict[str, Any]]]]:
    gorevler = [
        asyncio.to_thread(_cevre_getir_ist, ist, yaricap)
        for ist in istasyon_listesi
    ]
    return await asyncio.gather(*gorevler)


def _paralel_cevre_getir(
    istasyon_listesi: List[Dict[str, Any]], yaricap: int
) -> List[Optional[List[Dict[str, Any]]]]:
    """Overpass sorgularını asyncio.to_thread ile paralel çalıştırır."""
    if not istasyon_listesi:
        return []
    try:
        return asyncio.run(_paralel_cevre_getir_async(istasyon_listesi, yaricap))
    except RuntimeError:
        # Zaten çalışan bir event loop varsa (bazı ortamlarda olabilir) sıralı çalıştır.
        logger.warning("asyncio.run başarısız, sıralı Overpass sorgusu çalışıyor.")
        return [_cevre_getir_ist(ist, yaricap) for ist in istasyon_listesi]

# ==========================================
# 🔑 ANA SAYFA GİRİŞ PANELİ VE AYARLAR
# ==========================================
with st.expander("🔑 Giriş / Kullanıcı Paneli", expanded=("auth_token" not in st.session_state)):
    if "auth_token" not in st.session_state:
        # [Eksik Özellik: Kayıt + Şifre sıfırlama] — tek expander'da 3 sekme
        tab_giris, tab_kayit, tab_sifre = st.tabs(["🔑 Giriş", "📝 Kayıt Ol", "🔓 Şifremi Unuttum"])

        with tab_giris:
            email = st.text_input("E-posta", key="login_email")
            password = st.text_input("Şifre", type="password", key="login_password")
            if st.button("Giriş Yap", use_container_width=True, key="login_button"):
                user_data = firebase_login(email, password)
                if user_data:
                    st.session_state["auth_token"] = user_data["idToken"]
                    st.session_state["auth_email"] = user_data.get("email", "")
                    st.session_state["auth_uid"] = user_data.get("localId", "")
                    st.session_state["auth_login_time"] = datetime.now().isoformat(timespec="seconds")
                    st.success("Giriş başarılı!")
                    st.rerun()
                else:
                    st.error("Giriş başarısız. E-posta/şifreyi veya Firebase Authentication ayarlarını kontrol edin.")

        with tab_kayit:
            reg_email = st.text_input("E-posta", key="reg_email")
            reg_password = st.text_input("Şifre", type="password", key="reg_password")
            reg_password2 = st.text_input("Şifre Tekrar", type="password", key="reg_password2")
            if st.button("Kayıt Ol", use_container_width=True, key="reg_button"):
                if not reg_email or not reg_password:
                    st.error("E-posta ve şifre zorunludur.")
                elif reg_password != reg_password2:
                    st.error("Şifreler eşleşmiyor.")
                elif len(reg_password) < 6:
                    st.error("Şifre en az 6 karakter olmalıdır.")
                else:
                    user_data = firebase_register(reg_email, reg_password)
                    if user_data:
                        st.session_state["auth_token"] = user_data["idToken"]
                        st.session_state["auth_email"] = user_data.get("email", "")
                        st.session_state["auth_uid"] = user_data.get("localId", "")
                        st.session_state["auth_login_time"] = datetime.now().isoformat(timespec="seconds")
                        st.success("Kayıt başarılı! Hoş geldiniz.")
                        st.rerun()
                    else:
                        st.error("Kayıt başarısız. Bu e-posta zaten kayıtlı olabilir veya şifre çok zayıf.")

        with tab_sifre:
            reset_email = st.text_input("E-posta Adresiniz", key="reset_email")
            if st.button("Sıfırlama Bağlantısı Gönder", use_container_width=True, key="reset_button"):
                if not reset_email:
                    st.error("Lütfen e-posta adresinizi girin.")
                else:
                    ok, msg = firebase_sifre_sifirla(reset_email)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
    else:
        # [Gerçek Hata 2] Expander açıldığında token süresi kontrolü
        if token_suresi_doldu_mu():
            st.warning("⚠️ Oturum süreniz dolmuş. Lütfen yeniden giriş yapın.")
            oturumu_temizle()
            st.rerun()
        st.success("Giriş aktif: Doğrulanmış Sürücü")
        if st.button("Çıkış Yap", use_container_width=True, key="logout_button"):
            oturumu_temizle()
            st.rerun()

with st.expander("⚙️ Arama Ayarları", expanded=False):
    ayar_yaricap = st.slider(
        "Çevresel Mekan Arama Yarıçapı (m)",
        min_value=100,
        max_value=800,
        value=400,
        step=100,
        key="ayar_yaricap",
    )
    sonuc_sayisi = st.slider(
        "Gösterilecek İstasyon Sayısı",
        min_value=2,
        max_value=10,
        value=MAX_ISTASYON_SAYISI,
        step=1,
        key="sonuc_sayisi",
    )
    # [Eksik Özellik: Soket/hız filtresi]
    soket_filtreleri = st.multiselect(
        "Soket Tipi Filtresi",
        ["CCS", "CHAdeMO", "Type 2", "Schuko", "GB/T"],
        default=[],
        key="soket_filtre",
        help="Seçim yapılmazsa tüm soket tipleri gösterilir.",
    )
    hiz_filtresi = st.selectbox(
        "Minimum Şarj Hızı",
        ["Tümü", "AC (≥7 kW)", "DC (≥50 kW)", "Hızlı DC (≥150 kW)"],
        key="hiz_filtre",
    )
    st.caption("Durum bildirimi için giriş gerekir. Konum veriniz Firebase'e kaydedilmez.")

# ==========================================
# 🏛️ BAŞLIK VE KONUM
# ==========================================
st.markdown('''
    <table class="title-table">
        <tr><td class="title-cell">⚡ ŞarjBul</td></tr>
        <tr><td class="subtitle-cell">En yakın aktif şarj rotanız · Canlı durum · Rota tahmini · Yakın mekanlar</td></tr>
    </table>
''', unsafe_allow_html=True)

istasyonlar_verisi = istasyonlari_yukle()
if not istasyonlar_verisi:
    st.error("İstasyon verileri yüklenemedi. Ağ bağlantınızı ve Firebase/lokal JSON ayarlarını kontrol edin.")
    st.stop()

user_lat: Optional[float] = None
user_lon: Optional[float] = None
try:
    konum_verisi = get_geolocation()
    if isinstance(konum_verisi, dict) and "coords" in konum_verisi:
        lat = konum_verisi["coords"].get("latitude")
        lon = konum_verisi["coords"].get("longitude")
        if konum_gecerli_mi(lat, lon):
            user_lat, user_lon = float(lat), float(lon)
            st.session_state["last_valid_lat"] = user_lat
            st.session_state["last_valid_lon"] = user_lon
except Exception as e:
    sentry_sdk.capture_exception(e)
    logger.warning("Konum alınamadı: %s", e)

if user_lat is None or user_lon is None:
    last_lat = st.session_state.get("last_valid_lat")
    last_lon = st.session_state.get("last_valid_lon")
    if konum_gecerli_mi(last_lat, last_lon):
        user_lat, user_lon = float(last_lat), float(last_lon)

if user_lat is None or user_lon is None:
    # [Eksik Özellik: Konum izni reddedilince açıklama]
    st.info(
        "📍 **Konum erişimi gerekli.**\n\n"
        "Tarayıcınız konum izni isteyecektir. İzin verirseniz size en yakın istasyonlar "
        "otomatik bulunur. İzin vermek istemiyorsanız veya tarayıcı izin penceresi "
        "görünmüyorsa aşağıdan manuel konum seçebilirsiniz. "
        "**Konum veriniz sunucularımıza kaydedilmez.**"
    )
    manuel = st.selectbox(
        "Lütfen Mevcut Konumunuzu Seçin:",
        ["Seçiniz...", "İstanbul (Kadıköy)", "Ankara (Çankaya)", "İzmir (Alsancak)"],
    )
    SABIT_K = {
        "İstanbul (Kadıköy)": (40.9901, 29.0284),
        "Ankara (Çankaya)": (39.9208, 32.8541),
        "İzmir (Alsancak)": (38.4374, 27.1422),
    }
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
    batarya = c_b1.number_input(
        "Kapasite",
        min_value=1.0,
        max_value=250.0,
        value=float(varsayilan["batarya"]),
        step=0.5,
    )
    sarj_yuzdesi = c_b2.slider("Şarj %", min_value=1, max_value=100, value=30)
    tuketim = c_b3.number_input(
        "Tüketim",
        min_value=5.0,
        max_value=40.0,
        value=float(varsayilan["tuketim"]),
        step=0.1,
    )
    guvenlik_marji = st.slider("Güvenlik Marjı (%)", min_value=10, max_value=50, value=25)
    menzil_filtresi = st.checkbox("Menzil Filtresini Uygula", value=True)

ham_menzil = (batarya * (sarj_yuzdesi / 100.0) / tuketim) * 100.0
guvenli_menzil = ham_menzil * (1 - guvenlik_marji / 100.0)
st.info(
    f"Tahmini güvenli menziliniz: {guvenli_menzil:.0f} km. "
    f"Yol mesafesi hesabında x{YOL_UZAMA_KATSAYISI:.2f} rota katsayısı kullanılıyor."
)

# [Eksik Özellik: İsme/adrese göre arama]
arama_metni = st.text_input(
    "🔍 İstasyon Ara",
    placeholder="İstasyon adı veya adres ile filtrele...",
    key="arama_metni",
)

# ==========================================
# 🔎 İSTASYONLARI HAZIRLA
# ==========================================
tum_yorumlar = tum_yorumlari_getir()
uygun_istasyonlar: List[Dict[str, Any]] = []

for ist in istasyonlar_verisi:
    kus_ucusu_km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    tahmini_km = tahmini_yol_mesafesi_km(kus_ucusu_km)

    if menzil_filtresi and tahmini_km > guvenli_menzil:
        continue

    # [Eksik Özellik: Soket tipi filtresi]
    if soket_filtreleri:
        soket_val = str(ist.get("soket", "")).upper()
        if not any(sf.upper() in soket_val for sf in soket_filtreleri):
            continue

    # [Eksik Özellik: Hız filtresi]
    if hiz_filtresi != "Tümü":
        hiz_val = str(ist.get("hiz", "")).replace(",", ".")
        rakam = re.search(r"(\d+(?:\.\d+)?)", hiz_val)
        hiz_sayi = float(rakam.group(1)) if rakam else 0.0
        if hiz_sayi < HIZ_ESIK_MAP.get(hiz_filtresi, 0.0):
            continue

    # [Eksik Özellik: Metin arama filtresi]
    if arama_metni:
        aranan = arama_metni.lower()
        if aranan not in str(ist.get("isim", "")).lower() and \
           aranan not in str(ist.get("adres", "")).lower():
            continue

    station_key = clean_id_uret(istasyon_id_getir(ist))
    yorumlar = tum_yorumlar.get(station_key, [])
    ariza = ariza_skoru_hesapla(yorumlar)

    ist_kopya = ist.copy()
    ist_kopya["Mesafe"] = round(tahmini_km, 1)
    ist_kopya["KusUcusuMesafe"] = round(kus_ucusu_km, 1)
    ist_kopya["ArizaDurumu"] = ariza["durum"]
    ist_kopya["ArizaEtiketi"] = ariza["etiket"]
    ist_kopya["ArizaSkoru"] = ariza["skor"]
    uygun_istasyonlar.append(ist_kopya)

# Riskli istasyonları tamamen gizlemek yerine aşağıya iter.
uygun_istasyonlar = sorted(
    uygun_istasyonlar,
    key=lambda x: (1 if x.get("ArizaDurumu") == "riskli" else 0, x["Mesafe"]),
)
en_yakin = uygun_istasyonlar[:sonuc_sayisi]

# ==========================================
# ⭐ FAVORİLER
# ==========================================
# [Eksik Özellik: Favori istasyon kaydetme] — session_state tabanlı, oturum boyunca kalır
if "favoriler" not in st.session_state:
    st.session_state["favoriler"] = set()

favori_eslesmeler = [
    ist for ist in istasyonlar_verisi
    if clean_id_uret(istasyon_id_getir(ist)) in st.session_state["favoriler"]
]
if favori_eslesmeler:
    with st.expander(f"⭐ Favorilerim ({len(favori_eslesmeler)})", expanded=False):
        for fav in favori_eslesmeler:
            fav_isim = guvenli_metin(fav.get("isim", "Bilinmiyor"))
            fav_adres = guvenli_metin(fav.get("adres", ""))
            st.markdown(f"**⚡ {fav_isim}**  \n{fav_adres}", unsafe_allow_html=False)

# ==========================================
# 🎯 SONUÇ EKRANI VE KARTLAR
# ==========================================
if en_yakin:
    cevre_sonuclari = _paralel_cevre_getir(en_yakin, ayar_yaricap)

    # [UX/Kod 2] Overpass tamamen başarısız olduysa toast ile kullanıcıyı bilgilendir
    if any(y is None for y in cevre_sonuclari):
        st.toast(
            "Yakındaki mekan bilgisi alınamadı. Overpass API geçici olarak erişilemez olabilir.",
            icon="⚠️",
        )

    for sira, (istasyon, yakin_yerler_raw) in enumerate(zip(en_yakin, cevre_sonuclari)):
        # None (API hatası) veya [] (gerçekten boş) her ikisi de güvenle işlenir
        yakin_yerler = yakin_yerler_raw or []

        ist_id = istasyon_id_getir(istasyon)
        ist_key = clean_id_uret(ist_id)
        etiket = "🥇 En Yakın İstasyon" if sira == 0 else f"#{sira + 1} Alternatif İstasyon"
        durum = istasyon.get("ArizaDurumu", "belirsiz")
        durum_class = {
            "aktif": "durum-aktif",
            "riskli": "durum-riskli",
            "belirsiz": "durum-belirsiz",
        }.get(durum, "durum-belirsiz")
        card_class = "premium-card premium-card-risk" if durum == "riskli" else "premium-card"

        yakin_html = ""
        if yakin_yerler:
            yakin_html = '<div class="panel-bolucu"></div><div class="panel-alt-baslik">Yakındaki Yerler</div>'
            for yer in yakin_yerler:
                yakin_html += (
                    f'<div class="avantaj-item"><span>{yer["emoji"]} {yer["isim"]}</span>'
                    f'<span class="avantaj-badge">{yer["metre"]}m</span></div>'
                )

        yorum_html = ""
        # [Gerçek Hata 1] tum_yorumlar zaten bellekte; ayrı Firebase isteği atılmaz
        son_yorumlar = tum_yorumlar.get(ist_key, [])[:MAX_SON_YORUM]
        if son_yorumlar:
            yorum_html = '<div class="panel-bolucu"></div><div class="panel-alt-baslik">Son Bildirimler</div>'
            for y in son_yorumlar:
                yorum = guvenli_metin(y.get("yorum", ""), 100)
                durum_y = guvenli_metin(y.get("durum", ""), 50)
                tarih = guvenli_metin(str(y.get("tarih", ""))[:16])
                yorum_html += (
                    f'<div class="avantaj-item"><span>{durum_y}: {yorum}</span>'
                    f'<span class="avantaj-badge">{tarih}</span></div>'
                )

        # [UX/Kod 3] istasyon["adres"] normalize_et'te zaten temizlendi;
        # guvenli_metin doğrudan uygula, adres_metni_getir ile çift işleme yapma.
        adres_gosterim = guvenli_metin(istasyon.get("adres", "Adres Bilgisi Yok"))

        st.markdown(f"""
        <div class="{card_class}">
            <div class="kart-ust-satir">
                <div>
                    <div class="kart-etiket">{guvenli_metin(etiket)}</div>
                    <span class="durum-badge {durum_class}">{guvenli_metin(istasyon.get('ArizaEtiketi'))}</span>
                </div>
            </div>

            <div class="mesafe-text">{istasyon['Mesafe']} km tahmini yol</div>
            <div class="mesafe-alt-text">{istasyon['KusUcusuMesafe']} km kuş uçuşu · x{YOL_UZAMA_KATSAYISI:.2f} rota katsayısı</div>

            <div class="istasyon-isim">{guvenli_metin(istasyon['isim'])}</div>

            <div class="detay-chip-row">
                <span class="detay-chip">⚡ {guvenli_metin(istasyon.get('hiz', 'Bilinmiyor'))}</span>
                <span class="detay-chip">🔌 {guvenli_metin(istasyon.get('soket', 'Bilinmiyor'))}</span>
                <span class="detay-chip">🏢 {guvenli_metin(istasyon.get('operator', 'Bilinmiyor'))}</span>
            </div>

            <div class="detay-text" style="margin-top:13px;">Fiyat: {guvenli_metin(istasyon.get('fiyat', 'Bilinmiyor'))}</div>
            <div class="adres-text">{adres_gosterim}</div>
            {yakin_html}
            {yorum_html}
            <div class="mini-note">Not: Gerçek yol süresi trafik ve rota koşullarına göre değişebilir.</div>
        </div>
        """, unsafe_allow_html=True)

        # [Eksik Özellik: Favori] — 3. kolon eklendi
        c1, c2, c3 = st.columns([5, 3, 2])
        with c1:
            g_link = (
                "https://www.google.com/maps/dir/?api=1"
                f"&origin={user_lat},{user_lon}"
                f"&destination={istasyon['enlem']},{istasyon['boylam']}"
                "&travelmode=driving"
            )
            st.markdown(
                f'<a href="{g_link}" target="_blank" class="nav-link-btn">Navigasyonu Başlat</a>',
                unsafe_allow_html=True,
            )

        with c2:
            with st.popover("Durum Bildir"):
                if "auth_token" not in st.session_state:
                    st.warning("Durum bildirmek ve yorum yapmak için lütfen üstteki Giriş / Kullanıcı Paneli bölümünden giriş yapın.")
                else:
                    col_btn1, col_btn2 = st.columns(2)

                    with col_btn1:
                        st.markdown('<div class="rapor-calisiyor">', unsafe_allow_html=True)
                        if st.button("Sorunsuz", key=f"btn_ok_{sira}_{ist_key}"):
                            ok, msg = yorum_gonder(ist_id, "Sorunsuz / Boş", "Sorunsuz / Boş")
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                        st.markdown("</div>", unsafe_allow_html=True)

                    with col_btn2:
                        st.markdown('<div class="rapor-arizali">', unsafe_allow_html=True)
                        if st.button("Arızalı", key=f"btn_fail_{sira}_{ist_key}"):
                            ok, msg = yorum_gonder(ist_id, "Arızalı / Kapalı", "Arızalı / Kapalı")
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown("---")
                    yorum_txt = st.text_input(
                        "Durum Notu",
                        key=f"inp_txt_{sira}_{ist_key}",
                        max_chars=MAX_YORUM_KARAKTER,
                        placeholder="Örn: Soket çalışıyor ama sıra var",
                    )
                    if st.button("Detaylı Gönder", key=f"btn_detail_{sira}_{ist_key}"):
                        temiz_yorum = yorum_txt.strip()
                        if not temiz_yorum:
                            st.warning("Lütfen kısa bir durum notu yazın.")
                        else:
                            ok, msg = yorum_gonder(ist_id, temiz_yorum, "Durum Güncellemesi")
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

        with c3:
            is_favori = ist_key in st.session_state["favoriler"]
            fav_label = "★" if is_favori else "☆"
            if st.button(
                fav_label,
                key=f"fav_{sira}_{ist_key}",
                help="Favorilere ekle / çıkar",
                use_container_width=True,
            ):
                if is_favori:
                    st.session_state["favoriler"].discard(ist_key)
                else:
                    st.session_state["favoriler"].add(ist_key)
                st.rerun()

else:
    st.warning(
        "Mevcut şarj yüzdeniz ile ulaşılabilecek istasyon bulunamadı. "
        "Menzil filtresini kapatabilir veya güvenlik marjını düşürebilirsiniz."
    )
