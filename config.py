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

VARSAYILAN_ARAC_GORSELI = "https://images.unsplash.com/photo-1707758283240-814ee7fbb33a?auto=format&fit=crop&w=1200&q=72"

ARAC_GORSELLERI: Dict[str, str] = {
    "Tesla Model Y Long Range": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5c/Tesla_Model_Y_1X7A6211.jpg/1280px-Tesla_Model_Y_1X7A6211.jpg",
    "Tesla Model 3 Highland": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/86/Tesla_Model_3_%282023%29_IMG_9488_%28cropped%29.jpg/1280px-Tesla_Model_3_%282023%29_IMG_9488_%28cropped%29.jpg",
    "Togg T10X Uzun Menzil": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Togg_T10X_IAA_2025_DSC_1794_%28cropped%29.jpg/1280px-Togg_T10X_IAA_2025_DSC_1794_%28cropped%29.jpg",
    "BYD Atto 3": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/78/BYD_Atto_3_1X7A6495.jpg/1280px-BYD_Atto_3_1X7A6495.jpg",
    "Fiat 500e": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b1/Fiat_500e_Cabrio_%282020%29_IMG_0011.jpg/1280px-Fiat_500e_Cabrio_%282020%29_IMG_0011.jpg",
    "MG4 Electric": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4f/MG4_EV_Automesse_Ludwigsburg_2022_1X7A5920.jpg/1280px-MG4_EV_Automesse_Ludwigsburg_2022_1X7A5920.jpg",
    "Volkswagen ID.4": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/33/Volkswagen_ID.4_1X7A0360.jpg/1280px-Volkswagen_ID.4_1X7A0360.jpg",
    "Hyundai Ioniq 6": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Hyundai_Ioniq_6_1X7A7258.jpg/1280px-Hyundai_Ioniq_6_1X7A7258.jpg",
    "Renault Megane E-Tech": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Renault_Megane_E-Tech_1X7A6019.jpg/1280px-Renault_Megane_E-Tech_1X7A6019.jpg",
    "Özel Araç (Manuel)": VARSAYILAN_ARAC_GORSELI,
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

    html = f"<style>\n{css}\n</style>"
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)
