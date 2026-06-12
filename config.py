import streamlit as st
import logging
import sentry_sdk
from pathlib import Path
from typing import Dict, Tuple

# ==========================================
# 🪵 LOGLAMA VE SENTRY AYARI
# ==========================================
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def sentry_init() -> None:
    try:
        if "sentry" in st.secrets and "dsn" in st.secrets["sentry"]:
            sentry_sdk.init(
                dsn=st.secrets["sentry"]["dsn"],
                traces_sample_rate=float(st.secrets["sentry"].get("traces_sample_rate", 0.10)),
                send_default_pii=False,
            )
    except Exception as e:
        logger.warning("Sentry başlatılamadı: %s", e)

# ==========================================
# 🔐 FİREBASE BAĞLANTISI SABİTLERİ
# ==========================================
def normalize_firebase_url(url: str) -> str:
    return str(url).strip().rstrip("/") + "/"

try:
    FIREBASE_DB_URL = normalize_firebase_url(st.secrets["firebase"]["db_url"])
    FIREBASE_API_KEY = st.secrets["firebase"]["api_key"]
except (KeyError, FileNotFoundError):
    FIREBASE_DB_URL = ""
    FIREBASE_API_KEY = ""

FIREBASE_ENABLED = bool(FIREBASE_DB_URL and FIREBASE_API_KEY)

# ==========================================
# 📐 UYGULAMA SABİTLERİ
# ==========================================
MAX_ISTASYON_SAYISI       = 2
MAX_EKRAN_KART_SAYISI     = 2
OVERPASS_TIMEOUT_S        = 12.0
FIREBASE_TIMEOUT_S        = 4.0
ISTASYON_CACHE_TTL        = 300
YORUM_CACHE_TTL           = 60
CEVRE_CACHE_TTL           = 21_600
TOKEN_OMUR_DK             = 55
MAX_YAKIN_YER             = 5
MAX_SON_YORUM             = 2
YOL_UZAMA_KATSAYISI       = 1.25
ORTALAMA_SEYIR_HIZI_KMH   = 45.0
YORUM_BEKLEME_SURESI      = 30
ARIZA_GECERLILIK_SAATI    = 6
ARIZA_RISK_ESIGI          = 2
MAX_YORUM_KARAKTER        = 280
KONUM_DOGRULAMA_ESIGI_KM  = 0.30
YAKIN_CEVRE_MIN_M         = 100
YAKIN_CEVRE_VARSAYILAN_M  = 400
YAKIN_CEVRE_MAX_M         = 800
YAKIN_CEVRE_ADIM_M        = 100

ARAC_KATALOGU: Dict[str, Dict[str, float]] = {
    "Tesla Model Y Long Range": {"batarya": 75.0, "tuketim": 16.9},
    "Tesla Model 3 Highland":   {"batarya": 60.0, "tuketim": 14.0},
    "Togg T10X Uzun Menzil":   {"batarya": 88.5, "tuketim": 16.9},
    "BYD Atto 3":               {"batarya": 60.4, "tuketim": 16.0},
    "Fiat 500e":                {"batarya": 42.0, "tuketim": 14.0},
    "MG4 Electric":             {"batarya": 64.0, "tuketim": 16.6},
    "Volkswagen ID.4":          {"batarya": 77.0, "tuketim": 17.0},
    "Hyundai Ioniq 6":          {"batarya": 77.4, "tuketim": 14.3},
    "Renault Megane E-Tech":    {"batarya": 60.0, "tuketim": 15.5},
    "Özel Araç (Manuel)":       {"batarya": 60.0, "tuketim": 17.0},
}

KATEGORI_EMOJILER: Dict[str, Tuple[str, str]] = {
    "cafe":        ("", "Kafe"),
    "restaurant":  ("", "Restoran"),
    "fast_food":   ("", "Fast Food"),
    "supermarket": ("", "Süpermarket"),
    "convenience": ("", "Market"),
    "fuel":        ("", "Akaryakıt"),
    "parking":     ("", "Otopark"),
    "hotel":       ("", "Otel"),
    "mall":        ("", "AVM"),
    "pharmacy":    ("", "Eczane"),
    "atm":         ("", "ATM"),
    "toilets":     ("", "Tuvalet"),
}

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
OVERPASS_HEADERS = {
    "User-Agent": "SarjBul/2.1 (+https://streamlit.io)",
    "Accept": "application/json",
}

HIZ_ESIK_MAP: Dict[str, float] = {
    "AC (≥7 kW)": 7.0,
    "DC (≥50 kW)": 50.0,
    "Hızlı DC (≥150 kW)": 150.0,
}

# ==========================================
# 🎨 TASARIM SİSTEMİ (CSS)
# ==========================================
CSS_PATH = Path(__file__).with_name("style.css")

def load_css() -> None:
    try:
        css = CSS_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("CSS dosyası okunamadı: %s", e)
        css = ""

    st.markdown(
        f'<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"><style>{css}</style>',
        unsafe_allow_html=True,
    )
