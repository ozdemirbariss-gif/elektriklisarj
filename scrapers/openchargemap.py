import os
from typing import Any, Dict, List, Optional

import requests

from .common import Istasyon, ilk_dolu_deger, metin, standart_istasyon_uret


DEFAULT_URL = "https://api.openchargemap.io/v3/poi/"
DEFAULT_TIMEOUT_S = 25


def baglanti_ozetleri(connections: List[Dict[str, Any]]) -> Dict[str, str]:
    soketler = []
    gucler = []
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        conn_type = conn.get("ConnectionType") or {}
        title = conn_type.get("Title") if isinstance(conn_type, dict) else None
        if title:
            soketler.append(str(title))

        power_kw = conn.get("PowerKW")
        try:
            if power_kw is not None:
                gucler.append(float(power_kw))
        except Exception:
            pass

    return {
        "soket": ", ".join(dict.fromkeys(soketler)) or "Bilinmiyor",
        "hiz": f"{max(gucler):g} kW" if gucler else "Bilinmiyor",
    }


def adres_ozeti(address: Dict[str, Any]) -> str:
    parcalar = [
        address.get("AddressLine1"),
        address.get("AddressLine2"),
        address.get("Town"),
        address.get("StateOrProvince"),
        address.get("Postcode"),
    ]
    return metin(" ".join(str(x).strip() for x in parcalar if x), "Adres Bilgisi Yok")


def openchargemap_normalize_et(item: Dict[str, Any]) -> Optional[Istasyon]:
    address = item.get("AddressInfo") or {}
    operator_info = item.get("OperatorInfo") or {}
    usage_type = item.get("UsageType") or {}
    status_type = item.get("StatusType") or {}
    connections = item.get("Connections") or []
    baglanti = baglanti_ozetleri(connections if isinstance(connections, list) else [])

    return standart_istasyon_uret(
        kaynak="openchargemap",
        ham_id=item.get("ID"),
        isim=ilk_dolu_deger(address.get("Title"), address.get("AddressLine1")),
        adres=adres_ozeti(address),
        enlem=address.get("Latitude"),
        boylam=address.get("Longitude"),
        hiz=baglanti["hiz"],
        operator=ilk_dolu_deger(operator_info.get("Title"), "OpenChargeMap"),
        soket=baglanti["soket"],
        fiyat=ilk_dolu_deger(item.get("UsageCost"), usage_type.get("Title")),
        ekstra={
            "usage_type": usage_type.get("Title"),
            "status": status_type.get("Title"),
            "openchargemap_uuid": item.get("UUID"),
        },
    )


def openchargemap_istasyonlarini_getir() -> List[Istasyon]:
    url = os.getenv("OPENCHARGEMAP_URL", DEFAULT_URL).strip() or DEFAULT_URL
    api_key = os.getenv("OPENCHARGEMAP_API_KEY", "").strip()
    timeout_s = int(os.getenv("OPENCHARGEMAP_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))
    max_results = int(os.getenv("OPENCHARGEMAP_MAX_RESULTS", "5000"))
    country_code = os.getenv("OPENCHARGEMAP_COUNTRY_CODE", "TR").strip().upper() or "TR"

    headers = {"User-Agent": "SarjBul/2.1", "Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    response = requests.get(
        url,
        params={
            "output": "json",
            "countrycode": country_code,
            "maxresults": max_results,
            "compact": "false",
            "verbose": "false",
        },
        headers=headers,
        timeout=timeout_s,
    )
    if response.status_code in (401, 403):
        print("openchargemap: API anahtarı gerekebilir; kaynak atlanıyor.")
        return []
    if response.status_code != 200:
        print(f"openchargemap: HTTP {response.status_code}; kaynak atlanıyor.")
        return []

    sonuc: List[Istasyon] = []
    gorulen_idler = set()
    for item in response.json():
        if not isinstance(item, dict):
            continue
        normalized = openchargemap_normalize_et(item)
        if not normalized or normalized["id"] in gorulen_idler:
            continue
        gorulen_idler.add(normalized["id"])
        sonuc.append(normalized)
    return sonuc
