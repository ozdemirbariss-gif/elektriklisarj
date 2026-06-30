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
# 🗺️ HARİTA VE ROTA SAĞLAYICILARI
# ==========================================
DEFAULT_MAP_TILE_URL = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
DEFAULT_MAP_TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'

try:
    MAP_TILE_URL = str(st.secrets.get("map", {}).get("tile_url", DEFAULT_MAP_TILE_URL)).strip() or DEFAULT_MAP_TILE_URL
    MAP_TILE_ATTRIBUTION = str(
        st.secrets.get("map", {}).get("tile_attribution", DEFAULT_MAP_TILE_ATTRIBUTION)
    ).strip() or DEFAULT_MAP_TILE_ATTRIBUTION
    MAP_TILE_SUBDOMAINS = str(st.secrets.get("map", {}).get("tile_subdomains", "abcd")).strip()
    ROUTING_URL_TEMPLATE = str(st.secrets.get("map", {}).get("routing_url_template", "")).strip()
except Exception:
    MAP_TILE_URL = DEFAULT_MAP_TILE_URL
    MAP_TILE_ATTRIBUTION = DEFAULT_MAP_TILE_ATTRIBUTION
    MAP_TILE_SUBDOMAINS = "abcd"
    ROUTING_URL_TEMPLATE = ""

# ==========================================
# 📐 UYGULAMA SABİTLERİ
# ==========================================
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

VARSAYILAN_BATARYA_KWH   = 75.0
VARSAYILAN_TUKETIM_KWH   = 16.9

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
