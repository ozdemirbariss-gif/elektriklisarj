import os
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests

from .common import (
    Istasyon,
    bool_deger_mi,
    ilk_dolu_deger,
    listeyi_coz,
    metin,
    standart_istasyon_uret,
)


DEFAULT_URL = "https://www.chargeiq.com.tr/api/stations"
DEFAULT_TIMEOUT_S = 15
DEFAULT_MAX_PAGES = 20
NEXT_KEYS = ("next", "next_url", "nextUrl", "next_page_url", "nextPageUrl")


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


def chargeiq_normalize_et(istasyon: Dict[str, Any]) -> Optional[Istasyon]:
    enlem = ilk_dolu_deger(istasyon.get("latitude"), istasyon.get("lat"), istasyon.get("enlem"))
    boylam = ilk_dolu_deger(
        istasyon.get("longitude"),
        istasyon.get("lng"),
        istasyon.get("lon"),
        istasyon.get("boylam"),
    )
    ham_id = ilk_dolu_deger(
        istasyon.get("id"),
        istasyon.get("station_id"),
        istasyon.get("stationId"),
        istasyon.get("station_code"),
        istasyon.get("stationCode"),
        istasyon.get("code"),
        istasyon.get("uuid"),
    )

    return standart_istasyon_uret(
        kaynak="chargeiq",
        ham_id=ham_id,
        isim=ilk_dolu_deger(
            istasyon.get("station_name"),
            istasyon.get("stationName"),
            istasyon.get("name"),
            istasyon.get("title"),
            istasyon.get("isim"),
        ),
        adres=ilk_dolu_deger(
            istasyon.get("address"),
            istasyon.get("full_address"),
            istasyon.get("fullAddress"),
            istasyon.get("adres"),
        ),
        enlem=enlem,
        boylam=boylam,
        hiz=hiz_coz(istasyon),
        operator=ilk_dolu_deger(istasyon.get("operator"), istasyon.get("brand"), istasyon.get("provider"), "ChargeIQ"),
        soket=ilk_dolu_deger(
            istasyon.get("socket"),
            istasyon.get("connector"),
            istasyon.get("connector_type"),
            istasyon.get("connectorType"),
            istasyon.get("soket"),
        ),
        fiyat=ilk_dolu_deger(istasyon.get("price"), istasyon.get("tariff"), istasyon.get("fiyat")),
    )


def chargeiq_istasyonlarini_getir() -> List[Istasyon]:
    url = os.getenv("CHARGEIQ_STATIONS_URL", DEFAULT_URL).strip() or DEFAULT_URL
    timeout_s = int(os.getenv("CHARGEIQ_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))
    max_pages = int(os.getenv("CHARGEIQ_MAX_PAGES", str(DEFAULT_MAX_PAGES)))

    session = requests.Session()
    headers = headers_getir()
    temiz_veri: List[Istasyon] = []
    gorulen_idler = set()
    mevcut_url = url
    sayfa = 1

    while mevcut_url and sayfa <= max_pages:
        response = session.get(mevcut_url, headers=headers, timeout=timeout_s)
        if response.status_code in (401, 403):
            print(f"chargeiq: erişim reddedildi ({response.status_code}); kaynak atlanıyor.")
            return temiz_veri
        if response.status_code != 200:
            print(f"chargeiq: HTTP {response.status_code}; kaynak atlanıyor.")
            return temiz_veri

        ham_veri = response.json()
        istasyon_listesi = listeyi_coz(ham_veri)
        if not istasyon_listesi:
            break

        sayfa_oncesi_toplam = len(temiz_veri)
        for ham_istasyon in istasyon_listesi:
            if not isinstance(ham_istasyon, dict):
                continue
            normalized = chargeiq_normalize_et(ham_istasyon)
            if not normalized or normalized["id"] in gorulen_idler:
                continue
            gorulen_idler.add(normalized["id"])
            temiz_veri.append(normalized)

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

    return temiz_veri
