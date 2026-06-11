import math
import html
import hashlib
import unicodedata
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import streamlit as st

from config import (
    ORTALAMA_SEYIR_HIZI_KMH, YOL_UZAMA_KATSAYISI, ARIZA_GECERLILIK_SAATI, 
    ARIZA_RISK_ESIGI, TOKEN_OMUR_DK, YORUM_BEKLEME_SURESI, MAX_SON_YORUM
)

def guvenli_metin(metin: Any, max_len: Optional[int] = None) -> str:
    text = html.escape(str(metin or "").strip())
    if max_len is not None:
        text = text[:max_len]
    return text

def html_etiketlerini_temizle(metin: Any) -> str:
    text = html.unescape(str(metin or "").strip())
    while "<" in text and ">" in text:
        start = text.find("<")
        end = text.find(">", start)
        if end == -1: break
        text = text[:start] + " " + text[end + 1:]
    return " ".join(text.split())

def adres_metni_getir(istasyon: Dict[str, Any]) -> str:
    adres = html_etiketlerini_temizle(istasyon.get("adres", ""))
    return adres or "Adres Bilgisi Yok"

def arama_metni_normalize_et(metin: Any) -> str:
    text = str(metin or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.split())

def clean_id_uret(isim: str) -> str:
    raw = str(isim or "").strip()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_isim = normalized.encode("ascii", "ignore").decode("ascii").strip()
    safe = "".join(c for c in ascii_isim if c.isalnum() or c in (" ", "_", "-")).rstrip()
    safe = "_".join(safe.split())
    return safe[:80] if safe else hashlib.md5(raw.encode()).hexdigest()[:12]

def istasyon_id_getir(istasyon: Dict[str, Any]) -> str:
    for alan in ("id", "station_id", "place_id", "uid", "firebase_key", "key"):
        deger = istasyon.get(alan)
        if deger not in (None, ""):
            return str(deger).strip()
    isim = str(istasyon.get("isim") or istasyon.get("name") or "bilinmeyen_istasyon").strip()
    enlem = str(istasyon.get("enlem") or istasyon.get("lat") or "").strip()
    boylam = str(istasyon.get("boylam") or istasyon.get("lon") or istasyon.get("lng") or "").strip()
    fallback = f"{isim}_{enlem}_{boylam}".strip("_")
    return fallback or "bilinmeyen_istasyon"

def auth_uid_hash_getir() -> str:
    uid = str(st.session_state.get("auth_uid", "")).strip()
    return hashlib.sha256(uid.encode()).hexdigest()[:16] if uid else ""

def hiz_sayisi_ayikla(hiz: Any) -> float:
    hiz_val = str(hiz or "").replace(",", ".")
    rakam = re.search(r"(\d+(?:\.\d+)?)", hiz_val)
    return float(rakam.group(1)) if rakam else 0.0

def fiyat_sayisi_ayikla(fiyat: Any) -> float:
    fiyat_val = str(fiyat or "").replace(",", ".")
    rakam = re.search(r"(\d+(?:\.\d+)?)", fiyat_val)
    return float(rakam.group(1)) if rakam else 9999.0

def acik_24_saat_mi(istasyon: Dict[str, Any]) -> bool:
    metin = " ".join(str(istasyon.get(k, "")) for k in ("saat", "saatler", "calisma_saatleri", "çalışma_saatleri", "opening_hours")).lower()
    return "24" in metin or "7/24" in metin or "24/7" in metin

def durum_metni_sadelestir(durum: Any) -> str:
    text = str(durum or "").strip()
    if "Sorunsuz" in text or "Uygun" in text: return "Uygun"
    if "Arızalı" in text or "Sorun" in text: return "Sorun bildirildi"
    if "Sıra" in text: return "Sıra var"
    if "Güncelleme" in text: return "Not"
    return text or "Bildirim"

def tahmini_sure_dk(tahmini_km: float) -> int:
    if tahmini_km <= 0: return 1
    return max(1, int(round((tahmini_km / ORTALAMA_SEYIR_HIZI_KMH) * 60)))

def varis_sarj_yuzdesi_hesapla(baslangic_sarj: int, batarya_kwh: float, tuketim_kwh_100km: float, tahmini_km: float) -> float:
    if batarya_kwh <= 0: return 0.0
    harcanan_yuzde = (tahmini_km * tuketim_kwh_100km / 100.0) / batarya_kwh * 100.0
    return max(0.0, min(100.0, baslangic_sarj - harcanan_yuzde))

def cache_temizle_guvenli(cache_fn: Any, *args: Any) -> None:
    try:
        cache_fn.clear(*args)
    except TypeError:
        cache_fn.clear()

def utc_simdi() -> datetime:
    return datetime.now(timezone.utc)

def utc_isoformat(deger: Optional[datetime] = None) -> str:
    dt = deger or utc_simdi()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")

def token_suresi_doldu_mu() -> bool:
    login_time_str = st.session_state.get("auth_login_time")
    if not login_time_str: return True
    try:
        gecen_dk = (utc_simdi() - yorum_tarihi_parse(login_time_str)).total_seconds() / 60
        return gecen_dk > TOKEN_OMUR_DK
    except Exception:
        return True

def yorum_gonderilebilir_mi() -> Tuple[bool, int]:
    son = st.session_state.get("son_yorum_zamani")
    if son is None: return True, 0
    son_zamani = son if isinstance(son, datetime) else yorum_tarihi_parse(str(son))
    if son_zamani.tzinfo is None:
        son_zamani = son_zamani.replace(tzinfo=timezone.utc)
    else:
        son_zamani = son_zamani.astimezone(timezone.utc)
    kalan = YORUM_BEKLEME_SURESI - int((utc_simdi() - son_zamani).total_seconds())
    return kalan <= 0, max(0, kalan)

def yorum_tarihi_parse(tarih_str: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(tarih_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)

def mesafe_hesapla(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
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
    if not isinstance(ist, dict): return None
    try:
        isim = str(ist.get("isim", "")).strip()
        enlem, boylam = float(ist.get("enlem")), float(ist.get("boylam"))
        if not isim or not konum_gecerli_mi(enlem, boylam): return None

        yeni = dict(ist)
        yeni["isim"], yeni["enlem"], yeni["boylam"] = isim, enlem, boylam
        yeni.setdefault("hiz", "Bilinmiyor")
        yeni["adres"] = adres_metni_getir(yeni)
        yeni.setdefault("operator", yeni.get("operatör", "Bilinmiyor"))
        yeni.setdefault("soket", "Bilinmiyor")
        yeni.setdefault("fiyat", "Bilinmiyor")
        yeni["_station_key"] = clean_id_uret(istasyon_id_getir(yeni))
        yeni["_search_text"] = arama_metni_normalize_et(f"{yeni.get('isim', '')} {yeni.get('adres', '')} {yeni.get('operator', '')}")
        yeni["_soket_upper"] = str(yeni.get("soket", "")).upper()
        yeni["_hiz_sayi"] = hiz_sayisi_ayikla(yeni.get("hiz", ""))
        yeni["_fiyat_sayi"] = fiyat_sayisi_ayikla(yeni.get("fiyat", ""))
        yeni["_acik_24_saat"] = acik_24_saat_mi(yeni)
        return yeni
    except Exception:
        return None

def ariza_skoru_hesapla(yorumlar: List[Dict[str, Any]]) -> Dict[str, Any]:
    simdi = utc_simdi()
    baslangic = simdi - timedelta(hours=ARIZA_GECERLILIK_SAATI)
    aktif_yorumlar = [y for y in yorumlar if yorum_tarihi_parse(y.get("tarih", "")) >= baslangic]

    arizali = sum(1 for y in aktif_yorumlar if any(k in str(y.get("durum", "")) for k in ("Arızalı", "Sorun")))
    sorunsuz = sum(1 for y in aktif_yorumlar if any(k in str(y.get("durum", "")) for k in ("Sorunsuz", "Uygun")))
    skor = arizali - sorunsuz

    if skor >= ARIZA_RISK_ESIGI:
        durum, etiket = "riskli", f"Arıza riski bildirildi ({arizali}/{len(aktif_yorumlar)})"
    elif aktif_yorumlar:
        durum, etiket = "aktif", "Son bildirimler olumlu"
    else:
        durum, etiket = "belirsiz", "Canlı uygunluk verisi yok"

    return {
        "skor": skor, "durum": durum, "etiket": etiket, "arizali": arizali, "sorunsuz": sorunsuz,
        "aktif_yorum_sayisi": len(aktif_yorumlar),
        "son_bildirim_tarihi": utc_isoformat(max((yorum_tarihi_parse(y.get("tarih", "")) for y in aktif_yorumlar), default=datetime.min.replace(tzinfo=timezone.utc))) if aktif_yorumlar else "",
    }

def yorumlardan_durum_ozeti_uret(yorumlar: List[Dict[str, Any]]) -> Dict[str, Any]:
    sirali = sorted(yorumlar, key=lambda x: yorum_tarihi_parse(x.get("tarih", "")), reverse=True)
    ariza = ariza_skoru_hesapla(sirali)
    ariza["son_yorumlar"] = sirali[:MAX_SON_YORUM]
    return ariza

def durum_ozeti_fallback() -> Dict[str, Any]:
    return {"skor": 0, "durum": "belirsiz", "etiket": "Canlı uygunluk verisi yok", "arizali": 0, "sorunsuz": 0, "aktif_yorum_sayisi": 0, "son_bildirim_tarihi": "", "son_yorumlar": []}
