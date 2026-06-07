import streamlit as st
import json
import math
import hashlib
import logging
import unicodedata
import requests
from concurrent.futures import ThreadPoolExecutor
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
YORUM_CACHE_TTL           = 10        # durum verisi hızlı tazelensin
CEVRE_CACHE_TTL           = 21_600    # 6 saat
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

# ==========================================
# 🎨 PREMIUM CSS
# ==========================================
st.markdown('''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        [data-testid="stHeader"] { display: none !important; }
        .stApp { background-color: #f8f9fa !important; }
        .block-container { padding: 1.5rem 1rem !important; max-width: 440px !important; }
        .title-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; border: 2px solid #0f172a; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08); }
        .title-cell { background-color: #0f172a; color: #ffffff !important; font-family: 'Inter', sans-serif; font-weight: 800; font-size: 24px; text-align: center; padding: 14px; text-transform: uppercase; }
        .subtitle-cell { background-color: #ffffff; color: #475569 !important; font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 500; text-align: center; padding: 10px; border-top: 1px solid #e2e8f0; }
        .premium-card { background: #ffffff !important; border: 1px solid #e2e8f0 !important; border-top: 5px solid #0f172a !important; border-radius: 16px; padding: 24px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04); margin-bottom: 16px; }
        .premium-card-risk { border-top-color: #dc2626 !important; }
        .istasyon-isim { font-size: 20px; font-weight: 700; color: #0f172a !important; margin: 0 0 6px 0; letter-spacing: -0.3px; }
        .mesafe-text { font-size: 14px; font-weight: 700; color: #1e40af !important; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px; }
        .detay-text { font-size: 13px; color: #475569 !important; margin: 0; font-weight: 500; }
        .adres-text { font-size: 12px; color: #64748b !important; margin-top: 14px; line-height: 1.5; border-top: 1px solid #f1f5f9; padding-top: 14px; }
        .panel-bolucu { border-top: 1px solid #f1f5f9; margin: 18px 0; }
        .panel-alt-baslik { font-size: 13px; font-weight: 700; color: #0f172a !important; margin-bottom: 12px; text-transform: uppercase; }
        .avantaj-item { font-size: 12px; color: #475569 !important; margin-bottom: 8px; display: flex; justify-content: space-between; gap: 12px; font-weight: 500; }
        .avantaj-badge { color: #1e40af !important; font-weight: 700; white-space: nowrap; }
        .durum-badge { display:inline-block; font-size:11px; font-weight:800; padding:5px 8px; border-radius:999px; margin-bottom:10px; }
        .durum-aktif { background:#ecfdf5; color:#047857; border:1px solid #a7f3d0; }
        .durum-riskli { background:#fef2f2; color:#b91c1c; border:1px solid #fecaca; }
        .durum-belirsiz { background:#f8fafc; color:#475569; border:1px solid #e2e8f0; }
        .nav-link-btn { display: flex; align-items: center; justify-content: center; text-decoration: none; border-radius: 10px; height: 46px; font-weight: 600; background-color: #0f172a; color: #ffffff !important; border: 1px solid #0f172a; font-size: 14px; }
        .stButton>button { border-radius: 10px; height: 46px; font-weight: 600; width: 100%; }
        .rapor-calisiyor>button { border-color: #2563eb !important; color: #2563eb !important; background: #eff6ff !important; }
        .rapor-arizali>button { border-color: #dc2626 !important; color: #dc2626 !important; background: #fef2f2 !important; }
        .mini-note { font-size: 11px; color: #64748b !important; line-height:1.45; margin-top:8px; }
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


def clean_id_uret(isim: str) -> str:
    raw = str(isim or "").strip()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_isim = normalized.encode("ascii", "ignore").decode("ascii").strip()
    safe = "".join(c for c in ascii_isim if c.isalnum() or c in (" ", "_", "-")).rstrip()
    safe = "_".join(safe.split())
    return safe[:80] if safe else hashlib.md5(raw.encode()).hexdigest()[:12]


def istasyon_id_getir(istasyon: Dict[str, Any]) -> str:
    return str(istasyon.get("id") or istasyon.get("isim") or "bilinmeyen_istasyon")


def yorum_gonderilebilir_mi() -> Tuple[bool, int]:
    son = st.session_state.get("son_yorum_zamani")
    if son is None:
        return True, 0
    kalan = YORUM_BEKLEME_SURESI - int((datetime.now() - son).total_seconds())
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
        yeni.setdefault("adres", "")
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
    gonderilebilir, kalan = yorum_gonderilebilir_mi()
    if not gonderilebilir:
        return False, f"Çok sık bildirim yapıyorsunuz. {kalan} saniye sonra tekrar deneyin."

    token = st.session_state.get("auth_token")
    if not token:
        return False, "Durum bildirmek için giriş yapmalısınız."

    clean_id = clean_id_uret(istasyon_id)
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"

    # Privacy: e-posta prefix'i yerine anonim doğrulanmış kullanıcı etiketi.
    kullanici = "Doğrulanmış Sürücü"

    yeni_yorum = {
        "kullanici": kullanici,
        "yorum": guvenli_metin(yorum_metni or durum, MAX_YORUM_KARAKTER),
        "durum": guvenli_metin(durum, 60),
        "tarih": datetime.now().isoformat(timespec="seconds"),
        "uid_hash": hashlib.sha256(str(st.session_state.get("auth_uid", "")).encode()).hexdigest()[:16],
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
def yakin_cevre_getir(enlem: float, boylam: float, yaricap_m: int) -> List[Dict[str, Any]]:
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
            return filtrelenmis
        except Exception as e:
            sentry_sdk.capture_exception(e)
            logger.warning("Overpass denemesi başarısız (%s): %s", overpass_url, e)
            continue

    return []


def _cevre_getir_ist(ist: Dict[str, Any], yaricap: int) -> List[Dict[str, Any]]:
    return yakin_cevre_getir(ist["enlem"], ist["boylam"], yaricap)


def _paralel_cevre_getir(istasyon_listesi: List[Dict[str, Any]], yaricap: int) -> List[List[Dict[str, Any]]]:
    if not istasyon_listesi:
        return []
    max_workers = min(4, max(1, len(istasyon_listesi)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(lambda ist: _cevre_getir_ist(ist, yaricap), istasyon_listesi))

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
                st.session_state["auth_email"] = user_data.get("email", "")
                st.session_state["auth_uid"] = user_data.get("localId", "")
                st.session_state["auth_login_time"] = datetime.now().isoformat(timespec="seconds")
                st.success("Giriş başarılı!")
                st.rerun()
            else:
                st.error("Giriş başarısız. Lütfen bilgilerinizi kontrol edin.")
    else:
        st.success("Giriş aktif: Doğrulanmış Sürücü")
        if st.button("Çıkış Yap", use_container_width=True):
            oturumu_temizle()
            st.rerun()

    st.markdown("---")
    st.header("⚙️ Arama Ayarları")
    ayar_yaricap = st.slider(
        "Çevresel Mekan Arama Yarıçapı (m)",
        min_value=100,
        max_value=800,
        value=400,
        step=100,
    )
    sonuc_sayisi = st.slider(
        "Gösterilecek İstasyon Sayısı",
        min_value=2,
        max_value=10,
        value=MAX_ISTASYON_SAYISI,
        step=1,
    )
    st.markdown("---")
    st.info("Durum bildirimi için giriş gerekir. Konum veriniz Firebase'e kaydedilmez.")

# ==========================================
# 🏛️ BAŞLIK VE KONUM
# ==========================================
st.markdown('''
    <table class="title-table">
        <tr><td class="title-cell">ŞarjBul</td></tr>
        <tr><td class="subtitle-cell">En yakın aktif şarj rotanız</td></tr>
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
# 🎯 SONUÇ EKRANI VE KARTLAR
# ==========================================
if en_yakin:
    cevre_sonuclari = _paralel_cevre_getir(en_yakin, ayar_yaricap)

    for sira, (istasyon, yakin_yerler) in enumerate(zip(en_yakin, cevre_sonuclari)):
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
        son_yorumlar = istasyon_yorumlari_getir(istasyon_id_getir(istasyon), MAX_SON_YORUM)
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

        st.markdown(f"""
        <div class="{card_class}">
            <div style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:8px;">{guvenli_metin(etiket)}</div>
            <span class="durum-badge {durum_class}">{guvenli_metin(istasyon.get('ArizaEtiketi'))}</span>
            <div class="mesafe-text">Tahmini yol: {istasyon['Mesafe']} km · Kuş uçuşu: {istasyon['KusUcusuMesafe']} km</div>
            <div class="istasyon-isim">{guvenli_metin(istasyon['isim'])}</div>
            <div class="detay-text">Şarj Hızı: {guvenli_metin(istasyon.get('hiz', 'Bilinmiyor'))}</div>
            <div class="detay-text">Soket: {guvenli_metin(istasyon.get('soket', 'Bilinmiyor'))} · Operatör: {guvenli_metin(istasyon.get('operator', 'Bilinmiyor'))}</div>
            <div class="detay-text">Fiyat: {guvenli_metin(istasyon.get('fiyat', 'Bilinmiyor'))}</div>
            <div class="adres-text">{guvenli_metin(istasyon.get('adres', ''))}</div>
            {yakin_html}
            {yorum_html}
            <div class="mini-note">Not: Gerçek yol süresi trafik ve rota koşullarına göre değişebilir.</div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
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
                    st.warning("Durum bildirmek ve yorum yapmak için lütfen yan menüden giriş yapın.")
                else:
                    col_btn1, col_btn2 = st.columns(2)
                    ist_id = istasyon_id_getir(istasyon)

                    with col_btn1:
                        st.markdown('<div class="rapor-calisiyor">', unsafe_allow_html=True)
                        if st.button("Sorunsuz", key=f"btn_ok_{sira}"):
                            ok, msg = yorum_gonder(ist_id, "Sorunsuz / Boş", "Sorunsuz / Boş")
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                        st.markdown("</div>", unsafe_allow_html=True)

                    with col_btn2:
                        st.markdown('<div class="rapor-arizali">', unsafe_allow_html=True)
                        if st.button("Arızalı", key=f"btn_fail_{sira}"):
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
                        key=f"inp_txt_{sira}",
                        max_chars=MAX_YORUM_KARAKTER,
                        placeholder="Örn: Soket çalışıyor ama sıra var",
                    )
                    if st.button("Detaylı Gönder", key=f"btn_detail_{sira}"):
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
else:
    st.warning(
        "Mevcut şarj yüzdeniz ile ulaşılabilecek istasyon bulunamadı. "
        "Menzil filtresini kapatabilir veya güvenlik marjını düşürebilirsiniz."
    )
