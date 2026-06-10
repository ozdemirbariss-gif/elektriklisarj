import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


Istasyon = Dict[str, Any]


SOURCE_PRIORITY = {
    "chargeiq": 90,
    "extra_operator": 86,
    "openchargemap": 80,
    "osm": 70,
}


LIST_KEYS = ("data", "stations", "items", "results", "result", "records", "locations")
NEXT_KEYS = ("next", "next_url", "nextUrl", "next_page_url", "nextPageUrl")


def simdi_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ilk_dolu_deger(*degerler: Any) -> Any:
    for deger in degerler:
        if deger is not None and str(deger).strip() != "":
            return deger
    return None


def metin(deger: Any, varsayilan: str = "") -> str:
    secilen = ilk_dolu_deger(deger, varsayilan)
    return str(secilen).strip()


def floata_cevir(deger: Any) -> Optional[float]:
    try:
        return float(str(deger).strip().replace(",", "."))
    except Exception:
        return None


def konum_gecerli_mi(enlem: Any, boylam: Any) -> bool:
    enlem_f = floata_cevir(enlem)
    boylam_f = floata_cevir(boylam)
    if enlem_f is None or boylam_f is None:
        return False
    return -90 <= enlem_f <= 90 and -180 <= boylam_f <= 180


def bool_deger_mi(deger: Any) -> bool:
    if isinstance(deger, bool):
        return deger
    if isinstance(deger, (int, float)):
        return deger != 0
    return str(deger or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "evet",
        "dc",
        "fast",
        "hizli",
        "hızlı",
    }


def temiz_tokenlar(metin_degeri: Any) -> List[str]:
    raw = str(metin_degeri or "").lower()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^a-z0-9\s]", " ", ascii_text)
    stop = {
        "sarj",
        "sarz",
        "charging",
        "charger",
        "station",
        "istasyon",
        "istasyonu",
        "ev",
        "dc",
        "ac",
        "tr",
        "turkey",
    }
    return [x for x in ascii_text.split() if len(x) > 1 and x not in stop]


def temiz_slug(deger: Any) -> str:
    tokenlar = temiz_tokenlar(deger)
    return "_".join(tokenlar)[:80] or "istasyon"


def stabil_id_uret(kaynak: str, ham_id: Any, isim: Any, enlem: float, boylam: float) -> str:
    if ham_id is not None and str(ham_id).strip():
        safe_id = temiz_slug(str(ham_id)) or hashlib.sha1(str(ham_id).encode("utf-8")).hexdigest()[:12]
        return f"{kaynak}_{safe_id}"

    seed = f"{kaynak}|{isim}|{enlem:.5f}|{boylam:.5f}"
    return f"{kaynak}_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"


def mesafe_metre(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def guven_skoru_hesapla(istasyon: Istasyon) -> float:
    skor = 0.25
    for alan, puan in (
        ("isim", 0.12),
        ("adres", 0.10),
        ("enlem", 0.12),
        ("boylam", 0.12),
        ("operator", 0.10),
        ("soket", 0.10),
        ("hiz", 0.08),
        ("fiyat", 0.04),
    ):
        deger = istasyon.get(alan)
        if deger not in (None, "", "Bilinmiyor", "Adres Bilgisi Yok"):
            skor += puan

    kaynaklar = istasyon.get("kaynaklar") or [istasyon.get("kaynak")]
    if isinstance(kaynaklar, list) and len(kaynaklar) > 1:
        skor += 0.12

    kaynak = str(istasyon.get("kaynak") or "").lower()
    skor += SOURCE_PRIORITY.get(kaynak, 60) / 1000
    return round(min(1.0, skor), 3)


def standart_istasyon_uret(
    *,
    kaynak: str,
    ham_id: Any,
    isim: Any,
    adres: Any,
    enlem: Any,
    boylam: Any,
    hiz: Any = "Bilinmiyor",
    operator: Any = "Bilinmiyor",
    soket: Any = "Bilinmiyor",
    fiyat: Any = "Bilinmiyor",
    ekstra: Optional[Dict[str, Any]] = None,
) -> Optional[Istasyon]:
    if not konum_gecerli_mi(enlem, boylam):
        return None

    enlem_f = floata_cevir(enlem)
    boylam_f = floata_cevir(boylam)
    if enlem_f is None or boylam_f is None:
        return None

    istasyon: Istasyon = {
        "id": stabil_id_uret(kaynak, ham_id, isim, enlem_f, boylam_f),
        "isim": metin(isim, "Şarj İstasyonu"),
        "adres": metin(adres, "Adres Bilgisi Yok"),
        "enlem": enlem_f,
        "boylam": boylam_f,
        "hiz": metin(hiz, "Bilinmiyor"),
        "operator": metin(operator, "Bilinmiyor"),
        "soket": metin(soket, "Bilinmiyor"),
        "fiyat": metin(fiyat, "Bilinmiyor"),
        "kaynak": kaynak,
        "kaynaklar": [kaynak],
        "source_ids": {kaynak: str(ham_id or "")},
        "guncelleme_tarihi": simdi_utc_iso(),
    }
    if ekstra:
        istasyon.update({k: v for k, v in ekstra.items() if v not in (None, "")})
    istasyon["guven_skoru"] = guven_skoru_hesapla(istasyon)
    return istasyon


def listeyi_coz(ham_veri: Any) -> List[Any]:
    if isinstance(ham_veri, list):
        return ham_veri
    if not isinstance(ham_veri, dict):
        return []

    for anahtar in LIST_KEYS:
        deger = ham_veri.get(anahtar)
        if isinstance(deger, list):
            return deger
        if isinstance(deger, dict):
            ic_liste = listeyi_coz(deger)
            if ic_liste:
                return ic_liste

    for deger in ham_veri.values():
        if isinstance(deger, (list, dict)):
            ic_liste = listeyi_coz(deger)
            if ic_liste:
                return ic_liste
    return []


def nokta_anahtari(istasyon: Istasyon, grid: float = 0.002) -> Tuple[int, int]:
    return (
        int(float(istasyon["enlem"]) / grid),
        int(float(istasyon["boylam"]) / grid),
    )


def token_benzer_mi(a: Istasyon, b: Istasyon) -> bool:
    a_tokens = set(temiz_tokenlar(f"{a.get('isim', '')} {a.get('operator', '')}"))
    b_tokens = set(temiz_tokenlar(f"{b.get('isim', '')} {b.get('operator', '')}"))
    if not a_tokens or not b_tokens:
        return False
    ortak = a_tokens & b_tokens
    return len(ortak) >= 1 or (len(ortak) / max(len(a_tokens), len(b_tokens))) >= 0.34


def duplicate_mi(a: Istasyon, b: Istasyon, mesafe_m: int) -> bool:
    uzaklik = mesafe_metre(float(a["enlem"]), float(a["boylam"]), float(b["enlem"]), float(b["boylam"]))
    if uzaklik <= min(35, mesafe_m):
        return True
    return uzaklik <= mesafe_m and token_benzer_mi(a, b)


def deger_dolu_mu(deger: Any) -> bool:
    return deger not in (None, "", "Bilinmiyor", "Adres Bilgisi Yok", [])


def istasyonlari_birlestir(ana: Istasyon, yeni: Istasyon) -> Istasyon:
    kaynaklar = list(dict.fromkeys([*(ana.get("kaynaklar") or [ana.get("kaynak")]), *(yeni.get("kaynaklar") or [yeni.get("kaynak")])]))
    ana["kaynaklar"] = [str(k) for k in kaynaklar if k]
    ana["kaynak"] = str(ana.get("kaynak") or ana["kaynaklar"][0])

    source_ids = {}
    if isinstance(ana.get("source_ids"), dict):
        source_ids.update(ana["source_ids"])
    if isinstance(yeni.get("source_ids"), dict):
        source_ids.update(yeni["source_ids"])
    ana["source_ids"] = source_ids

    for alan in ("isim", "adres", "operator", "soket", "hiz", "fiyat"):
        if not deger_dolu_mu(ana.get(alan)) and deger_dolu_mu(yeni.get(alan)):
            ana[alan] = yeni[alan]

    for alan in ("opening_hours", "access", "capacity"):
        if not deger_dolu_mu(ana.get(alan)) and deger_dolu_mu(yeni.get(alan)):
            ana[alan] = yeni[alan]

    ana["guven_skoru"] = guven_skoru_hesapla(ana)
    ana["guncelleme_tarihi"] = simdi_utc_iso()
    return ana


def kaynak_onceligi(istasyon: Istasyon) -> Tuple[int, float]:
    kaynak = str(istasyon.get("kaynak") or "").lower()
    return (SOURCE_PRIORITY.get(kaynak, 50), float(istasyon.get("guven_skoru", 0.0)))


def duplicate_temizle(istasyonlar: Sequence[Istasyon], mesafe_m: int = 120) -> List[Istasyon]:
    sirali = sorted(istasyonlar, key=kaynak_onceligi, reverse=True)
    gruplar: Dict[Tuple[int, int], List[Istasyon]] = {}
    sonuc: List[Istasyon] = []

    for istasyon in sirali:
        if not konum_gecerli_mi(istasyon.get("enlem"), istasyon.get("boylam")):
            continue

        lat_key, lon_key = nokta_anahtari(istasyon)
        komsu_anahtarlar = [
            (lat_key + dx, lon_key + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        ]

        eslesen: Optional[Istasyon] = None
        for anahtar in komsu_anahtarlar:
            for aday in gruplar.get(anahtar, []):
                if duplicate_mi(aday, istasyon, mesafe_m):
                    eslesen = aday
                    break
            if eslesen is not None:
                break

        if eslesen is None:
            sonuc.append(istasyon)
            gruplar.setdefault((lat_key, lon_key), []).append(istasyon)
        else:
            istasyonlari_birlestir(eslesen, istasyon)

    return sorted(sonuc, key=lambda x: (str(x.get("operator", "")), str(x.get("isim", ""))))


def atomik_json_yaz(veri: Iterable[Istasyon], dosya_yolu: Path) -> None:
    dosya_yolu.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(dosya_yolu.parent),
            delete=False,
            suffix=".tmp",
        ) as f:
            tmp_path = Path(f.name)
            json.dump(list(veri), f, ensure_ascii=False, indent=2)
            f.write("\n")

        os.replace(tmp_path, dosya_yolu)
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
