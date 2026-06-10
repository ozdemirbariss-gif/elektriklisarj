import os
from typing import Any, Dict, List, Optional

import requests

from .common import Istasyon, ilk_dolu_deger, listeyi_coz, standart_istasyon_uret


def nested_get(data: Dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def alan_getir(data: Dict[str, Any], env_name: str, defaults: List[str]) -> Any:
    paths = os.getenv(env_name, "").strip()
    adaylar = [x.strip() for x in paths.split(",") if x.strip()] or defaults
    for path in adaylar:
        value = nested_get(data, path)
        if value is not None and str(value).strip() != "":
            return value
    return None


def ekstra_operator_normalize_et(item: Dict[str, Any], kaynak_adi: str) -> Optional[Istasyon]:
    return standart_istasyon_uret(
        kaynak="extra_operator",
        ham_id=alan_getir(item, "EXTRA_OPERATOR_ID_FIELDS", ["id", "station_id", "stationId", "uuid", "code"]),
        isim=alan_getir(item, "EXTRA_OPERATOR_NAME_FIELDS", ["name", "title", "station_name", "stationName", "isim"]),
        adres=alan_getir(item, "EXTRA_OPERATOR_ADDRESS_FIELDS", ["address", "full_address", "fullAddress", "adres"]),
        enlem=alan_getir(item, "EXTRA_OPERATOR_LAT_FIELDS", ["latitude", "lat", "enlem", "location.lat"]),
        boylam=alan_getir(item, "EXTRA_OPERATOR_LON_FIELDS", ["longitude", "lng", "lon", "boylam", "location.lng"]),
        hiz=alan_getir(item, "EXTRA_OPERATOR_POWER_FIELDS", ["power_kw", "powerKw", "power", "hiz"]),
        operator=alan_getir(item, "EXTRA_OPERATOR_OPERATOR_FIELDS", ["operator", "brand", "provider"]) or kaynak_adi,
        soket=alan_getir(item, "EXTRA_OPERATOR_SOCKET_FIELDS", ["socket", "connector", "connector_type", "connectorType", "soket"]),
        fiyat=alan_getir(item, "EXTRA_OPERATOR_PRICE_FIELDS", ["price", "tariff", "fiyat"]),
        ekstra={"extra_operator_name": kaynak_adi},
    )


def ekstra_operator_istasyonlarini_getir() -> List[Istasyon]:
    url = os.getenv("EXTRA_OPERATOR_STATIONS_URL", "").strip()
    if not url:
        return []

    kaynak_adi = os.getenv("EXTRA_OPERATOR_NAME", "Ek Operatör").strip() or "Ek Operatör"
    timeout_s = int(os.getenv("EXTRA_OPERATOR_TIMEOUT_S", "20"))
    headers = {
        "User-Agent": "SarjBul/2.1",
        "Accept": "application/json",
    }

    authorization = os.getenv("EXTRA_OPERATOR_AUTHORIZATION", "").strip()
    cookie = os.getenv("EXTRA_OPERATOR_COOKIE", "").strip()
    api_key = os.getenv("EXTRA_OPERATOR_API_KEY", "").strip()
    if authorization:
        headers["Authorization"] = authorization
    if cookie:
        headers["Cookie"] = cookie
    if api_key:
        headers["X-API-Key"] = api_key

    response = requests.get(url, headers=headers, timeout=timeout_s)
    if response.status_code in (401, 403):
        print(f"extra_operator: erişim reddedildi ({response.status_code}); kaynak atlanıyor.")
        return []
    if response.status_code != 200:
        print(f"extra_operator: HTTP {response.status_code}; kaynak atlanıyor.")
        return []

    ham_liste = listeyi_coz(response.json())
    sonuc: List[Istasyon] = []
    gorulen_idler = set()
    for item in ham_liste:
        if not isinstance(item, dict):
            continue
        normalized = ekstra_operator_normalize_et(item, kaynak_adi)
        if not normalized or normalized["id"] in gorulen_idler:
            continue
        gorulen_idler.add(normalized["id"])
        sonuc.append(normalized)
    return sonuc
