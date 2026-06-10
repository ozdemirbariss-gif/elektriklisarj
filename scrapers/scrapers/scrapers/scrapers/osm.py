import os
from typing import Any, Dict, List, Optional

import requests

from .common import Istasyon, ilk_dolu_deger, metin, standart_istasyon_uret


DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_TIMEOUT_S = 35


def osm_sorgusu_uret(country_code: str) -> str:
    return f"""
    [out:json][timeout:{int(os.getenv("OSM_OVERPASS_QUERY_TIMEOUT_S", "30"))}];
    area["ISO3166-1"="{country_code}"][admin_level=2]->.searchArea;
    (
      node["amenity"="charging_station"](area.searchArea);
      way["amenity"="charging_station"](area.searchArea);
      relation["amenity"="charging_station"](area.searchArea);
    );
    out center tags;
    """


def adres_uret(tags: Dict[str, Any]) -> str:
    parcalar = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:district"),
        tags.get("addr:city"),
        tags.get("addr:province"),
    ]
    adres = " ".join(str(x).strip() for x in parcalar if x)
    return metin(ilk_dolu_deger(tags.get("addr:full"), adres), "Adres Bilgisi Yok")


def soket_ozeti(tags: Dict[str, Any]) -> str:
    socket_names = {
        "socket:type2": "Type 2",
        "socket:type2_combo": "CCS",
        "socket:ccs": "CCS",
        "socket:chademo": "CHAdeMO",
        "socket:schuko": "Schuko",
        "socket:tesla_supercharger": "Tesla Supercharger",
        "socket:tesla_supercharger_ccs": "Tesla Supercharger CCS",
    }
    bulunanlar = []
    for tag, label in socket_names.items():
        deger = tags.get(tag)
        if deger and str(deger).strip().lower() not in {"0", "false", "no"}:
            bulunanlar.append(label)
    return ", ".join(dict.fromkeys(bulunanlar)) or "Bilinmiyor"


def hiz_ozeti(tags: Dict[str, Any]) -> str:
    guc = ilk_dolu_deger(
        tags.get("max_power"),
        tags.get("charging_station:output"),
        tags.get("socket:type2:output"),
        tags.get("socket:type2_combo:output"),
        tags.get("socket:ccs:output"),
        tags.get("socket:chademo:output"),
    )
    if guc is None:
        return "Bilinmiyor"
    guc_str = metin(guc)
    return guc_str if "w" in guc_str.lower() else f"{guc_str} kW"


def fiyat_ozeti(tags: Dict[str, Any]) -> str:
    fee = str(tags.get("fee", "")).strip().lower()
    if fee in {"no", "0", "false"}:
        return "Ücretsiz olabilir"
    if fee in {"yes", "true", "1"}:
        return "Ücretli"
    return metin(ilk_dolu_deger(tags.get("charge"), tags.get("payment:app")), "Bilinmiyor")


def osm_eleman_normalize_et(eleman: Dict[str, Any]) -> Optional[Istasyon]:
    tags = eleman.get("tags") or {}
    center = eleman.get("center") or {}
    enlem = ilk_dolu_deger(eleman.get("lat"), center.get("lat"))
    boylam = ilk_dolu_deger(eleman.get("lon"), center.get("lon"))
    operator = ilk_dolu_deger(tags.get("operator"), tags.get("network"), tags.get("brand"))
    isim = ilk_dolu_deger(tags.get("name"), operator, "Şarj İstasyonu")

    return standart_istasyon_uret(
        kaynak="osm",
        ham_id=eleman.get("id"),
        isim=isim,
        adres=adres_uret(tags),
        enlem=enlem,
        boylam=boylam,
        hiz=hiz_ozeti(tags),
        operator=operator,
        soket=soket_ozeti(tags),
        fiyat=fiyat_ozeti(tags),
        ekstra={
            "opening_hours": tags.get("opening_hours"),
            "access": tags.get("access"),
            "capacity": tags.get("capacity"),
            "osm_type": eleman.get("type"),
        },
    )


def osm_istasyonlarini_getir() -> List[Istasyon]:
    url = os.getenv("OSM_OVERPASS_URL", DEFAULT_OVERPASS_URL).strip() or DEFAULT_OVERPASS_URL
    country_code = os.getenv("OSM_COUNTRY_CODE", "TR").strip().upper() or "TR"
    timeout_s = int(os.getenv("OSM_OVERPASS_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))

    response = requests.post(
        url,
        data={"data": osm_sorgusu_uret(country_code)},
        headers={"User-Agent": "SarjBul/2.1 (+https://streamlit.io)", "Accept": "application/json"},
        timeout=timeout_s,
    )
    if response.status_code != 200:
        print(f"osm: HTTP {response.status_code}; kaynak atlanıyor.")
        return []

    ham_veri = response.json()
    sonuc: List[Istasyon] = []
    gorulen_idler = set()
    for eleman in ham_veri.get("elements", []):
        if not isinstance(eleman, dict):
            continue
        normalized = osm_eleman_normalize_et(eleman)
        if not normalized or normalized["id"] in gorulen_idler:
            continue
        gorulen_idler.add(normalized["id"])
        sonuc.append(normalized)
    return sonuc
