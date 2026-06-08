import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests


DEFAULT_URL = "https://www.chargeiq.com.tr/api/stations"
DEFAULT_OUTPUT = "istasyonlar.json"
DEFAULT_TIMEOUT_S = 15
DEFAULT_MAX_PAGES = 20

LIST_KEYS = ("data", "stations", "items", "results", "result")
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


def stabil_id_uret(istasyon: Dict[str, Any], enlem: float, boylam: float, sira: int) -> str:
    api_id = ilk_dolu_deger(
        istasyon.get("id"),
        istasyon.get("station_id"),
        istasyon.get("stationId"),
        istasyon.get("station_code"),
        istasyon.get("stationCode"),
        istasyon.get("code"),
        istasyon.get("uuid"),
    )
    if api_id is not None:
        return f"chargeiq_{metin(api_id)}"

    isim = metin(ilk_dolu_deger(istasyon.get("station_name"), istasyon.get("name"), istasyon.get("isim")))
    adres = metin(ilk_dolu_deger(istasyon.get("address"), istasyon.get("adres")))
    seed = f"{isim}|{adres}|{enlem:.6f}|{boylam:.6f}"
    if not seed.strip("|"):
        seed = f"chargeiq_sira_{sira}"
    return "chargeiq_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def hiz_coz(istasyon: Dict[str, Any]) -> str:
    guc = ilk_dolu_deger(
        istasyon.get("power_kw"),
        istasyon.get("powerKw"),
        istasyon.get("power"),
        istasyon.get("hiz"),
    )
    if guc is not None:
        guc_str = metin(guc)
        if guc_str.lower().endswith("kw"):
            return guc_str
        return f"{guc_str} kW"
    return "Hızlı (DC)" if bool_deger_mi(istasyon.get("is_fast")) else "Standart (AC)"


def istasyon_normalize_et(istasyon: Dict[str, Any], sira: int) -> Optional[Dict[str, Any]]:
    if not isinstance(istasyon, dict):
        return None

    enlem = ilk_dolu_deger(istasyon.get("latitude"), istasyon.get("lat"), istasyon.get("enlem"))
    boylam = ilk_dolu_deger(
        istasyon.get("longitude"),
        istasyon.get("lng"),
        istasyon.get("lon"),
        istasyon.get("boylam"),
    )
    if not konum_gecerli_mi(enlem, boylam):
        return None

    enlem_f = floata_cevir(enlem)
    boylam_f = floata_cevir(boylam)
    if enlem_f is None or boylam_f is None:
        return None

    return {
        "id": stabil_id_uret(istasyon, enlem_f, boylam_f, sira),
        "isim": metin(
            ilk_dolu_deger(
                istasyon.get("station_name"),
                istasyon.get("stationName"),
                istasyon.get("name"),
                istasyon.get("title"),
                istasyon.get("isim"),
            ),
            "Şarj İstasyonu",
        ),
        "adres": metin(
            ilk_dolu_deger(
                istasyon.get("address"),
                istasyon.get("full_address"),
                istasyon.get("fullAddress"),
                istasyon.get("adres"),
            ),
            "Adres Bilgisi Yok",
        ),
        "enlem": enlem_f,
        "boylam": boylam_f,
        "hiz": hiz_coz(istasyon),
        "operator": metin(
            ilk_dolu_deger(istasyon.get("operator"), istasyon.get("brand"), istasyon.get("provider")),
            "ChargeIQ",
        ),
        "soket": metin(
            ilk_dolu_deger(
                istasyon.get("socket"),
                istasyon.get("connector"),
                istasyon.get("connector_type"),
                istasyon.get("connectorType"),
                istasyon.get("soket"),
            ),
            "Bilinmiyor",
        ),
        "fiyat": metin(
            ilk_dolu_deger(istasyon.get("price"), istasyon.get("tariff"), istasyon.get("fiyat")),
            "Bilinmiyor",
        ),
        "kaynak": "chargeiq",
        "guncelleme_tarihi": simdi_utc_iso(),
    }


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


def sonraki_url_getir(ham_veri: Any, mevcut_url: str) -> Optional[str]:
    if not isinstance(ham_veri, dict):
        return None

    for anahtar in NEXT_KEYS:
        deger = ham_veri.get(anahtar)
        if isinstance(deger, str) and deger.strip():
            return urljoin(mevcut_url, deger.strip())

    links = ham_veri.get("links")
    if isinstance(links, dict):
        next_link = links.get("next")
        if isinstance(next_link, str) and next_link.strip():
            return urljoin(mevcut_url, next_link.strip())
        if isinstance(next_link, dict):
            href = next_link.get("href")
            if isinstance(href, str) and href.strip():
                return urljoin(mevcut_url, href.strip())

    return None


def sayfa_paramli_url(url: str, sayfa: int) -> str:
    page_param = os.getenv("CHARGEIQ_PAGE_PARAM", "").strip()
    if not page_param:
        return ""

    parcalar = urlsplit(url)
    query = dict(parse_qsl(parcalar.query, keep_blank_values=True))
    query[page_param] = str(sayfa)
    return urlunsplit((parcalar.scheme, parcalar.netloc, parcalar.path, urlencode(query), parcalar.fragment))


def headers_getir() -> Dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    authorization = os.getenv("CHARGEIQ_AUTHORIZATION", "").strip()
    cookie = os.getenv("CHARGEIQ_COOKIE", "").strip()
    api_key = os.getenv("CHARGEIQ_API_KEY", "").strip()

    if authorization:
        headers["Authorization"] = authorization
    if cookie:
        headers["Cookie"] = cookie
    if api_key:
        headers["X-API-Key"] = api_key

    return headers


def atomik_json_yaz(veri: List[Dict[str, Any]], dosya_yolu: Path) -> None:
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
            json.dump(veri, f, ensure_ascii=False, indent=2)
            f.write("\n")

        os.replace(tmp_path, dosya_yolu)
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def istasyonlari_kaziyici() -> None:
    print("⏳ Şarj ağı sunucusuna bağlanılıyor...")

    url = os.getenv("CHARGEIQ_STATIONS_URL", DEFAULT_URL).strip() or DEFAULT_URL
    cikti_yolu = Path(os.getenv("ISTASYON_OUTPUT", DEFAULT_OUTPUT).strip() or DEFAULT_OUTPUT)
    timeout_s = int(os.getenv("CHARGEIQ_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))
    max_pages = int(os.getenv("CHARGEIQ_MAX_PAGES", str(DEFAULT_MAX_PAGES)))

    session = requests.Session()
    headers = headers_getir()
    temiz_veri: List[Dict[str, Any]] = []
    gorulen_idler = set()
    mevcut_url = url
    sayfa = 1

    try:
        while mevcut_url and sayfa <= max_pages:
            response = session.get(mevcut_url, headers=headers, timeout=timeout_s)

            if response.status_code in (401, 403):
                print(
                    f"⛔ Erişim reddedildi (Durum Kodu: {response.status_code}). "
                    "CHARGEIQ_AUTHORIZATION veya CHARGEIQ_COOKIE gerekebilir."
                )
                return

            if response.status_code != 200:
                print(f"❌ Sunucu hata döndürdü. Durum Kodu: {response.status_code}")
                return

            try:
                ham_veri = response.json()
            except ValueError:
                print("⚠️ Sunucu JSON olmayan bir yanıt döndürdü.")
                return

            istasyon_listesi = listeyi_coz(ham_veri)
            if not istasyon_listesi:
                print("⚠️ Beklenmeyen veri formatı! API çıktısını kontrol edin.")
                return

            sayfa_oncesi_toplam = len(temiz_veri)
            for sira, istasyon in enumerate(istasyon_listesi):
                try:
                    normalized = istasyon_normalize_et(istasyon, len(temiz_veri) + sira)
                    if not normalized:
                        continue

                    istasyon_id = normalized["id"]
                    if istasyon_id in gorulen_idler:
                        continue

                    gorulen_idler.add(istasyon_id)
                    temiz_veri.append(normalized)
                except Exception as e:
                    print(f"⚠️ Bir istasyon atlandı: {e}")

            sonraki_url = sonraki_url_getir(ham_veri, mevcut_url)
            if sonraki_url and sonraki_url != mevcut_url:
                mevcut_url = sonraki_url
                sayfa += 1
                continue

            if len(temiz_veri) == sayfa_oncesi_toplam:
                break

            paramli_url = sayfa_paramli_url(url, sayfa + 1)
            if paramli_url:
                mevcut_url = paramli_url
                sayfa += 1
                continue

            break

        if not temiz_veri:
            print("⚠️ Geçerli koordinata sahip istasyon bulunamadı.")
            return

        atomik_json_yaz(temiz_veri, cikti_yolu)
        print(f"✅ Veri başarıyla çekildi! Toplam {len(temiz_veri)} istasyon bulundu.")
        print(f"💾 '{cikti_yolu}' başarıyla güncellendi!")

    except requests.exceptions.Timeout:
        print("⏰ Bağlantı zaman aşımına uğradı. Sunucu yanıt vermiyor.")
    except requests.exceptions.RequestException as e:
        print(f"💥 Bağlantı hatası: {e}")
    except Exception as e:
        print(f"💥 Beklenmeyen işleme hatası: {e}")


if __name__ == "__main__":
    istasyonlari_kaziyici()
