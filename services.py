import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import json
import sentry_sdk
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple
import streamlit as st

from config import (
    logger, FIREBASE_DB_URL, FIREBASE_API_KEY, FIREBASE_ENABLED, MAX_SON_YORUM, ISTASYON_CACHE_TTL,
    YORUM_CACHE_TTL, CEVRE_CACHE_TTL, FIREBASE_TIMEOUT_S, OVERPASS_TIMEOUT_S,
    OVERPASS_URLS, OVERPASS_HEADERS, KATEGORI_EMOJILER, MAX_YAKIN_YER, MAX_YORUM_KARAKTER, YORUM_BEKLEME_SURESI
)
from utils import (
    istasyon_normalize_et, yorum_tarihi_parse, clean_id_uret,
    auth_uid_hash_getir, cache_temizle_guvenli, guvenli_metin, mesafe_hesapla,
    token_yenileme_gerekli_mi, yorum_gonderilebilir_mi, yorumlardan_durum_ozeti_uret,
    utc_simdi, utc_isoformat
)

RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
SAFE_RETRY_METHODS = frozenset(("GET", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"))
OVERPASS_RETRY_METHODS = frozenset(("POST",))


def _retry_adapter(allowed_methods: frozenset[str]) -> HTTPAdapter:
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.35,
        status_forcelist=RETRY_STATUS_CODES,
        allowed_methods=allowed_methods,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    return HTTPAdapter(max_retries=retry)


def _retry_session(allowed_methods: frozenset[str]) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "SarjBul/2.1", "Accept": "application/json"})
    session.mount("https://", _retry_adapter(allowed_methods))
    session.mount("http://", _retry_adapter(allowed_methods))
    return session


@st.cache_resource
def get_session() -> requests.Session:
    return _retry_session(SAFE_RETRY_METHODS)

@st.cache_resource
def get_overpass_session() -> requests.Session:
    return _retry_session(OVERPASS_RETRY_METHODS)

def _hata_bildir(baglam: str, hata: Exception) -> None:
    logger.warning("%s: %s", baglam, hata, exc_info=True)
    sentry_sdk.capture_exception(hata)

def firebase_login(email: str, password: str) -> Optional[Dict[str, Any]]:
    if not FIREBASE_ENABLED:
        return None
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    try:
        r = get_session().post(url, json={"email": email, "password": password, "returnSecureToken": True}, timeout=5)
        if r.status_code == 200: return r.json()
        logger.warning("Firebase auth başarısız: %s", r.status_code)
    except Exception as e:
        _hata_bildir("Firebase auth isteği başarısız", e)
    return None

def firebase_register(email: str, password: str) -> Optional[Dict[str, Any]]:
    if not FIREBASE_ENABLED:
        return None
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    try:
        r = get_session().post(url, json={"email": email, "password": password, "returnSecureToken": True}, timeout=5)
        if r.status_code == 200: return r.json()
        logger.warning("Firebase kayıt başarısız: %s", r.status_code)
    except Exception as e:
        _hata_bildir("Firebase kayıt isteği başarısız", e)
    return None

def firebase_sifre_sifirla(email: str) -> Tuple[bool, str]:
    if not FIREBASE_ENABLED:
        return False, "Firebase bağlantısı yapılandırılmamış."
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_API_KEY}"
    try:
        r = get_session().post(url, json={"requestType": "PASSWORD_RESET", "email": email}, timeout=5)
        if r.status_code == 200: return True, "Şifre sıfırlama bağlantısı gönderildi."
        return False, f"Gönderilemedi: {r.json().get('error', {}).get('message', 'Hata')}"
    except Exception as e:
        _hata_bildir("Firebase şifre sıfırlama isteği başarısız", e)
        return False, "Bağlantı hatası."

def oturum_bilgilerini_kaydet(user_data: Dict[str, Any]) -> bool:
    token = user_data.get("idToken") or user_data.get("id_token")
    if not token:
        logger.warning("Oturum bilgileri kaydedilemedi: id token yok")
        return False

    refresh_token = (
        user_data.get("refreshToken")
        or user_data.get("refresh_token")
        or st.session_state.get("auth_refresh_token", "")
    )
    expires_in_raw = user_data.get("expiresIn") or user_data.get("expires_in") or 3600
    try:
        expires_in = max(60, int(expires_in_raw))
    except (TypeError, ValueError):
        expires_in = 3600

    simdi = utc_simdi()
    st.session_state.update(
        {
            "auth_token": token,
            "auth_refresh_token": refresh_token,
            "auth_email": user_data.get("email", st.session_state.get("auth_email", "")),
            "auth_uid": user_data.get("localId") or user_data.get("user_id") or st.session_state.get("auth_uid", ""),
            "auth_login_time": utc_isoformat(simdi),
            "auth_expires_at": utc_isoformat(simdi + timedelta(seconds=expires_in)),
        }
    )
    return True

def firebase_token_yenile(refresh_token: str) -> Optional[Dict[str, Any]]:
    if not FIREBASE_ENABLED or not refresh_token:
        return None

    url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    payload = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    try:
        res = get_session().post(url, data=payload, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code == 200:
            return res.json()
        logger.warning("Firebase token yenileme başarısız: %s %s", res.status_code, res.text[:180])
    except Exception as e:
        _hata_bildir("Firebase token yenileme isteği başarısız", e)
    return None

def oturum_token_yenile() -> bool:
    user_data = firebase_token_yenile(str(st.session_state.get("auth_refresh_token", "")))
    if not user_data:
        return False
    return oturum_bilgilerini_kaydet(user_data)

def oturum_gecerli_tut() -> bool:
    if "auth_token" not in st.session_state:
        return False
    if not token_yenileme_gerekli_mi():
        return True
    if oturum_token_yenile():
        return True
    oturumu_temizle()
    return False

def oturumu_temizle() -> None:
    for key in (
        "auth_token", "auth_refresh_token", "auth_email", "auth_uid",
        "auth_login_time", "auth_expires_at", "favoriler_uid_hash",
        "favoriler_yuklendi", "favoriler",
    ):
        st.session_state.pop(key, None)
    st.session_state["favoriler"] = set()

@st.cache_data(ttl=ISTASYON_CACHE_TTL, show_spinner=False)
def istasyonlari_yukle() -> List[Dict[str, Any]]:
    if FIREBASE_ENABLED:
        try:
            res = get_session().get(f"{FIREBASE_DB_URL}istasyonlar.json", timeout=3.0)
            if res.status_code == 200 and res.json():
                ham_veri = res.json()
                ham_liste = list(ham_veri.values()) if isinstance(ham_veri, dict) else ham_veri
                return [x for item in ham_liste if (x := istasyon_normalize_et(item))]
        except Exception as e:
            _hata_bildir("İstasyonlar Firebase'den yüklenemedi", e)

    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            ham_veri = json.load(f)

        ham_liste = list(ham_veri.values()) if isinstance(ham_veri, dict) else ham_veri
        if not isinstance(ham_liste, list):
            return []

        return [x for item in ham_liste if (x := istasyon_normalize_et(item))]
    except Exception as e:
        _hata_bildir("Yerel istasyon dosyası yüklenemedi", e)
        return []

@st.cache_data(ttl=YORUM_CACHE_TTL, show_spinner=False)
def istasyon_yorumlari_getir(istasyon_id: str, limit: int = MAX_SON_YORUM) -> List[Dict[str, Any]]:
    if not FIREBASE_ENABLED:
        return []
    clean_id = clean_id_uret(istasyon_id)
    try:
        res = get_session().get(
            f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json",
            timeout=FIREBASE_TIMEOUT_S,
        )
        if res.status_code == 200 and res.json():
            yorumlar = [y for y in res.json().values() if isinstance(y, dict)]
            return sorted(
                yorumlar,
                key=lambda x: yorum_tarihi_parse(x.get("tarih", "")),
                reverse=True,
            )[:limit]
    except Exception as e:
        _hata_bildir("İstasyon yorumları alınamadı", e)

    return []

@st.cache_data(ttl=YORUM_CACHE_TTL, show_spinner=False)
def durum_ozetleri_getir() -> Dict[str, Dict[str, Any]]:
    if not FIREBASE_ENABLED:
        return {}
    try:
        res = get_session().get(f"{FIREBASE_DB_URL}station_status.json", timeout=FIREBASE_TIMEOUT_S)
        if res.status_code == 200 and res.json():
            return {c_id: data for c_id, data in res.json().items() if isinstance(data, dict)}
    except Exception as e:
        _hata_bildir("Durum özetleri alınamadı", e)
    return {}

@st.cache_data(ttl=YORUM_CACHE_TTL, show_spinner=False)
def gorunen_yorumlari_getir(station_keys: Tuple[str, ...]) -> Dict[str, List[Dict[str, Any]]]:
    return {key: istasyon_yorumlari_getir(key, MAX_SON_YORUM) for key in station_keys}

@st.cache_data(ttl=YORUM_CACHE_TTL, show_spinner=False)
def tahmin_yorumlari_getir(station_keys: Tuple[str, ...], limit: int = 120) -> Dict[str, List[Dict[str, Any]]]:
    if not FIREBASE_ENABLED:
        return {}
    return {key: istasyon_yorumlari_getir(key, limit) for key in station_keys}

@st.cache_data(ttl=YORUM_CACHE_TTL, show_spinner=False)
def kullanici_son_yorum_zamani_getir(uid_hash: str, token: str) -> Optional[str]:
    if not FIREBASE_ENABLED or not uid_hash or not token: return None
    try:
        res = get_session().get(f"{FIREBASE_DB_URL}kullanici_yorum_meta/{uid_hash}.json", params={"auth": token}, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code == 200 and isinstance(res.json(), dict):
            return str(res.json().get("son_yorum_zamani", "")) or None
    except Exception as e:
        _hata_bildir("Kullanıcı yorum metası alınamadı", e)
    return None

def sunucu_tarafli_hizli_cooldown_kontrol(uid_hash: str, token: str) -> Tuple[bool, int]:
    son_str = kullanici_son_yorum_zamani_getir(uid_hash, token)
    if not son_str: return True, 0
    son = yorum_tarihi_parse(son_str)
    kalan = YORUM_BEKLEME_SURESI - int((utc_simdi() - son).total_seconds())
    return kalan <= 0, max(0, kalan)

def kullanici_yorum_meta_guncelle(uid_hash: str, token: str, tarih: str) -> None:
    if not FIREBASE_ENABLED:
        return
    try:
        get_session().patch(f"{FIREBASE_DB_URL}kullanici_yorum_meta/{uid_hash}.json", params={"auth": token}, json={"son_yorum_zamani": tarih}, timeout=FIREBASE_TIMEOUT_S)
        cache_temizle_guvenli(kullanici_son_yorum_zamani_getir, uid_hash, token)
    except Exception as e:
        _hata_bildir("Kullanıcı yorum metası güncellenemedi", e)

def istasyon_durum_ozetini_guncelle(clean_id: str, token: str) -> None:
    if not FIREBASE_ENABLED:
        return
    try:
        res = get_session().get(f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json", params={"auth": token}, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code == 200 and res.json():
            ozet = yorumlardan_durum_ozeti_uret([y for y in res.json().values() if isinstance(y, dict)])
            get_session().patch(f"{FIREBASE_DB_URL}station_status/{clean_id}.json", params={"auth": token}, json=ozet, timeout=FIREBASE_TIMEOUT_S)
            cache_temizle_guvenli(durum_ozetleri_getir)
            cache_temizle_guvenli(gorunen_yorumlari_getir)
            cache_temizle_guvenli(istasyon_yorumlari_getir, clean_id, MAX_SON_YORUM)
    except Exception as e:
        _hata_bildir("İstasyon durum özeti güncellenemedi", e)

@st.cache_data(ttl=ISTASYON_CACHE_TTL, show_spinner=False)
def favorileri_getir(uid_hash: str, token: str) -> List[str]:
    if not FIREBASE_ENABLED or not uid_hash or not token: return []
    try:
        res = get_session().get(f"{FIREBASE_DB_URL}favoriler/{uid_hash}.json", params={"auth": token}, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code == 200 and isinstance(res.json(), dict):
            return [str(k) for k, v in res.json().items() if v]
    except Exception as e:
        _hata_bildir("Favoriler alınamadı", e)
    return []

def favori_guncelle(ist_key: str, favori_mi: bool) -> Tuple[bool, str]:
    token, uid_hash = st.session_state.get("auth_token"), auth_uid_hash_getir()
    favoriler = st.session_state.setdefault("favoriler", set())
    if not isinstance(favoriler, set):
        favoriler = set(favoriler)
        st.session_state["favoriler"] = favoriler

    if not FIREBASE_ENABLED or not token or not uid_hash:
        favoriler.add(ist_key) if favori_mi else favoriler.discard(ist_key)
        return True, "Oturum için güncellendi."

    if token_yenileme_gerekli_mi() and not oturum_token_yenile():
        oturumu_temizle()
        return False, "Oturum yenilenemedi. Lütfen tekrar giriş yapın."

    token, uid_hash = st.session_state.get("auth_token"), auth_uid_hash_getir()
    try:
        url = f"{FIREBASE_DB_URL}favoriler/{uid_hash}/{ist_key}.json"
        res = get_session().put(url, params={"auth": token}, json=True, timeout=FIREBASE_TIMEOUT_S) if favori_mi else get_session().delete(url, params={"auth": token}, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code in (200, 204):
            cache_temizle_guvenli(favorileri_getir, uid_hash, token)
            favoriler.add(ist_key) if favori_mi else favoriler.discard(ist_key)
            st.session_state["favoriler_uid_hash"] = uid_hash
            st.session_state["favoriler_yuklendi"] = True
            return True, "Favoriler güncellendi."
        logger.warning("Favori güncelleme başarısız: %s %s", res.status_code, res.text[:180])
    except Exception as e:
        _hata_bildir("Favori güncellenemedi", e)
    return False, "Favori güncellenemedi."

def yorum_gonder(istasyon_id: str, yorum_metni: str, durum: str, ek_bilgi: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    if not FIREBASE_ENABLED:
        return False, "Bildirim için Firebase bağlantısı gerekli."
    if not oturum_gecerli_tut():
        return False, "Oturum yenilenemedi. Lütfen tekrar giriş yapın."
    gonderilebilir, kalan = yorum_gonderilebilir_mi()
    if not gonderilebilir: return False, f"{kalan} saniye bekleyin."
    token, uid_hash = st.session_state.get("auth_token"), auth_uid_hash_getir()
    if not token: return False, "Giriş yapmalısınız."

    sunucu_ok, sunucu_kalan = sunucu_tarafli_hizli_cooldown_kontrol(uid_hash, token)
    if not sunucu_ok: return False, f"{sunucu_kalan} saniye bekleyin."

    clean_id, tarih = clean_id_uret(istasyon_id), utc_isoformat()
    yeni_yorum = {"kullanici": "Doğrulanmış Sürücü", "yorum": guvenli_metin(yorum_metni or durum, MAX_YORUM_KARAKTER), "durum": guvenli_metin(durum, 60), "tarih": tarih, "uid_hash": uid_hash}
    if ek_bilgi: yeni_yorum["ek_bilgi"] = ek_bilgi

    try:
        r = get_session().post(f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json", params={"auth": token}, json=yeni_yorum, timeout=FIREBASE_TIMEOUT_S)
        if r.status_code in (200, 201):
            st.session_state["son_yorum_zamani"] = utc_simdi()
            kullanici_yorum_meta_guncelle(uid_hash, token, tarih)
            istasyon_durum_ozetini_guncelle(clean_id, token)
            return True, "Bildirim kaydedildi."
        logger.warning("Yorum gönderme başarısız: %s %s", r.status_code, r.text[:180])
    except Exception as e:
        _hata_bildir("Yorum gönderilemedi", e)
    return False, "Gönderilemedi."

def yakin_cevre_getir(enlem: float, boylam: float, yaricap_m: int) -> Optional[List[Dict[str, Any]]]:
    try:
        normalized_enlem = round(float(enlem), 4)
        normalized_boylam = round(float(boylam), 4)
        normalized_yaricap = int(yaricap_m)
    except (TypeError, ValueError) as e:
        logger.warning("Yakın çevre parametreleri geçersiz: %s", e)
        return None

    return _yakin_cevre_getir_cached(normalized_enlem, normalized_boylam, normalized_yaricap)


@st.cache_data(ttl=CEVRE_CACHE_TTL, show_spinner=False)
def _yakin_cevre_getir_cached(enlem: float, boylam: float, yaricap_m: int) -> Optional[List[Dict[str, Any]]]:
    sorgu = f"""[out:json][timeout:{int(OVERPASS_TIMEOUT_S)}];
    (nwr["amenity"~"cafe|restaurant|fast_food|parking|pharmacy|atm|toilets|fuel"](around:{yaricap_m},{enlem},{boylam});
     nwr["shop"~"supermarket|convenience|mall"](around:{yaricap_m},{enlem},{boylam});
     nwr["tourism"="hotel"](around:{yaricap_m},{enlem},{boylam}););out center tags;"""
    for url in OVERPASS_URLS:
        try:
            res = get_overpass_session().post(url, data={"data": sorgu}, headers=OVERPASS_HEADERS, timeout=OVERPASS_TIMEOUT_S)
            if res.status_code == 200:
                sonuclar = []
                for el in res.json().get("elements", []):
                    tags = el.get("tags", {}) or {}
                    kategori_kodu = tags.get("amenity") or tags.get("shop") or tags.get("tourism") or ""
                    if kategori_kodu not in KATEGORI_EMOJILER: continue
                    lat, lon = el.get("lat") or el.get("center", {}).get("lat"), el.get("lon") or el.get("center", {}).get("lon")
                    if lat is None or lon is None: continue
                    km = mesafe_hesapla(enlem, boylam, float(lat), float(lon))
                    emoji, kat_adi = KATEGORI_EMOJILER[kategori_kodu]
                    sonuclar.append({"isim": guvenli_metin(tags.get("name") or kat_adi, 80), "kategori": kat_adi, "metre": int(km * 1000)})

                gorulmus, filtrelenmis = set(), []
                for s in sorted(sonuclar, key=lambda x: x["metre"]):
                    isim_key = str(s["isim"]).lower()
                    if isim_key in gorulmus: continue
                    gorulmus.add(isim_key)
                    filtrelenmis.append(s)
                    if len(filtrelenmis) >= MAX_YAKIN_YER: break
                return filtrelenmis
        except Exception as e:
            logger.warning("Yakın çevre isteği başarısız (%s): %s", url, e, exc_info=True)
    return None
