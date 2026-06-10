import argparse
import os
from pathlib import Path
from typing import Callable, Dict, List

from scrapers.chargeiq import chargeiq_istasyonlarini_getir
from scrapers.common import Istasyon, atomik_json_yaz, duplicate_temizle
from scrapers.openchargemap import openchargemap_istasyonlarini_getir
from scrapers.operator_api import ekstra_operator_istasyonlarini_getir
from scrapers.osm import osm_istasyonlarini_getir


DEFAULT_OUTPUT = "istasyonlar.json"


SourceFn = Callable[[], List[Istasyon]]


def env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "hayir", "hayır", "no", "off"}


def kaynaklari_getir() -> Dict[str, SourceFn]:
    kaynaklar: Dict[str, SourceFn] = {}

    if env_bool("ENABLE_CHARGEIQ", True):
        kaynaklar["chargeiq"] = chargeiq_istasyonlarini_getir

    if env_bool("ENABLE_OSM", True):
        kaynaklar["osm"] = osm_istasyonlarini_getir

    if env_bool("ENABLE_OPENCHARGEMAP", True):
        kaynaklar["openchargemap"] = openchargemap_istasyonlarini_getir

    if env_bool("ENABLE_EXTRA_OPERATOR", True) and os.getenv("EXTRA_OPERATOR_STATIONS_URL"):
        kaynaklar["extra_operator"] = ekstra_operator_istasyonlarini_getir

    return kaynaklar


def kaynak_sec(kaynaklar: Dict[str, SourceFn], secimler: str) -> Dict[str, SourceFn]:
    if not secimler:
        return kaynaklar

    istenenler = {x.strip().lower() for x in secimler.split(",") if x.strip()}
    return {ad: fn for ad, fn in kaynaklar.items() if ad in istenenler}


def istasyonlari_kaziyici(kaynak_secimi: str = "", output: str = DEFAULT_OUTPUT) -> None:
    secili_kaynaklar = kaynak_sec(kaynaklari_getir(), kaynak_secimi)
    if not secili_kaynaklar:
        print("Aktif kaynak bulunamadı. ENABLE_* ayarlarını veya --sources değerini kontrol edin.")
        return

    tum_istasyonlar: List[Istasyon] = []

    print("Çok kaynaklı istasyon toplama başladı.")
    for kaynak_adi, kaynak_fn in secili_kaynaklar.items():
        try:
            print(f"{kaynak_adi}: veri alınıyor...")
            istasyonlar = kaynak_fn()
            tum_istasyonlar.extend(istasyonlar)
            print(f"{kaynak_adi}: {len(istasyonlar)} istasyon alındı.")
        except Exception as exc:
            print(f"{kaynak_adi}: kaynak atlandı. Hata: {exc}")

    if not tum_istasyonlar:
        print("Hiç istasyon alınamadı; mevcut çıktı dosyası değiştirilmedi.")
        return

    mesafe_m = int(os.getenv("DEDUP_DISTANCE_M", "120"))
    temiz_istasyonlar = duplicate_temizle(tum_istasyonlar, mesafe_m=mesafe_m)

    atomik_json_yaz(temiz_istasyonlar, Path(output))
    print(f"Toplam ham kayıt: {len(tum_istasyonlar)}")
    print(f"Duplicate sonrası: {len(temiz_istasyonlar)}")
    print(f"Çıktı güncellendi: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Şarj istasyonlarını çok kaynaktan toplar.")
    parser.add_argument(
        "--sources",
        default=os.getenv("SCRAPER_SOURCES", ""),
        help="Virgülle ayrılmış kaynak listesi: chargeiq,osm,openchargemap,extra_operator",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("ISTASYON_OUTPUT", DEFAULT_OUTPUT),
        help="Yazılacak JSON dosyası.",
    )
    args = parser.parse_args()
    istasyonlari_kaziyici(kaynak_secimi=args.sources, output=args.output)


if __name__ == "__main__":
    main()
