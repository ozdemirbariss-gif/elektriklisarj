import requests
import json
import asyncio
import sentry_sdk
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
    token_suresi_doldu_mu, yorum_gonderilebilir_mi, yorumlardan_durum_ozeti_uret,
    utc_simdi, utc_isoformat
)

@st.cache_resource
def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "SarjBul/2.1", "Accept": "application/json"})
    return session

def firebase_login(email: str, password: str) -> Optional[Dict[str, Any]]:
    if not FIREBASE_ENABLED:
        return None
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    try:
        r = get_session().post(url, json={"email": email, "password": password, "returnSecureToken": True}, timeout=5)
        if r.status_code == 200: return r.json()
        logger.warning("Firebase auth başarısız: %s", r.status_code)
    except Exception as e:
        sentry_sdk.capture_exception(e)
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
        sentry_sdk.capture_exception(e)
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
        sentry_sdk.capture_exception(e)
        return False, "Bağlantı hatası."

def oturumu_temizle() -> None:
    for key in ("auth_token", "auth_email", "auth_uid", "auth_login_time"):
        st.session_state.pop(key, None)

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
            sentry_sdk.capture_exception(e)

    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            ham_veri = json.load(f)

        ham_liste = list(ham_veri.values()) if isinstance(ham_veri, dict) else ham_veri
        if not isinstance(ham_liste, list):
            return []

        return [x for item in ham_liste if (x := istasyon_normalize_et(item))]
    except Exception as e:
        sentry_sdk.capture_exception(e)
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
        sentry_sdk.capture_exception(e)

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
        sentry_sdk.capture_exception(e)
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
        sentry_sdk.capture_exception(e)
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
    except Exception: pass

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
    except Exception: pass

@st.cache_data(ttl=ISTASYON_CACHE_TTL, show_spinner=False)
def favorileri_getir(uid_hash: str, token: str) -> List[str]:
    if not FIREBASE_ENABLED or not uid_hash or not token: return []
    try:
        res = get_session().get(f"{FIREBASE_DB_URL}favoriler/{uid_hash}.json", params={"auth": token}, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code == 200 and isinstance(res.json(), dict):
            return [str(k) for k, v in res.json().items() if v]
    except Exception as e:
        logger.warning("İstasyon durum özeti güncellenemedi (%s): %s", clean_id, e)
        sentry_sdk.capture_exception(e)
    return []

def favori_guncelle(ist_key: str, favori_mi: bool) -> Tuple[bool, str]:
    token, uid_hash = st.session_state.get("auth_token"), auth_uid_hash_getir()
    if not FIREBASE_ENABLED or not token or not uid_hash:
        st.session_state["favoriler"].add(ist_key) if favori_mi else st.session_state["favoriler"].discard(ist_key)
        return True, "Oturum için güncellendi."
    if token_suresi_doldu_mu():
        oturumu_temizle()
        return False, "Oturum süresi dolmuş."
    try:
        url = f"{FIREBASE_DB_URL}favoriler/{uid_hash}/{ist_key}.json"
        res = get_session().put(url, params={"auth": token}, json=True, timeout=FIREBASE_TIMEOUT_S) if favori_mi else get_session().delete(url, params={"auth": token}, timeout=FIREBASE_TIMEOUT_S)
        if res.status_code in (200, 204):
            cache_temizle_guvenli(favorileri_getir, uid_hash, token)
            return True, "Favoriler güncellendi."
    except Exception: pass
    return False, "Favori güncellenemedi."

def yorum_gonder(istasyon_id: str, yorum_metni: str, durum: str, ek_bilgi: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    if not FIREBASE_ENABLED:
        return False, "Bildirim için Firebase bağlantısı gerekli."
    if token_suresi_doldu_mu():
        oturumu_temizle()
        return False, "Oturum süresi dolmuş."
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
    except Exception: pass
    return False, "Gönderilemedi."

def yakin_cevre_getir(enlem: float, boylam: float, yaricap_m: int) -> Optional[List[Dict[str, Any]]]:
    try:
        normalized_enlem = round(float(enlem), 4)
        normalized_boylam = round(float(boylam), 4)
        normalized_yaricap = int(yaricap_m)
    except (TypeError, ValueError):
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
            res = get_session().post(url, data={"data": sorgu}, headers=OVERPASS_HEADERS, timeout=OVERPASS_TIMEOUT_S)
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
        except Exception: continue
    return None
