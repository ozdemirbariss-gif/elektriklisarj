import math
import unicodedata
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


TAHMIN_VARSAYILAN_OLASILIK = 0.58


def _normalize(metin: Any) -> str:
    text = str(metin or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.split())


def _tarih_parse(tarih: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(tarih).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _bildirim_sinifi_getir(yorum: Dict[str, Any]) -> str:
    metin = _normalize(f"{yorum.get('durum', '')} {yorum.get('yorum', '')}")
    olumlu_guclu = ("sorunsuz", "sorun yok", "uygun", "bos", "musait", "arizasiz")
    olumsuz = ("sorun", "ariza", "arizali", "calismiyor", "dolu", "sira", "bekleme", "risk")
    olumlu = ("aktif",)

    if any(kelime in metin for kelime in olumlu_guclu):
        return "bos"
    if any(kelime in metin for kelime in olumsuz):
        return "mesgul"
    if any(kelime in metin for kelime in olumlu):
        return "bos"
    return "belirsiz"


def _yas_agirligi(tarih: datetime, simdi: datetime) -> float:
    gun = max(0.0, (simdi - tarih).total_seconds() / 86400.0)
    return max(0.08, math.exp(-gun / 21.0))


def _saat_benzerligi(tarih: datetime, hedef_zaman: datetime) -> float:
    saat_farki = abs(tarih.hour - hedef_zaman.hour)
    saat_farki = min(saat_farki, 24 - saat_farki)
    if saat_farki == 0:
        saat_skoru = 1.0
    elif saat_farki == 1:
        saat_skoru = 0.72
    elif saat_farki == 2:
        saat_skoru = 0.38
    else:
        saat_skoru = 0.0

    gun_skoru = 1.0 if tarih.weekday() == hedef_zaman.weekday() else 0.46
    return saat_skoru * gun_skoru


def _oran(olumlu: float, toplam: float) -> Optional[float]:
    if toplam <= 0:
        return None
    return olumlu / toplam


def _guven_seviyesi(skor: float) -> str:
    if skor >= 0.66:
        return "yuksek"
    if skor >= 0.34:
        return "orta"
    return "dusuk"


def bosluk_tahmini_hesapla(
    yorumlar: Iterable[Dict[str, Any]],
    hedef_zaman: Optional[datetime] = None,
    simdi: Optional[datetime] = None,
) -> Dict[str, Any]:
    simdi = simdi or datetime.now()
    hedef_zaman = hedef_zaman or simdi

    genel_toplam = 0.0
    genel_bos = 0.0
    saat_toplam = 0.0
    saat_bos = 0.0
    son_toplam = 0.0
    son_bos = 0.0
    ornek_sayisi = 0
    son_bildirim: Optional[datetime] = None

    for yorum in yorumlar:
        if not isinstance(yorum, dict):
            continue

        sinif = _bildirim_sinifi_getir(yorum)
        if sinif == "belirsiz":
            continue

        tarih = _tarih_parse(yorum.get("tarih"))
        if tarih is None or tarih > simdi:
            continue

        bos_mu = 1.0 if sinif == "bos" else 0.0
        yas_agirligi = _yas_agirligi(tarih, simdi)
        saat_agirligi = yas_agirligi * _saat_benzerligi(tarih, hedef_zaman)
        saat_farki = (simdi - tarih).total_seconds() / 3600.0
        son_agirlik = yas_agirligi if saat_farki <= 6 else 0.0

        genel_toplam += yas_agirligi
        genel_bos += yas_agirligi * bos_mu
        saat_toplam += saat_agirligi
        saat_bos += saat_agirligi * bos_mu
        son_toplam += son_agirlik
        son_bos += son_agirlik * bos_mu
        ornek_sayisi += 1
        son_bildirim = max(son_bildirim, tarih) if son_bildirim else tarih

    genel_oran = _oran(genel_bos, genel_toplam)
    saat_oran = _oran(saat_bos, saat_toplam)
    son_oran = _oran(son_bos, son_toplam)

    parcala: List[Tuple[float, float]] = [(TAHMIN_VARSAYILAN_OLASILIK, 0.28)]
    if genel_oran is not None:
        parcala.append((genel_oran, min(0.30, 0.10 + genel_toplam / 20.0)))
    if saat_oran is not None:
        parcala.append((saat_oran, min(0.32, 0.12 + saat_toplam / 8.0)))
    if son_oran is not None:
        parcala.append((son_oran, min(0.22, 0.10 + son_toplam / 5.0)))

    agirlik_toplami = sum(agirlik for _, agirlik in parcala)
    olasilik = sum(deger * agirlik for deger, agirlik in parcala) / agirlik_toplami
    guven_skoru = min(1.0, (genel_toplam / 18.0) * 0.34 + (saat_toplam / 6.0) * 0.42 + (son_toplam / 3.0) * 0.24)

    if ornek_sayisi < 2 or guven_skoru < 0.18:
        seviye = "belirsiz"
    elif olasilik >= 0.72:
        seviye = "yuksek"
    elif olasilik >= 0.52:
        seviye = "orta"
    else:
        seviye = "dusuk"

    yuzde = int(round(max(0.0, min(1.0, olasilik)) * 100))
    hedef_saat = hedef_zaman.strftime("%H:%M")
    return {
        "olasilik": yuzde,
        "seviye": seviye,
        "guven": _guven_seviyesi(guven_skoru),
        "guven_skoru": round(guven_skoru, 3),
        "ornek_sayisi": ornek_sayisi,
        "hedef_saat": hedef_saat,
        "son_bildirim": son_bildirim.isoformat(timespec="seconds") if son_bildirim else "",
        "metin": f"Bugun {hedef_saat} civari bos olma ihtimali %{yuzde}.",
    }


def tahmin_skoru_getir(tahmin: Optional[Dict[str, Any]]) -> int:
    if not tahmin or tahmin.get("seviye") == "belirsiz":
        return 0

    olasilik = float(tahmin.get("olasilik", 58)) / 100.0
    guven = max(0.30, float(tahmin.get("guven_skoru", 0.0) or 0.0))
    skor = (olasilik - 0.54) * 24.0 * guven
    return max(-7, min(9, int(round(skor))))


def tahmin_rozetleri_getir(tahmin: Optional[Dict[str, Any]]) -> List[Tuple[str, str]]:
    if not tahmin:
        return []

    seviye = str(tahmin.get("seviye", "belirsiz"))
    if seviye == "yuksek":
        return [("Boşluk ihtimali yüksek", "sb-chip-good")]
    if seviye == "orta":
        return [("Boşluk ihtimali orta", "sb-chip-info")]
    if seviye == "dusuk":
        return [("Yoğun olabilir", "sb-chip-warn")]
    return []
