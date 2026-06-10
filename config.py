import streamlit as st
import logging
import sentry_sdk
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
    st.error("Firebase bağlantı bilgileri (db_url ve api_key) bulunamadı.")
    st.stop()

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

ARAC_KATALOGU: Dict[str, Dict[str, float]] = {
    "Tesla Model Y Long Range": {"batarya": 75.0, "tuketim": 16.9},
    "Togg T10X Uzun Menzil":   {"batarya": 88.5, "tuketim": 16.9},
    "BYD Atto 3":               {"batarya": 60.4, "tuketim": 16.0},
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
def load_css():
    st.markdown('''
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <style>
            :root {
                --sb-bg: #101211;
                --sb-surface: #171A18;
                --sb-surface-soft: #1E221F;
                --sb-line: rgba(226, 232, 220, 0.12);
                --sb-line-strong: rgba(226, 232, 220, 0.22);
                --sb-text: #F3F5F0;
                --sb-text-soft: #C8CEC4;
                --sb-text-muted: #8F978C;
                --sb-primary: #B7F0D0;
                --sb-primary-deep: #6EC89A;
                --sb-danger: #E68484;
                --sb-warning: #D8B46A;
            }

            [data-testid="stHeader"] { display: none !important; }

            .stApp {
                background: linear-gradient(180deg, #101211 0%, #141714 100%) !important;
                color: var(--sb-text) !important;
            }

            .block-container {
                padding: 1rem 0.9rem 4.5rem !important;
                max-width: 480px !important;
            }

            h1, h2, h3 {
                color: var(--sb-text) !important;
                letter-spacing: 0 !important;
                font-weight: 720 !important;
            }

            h1 {
                font-size: 30px !important;
                margin: 0.25rem 0 0.15rem !important;
            }

            h2, h3 {
                font-size: 22px !important;
            }

            p, span, label, .stMarkdown, .stCaption,
            .stTextInput label, .stNumberInput label, .stSelectbox label,
            .stSlider label, .stMultiSelect label {
                color: var(--sb-text-soft) !important;
                letter-spacing: 0 !important;
            }

            .stCaption, .caption, small {
                color: var(--sb-text-muted) !important;
            }

            div[data-testid="stExpander"] {
                background: rgba(23, 26, 24, 0.82) !important;
                border: 1px solid var(--sb-line) !important;
                border-radius: 8px !important;
                box-shadow: none !important;
                overflow: hidden;
            }

            div[data-testid="stExpander"] details summary {
                color: var(--sb-text-soft) !important;
                font-weight: 620 !important;
            }

            div[data-testid="stVerticalBlockBorderWrapper"] {
                background: rgba(23, 26, 24, 0.92) !important;
                border: 1px solid var(--sb-line) !important;
                border-radius: 8px !important;
                box-shadow: 0 18px 42px rgba(0, 0, 0, 0.18);
            }

            div[data-testid="stAlert"] {
                background: rgba(30, 34, 31, 0.92) !important;
                border: 1px solid var(--sb-line) !important;
                border-radius: 8px !important;
                color: var(--sb-text-soft) !important;
            }

            input, textarea, [data-baseweb="select"] > div {
                background-color: var(--sb-surface) !important;
                color: var(--sb-text) !important;
                border-radius: 8px !important;
                border-color: var(--sb-line-strong) !important;
            }

            .stButton>button, .stDownloadButton>button,
            div[data-testid="stLinkButton"] a {
                min-height: 48px;
                width: 100%;
                border-radius: 8px !important;
                border: 1px solid var(--sb-line-strong) !important;
                background: var(--sb-surface-soft) !important;
                color: var(--sb-text) !important;
                font-weight: 650 !important;
                box-shadow: none !important;
            }

            div[data-testid="stLinkButton"] a {
                background: var(--sb-primary) !important;
                color: #0E1511 !important;
                border-color: var(--sb-primary) !important;
            }

            .stButton>button:hover,
            div[data-testid="stLinkButton"] a:hover {
                border-color: var(--sb-primary-deep) !important;
                filter: brightness(1.03);
            }

            hr {
                border-color: var(--sb-line) !important;
            }
        </style>
    ''', unsafe_allow_html=True)
