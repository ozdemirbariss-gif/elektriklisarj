from typing import Any, Dict, List, Tuple

from predictor import tahmin_rozetleri_getir


def kaynak_sayisi_getir(istasyon: Dict[str, Any]) -> int:
    kaynaklar = istasyon.get("kaynaklar")
    if isinstance(kaynaklar, list):
        return len({str(k).strip() for k in kaynaklar if str(k).strip()})
    return 1 if istasyon.get("kaynak") else 0


def fiyat_skoru_getir(istasyon: Dict[str, Any]) -> int:
    fiyat = float(istasyon.get("_fiyat_sayi", 9999.0))
    if fiyat >= 9999:
        return 4
    if fiyat <= 8:
        return 9
    if fiyat <= 12:
        return 7
    if fiyat <= 18:
        return 5
    return 3


def hiz_skoru_getir(istasyon: Dict[str, Any]) -> int:
    hiz = float(istasyon.get("_hiz_sayi", 0.0))
    if hiz >= 150:
        return 18
    if hiz >= 50:
        return 14
    if hiz >= 22:
        return 10
    if hiz >= 7:
        return 7
    return 4


def mesafe_skoru_getir(istasyon: Dict[str, Any]) -> int:
    mesafe = float(istasyon.get("Mesafe", 999.0))
    if mesafe <= 2:
        return 22
    if mesafe <= 5:
        return 20
    if mesafe <= 10:
        return 16
    if mesafe <= 20:
        return 11
    return max(4, int(12 - min(mesafe, 60) / 7))


def varis_sarji_skoru_getir(istasyon: Dict[str, Any]) -> int:
    varis = float(istasyon.get("VarisSarjYuzdesi", 0.0))
    if varis >= 25:
        return 13
    if varis >= 15:
        return 10
    if varis >= 8:
        return 6
    return 2


def durum_skoru_getir(istasyon: Dict[str, Any]) -> int:
    durum = str(istasyon.get("ArizaDurumu", "belirsiz"))
    if durum == "riskli":
        return 0
    if durum == "aktif":
        return 14
    return 8


def veri_skoru_getir(istasyon: Dict[str, Any]) -> int:
    guven = float(istasyon.get("guven_skoru", 0.62) or 0.62)
    kaynak_bonus = min(6, max(0, kaynak_sayisi_getir(istasyon) - 1) * 3)
    return min(15, int(round(guven * 9)) + kaynak_bonus)


def istasyon_skoru_hesapla(istasyon: Dict[str, Any]) -> int:
    skor = (
        mesafe_skoru_getir(istasyon)
        + hiz_skoru_getir(istasyon)
        + varis_sarji_skoru_getir(istasyon)
        + durum_skoru_getir(istasyon)
        + fiyat_skoru_getir(istasyon)
        + veri_skoru_getir(istasyon)
        + int(istasyon.get("TahminSkoru", 0) or 0)
    )
    return max(1, min(100, int(round(skor))))


def istasyon_rozetleri_getir(istasyon: Dict[str, Any]) -> List[Tuple[str, str]]:
    rozetler: List[Tuple[str, str]] = []
    durum = str(istasyon.get("ArizaDurumu", "belirsiz"))
    hiz = float(istasyon.get("_hiz_sayi", 0.0))
    kaynak_sayisi = kaynak_sayisi_getir(istasyon)
    guven = float(istasyon.get("guven_skoru", 0.0) or 0.0)

    if durum == "riskli":
        rozetler.append(("Risk bildirildi", "sb-chip-risk"))
    elif durum == "aktif":
        rozetler.append(("Son bildirim olumlu", "sb-chip-good"))
    else:
        rozetler.append(("Canlı veri yok", "sb-chip-warn"))

    rozetler.extend(tahmin_rozetleri_getir(istasyon.get("BoslukTahmini")))

    if float(istasyon.get("VarisSarjYuzdesi", 0.0)) >= 15:
        rozetler.append(("Varış güvenli", "sb-chip-good"))
    else:
        rozetler.append(("Varış düşük", "sb-chip-warn"))

    if hiz >= 150:
        rozetler.append(("Hızlı DC", "sb-chip-info"))
    elif hiz >= 50:
        rozetler.append(("DC", "sb-chip-info"))

    if kaynak_sayisi > 1:
        rozetler.append((f"{kaynak_sayisi} kaynak doğruladı", "sb-chip-good"))
    elif guven >= 0.8:
        rozetler.append(("Yüksek veri güveni", "sb-chip-good"))

    return rozetler[:5]
