import importlib
import json
import math
import streamlit as st
import folium
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple
import streamlit.components.v1 as components
from streamlit_js_eval import get_geolocation
from streamlit_folium import st_folium

import i18n as i18n_module

EXPECTED_TRANSLATION_SCHEMA_VERSION = 7
if getattr(i18n_module, "TRANSLATION_SCHEMA_VERSION", 0) < EXPECTED_TRANSLATION_SCHEMA_VERSION:
    importlib.reload(i18n_module)

from config import (
    sentry_init, load_css, logger,
    ARAC_KATALOGU, HIZ_ESIK_MAP, KONUM_DOGRULAMA_ESIGI_KM,
    FIREBASE_ENABLED, YAKIN_CEVRE_MIN_M,
    YAKIN_CEVRE_VARSAYILAN_M, YAKIN_CEVRE_MAX_M, YAKIN_CEVRE_ADIM_M
)
from i18n import get_language, localize_text, set_language, t
from utils import (
    guvenli_metin, arama_metni_normalize_et, clean_id_uret, istasyon_id_getir,
    auth_uid_hash_getir, tahmini_sure_dk, varis_sarj_yuzdesi_hesapla, 
    mesafe_hesapla, tahmini_yol_mesafesi_km, konum_gecerli_mi,
    durum_metni_sadelestir, durum_ozeti_fallback, utc_simdi, utc_isoformat
)
from services import (
    firebase_login, firebase_register, firebase_sifre_sifirla, oturumu_temizle,
    istasyonlari_yukle, durum_ozetleri_getir, tahmin_yorumlari_getir,
    favorileri_getir, favori_guncelle, yorum_gonder, yakin_cevre_getir,
    oturum_bilgilerini_kaydet, oturum_gecerli_tut
)
from predictor import bosluk_tahmini_hesapla, tahmin_skoru_getir
from scoring import istasyon_rozetleri_getir, istasyon_skoru_hesapla
from waiting_lounge import bekleme_salonu_ciz


HAM_ADAY_LIMITI = 240
ZENGIN_ADAY_LIMITI = 80
TAHMIN_GECMISI_LIMITI = 24
TAHMIN_GECMISI_YORUM_LIMITI = 120
VARSAYILAN_ADAY_YARICAP_KM = 80.0
MAX_ADAY_YARICAP_KM = 900.0
KONUM_JS_TTL_SN = 120


def kisa_deger(deger: Any, varsayilan: str = "Bilinmiyor", max_len: int = 80) -> str:
    text = str(deger or "").strip() or localize_text(varsayilan)
    return guvenli_metin(text, max_len)


def kisa_duz_metin(deger: Any, varsayilan: str = "Bilinmiyor", max_len: int = 120) -> str:
    text = str(deger or "").strip() or localize_text(varsayilan)
    return text[:max_len]


def secili_arac_getir() -> str:
    varsayilan = list(ARAC_KATALOGU.keys())[0]
    secili = st.session_state.get("secilen_arac")
    return secili if secili in ARAC_KATALOGU else varsayilan


def tarayici_konumu_okunmali_mi() -> bool:
    if st.session_state.get("konum_kaynagi") != KONUM_KAYNAGI_TARAYICI:
        return True
    if st.session_state.get("last_valid_lat") is None or st.session_state.get("last_valid_lon") is None:
        return True

    son_okuma = st.session_state.get("browser_location_checked_at")
    if not son_okuma:
        return True
    try:
        son = datetime.fromisoformat(str(son_okuma).replace("Z", "+00:00"))
    except ValueError:
        return True
    return (utc_simdi() - son).total_seconds() > KONUM_JS_TTL_SN


def bildirim_goster(metin: str, basarili: bool = True) -> None:
    onek = t("status.ok") if basarili else t("status.error")
    st.markdown(
        f'<div class="sb-live-region" role="status" aria-live="polite">{guvenli_metin(metin, 180)}</div>',
        unsafe_allow_html=True,
    )
    st.toast(f"{onek}: {metin}")


def dil_secimi_degisti(widget_key: str) -> None:
    set_language(str(st.session_state.get(widget_key, "TR")).lower())


def dil_secici_ciz(widget_key: str) -> None:
    secili = get_language().upper()
    if st.session_state.get(widget_key) != secili:
        st.session_state[widget_key] = secili
    st.segmented_control(
        t("language.label"),
        ["TR", "EN"],
        key=widget_key,
        on_change=dil_secimi_degisti,
        args=(widget_key,),
        label_visibility="collapsed",
        width="stretch",
    )


def rota_sonucunu_sifirla() -> None:
    st.session_state["rota_goster"] = False


def bekleme_salonunu_ac() -> None:
    st.session_state["bekleme_salonu_goster"] = True
    st.session_state["rota_goster"] = False
    st.session_state["account_panel_open"] = False
    st.session_state["bekleme_salonu_scroll_nonce"] = st.session_state.get("bekleme_salonu_scroll_nonce", 0) + 1


def bekleme_salonunu_kapat() -> None:
    st.session_state["bekleme_salonu_goster"] = False


FILTRE_SESSION_KEYS = (
    "niyet",
    "guvenlik_marji",
    "menzil_filtresi",
    "arama_metni",
    "soket_filtreleri",
    "hiz_filtresi",
    "operator_filtreleri",
    "sadece_24_saat",
    "ayar_yaricap",
    "haritayi_goster",
)


def filtreleri_sifirla() -> None:
    for key in FILTRE_SESSION_KEYS:
        st.session_state.pop(key, None)
    st.session_state["rota_goster"] = False


def aktif_filtre_sayisi_getir() -> int:
    aktif = 0
    aktif += str(st.session_state.get("niyet", "Dengeli")) != "Dengeli"
    aktif += int(st.session_state.get("guvenlik_marji", 25)) != 25
    aktif += bool(st.session_state.get("menzil_filtresi", True)) is False
    aktif += bool(str(st.session_state.get("arama_metni", "")).strip())
    aktif += bool(st.session_state.get("soket_filtreleri", []))
    aktif += str(st.session_state.get("hiz_filtresi", "Tümü")) != "Tümü"
    aktif += bool(st.session_state.get("operator_filtreleri", []))
    aktif += bool(st.session_state.get("sadece_24_saat", False))
    aktif += int(st.session_state.get("ayar_yaricap", YAKIN_CEVRE_VARSAYILAN_M)) != YAKIN_CEVRE_VARSAYILAN_M
    aktif += bool(st.session_state.get("haritayi_goster", False))
    return int(aktif)


def veri_guncelleme_metni_ciz() -> None:
    son_yukleme = st.session_state.get("istasyon_son_yukleme")
    if not son_yukleme:
        return
    try:
        yukleme_dt = datetime.fromisoformat(str(son_yukleme).replace("Z", "+00:00"))
        gecen_dk = max(0, int((utc_simdi() - yukleme_dt).total_seconds() // 60))
    except (TypeError, ValueError) as e:
        logger.warning("Veri güncelleme zamanı okunamadı: %s", e)
        return

    gecen = t("data.just_now") if gecen_dk < 1 else t("data.minutes_ago", minutes=gecen_dk)
    st.markdown(
        f'<div class="sb-data-freshness">{guvenli_metin(t("data.updated", time=gecen), 80)}</div>',
        unsafe_allow_html=True,
    )


def istasyon_hata_state_ciz() -> None:
    detay = guvenli_metin(t("data.unavailable_detail"), 180)
    st.markdown(
        f"""
        <div class="sb-empty-state sb-empty-state-error">
            <strong>{t("data.unavailable")}</strong>
            <span>{detay}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(t("data.refresh"), key="refresh_station_data", type="primary", use_container_width=True):
        try:
            istasyonlari_yukle.clear()
        except Exception as e:
            logger.warning("İstasyon cache temizlenemedi: %s", e, exc_info=True)
        st.session_state.pop("istasyon_yukleme_hatasi", None)
        st.rerun()


def uygulama_akisini_hazirla() -> None:
    st.session_state.setdefault("language", "tr")
    st.session_state.setdefault("sb_access_granted", False)
    st.session_state.setdefault("sb_guest_mode", False)
    st.session_state.setdefault("rota_goster", False)
    st.session_state.setdefault("bekleme_salonu_goster", False)

    if "auth_token" in st.session_state:
        st.session_state["sb_access_granted"] = True
        st.session_state["sb_guest_mode"] = False


def uygulama_girisini_ac(misafir: bool = False) -> None:
    st.session_state["sb_access_granted"] = True
    st.session_state["sb_guest_mode"] = misafir
    st.session_state["rota_goster"] = False
    st.session_state["bekleme_salonu_goster"] = False


def sosyal_giris_butonlari_ciz() -> None:
    st.markdown('<div class="sb-social-icons" aria-hidden="true"></div>', unsafe_allow_html=True)
    sosyal1, sosyal2, sosyal3 = st.columns(3)
    sosyal_butonlar = (
        (sosyal1, "Google", "social_google"),
        (sosyal2, "Apple", "social_apple"),
        (sosyal3, "Twitter", "social_twitter"),
    )
    for kolon, metin, anahtar in sosyal_butonlar:
        with kolon:
            if st.button(metin, key=anahtar, help=t("auth.social_help", provider=metin), use_container_width=True):
                bildirim_goster(t("auth.social_soon", provider=metin), basarili=False)


def auth_form_ciz(caller_context: str, entry_context: bool = False) -> None:
    prefix = caller_context.strip().replace(" ", "_") or "auth"
    secenekler = ("login", "register", "reset")
    mod_anahtari = f"{prefix}_auth_mode"
    st.session_state.setdefault(mod_anahtari, "login")
    auth_mode = st.segmented_control(
        t("auth.mode_label"),
        secenekler,
        key=mod_anahtari,
        format_func=lambda value: t(f"auth.{value}"),
        label_visibility="collapsed",
        width="stretch",
    )

    if auth_mode == "login":
        if not FIREBASE_ENABLED:
            st.info(t("auth.firebase_login_disabled"))
            st.button(t("auth.continue"), use_container_width=True, key=f"{prefix}_login_disabled", disabled=True)
        else:
            email = st.text_input(t("auth.email"), key=f"{prefix}_login_email", placeholder=t("auth.email_placeholder"))
            password = st.text_input(t("auth.password"), type="password", key=f"{prefix}_login_password", placeholder=t("auth.password_placeholder"))
            if st.button(t("auth.continue"), use_container_width=True, key=f"{prefix}_login_btn", type="primary"):
                user_data = firebase_login(email, password)
                if user_data and oturum_bilgilerini_kaydet(user_data):
                    if entry_context:
                        uygulama_girisini_ac(misafir=False)
                    st.rerun()
                bildirim_goster(t("auth.login_failed"), basarili=False)

    if auth_mode == "register":
        if not FIREBASE_ENABLED:
            st.info(t("auth.firebase_register_disabled"))
        else:
            reg_email = st.text_input(t("auth.new_email"), key=f"{prefix}_register_email")
            reg_password = st.text_input(t("auth.new_password"), type="password", key=f"{prefix}_register_password")
            if st.button(t("auth.register_action"), use_container_width=True, key=f"{prefix}_register_btn"):
                user_data = firebase_register(reg_email, reg_password)
                if user_data and oturum_bilgilerini_kaydet(user_data):
                    if entry_context:
                        uygulama_girisini_ac(misafir=False)
                    st.rerun()
                bildirim_goster(t("auth.register_failed"), basarili=False)

    if auth_mode == "reset":
        if not FIREBASE_ENABLED:
            st.info(t("auth.firebase_reset_disabled"))
        else:
            reset_email = st.text_input(t("auth.reset_email"), key=f"{prefix}_reset_email")
            if st.button(t("auth.reset_action"), use_container_width=True, key=f"{prefix}_reset_btn"):
                ok, msg = firebase_sifre_sifirla(reset_email)
                bildirim_goster(msg, ok)


def giris_formlari_ciz() -> None:
    st.markdown('<section class="sb-entry-panel">', unsafe_allow_html=True)
    auth_form_ciz("entry", entry_context=True)

    if st.button(t("auth.guest_continue"), key="guest_continue", use_container_width=True):
        uygulama_girisini_ac(misafir=True)
        st.rerun()

    st.markdown(f'<div class="sb-social-separator"><span>{t("auth.or")}</span></div>', unsafe_allow_html=True)
    sosyal_giris_butonlari_ciz()
    st.markdown('</section>', unsafe_allow_html=True)


def giris_ekrani_ciz() -> None:
    st.markdown('<div class="sb-entry-language">', unsafe_allow_html=True)
    dil_secici_ciz("language_entry")
    st.markdown('</div>', unsafe_allow_html=True)
    hero_subtitle = t("auth.hero_subtitle")
    subtitle_html = (
        f"<p>{guvenli_metin(hero_subtitle, 140)}</p>"
        if hero_subtitle and hero_subtitle != "auth.hero_subtitle"
        else ""
    )
    st.markdown(
        f"""
        <section class="sb-entry-hero">
            <div class="sb-entry-mark"><span></span>ŞarjBul</div>
            <h1>{t("auth.hero_title")}</h1>
            {subtitle_html}
        </section>
        """,
        unsafe_allow_html=True,
    )

    giris_formlari_ciz()


def ust_bilgi_ciz() -> None:
    oturumlu = "auth_token" in st.session_state
    rota_aktif = st.session_state.get("rota_goster") is True
    bekleme_aktif = st.session_state.get("bekleme_salonu_goster") is True
    geri_yardimi = (
        t("nav.back_vehicle")
        if rota_aktif
        else t("nav.back_home")
        if bekleme_aktif
        else t("nav.back_entry")
    )

    st.markdown('<div class="sb-top-nav-anchor" aria-hidden="true"></div>', unsafe_allow_html=True)
    if st.button("←", key="top_nav_back", help=geri_yardimi):
        if rota_aktif or bekleme_aktif:
            st.session_state["rota_goster"] = False
            st.session_state["bekleme_salonu_goster"] = False
            st.rerun()
        if oturumlu:
            oturumu_temizle()
        st.session_state["sb_access_granted"] = False
        st.session_state["sb_guest_mode"] = False
        st.session_state["rota_goster"] = False
        st.session_state["bekleme_salonu_goster"] = False
        st.rerun()


def ana_mod_secici_ciz() -> None:
    st.markdown(
        f"""
        <section class="sb-home-intro">
            <div class="sb-kicker">{t("home.kicker")}</div>
            <h1>{t("home.title")}</h1>
            <p>{t("home.subtitle")}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def hizli_tercih_uygula(niyet: str, hiz: str = "Tümü") -> None:
    st.session_state["niyet"] = niyet
    st.session_state["hiz_filtresi"] = hiz
    st.session_state["haritayi_goster"] = False
    st.session_state["rota_goster"] = False
    st.session_state["bekleme_salonu_goster"] = False


def hizli_islemler_ciz() -> None:
    st.markdown(
        f'<div class="sb-quick-heading"><strong>{t("home.quick_title")}</strong><span>{t("home.quick_hint")}</span></div>',
        unsafe_allow_html=True,
    )
    yakin_col, hizli_col, uygun_col = st.columns(3, gap="small")
    niyet = str(st.session_state.get("niyet", "Dengeli"))
    hiz = str(st.session_state.get("hiz_filtresi", "Tümü"))

    with yakin_col:
        if st.button(
            t("home.quick_near"),
            key="quick_near",
            icon=":material/near_me:",
            type="primary" if niyet == "Yakın" else "secondary",
            use_container_width=True,
        ):
            hizli_tercih_uygula("Yakın")
            st.rerun()

    with hizli_col:
        if st.button(
            t("home.quick_fast"),
            key="quick_fast",
            icon=":material/bolt:",
            type="primary" if niyet == "Hızlı" and hiz == "Hızlı DC (≥150 kW)" else "secondary",
            use_container_width=True,
        ):
            hizli_tercih_uygula("Hızlı", "Hızlı DC (≥150 kW)")
            st.rerun()

    with uygun_col:
        if st.button(
            t("home.quick_value"),
            key="quick_value",
            icon=":material/savings:",
            type="primary" if niyet == "Ekonomik" else "secondary",
            use_container_width=True,
        ):
            hizli_tercih_uygula("Ekonomik")
            st.rerun()


def arac_secimi_degisti() -> None:
    secilen = st.session_state.get("secilen_arac")
    if secilen in ARAC_KATALOGU:
        st.session_state["batarya_kwh"] = float(ARAC_KATALOGU[secilen]["batarya"])
        st.session_state["tuketim_kwh"] = float(ARAC_KATALOGU[secilen]["tuketim"])
    rota_sonucunu_sifirla()


def sarj_gostergesi_ciz(sarj_yuzdesi: int) -> None:
    yuzde = max(1, min(100, int(sarj_yuzdesi)))
    aci = yuzde * 3.6
    durum = t("charge.low") if yuzde < 25 else t("charge.ready") if yuzde < 75 else t("charge.long_range")
    st.markdown(
        f"""
        <div class="sb-charge-visual" style="--charge-angle: {aci:.1f}deg; --charge-width: {yuzde}%;">
            <div class="sb-charge-ring" role="img" aria-label="{t("charge.aria", percent=yuzde)}">
                <div class="sb-charge-ring-core">
                    <strong>%{yuzde}</strong>
                    <span>{t("charge.label")}</span>
                </div>
            </div>
            <div class="sb-charge-copy">
                <span>{t("charge.selected_level")}</span>
                <strong>{durum}</strong>
                <div class="sb-battery-shell" aria-hidden="true">
                    <div class="sb-battery-fill"></div>
                    <i></i>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def arac_katalogu_ciz(operator_secenekleri: List[str]) -> Tuple[
    str, float, int, float, int, str, int, List[str], str, List[str], bool, bool, bool, str
]:
    secilen_baslangic = secili_arac_getir()
    st.session_state.setdefault("secilen_arac", secilen_baslangic)

    st.markdown(
        f"""
        <section class="sb-catalog-panel" id="sarj-katalogu">
            <div class="sb-kicker">{t("catalog.kicker")}</div>
            <h2>{t("catalog.title")}</h2>
        </section>
        """,
        unsafe_allow_html=True,
    )

    secilen_arac = st.selectbox(
        t("catalog.vehicle"),
        list(ARAC_KATALOGU.keys()),
        key="secilen_arac",
        on_change=arac_secimi_degisti,
        format_func=lambda value: t("vehicle.manual") if value == "Özel Araç (Manuel)" else value,
    )
    v = ARAC_KATALOGU[secilen_arac]

    sarj_kwargs = {
        "label": t("catalog.charge_percent"),
        "min_value": 1,
        "max_value": 100,
        "key": "sarj_yuzdesi",
        "on_change": rota_sonucunu_sifirla,
    }
    if "sarj_yuzdesi" not in st.session_state:
        sarj_kwargs["value"] = 30
    with st.container(key="charge_level_panel"):
        sarj_yuzdesi = st.slider(**sarj_kwargs)
        sarj_gostergesi_ciz(sarj_yuzdesi)

    batarya_kwargs = {
        "label": t("catalog.capacity"),
        "min_value": 1.0,
        "max_value": 250.0,
        "key": "batarya_kwh",
        "on_change": rota_sonucunu_sifirla,
    }
    if "batarya_kwh" not in st.session_state:
        batarya_kwargs["value"] = float(v["batarya"])

    tuketim_kwargs = {
        "label": t("catalog.consumption"),
        "min_value": 5.0,
        "max_value": 40.0,
        "key": "tuketim_kwh",
        "on_change": rota_sonucunu_sifirla,
    }
    if "tuketim_kwh" not in st.session_state:
        tuketim_kwargs["value"] = float(v["tuketim"])

    with st.expander(t("catalog.advanced"), expanded=False):
        c1, c2 = st.columns(2)
        batarya = c1.number_input(**batarya_kwargs)
        tuketim = c2.number_input(**tuketim_kwargs)

    niyet = "Dengeli"
    ayar_yaricap = YAKIN_CEVRE_VARSAYILAN_M
    soket_filtreleri: List[str] = []
    hiz_filtresi = "Tümü"
    operator_filtreleri: List[str] = []
    sadece_24_saat = False
    haritayi_goster = False
    menzil_filtresi = True
    arama_metni = ""

    aktif_filtre_sayisi = aktif_filtre_sayisi_getir()
    filtre_basligi = (
        t("filters.title_active", count=aktif_filtre_sayisi)
        if aktif_filtre_sayisi
        else t("filters.title")
    )
    with st.expander(filtre_basligi, expanded=False):
        niyet = st.radio(
            t("filters.preference"),
            ["Dengeli", "Yakın", "Hızlı", "Ekonomik"],
            horizontal=True,
            key="niyet",
            on_change=rota_sonucunu_sifirla,
            format_func=lambda value: t({
                "Dengeli": "intent.balanced",
                "Yakın": "intent.near",
                "Hızlı": "intent.fast",
                "Ekonomik": "intent.economic",
            }[value]),
        )
        guvenlik_kwargs = {
            "label": t("filters.safety_margin"),
            "min_value": 10,
            "max_value": 50,
            "key": "guvenlik_marji",
            "on_change": rota_sonucunu_sifirla,
        }
        if "guvenlik_marji" not in st.session_state:
            guvenlik_kwargs["value"] = 25
        guvenlik_marji = st.slider(**guvenlik_kwargs)
        menzil_filtresi = st.checkbox(
            t("filters.range"),
            True,
            key="menzil_filtresi",
            on_change=rota_sonucunu_sifirla,
        )
        arama_metni = st.text_input(t("filters.search"), key="arama_metni", on_change=rota_sonucunu_sifirla)
        soket_filtreleri = st.multiselect(
            t("filters.socket"),
            ["CCS", "CHAdeMO", "Type 2", "Schuko", "GB/T"],
            key="soket_filtreleri",
            on_change=rota_sonucunu_sifirla,
        )
        hiz_filtresi = st.selectbox(
            t("filters.minimum_power"),
            ["Tümü", "AC (≥7 kW)", "DC (≥50 kW)", "Hızlı DC (≥150 kW)"],
            key="hiz_filtresi",
            on_change=rota_sonucunu_sifirla,
            format_func=lambda value: (
                t("filters.all") if value == "Tümü"
                else t("filters.fast_dc") if value == "Hızlı DC (≥150 kW)"
                else value
            ),
        )
        operator_filtreleri = st.multiselect(
            t("filters.operator"),
            operator_secenekleri,
            key="operator_filtreleri",
            on_change=rota_sonucunu_sifirla,
        )
        sadece_24_saat = st.checkbox(
            t("filters.open_24h"),
            key="sadece_24_saat",
            on_change=rota_sonucunu_sifirla,
        )
        ayar_yaricap = st.slider(
            t("filters.nearby_radius"),
            YAKIN_CEVRE_MIN_M,
            YAKIN_CEVRE_MAX_M,
            YAKIN_CEVRE_VARSAYILAN_M,
            YAKIN_CEVRE_ADIM_M,
            key="ayar_yaricap",
            on_change=rota_sonucunu_sifirla,
        )
        haritayi_goster = st.checkbox(t("filters.show_map"), key="haritayi_goster", on_change=rota_sonucunu_sifirla)

    guvenlik_marji = int(st.session_state.get("guvenlik_marji", 25))
    return (
        secilen_arac,
        float(batarya),
        int(sarj_yuzdesi),
        float(tuketim),
        guvenlik_marji,
        niyet,
        int(ayar_yaricap),
        soket_filtreleri,
        hiz_filtresi,
        operator_filtreleri,
        sadece_24_saat,
        haritayi_goster,
        menzil_filtresi,
        arama_metni,
    )


def arac_ayarlarini_sessiondan_getir() -> Tuple[
    str, float, int, float, int, str, int, List[str], str, List[str], bool, bool, bool, str
]:
    secilen_arac = secili_arac_getir()
    v = ARAC_KATALOGU[secilen_arac]
    return (
        secilen_arac,
        float(st.session_state.get("batarya_kwh", v["batarya"])),
        int(st.session_state.get("sarj_yuzdesi", 30)),
        float(st.session_state.get("tuketim_kwh", v["tuketim"])),
        int(st.session_state.get("guvenlik_marji", 25)),
        str(st.session_state.get("niyet", "Dengeli")),
        int(st.session_state.get("ayar_yaricap", YAKIN_CEVRE_VARSAYILAN_M)),
        list(st.session_state.get("soket_filtreleri", [])),
        str(st.session_state.get("hiz_filtresi", "Tümü")),
        list(st.session_state.get("operator_filtreleri", [])),
        bool(st.session_state.get("sadece_24_saat", False)),
        bool(st.session_state.get("haritayi_goster", False)),
        bool(st.session_state.get("menzil_filtresi", True)),
        str(st.session_state.get("arama_metni", "")),
    )
SABIT_KONUMLAR: Dict[str, Tuple[float, float]] = {
    "İstanbul (Kadıköy)": (40.9901, 29.0284),
    "İstanbul (Maslak)": (41.1082, 29.0195),
    "Ankara (Çankaya)": (39.9208, 32.8541),
    "İzmir (Alsancak)": (38.4374, 27.1422),
    "İzmir (Buca)": (38.3844, 27.1748),
    "Bursa (Nilüfer)": (40.2140, 28.9847),
    "Antalya (Muratpaşa)": (36.8841, 30.7056),
    "Muğla (Fethiye)": (36.6217, 29.1164),
    "Kocaeli (Gebze)": (40.8028, 29.4307),
    "Eskişehir (Odunpazarı)": (39.7667, 30.5256),
    "Konya (Selçuklu)": (37.9464, 32.4932),
    "Adana (Seyhan)": (36.9914, 35.3308),
    "Mersin (Yenişehir)": (36.8121, 34.6415),
    "Samsun (Atakum)": (41.3452, 36.2496),
}

KONUM_KAYNAGI_TARAYICI = "browser"
KONUM_KAYNAGI_MANUEL = "manual"


def konumu_sessiona_yaz(lat: float, lon: float, kaynak: str | None = None) -> Tuple[float, float]:
    if kaynak:
        st.session_state["konum_kaynagi"] = kaynak

    onceki_lat = st.session_state.get("last_valid_lat")
    onceki_lon = st.session_state.get("last_valid_lon")
    if konum_gecerli_mi(onceki_lat, onceki_lon):
        fark_km = mesafe_hesapla(float(onceki_lat), float(onceki_lon), lat, lon)
        if fark_km <= KONUM_DOGRULAMA_ESIGI_KM:
            return float(onceki_lat), float(onceki_lon)

    st.session_state.update({"last_valid_lat": lat, "last_valid_lon": lon})
    return lat, lon


def manuel_konum_degisti() -> None:
    manuel = str(st.session_state.get("manuel_konum_secimi", ""))
    if manuel not in SABIT_KONUMLAR:
        return
    secili_lat, secili_lon = SABIT_KONUMLAR[manuel]
    konumu_sessiona_yaz(secili_lat, secili_lon, KONUM_KAYNAGI_MANUEL)
    rota_sonucunu_sifirla()


def koordinat_girdisi_ciz() -> None:
    with st.expander(t("location.coordinates"), expanded=False):
        lat = st.number_input(
            t("location.latitude"),
            min_value=-90.0,
            max_value=90.0,
            value=39.0000,
            step=0.0001,
            format="%.6f",
            key="manual_latitude",
        )
        lon = st.number_input(
            t("location.longitude"),
            min_value=-180.0,
            max_value=180.0,
            value=35.0000,
            step=0.0001,
            format="%.6f",
            key="manual_longitude",
        )
        if st.button(t("location.use"), key="use_coordinates", use_container_width=True):
            if konum_gecerli_mi(lat, lon):
                konumu_sessiona_yaz(float(lat), float(lon), KONUM_KAYNAGI_MANUEL)
                rota_sonucunu_sifirla()
                st.rerun()
            else:
                bildirim_goster(t("location.invalid"), basarili=False)


def ana_konum_arama_ciz(konum_hazir: bool, user_lat: Any, user_lon: Any) -> None:
    if st.session_state.get("manuel_konum_secimi") == "Seçiniz...":
        st.session_state["manuel_konum_secimi"] = ""

    with st.container(key="home_location_search"):
        st.markdown(
            f"""
            <div class="sb-location-search-head">
                <span aria-hidden="true">⌖</span>
                <div><strong>{t("home.search_title")}</strong><small>{t("home.search_hint")}</small></div>
                <b>{t("home.now")}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.selectbox(
            t("home.search_label"),
            ["", *SABIT_KONUMLAR.keys()],
            key="manuel_konum_secimi",
            format_func=lambda value: t("home.search_placeholder") if not value else value,
            on_change=manuel_konum_degisti,
            label_visibility="collapsed",
        )

        if konum_hazir and konum_gecerli_mi(user_lat, user_lon):
            secili_yer = st.session_state.get("manuel_konum_secimi") or t("home.current_location")
            st.markdown(
                f"""
                <div class="sb-location-ready">
                    <span></span><strong>{guvenli_metin(secili_yer, 80)}</strong>
                    <small>{float(user_lat):.4f}, {float(user_lon):.4f}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

        koordinat_girdisi_ciz()


def harita_rengi_getir(skor: int) -> str:
    if skor >= 80:
        return "#C8FF2E"
    if skor >= 60:
        return "#0E1012"
    return "#9FE000"


def harita_popup_html_olustur(istasyon: Dict[str, Any]) -> str:
    isim = kisa_deger(istasyon.get("isim"), t("common.station"), 90)
    operator = kisa_deger(istasyon.get("operator"), t("common.operator_unknown"), 70)
    skor = int(istasyon.get("Skor", 0) or 0)
    mesafe = float(istasyon.get("Mesafe", 0.0) or 0.0)
    guc = localize_text(kisa_duz_metin(istasyon.get("hiz"), t("common.power_unknown"), 42))
    durum = localize_text(kisa_duz_metin(istasyon.get("ArizaEtiketi"), t("common.live_data_none"), 60))
    renk = harita_rengi_getir(skor)
    return f"""
        <div style="min-width:190px;background:#FFFFFF;border:1px solid rgba(14,16,18,0.28);border-radius:12px;box-shadow:0 18px 40px rgba(14,16,18,0.18);color:#0E1012;font-family:Inter,Arial,sans-serif;padding:12px;">
            <div style="font-size:14px;font-weight:800;line-height:1.2;margin-bottom:4px;">{isim}</div>
            <div style="font-size:12px;color:rgba(14,16,18,0.72);margin-bottom:8px;">{operator}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
                <div style="background:rgba(200,255,46,0.24);border:1px solid rgba(14,16,18,0.14);border-radius:8px;padding:6px;">
                    <div style="font-size:10px;color:rgba(14,16,18,0.72);font-weight:700;">{t("map.score")}</div>
                    <div style="font-size:16px;font-weight:850;color:{renk};">{skor}</div>
                </div>
                <div style="background:rgba(200,255,46,0.24);border:1px solid rgba(14,16,18,0.14);border-radius:8px;padding:6px;">
                    <div style="font-size:10px;color:rgba(14,16,18,0.72);font-weight:700;">{t("map.distance")}</div>
                    <div style="font-size:16px;font-weight:850;">{mesafe:.1f} km</div>
                </div>
            </div>
            <div style="font-size:12px;margin-top:8px;"><strong>{t("map.power")}:</strong> {guc}</div>
            <div style="font-size:12px;margin-top:3px;"><strong>{t("map.status")}:</strong> {durum}</div>
        </div>
    """


def harita_ciz(istasyonlar: List[Dict[str, Any]]) -> None:
    harita_verisi: List[Dict[str, Any]] = []
    for istasyon in istasyonlar:
        try:
            harita_verisi.append({**istasyon, "lat": float(istasyon["enlem"]), "lon": float(istasyon["boylam"])})
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Harita noktası çizilemedi: %s", e)

    if not harita_verisi:
        return

    merkez_lat = sum(i["lat"] for i in harita_verisi) / len(harita_verisi)
    merkez_lon = sum(i["lon"] for i in harita_verisi) / len(harita_verisi)
    harita = folium.Map(
        location=[merkez_lat, merkez_lon],
        zoom_start=11,
        tiles="CartoDB dark_matter",
        control_scale=True,
    )

    bounds = []
    for istasyon in harita_verisi:
        skor = int(istasyon.get("Skor", 0) or 0)
        isim = kisa_deger(istasyon.get("isim"), t("common.station"), 70)
        konum = [istasyon["lat"], istasyon["lon"]]
        bounds.append(konum)
        folium.CircleMarker(
            location=konum,
            radius=8 + min(6, max(0, skor) / 18),
            color=harita_rengi_getir(skor),
            weight=2,
            fill=True,
            fill_color=harita_rengi_getir(skor),
            fill_opacity=0.84,
            popup=folium.Popup(harita_popup_html_olustur(istasyon), max_width=280),
            tooltip=f"{isim} - {skor} {t('map.points')}",
        ).add_to(harita)

    if len(bounds) > 1:
        harita.fit_bounds(bounds, padding=(24, 24))

    st_folium(
        harita,
        height=360,
        use_container_width=True,
        returned_objects=[],
    )


def rozet_html(rozetler: List[Tuple[str, str]]) -> str:
    return "".join(
        f'<span class="sb-chip {css_class}">{guvenli_metin(metin, 40)}</span>'
        for metin, css_class in rozetler
    )


def istasyon_tahminini_guncelle(istasyon: Dict[str, Any], yorumlar: List[Dict[str, Any]]) -> None:
    hedef_zaman = utc_simdi() + timedelta(minutes=int(istasyon.get("TahminiSureDk", 0) or 0))
    tahmin = bosluk_tahmini_hesapla(yorumlar, hedef_zaman=hedef_zaman)
    istasyon["BoslukTahmini"] = tahmin
    istasyon["TahminSkoru"] = tahmin_skoru_getir(tahmin)
    istasyon["Skor"] = istasyon_skoru_hesapla(istasyon)
    istasyon["Rozetler"] = istasyon_rozetleri_getir(istasyon)


def istasyon_veri_fingerprint_getir(istasyonlar: List[Dict[str, Any]]) -> Tuple[int, str, str]:
    if not istasyonlar:
        return (0, "", "")
    ilk = str(istasyonlar[0].get("_station_key") or istasyon_id_getir(istasyonlar[0]))
    son = str(istasyonlar[-1].get("_station_key") or istasyon_id_getir(istasyonlar[-1]))
    return (len(istasyonlar), ilk, son)


def yaricap_kademeleri_getir(menzil_filtresi: bool, guvenli_menzil: float) -> Tuple[float, ...]:
    baslangic = max(20.0, guvenli_menzil if menzil_filtresi else VARSAYILAN_ADAY_YARICAP_KM)
    kademeler: List[float] = []
    yaricap = baslangic
    while yaricap <= MAX_ADAY_YARICAP_KM:
        kademeler.append(round(yaricap, 1))
        yaricap *= 2
    if not kademeler or kademeler[-1] < MAX_ADAY_YARICAP_KM:
        kademeler.append(MAX_ADAY_YARICAP_KM)
    return tuple(dict.fromkeys(kademeler))


def koordinat_kutusu_icinde_mi(
    istasyon: Dict[str, Any],
    user_lat: float,
    user_lon: float,
    yaricap_km: float,
) -> bool:
    lat_delta = yaricap_km / 111.0
    cos_lat = max(0.18, abs(math.cos(math.radians(user_lat))))
    lon_delta = yaricap_km / (111.0 * cos_lat)
    enlem = float(istasyon.get("enlem", 0.0) or 0.0)
    boylam = float(istasyon.get("boylam", 0.0) or 0.0)
    return abs(enlem - user_lat) <= lat_delta and abs(boylam - user_lon) <= lon_delta


def kaba_aday_siralama_anahtari(istasyon: Dict[str, Any], siralama_modu: str) -> Tuple:
    mesafe = float(istasyon.get("Mesafe", 9999.0) or 9999.0)
    if siralama_modu == "Fiyat":
        return (float(istasyon.get("_fiyat_sayi", 9999.0)), mesafe)
    if siralama_modu == "Hız":
        return (-float(istasyon.get("_hiz_sayi", 0.0)), mesafe)
    if siralama_modu == "Mesafe":
        return (mesafe,)
    return (mesafe, -float(istasyon.get("_hiz_sayi", 0.0)), float(istasyon.get("_fiyat_sayi", 9999.0)))


@st.cache_data(ttl=90, show_spinner=False)
def istasyon_adaylarini_hazirla(
    _istasyonlar: List[Dict[str, Any]],
    veri_fingerprint: Tuple[int, str, str],
    user_lat: float,
    user_lon: float,
    menzil_filtresi: bool,
    guvenli_menzil: float,
    sarj_yuzdesi: int,
    batarya: float,
    tuketim: float,
    soket_filtreleri: Tuple[str, ...],
    hiz_filtresi: str,
    operator_filtreleri: Tuple[str, ...],
    sadece_24_saat: bool,
    arama_norm: str,
    siralama_modu: str,
) -> List[Dict[str, Any]]:
    del veri_fingerprint
    adaylar: List[Dict[str, Any]] = []
    hiz_esigi = HIZ_ESIK_MAP.get(hiz_filtresi, 0.0)
    operator_set = set(operator_filtreleri)
    soketler = tuple(sf.upper() for sf in soket_filtreleri)

    for yaricap in yaricap_kademeleri_getir(menzil_filtresi, guvenli_menzil):
        adaylar.clear()
        for ist in _istasyonlar:
            if not koordinat_kutusu_icinde_mi(ist, user_lat, user_lon, yaricap):
                continue
            if soketler and not any(sf in str(ist.get("_soket_upper", "")).upper() for sf in soketler):
                continue
            if hiz_filtresi != "Tümü" and float(ist.get("_hiz_sayi", 0.0) or 0.0) < hiz_esigi:
                continue
            if operator_set and str(ist.get("operator")) not in operator_set:
                continue
            if sadece_24_saat and not ist.get("_acik_24_saat"):
                continue
            if arama_norm and arama_norm not in str(ist.get("_search_text", "")):
                continue

            kus_ucusu = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
            tahmini = tahmini_yol_mesafesi_km(kus_ucusu)
            if menzil_filtresi and tahmini > guvenli_menzil:
                continue

            ist_kopya = ist.copy()
            ist_kopya.update({
                "Mesafe": round(tahmini, 1),
                "KusUcusuMesafe": round(kus_ucusu, 1),
                "TahminiSureDk": tahmini_sure_dk(tahmini),
                "VarisSarjYuzdesi": varis_sarj_yuzdesi_hesapla(sarj_yuzdesi, batarya, tuketim, tahmini),
                "KalanGuvenliMenzil": max(0.0, guvenli_menzil - tahmini),
            })
            adaylar.append(ist_kopya)

        if len(adaylar) >= ZENGIN_ADAY_LIMITI or yaricap >= MAX_ADAY_YARICAP_KM:
            break

    return sorted(adaylar, key=lambda ist: kaba_aday_siralama_anahtari(ist, siralama_modu))[:HAM_ADAY_LIMITI]


def istasyonlari_durum_ve_skorla(
    adaylar: List[Dict[str, Any]],
    durum_ozetleri: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    zengin_istasyonlar: List[Dict[str, Any]] = []
    simdi = utc_simdi()
    for istasyon in adaylar[:ZENGIN_ADAY_LIMITI]:
        ist_key = str(istasyon.get("_station_key") or clean_id_uret(istasyon_id_getir(istasyon)))
        ariza = {**durum_ozeti_fallback(), **durum_ozetleri.get(ist_key, {})}
        hedef_zaman = simdi + timedelta(minutes=int(istasyon.get("TahminiSureDk", 0) or 0))
        bosluk_tahmini = bosluk_tahmini_hesapla(ariza.get("son_yorumlar", []), hedef_zaman=hedef_zaman, simdi=simdi)

        istasyon.update({
            "ArizaDurumu": ariza.get("durum"),
            "ArizaEtiketi": ariza.get("etiket"),
            "SonYorumlar": ariza.get("son_yorumlar", []),
            "BoslukTahmini": bosluk_tahmini,
            "TahminSkoru": tahmin_skoru_getir(bosluk_tahmini),
        })
        istasyon["Skor"] = istasyon_skoru_hesapla(istasyon)
        istasyon["Rozetler"] = istasyon_rozetleri_getir(istasyon)
        zengin_istasyonlar.append(istasyon)
    return zengin_istasyonlar


def tahmin_gecmisini_top_adaylara_uygula(istasyonlar: List[Dict[str, Any]]) -> None:
    station_keys = tuple(
        str(istasyon.get("_station_key") or clean_id_uret(istasyon_id_getir(istasyon)))
        for istasyon in istasyonlar[:TAHMIN_GECMISI_LIMITI]
    )
    if not station_keys:
        return

    yorum_gecmisi = tahmin_yorumlari_getir(station_keys, limit=TAHMIN_GECMISI_YORUM_LIMITI)
    for istasyon, station_key in zip(istasyonlar[:TAHMIN_GECMISI_LIMITI], station_keys):
        yorumlar = yorum_gecmisi.get(station_key) or istasyon.get("SonYorumlar", [])
        istasyon_tahminini_guncelle(istasyon, yorumlar)


def ozet_paneli_ciz(guvenli_menzil: float, sarj_yuzdesi: int, istasyon_sayisi: int) -> None:
    st.markdown(
        f"""
        <div class="sb-summary-grid">
            <div class="sb-summary-item">
                <div class="sb-kicker">{t("summary.safe_range")}</div>
                <div class="sb-summary-value">{guvenli_menzil:.0f} km</div>
                <div class="sb-summary-sub">{t("summary.filter_calculation")}</div>
            </div>
            <div class="sb-summary-item">
                <div class="sb-kicker">{t("summary.charge_status")}</div>
                <div class="sb-summary-value">%{sarj_yuzdesi}</div>
                <div class="sb-summary-sub">{t("summary.current_battery")}</div>
            </div>
            <div class="sb-summary-item">
                <div class="sb-kicker">{t("summary.data_pool")}</div>
                <div class="sb-summary-value">{istasyon_sayisi}</div>
                <div class="sb-summary-sub">{t("summary.normalized_records")}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def surus_ozeti_ciz(arac: str, guvenli_menzil: float, sarj_yuzdesi: int) -> None:
    st.markdown(
        f"""
        <section class="sb-smart-insight">
            <div class="sb-smart-icon" aria-hidden="true">↯</div>
            <div class="sb-smart-copy">
                <span>{t("home.insight_kicker")}</span>
                <strong>{t("home.insight_title", range=guvenli_menzil)}</strong>
                <p>{kisa_deger(arac, max_len=36)} · {t("summary.safe_range_value", percent=sarj_yuzdesi, range=guvenli_menzil)}</p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def rota_eylem_paneli_ciz(
    arac: str,
    guvenli_menzil: float,
    sarj_yuzdesi: int,
    konum_hazir: bool,
) -> None:
    if not konum_hazir:
        st.markdown(
            f"""
            <div class="sb-inline-hint">
                <strong>{t("location.waiting")}</strong>
                <span>{t("location.enable_hint")}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.container(key="route_action_panel"):
        surus_ozeti_ciz(arac, guvenli_menzil, sarj_yuzdesi)
        if st.button(
            t("location.find_charger"),
            key="find_route_btn",
            use_container_width=True,
            disabled=not konum_hazir,
            type="primary",
        ):
            st.session_state["rota_goster"] = True
            st.rerun()


def rota_linki_olustur(istasyon: Dict[str, Any], user_lat: float, user_lon: float) -> str:
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={user_lat},{user_lon}"
        f"&destination={istasyon['enlem']},{istasyon['boylam']}"
        "&travelmode=driving"
    )


def apple_maps_linki_olustur(istasyon: Dict[str, Any], user_lat: float, user_lon: float) -> str:
    return (
        "https://maps.apple.com/"
        f"?saddr={user_lat},{user_lon}"
        f"&daddr={istasyon['enlem']},{istasyon['boylam']}"
        "&dirflg=d"
    )


def istasyon_akis_verisi_hazirla(
    istasyonlar: List[Dict[str, Any]],
    user_lat: float,
    user_lon: float,
) -> List[Dict[str, Any]]:
    toplam = len(istasyonlar)
    payload = []
    for sira, istasyon in enumerate(istasyonlar, start=1):
        payload.append(
            {
                "rank": sira,
                "total": toplam,
                "featured": sira == 1,
                "name": kisa_duz_metin(istasyon.get("isim"), t("common.station"), 118),
                "operator": kisa_duz_metin(istasyon.get("operator"), t("common.operator_unknown"), 64),
                "address": localize_text(kisa_duz_metin(istasyon.get("adres"), t("common.address_missing"), 160)),
                "distance": f"{float(istasyon.get('Mesafe', 0.0) or 0.0):.1f} km",
                "duration": f"{int(istasyon.get('TahminiSureDk', 0) or 0)} {t('feed.minute')}",
                "arrival": f"%{float(istasyon.get('VarisSarjYuzdesi', 0.0) or 0.0):.0f}",
                "power": localize_text(kisa_duz_metin(istasyon.get("hiz"), t("common.power_unknown"), 42)),
                "socket": localize_text(kisa_duz_metin(istasyon.get("soket"), t("common.socket_unknown"), 42)),
                "price": localize_text(kisa_duz_metin(istasyon.get("fiyat"), t("common.price_missing"), 42)),
                "score": int(istasyon.get("Skor", 0) or 0),
                "originLat": float(user_lat),
                "originLon": float(user_lon),
                "latitude": float(istasyon["enlem"]),
                "longitude": float(istasyon["boylam"]),
                "routeUrl": rota_linki_olustur(istasyon, user_lat, user_lon),
                "appleRouteUrl": apple_maps_linki_olustur(istasyon, user_lat, user_lon),
                "chips": [
                    {"text": localize_text(kisa_duz_metin(metin, "", 38)), "className": kisa_duz_metin(css_class, "", 32)}
                    for metin, css_class in istasyon.get("Rozetler", [])
                ],
            }
        )
    return payload


def istasyon_akis_ciz(istasyonlar: List[Dict[str, Any]], user_lat: float, user_lon: float) -> None:
    payload_json = json.dumps(
        istasyon_akis_verisi_hazirla(istasyonlar, user_lat, user_lon),
        ensure_ascii=False,
    ).replace("</", "<\\/")
    labels_json = json.dumps(
        {
            "arrival": t("feed.arrival"),
            "badgeHelp": t("feed.badge_help"),
            "badgeAria": t("feed.badge_aria"),
            "score": t("feed.score"),
            "power": t("feed.power"),
            "socket": t("feed.socket"),
            "price": t("feed.price"),
            "detailCard": t("feed.detail_card"),
            "address": t("feed.address"),
            "openRoute": t("feed.open_route"),
            "appleMaps": t("feed.apple_maps"),
            "googleMaps": t("feed.google_maps"),
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    feed_html = """
        <link
            rel="stylesheet"
            href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
            integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
            crossorigin=""
        />
        <script
            src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
            integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
            crossorigin=""
        ></script>
        <section class="sb-feed-shell" id="rotayi-ac" aria-label="__FEED_ARIA__">
            <div class="sb-feed-viewport" id="station-feed" tabindex="0" aria-live="polite">
                <div class="sb-feed-track" id="station-track">
                    <div class="sb-feed-spacer" id="station-top-spacer"></div>
                    <div class="sb-feed-window" id="station-window"></div>
                    <div class="sb-feed-spacer" id="station-bottom-spacer"></div>
                </div>
            </div>
        </section>
        <script>
            const stations = __STATIONS_JSON__;
            const labels = __LABELS_JSON__;
            const viewport = document.getElementById("station-feed");
            const track = document.getElementById("station-track");
            const windowEl = document.getElementById("station-window");
            const topSpacer = document.getElementById("station-top-spacer");
            const bottomSpacer = document.getElementById("station-bottom-spacer");
            const visibleWindowSize = Math.min(9, Math.max(1, stations.length));
            const windowBuffer = Math.min(4, Math.floor(visibleWindowSize / 2));
            let activeIndex = 0;
            let visibleIndex = 0;
            let windowStart = 0;
            let observer = null;
            let scrollTimer = null;
            let motionFrame = null;

            const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;"
            }[char]));

            const clampIndex = (value) => Math.max(0, Math.min(stations.length - 1, value));
            const windowEnd = () => Math.min(stations.length, windowStart + visibleWindowSize);
            const frameHeight = () => Math.max(1, viewport.clientHeight);

            function nextWindowStart(index) {
                if (stations.length <= visibleWindowSize) return 0;
                return Math.max(0, Math.min(index - windowBuffer, stations.length - visibleWindowSize));
            }

            function chipHtml(chips) {
                if (!chips.length) return "";
                const chipMarkup = chips.map((chip) => {
                    const item = typeof chip === "string" ? { text: chip, className: "" } : chip;
                    const classes = ["sb-feed-chip", item.className || ""].filter(Boolean).join(" ");
                    return `<span class="${esc(classes)}">${esc(item.text)}</span>`;
                }).join("");
                return `
                    <div class="sb-feed-chip-row">
                        <div class="sb-feed-chips">${chipMarkup}</div>
                        <button
                            class="sb-feed-chip-help"
                            type="button"
                            title="${esc(labels.badgeHelp)}"
                            aria-label="${esc(labels.badgeAria)}"
                        >?</button>
                    </div>
                `;
            }

            function cardHtml(station, index) {
                const rank = String(station.rank).padStart(2, "0");
                return `
                    <article
                        class="sb-feed-card ${station.featured ? "is-featured" : ""}"
                        data-card-index="${index}"
                        aria-label="${esc(station.name)}"
                    >
                        <div class="sb-route-map-stage" aria-hidden="true">
                            <div class="sb-route-map" data-map-index="${index}"></div>
                            <div class="sb-route-map-fade"></div>
                            <div class="sb-route-map-score">
                                <strong>${station.score}</strong><span>${esc(labels.score)}</span>
                            </div>
                            <div class="sb-route-map-rank">
                                <strong>${rank}</strong><span>/ ${station.total}</span>
                            </div>
                        </div>
                        <div class="sb-route-detail">
                            <div class="sb-route-journey">
                                <strong>${esc(station.distance)}</strong>
                                <span>${esc(station.duration)} · ${esc(labels.arrival)} ${esc(station.arrival)}</span>
                            </div>
                            <div class="sb-route-station">
                                <span>${esc(labels.detailCard)}</span>
                                <strong>${esc(station.name)}</strong>
                                <small>${esc(station.operator)}</small>
                            </div>
                            <div class="sb-route-metrics">
                                <div><span>${esc(labels.power)}</span><strong>${esc(station.power)}</strong></div>
                                <div><span>${esc(labels.socket)}</span><strong>${esc(station.socket)}</strong></div>
                                <div><span>${esc(labels.price)}</span><strong>${esc(station.price)}</strong></div>
                            </div>
                            ${chipHtml(station.chips)}
                            <div class="sb-route-actions">
                                <strong>${esc(labels.openRoute)}</strong>
                                <div>
                                    <a href="${esc(station.appleRouteUrl)}" target="_blank" rel="noopener noreferrer">${esc(labels.appleMaps)}</a>
                                    <a href="${esc(station.routeUrl)}" target="_blank" rel="noopener noreferrer">${esc(labels.googleMaps)}</a>
                                </div>
                            </div>
                            <div class="sb-route-address">
                                <span>${esc(labels.address)}</span>
                                <strong>${esc(station.address)}</strong>
                            </div>
                        </div>
                    </article>
                `;
            }

            const stationMaps = new WeakMap();

            function fitRoute(map, bounds) {
                if (!bounds || !bounds.isValid()) return;
                map.fitBounds(bounds, {
                    animate: false,
                    maxZoom: 15,
                    paddingTopLeft: [28, 28],
                    paddingBottomRight: [28, 82]
                });
            }

            function ensureMapForSlide(slide) {
                if (!slide) return;
                const canvas = slide.querySelector(".sb-route-map");
                if (!canvas || stationMaps.has(canvas)) return;
                if (!window.L) {
                    canvas.classList.add("is-fallback");
                    return;
                }

                const index = Number(slide.dataset.index);
                const station = stations[index];
                const origin = [Number(station.originLat), Number(station.originLon)];
                const destination = [Number(station.latitude), Number(station.longitude)];
                const map = L.map(canvas, {
                    attributionControl: false,
                    boxZoom: false,
                    doubleClickZoom: false,
                    dragging: false,
                    keyboard: false,
                    preferCanvas: true,
                    scrollWheelZoom: false,
                    touchZoom: false,
                    zoomControl: false
                });

                L.control.attribution({ position: "bottomright", prefix: false }).addTo(map);
                L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
                    maxZoom: 19
                }).addTo(map);

                const originMarker = L.circleMarker(origin, {
                    color: "#FFFFFF",
                    fillColor: "#C8FF2E",
                    fillOpacity: 1,
                    interactive: false,
                    radius: 8,
                    weight: 3
                }).addTo(map);
                const destinationMarker = L.circleMarker(destination, {
                    color: "#FFFFFF",
                    fillColor: "#0E1012",
                    fillOpacity: 1,
                    interactive: false,
                    radius: 9,
                    weight: 3
                }).addTo(map);
                const routeLine = L.polyline([origin, destination], {
                    color: "#0E1012",
                    dashArray: "7 7",
                    interactive: false,
                    lineCap: "round",
                    opacity: 0.88,
                    weight: 5
                }).addTo(map);
                const initialBounds = L.featureGroup([originMarker, destinationMarker, routeLine]).getBounds();
                fitRoute(map, initialBounds);
                stationMaps.set(canvas, { map, routeLine });
                window.requestAnimationFrame(() => map.invalidateSize(false));

                const routeEndpoint = (
                    `https://router.project-osrm.org/route/v1/driving/`
                    + `${station.originLon},${station.originLat};${station.longitude},${station.latitude}`
                    + `?overview=full&geometries=geojson&steps=false`
                );
                window.fetch(routeEndpoint)
                    .then((response) => response.ok ? response.json() : Promise.reject(new Error("route")))
                    .then((data) => {
                        const coordinates = data?.routes?.[0]?.geometry?.coordinates;
                        if (!Array.isArray(coordinates) || coordinates.length < 2) return;
                        const routePoints = coordinates.map(([lon, lat]) => [lat, lon]);
                        routeLine.setLatLngs(routePoints);
                        routeLine.setStyle({ dashArray: null, opacity: 0.96 });
                        fitRoute(map, routeLine.getBounds());
                    })
                    .catch(() => {});
            }

            function paintActiveSlide() {
                const slides = Array.from(windowEl.querySelectorAll(".sb-feed-slide"));
                slides.forEach((slide) => {
                    const index = Number(slide.dataset.index);
                    const isActive = index === visibleIndex;
                    const isNear = Math.abs(index - visibleIndex) === 1;
                    slide.classList.toggle("is-active", isActive);
                    slide.classList.toggle("is-near", isNear);
                    const card = slide.querySelector(".sb-feed-card");
                    if (card) {
                        card.toggleAttribute("aria-current", isActive);
                    }
                });
                ensureMapForSlide(windowEl.querySelector(`.sb-feed-slide[data-index="${visibleIndex}"]`));
            }

            function syncMotion() {
                const height = frameHeight();
                const center = viewport.scrollTop / height;
                Array.from(windowEl.querySelectorAll(".sb-feed-slide")).forEach((slide) => {
                    const index = Number(slide.dataset.index);
                    const distance = Math.min(2, Math.abs(index - center));
                    const card = slide.querySelector(".sb-feed-card");
                    if (!card) return;
                    card.style.setProperty("--sb-card-scale", String(1 - Math.min(0.12, distance * 0.065)));
                    card.style.setProperty("--sb-card-opacity", String(1 - Math.min(0.62, distance * 0.46)));
                    card.style.setProperty("--sb-card-shift", `${Math.min(34, distance * 22)}px`);
                });
            }

            function scheduleSyncMotion() {
                if (motionFrame) return;
                motionFrame = window.requestAnimationFrame(() => {
                    motionFrame = null;
                    syncMotion();
                });
            }

            function setupObserver() {
                if (observer) observer.disconnect();
                observer = new IntersectionObserver((entries) => {
                    const best = entries
                        .filter((entry) => entry.isIntersecting)
                        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
                    if (!best || best.intersectionRatio < 0.52) return;
                    visibleIndex = clampIndex(Number(best.target.dataset.index));
                    paintActiveSlide();
                }, {
                    root: viewport,
                    threshold: [0.28, 0.52, 0.72, 0.9]
                });
                Array.from(windowEl.querySelectorAll(".sb-feed-slide")).forEach((slide) => observer.observe(slide));
            }

            function updateSpacers() {
                const height = frameHeight();
                const end = windowEnd();
                topSpacer.style.height = `${windowStart * height}px`;
                bottomSpacer.style.height = `${Math.max(0, stations.length - end) * height}px`;
            }

            function renderWindowForIndex(index) {
                const currentEnd = windowEnd();
                if (windowEl.childElementCount && index >= windowStart && index < currentEnd) {
                    updateSpacers();
                    return;
                }
                const nextStart = nextWindowStart(index);
                if (windowEl.childElementCount && nextStart === windowStart) {
                    updateSpacers();
                    return;
                }
                windowStart = nextStart;
                const end = windowEnd();
                windowEl.innerHTML = Array.from({ length: end - windowStart }, (_, offset) => {
                    const stationIndex = windowStart + offset;
                    return (
                        `<div class="sb-feed-slide" data-index="${stationIndex}">${cardHtml(stations[stationIndex], stationIndex)}</div>`
                    );
                }).join("");
                updateSpacers();
                setupObserver();
                paintActiveSlide();
            }

            function renderWindow() {
                renderWindowForIndex(activeIndex);
                window.requestAnimationFrame(() => {
                    viewport.scrollTop = Math.max(0, activeIndex) * frameHeight();
                    syncMotion();
                });
            }

            function settleToSnap() {
                const height = frameHeight();
                const next = clampIndex(Math.round(viewport.scrollTop / height));
                activeIndex = next;
                visibleIndex = next;
                renderWindowForIndex(next);
                paintActiveSlide();
                scheduleSyncMotion();
            }

            function scrollToIndex(index) {
                const next = clampIndex(index);
                activeIndex = next;
                visibleIndex = next;
                renderWindowForIndex(next);
                paintActiveSlide();
                viewport.scrollTo({ top: next * frameHeight(), behavior: "smooth" });
            }

            viewport.addEventListener("scroll", () => {
                const next = clampIndex(Math.round(viewport.scrollTop / frameHeight()));
                renderWindowForIndex(next);
                scheduleSyncMotion();
                window.clearTimeout(scrollTimer);
                scrollTimer = window.setTimeout(settleToSnap, 120);
            }, { passive: true });

            viewport.addEventListener("pointerdown", () => {
                viewport.focus({ preventScroll: true });
            }, { passive: true });

            document.addEventListener("keydown", (event) => {
                if (event.key === "ArrowDown" || event.key === "PageDown" || event.key === " ") {
                    event.preventDefault();
                    scrollToIndex(visibleIndex + 1);
                }
                if (event.key === "ArrowUp" || event.key === "PageUp") {
                    event.preventDefault();
                    scrollToIndex(visibleIndex - 1);
                }
                if (event.key === "Home") {
                    event.preventDefault();
                    scrollToIndex(0);
                }
                if (event.key === "End") {
                    event.preventDefault();
                    scrollToIndex(stations.length - 1);
                }
            });

            window.addEventListener("resize", () => {
                updateSpacers();
                viewport.scrollTop = activeIndex * frameHeight();
                const activeCanvas = windowEl.querySelector(
                    `.sb-feed-slide[data-index="${visibleIndex}"] .sb-route-map`
                );
                const mapState = activeCanvas ? stationMaps.get(activeCanvas) : null;
                if (mapState) {
                    mapState.map.invalidateSize(false);
                }
                scheduleSyncMotion();
            }, { passive: true });

            renderWindow();
        </script>
        <style>
            :root {
                color-scheme: light;
                --feed-bg: #FFFFFF;
                --feed-text: #0E1012;
                --feed-soft: rgba(14, 16, 18, 0.68);
                --feed-muted: rgba(14, 16, 18, 0.46);
                --feed-green: #C8FF2E;
                --feed-blue: #0E1012;
                --feed-frame-height: 590px;
                --feed-font-display: "Space Grotesk", "Inter", system-ui, sans-serif;
                --feed-font-body: "Inter", system-ui, sans-serif;
            }

            * { box-sizing: border-box; }
            html,
            body {
                background: transparent;
                margin: 0;
                min-height: 100%;
                overflow: hidden;
                overscroll-behavior: contain;
            }

            body {
                font-family: var(--feed-font-body);
                padding: 0;
            }

            .sb-feed-shell {
                background: transparent;
                height: var(--feed-frame-height);
                overflow: hidden;
                position: relative;
                width: 100%;
            }

            .sb-feed-viewport {
                height: var(--feed-frame-height);
                outline: 0;
                overflow-x: hidden;
                overflow-y: auto;
                overscroll-behavior-y: contain;
                scroll-behavior: auto;
                scroll-padding: 0;
                scroll-snap-type: y mandatory;
                scrollbar-width: none;
                touch-action: pan-y;
                -webkit-overflow-scrolling: touch;
            }

            .sb-feed-viewport::-webkit-scrollbar {
                display: none;
            }

            .sb-feed-track {
                min-height: 100%;
                transform: translateZ(0);
            }

            .sb-feed-window {
                min-height: var(--feed-frame-height);
            }

            .sb-feed-spacer {
                flex: 0 0 auto;
                height: 0;
                pointer-events: none;
            }

            .sb-feed-slide {
                align-items: stretch;
                backface-visibility: hidden;
                contain: layout paint;
                display: flex;
                height: var(--feed-frame-height);
                justify-content: center;
                padding: 4px 0 14px;
                scroll-snap-align: center;
                scroll-snap-stop: always;
            }

            .sb-feed-card {
                --sb-card-opacity: 0.44;
                --sb-card-scale: 0.92;
                --sb-card-shift: 24px;
                background:
                    radial-gradient(circle at 18% -8%, rgba(200, 255, 46, 0.20), transparent 34%),
                    linear-gradient(180deg, rgba(250, 254, 251, 0.98), rgba(239, 249, 243, 0.97));
                border: 1px solid rgba(14, 16, 18, 0.10);
                border-radius: 26px;
                box-shadow: 0 18px 44px rgba(14, 16, 18, 0.11);
                color: var(--feed-text);
                display: flex;
                flex-direction: column;
                height: calc(var(--feed-frame-height) - 18px);
                isolation: isolate;
                outline: 0;
                overflow: hidden;
                padding: 24px 20px 18px;
                position: relative;
                opacity: var(--sb-card-opacity);
                transform: translate3d(0, var(--sb-card-shift), 0) scale(var(--sb-card-scale));
                transform-origin: center center;
                transition:
                    box-shadow 260ms ease,
                    filter 260ms ease;
                width: min(100%, 500px);
                will-change: opacity, transform;
            }

            .sb-feed-slide.is-active .sb-feed-card {
                --sb-card-opacity: 1;
                --sb-card-scale: 1;
                --sb-card-shift: 0px;
                filter: saturate(1.08);
            }

            .sb-feed-slide.is-near .sb-feed-card {
                box-shadow: 0 14px 34px rgba(14, 16, 18, 0.08);
            }

            .sb-feed-card.is-featured {
                box-shadow: 0 20px 48px rgba(14, 16, 18, 0.12);
            }

            .sb-feed-glow {
                background:
                    linear-gradient(90deg, transparent, rgba(200, 255, 46, 0.54), rgba(14, 16, 18, 0.42), transparent);
                filter: blur(13px);
                height: 18px;
                left: 14%;
                opacity: 0.70;
                position: absolute;
                right: 14%;
                top: 47%;
                transform: perspective(140px) rotateX(55deg);
            }

            .sb-feed-top {
                align-items: flex-start;
                display: flex;
                gap: 14px;
                justify-content: space-between;
                position: relative;
                z-index: 2;
            }

            .sb-feed-head-actions {
                align-items: flex-end;
                display: flex;
                flex: 0 0 auto;
                flex-direction: column;
                gap: 8px;
                min-width: 72px;
            }

            .sb-feed-head-score {
                align-items: center;
                background: linear-gradient(135deg, rgba(200, 255, 46, 0.24), rgba(14, 16, 18, 0.20));
                border: 1px solid rgba(200, 255, 46, 0.32);
                border-radius: 16px;
                box-shadow: 0 10px 24px rgba(200, 255, 46, 0.14);
                color: var(--feed-text);
                display: flex;
                gap: 6px;
                justify-content: center;
                min-height: 36px;
                padding: 7px 9px;
            }

            .sb-feed-head-score strong {
                color: var(--feed-green);
                font-family: var(--feed-font-display);
                font-size: 19px;
                line-height: 1;
            }

            .sb-feed-head-score span {
                color: var(--feed-muted);
                font-size: 10px;
                font-weight: 900;
            }

            .sb-feed-bookmark {
                align-items: center;
                background: rgba(255, 255, 255, 0.62);
                border: 1px solid rgba(14, 16, 18, 0.13);
                border-radius: 999px;
                color: var(--feed-green);
                display: flex;
                font-size: 18px;
                font-weight: 900;
                height: 34px;
                justify-content: center;
                line-height: 1;
                width: 34px;
            }

            .sb-feed-eyebrow {
                color: var(--feed-green);
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0;
                margin-bottom: 8px;
                text-transform: uppercase;
            }

            .sb-feed-title h2 {
                color: var(--feed-text);
                font-family: var(--feed-font-display);
                font-size: 28px;
                letter-spacing: 0;
                line-height: 1.04;
                margin: 0;
                overflow-wrap: anywhere;
            }

            .sb-feed-title {
                min-width: 0;
            }

            .sb-feed-title p {
                color: var(--feed-soft);
                font-size: 13px;
                font-weight: 600;
                margin: 8px 0 0;
            }

            .sb-feed-counter {
                align-items: flex-end;
                display: flex;
                flex: 0 0 auto;
                gap: 2px;
                line-height: 1;
            }

            .sb-feed-counter strong {
                color: var(--feed-green);
                font-family: var(--feed-font-display);
                font-size: 28px;
            }

            .sb-feed-counter span {
                color: var(--feed-muted);
                font-size: 12px;
                font-weight: 800;
                padding-bottom: 4px;
            }

            .sb-feed-hero {
                margin: auto 0 18px;
                position: relative;
                z-index: 2;
            }

            .sb-feed-hero strong {
                color: var(--feed-text);
                display: block;
                font-family: var(--feed-font-display);
                font-size: 50px;
                letter-spacing: 0;
                line-height: 0.95;
            }

            .sb-feed-hero span {
                color: var(--feed-soft);
                display: block;
                font-size: 14px;
                font-weight: 700;
                margin-top: 10px;
            }

            .sb-feed-score-row {
                align-items: center;
                display: flex;
                gap: 10px;
                margin-bottom: 12px;
                position: relative;
                z-index: 2;
            }

            .sb-feed-score {
                align-items: center;
                background: linear-gradient(135deg, var(--feed-green), var(--feed-blue));
                border-radius: 18px;
                box-shadow: 0 14px 28px rgba(200, 255, 46, 0.22);
                color: #0E1012;
                display: flex;
                flex: 0 0 auto;
                flex-direction: column;
                justify-content: center;
                min-height: 58px;
                min-width: 68px;
                padding: 7px 9px;
            }

            .sb-feed-score strong {
                font-family: var(--feed-font-display);
                font-size: 22px;
                line-height: 1;
            }

            .sb-feed-score span {
                font-size: 10px;
                font-weight: 900;
                opacity: 0.72;
            }

            .sb-feed-status {
                align-items: center;
                background: rgba(255, 255, 255, 0.58);
                border: 1px solid rgba(14, 16, 18, 0.13);
                border-radius: 18px;
                color: var(--feed-soft);
                display: flex;
                flex: 1 1 auto;
                font-size: 12px;
                font-weight: 750;
                min-height: 48px;
                padding: 11px 14px;
            }

            .sb-feed-grid {
                display: grid;
                gap: 8px;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                position: relative;
                z-index: 2;
            }

            .sb-feed-grid div {
                align-items: flex-start;
                background: rgba(255, 255, 255, 0.58);
                border: 1px solid rgba(14, 16, 18, 0.13);
                border-radius: 18px;
                display: flex;
                flex-direction: column;
                min-height: 70px;
                padding: 10px;
            }

            .sb-feed-grid span {
                color: var(--feed-muted);
                display: block;
                font-size: 10px;
                font-weight: 800;
                text-transform: uppercase;
            }

            .sb-feed-grid strong {
                color: var(--feed-text);
                display: block;
                font-size: 13px;
                line-height: 1.18;
                margin-top: 6px;
                overflow-wrap: anywhere;
            }

            .sb-feed-chips {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                min-width: 0;
                position: relative;
                z-index: 2;
            }

            .sb-feed-chip-row {
                align-items: flex-start;
                display: flex;
                gap: 8px;
                justify-content: space-between;
                margin-top: 12px;
                position: relative;
                z-index: 2;
            }

            .sb-feed-chip {
                background: rgba(200, 255, 46, 0.18);
                border: 1px solid rgba(200, 255, 46, 0.34);
                border-radius: 999px;
                color: var(--feed-green);
                font-size: 11px;
                font-weight: 800;
                min-height: 26px;
                padding: 6px 9px;
            }

            .sb-feed-chip.sb-chip-risk {
                background: rgba(230, 120, 120, 0.16);
                border-color: rgba(230, 120, 120, 0.34);
                color: #E67878;
            }

            .sb-feed-chip.sb-chip-warn {
                background: rgba(245, 205, 95, 0.16);
                border-color: rgba(245, 205, 95, 0.34);
                color: #DFAF3D;
            }

            .sb-feed-chip.sb-chip-info {
                background: rgba(14, 16, 18, 0.16);
                border-color: rgba(14, 16, 18, 0.34);
                color: #0E1012;
            }

            .sb-feed-chip-help {
                appearance: none;
                background: rgba(255, 255, 255, 0.68);
                border: 1px solid rgba(14, 16, 18, 0.15);
                border-radius: 999px;
                color: var(--feed-soft);
                cursor: help;
                flex: 0 0 auto;
                font-size: 12px;
                font-weight: 900;
                height: 28px;
                padding: 0;
                width: 28px;
            }

            .sb-feed-comments {
                display: grid;
                gap: 7px;
                margin-top: 12px;
                position: relative;
                z-index: 2;
            }

            .sb-feed-comments div {
                background: rgba(255, 255, 255, 0.58);
                border: 1px solid rgba(14, 16, 18, 0.13);
                border-radius: 18px;
                min-height: 48px;
                padding: 8px 10px;
            }

            .sb-feed-comments strong,
            .sb-feed-comments span {
                display: block;
                font-size: 11px;
                line-height: 1.25;
            }

            .sb-feed-comments strong {
                color: var(--feed-green);
                margin-bottom: 3px;
            }

            .sb-feed-comments span {
                color: var(--feed-soft);
            }

            .sb-feed-address {
                color: var(--feed-muted);
                font-size: 12px;
                line-height: 1.34;
                margin-top: 13px;
                min-height: 32px;
                overflow-wrap: anywhere;
                position: relative;
                z-index: 2;
            }

            .sb-feed-route {
                align-items: center;
                background:
                    linear-gradient(90deg, rgba(255, 255, 255, 0.18), transparent 30%, transparent 70%, rgba(255, 255, 255, 0.14)),
                    linear-gradient(135deg, var(--feed-green), var(--feed-blue));
                border-radius: 18px;
                box-shadow: 0 18px 36px rgba(200, 255, 46, 0.24), 0 8px 24px rgba(14, 16, 18, 0.18);
                color: #0E1012;
                display: flex;
                gap: 12px;
                justify-content: space-between;
                margin-top: 15px;
                min-height: 58px;
                padding: 13px 15px;
                position: relative;
                text-decoration: none;
                z-index: 2;
            }

            .sb-feed-route span {
                line-height: 1.15;
                font-family: var(--feed-font-display);
                font-size: 16px;
                font-weight: 850;
            }

            .sb-feed-route small {
                flex: 0 0 auto;
                font-size: 11px;
                font-weight: 800;
                opacity: 0.66;
                text-align: right;
            }

            @media (prefers-reduced-motion: reduce) {
                .sb-feed-viewport {
                    scroll-behavior: auto;
                }

                .sb-feed-card {
                    animation: none;
                    transition: none;
                }
            }

            @media (max-width: 430px) {
                :root {
                    --feed-frame-height: 636px;
                }

                .sb-feed-slide {
                    padding: 4px 0 10px;
                }

                .sb-feed-card {
                    height: calc(var(--feed-frame-height) - 14px);
                    padding: 18px 16px 16px;
                }

                .sb-feed-title h2 {
                    font-size: 24px;
                }

                .sb-feed-hero strong {
                    font-size: 42px;
                }

                .sb-feed-grid {
                    gap: 6px;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                }

                .sb-feed-grid div {
                    border-radius: 14px;
                    min-height: 62px;
                    padding: 9px 7px;
                }

                .sb-feed-grid strong {
                    font-size: 11px;
                    margin-top: 5px;
                }

                .sb-feed-comments {
                    display: none;
                }

                .sb-feed-address {
                    margin-top: 9px;
                    min-height: 20px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }

                .sb-feed-route {
                    flex: 0 0 auto;
                    margin-top: auto;
                    min-height: 54px;
                }
            }

            .sb-feed-card {
                background:
                    radial-gradient(circle at 18% -6%, rgba(200, 255, 46, 0.16), transparent 32%),
                    linear-gradient(180deg, rgba(250, 254, 251, 0.98), rgba(239, 249, 243, 0.97));
                padding: 0;
            }

            .sb-route-map-stage {
                background: #F7FCF8;
                flex: 0 0 238px;
                min-height: 238px;
                overflow: hidden;
                position: relative;
            }

            .sb-route-map {
                background:
                    linear-gradient(135deg, rgba(200, 255, 46, 0.18), rgba(14, 16, 18, 0.12)),
                    #F7FCF8;
                height: 100%;
                pointer-events: none;
                width: 100%;
                z-index: 1;
            }

            .sb-route-map.is-fallback {
                background:
                    linear-gradient(36deg, transparent 47%, rgba(255, 255, 255, 0.78) 48% 52%, transparent 53%),
                    linear-gradient(144deg, transparent 46%, rgba(14, 16, 18, 0.08) 47% 50%, transparent 51%),
                    linear-gradient(135deg, rgba(200, 255, 46, 0.22), rgba(14, 16, 18, 0.12)),
                    #F7FCF8;
                background-size: 90px 90px, 118px 118px, auto, auto;
            }

            .sb-route-map-fade {
                background: linear-gradient(180deg, transparent 42%, rgba(250, 254, 251, 0.88) 86%, rgba(250, 254, 251, 0.98) 100%);
                inset: 0;
                pointer-events: none;
                position: absolute;
                z-index: 2;
            }

            .sb-route-map-score,
            .sb-route-map-rank {
                align-items: baseline;
                backdrop-filter: blur(14px);
                background: rgba(250, 254, 251, 0.72);
                border: 1px solid rgba(14, 16, 18, 0.08);
                border-radius: 999px;
                box-shadow: 0 8px 18px rgba(14, 16, 18, 0.07);
                display: flex;
                gap: 4px;
                padding: 7px 10px;
                position: absolute;
                top: 12px;
                z-index: 5;
            }

            .sb-route-map-score {
                left: 12px;
            }

            .sb-route-map-rank {
                right: 12px;
            }

            .sb-route-map-score strong,
            .sb-route-map-rank strong {
                color: var(--feed-blue);
                font-family: var(--feed-font-display);
                font-size: 15px;
                line-height: 1;
            }

            .sb-route-map-score span,
            .sb-route-map-rank span {
                color: var(--feed-soft);
                font-size: 9px;
                font-weight: 850;
                text-transform: uppercase;
            }

            .sb-route-detail {
                backdrop-filter: blur(22px);
                background:
                    linear-gradient(180deg, rgba(250, 254, 251, 0.96), rgba(247, 252, 248, 0.98));
                border: 0;
                border-radius: 22px 22px 0 0;
                box-shadow: 0 -14px 32px rgba(14, 16, 18, 0.08);
                display: flex;
                flex: 1 1 auto;
                flex-direction: column;
                margin-top: -66px;
                min-height: 0;
                padding: 16px;
                position: relative;
                z-index: 6;
            }

            .sb-route-journey {
                display: flex;
                flex-direction: column;
                margin-bottom: 9px;
            }

            .sb-route-journey strong {
                color: var(--feed-text);
                font-family: var(--feed-font-display);
                font-size: 40px;
                font-weight: 900;
                letter-spacing: 0;
                line-height: 0.95;
            }

            .sb-route-journey span {
                color: var(--feed-soft);
                font-size: 12px;
                font-weight: 760;
                margin-top: 6px;
            }

            .sb-route-station {
                background: rgba(255, 255, 255, 0.58);
                border: 1px solid rgba(14, 16, 18, 0.07);
                border-radius: 13px;
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
                min-height: 56px;
                padding: 8px 10px;
            }

            .sb-route-station span,
            .sb-route-station strong,
            .sb-route-station small {
                display: block;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .sb-route-station span,
            .sb-route-address span {
                color: var(--feed-muted);
                font-size: 9px;
                font-weight: 850;
                text-transform: uppercase;
            }

            .sb-route-station strong {
                color: var(--feed-text);
                font-family: var(--feed-font-display);
                font-size: 14px;
                line-height: 1.15;
                margin-top: 2px;
            }

            .sb-route-station small {
                color: var(--feed-soft);
                font-size: 10px;
                font-weight: 650;
                margin-top: 2px;
            }

            .sb-route-metrics {
                display: grid;
                gap: 7px;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                margin-top: 8px;
            }

            .sb-route-metrics > div {
                background: rgba(255, 255, 255, 0.54);
                border: 1px solid rgba(14, 16, 18, 0.07);
                border-radius: 13px;
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.62);
                min-height: 58px;
                padding: 8px;
            }

            .sb-route-metrics span,
            .sb-route-metrics strong {
                display: block;
                overflow-wrap: anywhere;
            }

            .sb-route-metrics span {
                color: var(--feed-muted);
                font-size: 9px;
                font-weight: 850;
                text-transform: uppercase;
            }

            .sb-route-metrics strong {
                color: var(--feed-text);
                font-size: 11px;
                line-height: 1.15;
                margin-top: 5px;
            }

            .sb-route-detail .sb-feed-chip-row {
                margin-top: 7px;
            }

            .sb-route-detail .sb-feed-chip {
                color: #365F2D;
                font-size: 9px;
                min-height: 22px;
                padding: 4px 7px;
            }

            .sb-route-detail .sb-feed-chip-help {
                height: 23px;
                width: 23px;
            }

            .sb-route-actions {
                align-items: center;
                background:
                    linear-gradient(90deg, rgba(255, 255, 255, 0.14), transparent 38%),
                    linear-gradient(135deg, var(--feed-green), var(--feed-blue));
                border-radius: 14px;
                box-shadow: 0 10px 22px rgba(14, 16, 18, 0.15);
                display: flex;
                gap: 8px;
                justify-content: space-between;
                margin-top: 8px;
                min-height: 48px;
                padding: 8px 9px 8px 12px;
            }

            .sb-route-actions > strong {
                color: #FFFFFF;
                font-family: var(--feed-font-display);
                font-size: 13px;
                line-height: 1.1;
            }

            .sb-route-actions > div {
                display: flex;
                flex: 0 0 auto;
                gap: 4px;
            }

            .sb-route-actions a {
                background: rgba(14, 16, 18, 0.46);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 9px;
                color: #FFFFFF;
                font-size: 9px;
                font-weight: 820;
                padding: 7px 8px;
                text-decoration: none;
                white-space: nowrap;
            }

            .sb-route-actions a:focus-visible {
                outline: 2px solid #FFFFFF;
                outline-offset: 2px;
            }

            .sb-route-address {
                border-top: 1px solid rgba(14, 16, 18, 0.08);
                margin-top: auto;
                min-height: 34px;
                overflow: hidden;
                padding-top: 8px;
            }

            .sb-route-address strong {
                color: var(--feed-soft);
                display: -webkit-box;
                font-size: 10px;
                font-weight: 650;
                line-height: 1.25;
                margin-top: 3px;
                overflow: hidden;
                overflow-wrap: anywhere;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 2;
            }

            .leaflet-container {
                background: #F7FCF8;
                font-family: var(--feed-font-body);
            }

            .leaflet-tile {
                filter: saturate(0.82) contrast(0.94) opacity(0.76);
            }

            .leaflet-control-attribution {
                background: rgba(250, 254, 251, 0.58) !important;
                border-radius: 999px;
                color: rgba(14, 16, 18, 0.42) !important;
                font-size: 7px !important;
                opacity: 0.48;
                padding: 1px 5px !important;
            }

            .leaflet-control-attribution a {
                color: rgba(14, 16, 18, 0.52) !important;
            }

            .leaflet-bottom .leaflet-control {
                margin-bottom: 72px !important;
                margin-right: 12px !important;
            }

            @media (max-width: 430px) {
                .sb-feed-card {
                    padding: 0;
                }

                .sb-route-map-stage {
                    flex-basis: 222px;
                    min-height: 222px;
                }

                .sb-route-detail {
                    margin-top: -58px;
                    padding: 13px;
                }

                .sb-route-journey {
                    margin-bottom: 7px;
                }

                .sb-route-journey strong {
                    font-size: 36px;
                }

                .sb-route-station {
                    min-height: 52px;
                    padding: 7px 9px;
                }

                .sb-route-station strong {
                    font-size: 13px;
                }

                .sb-route-metrics {
                    gap: 5px;
                    margin-top: 6px;
                }

                .sb-route-metrics > div {
                    min-height: 54px;
                    padding: 7px 6px;
                }

                .sb-route-actions {
                    margin-top: 7px;
                    padding-left: 10px;
                }

                .sb-route-actions > strong {
                    font-size: 12px;
                }

                .sb-route-actions a {
                    font-size: 8px;
                    padding: 7px 6px;
                }

                .sb-route-address {
                    margin-top: auto;
                    padding-top: 7px;
                }
            }
        </style>
    """.replace("__STATIONS_JSON__", payload_json)
    feed_html = (
        feed_html
        .replace("__LABELS_JSON__", labels_json)
        .replace("__FEED_ARIA__", guvenli_metin(t("feed.aria"), 80))
    )

    st.markdown('<div class="sb-route-feed-mode" aria-hidden="true"></div>', unsafe_allow_html=True)
    components.html(
        feed_html,
        height=640,
        scrolling=False,
    )


def istasyon_aksiyon_hedefi_sec(istasyonlar: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
    hedefler: List[Tuple[str, str, Dict[str, Any]]] = []
    for sira, istasyon in enumerate(istasyonlar, start=1):
        ist_key = str(istasyon.get("_station_key") or clean_id_uret(istasyon_id_getir(istasyon)))
        mesafe = float(istasyon.get("Mesafe", 0.0) or 0.0)
        etiket = f"{sira}. {kisa_deger(istasyon.get('isim'), t('common.station'), 54)} · {mesafe:.1f} km"
        hedefler.append((ist_key, etiket, istasyon))

    if not hedefler:
        return {}, ""

    etiketler = {anahtar: etiket for anahtar, etiket, _ in hedefler}
    istasyon_map = {anahtar: istasyon for anahtar, _, istasyon in hedefler}
    secenekler = [anahtar for anahtar, _, _ in hedefler]

    if st.session_state.get("station_action_target") not in secenekler:
        st.session_state["station_action_target"] = secenekler[0]

    if len(secenekler) > 1:
        secilen_key = st.selectbox(
            t("actions.station_label"),
            secenekler,
            format_func=lambda anahtar: etiketler.get(anahtar, anahtar),
            key="station_action_target",
        )
        st.caption(t("actions.station_help"))
    else:
        secilen_key = secenekler[0]
        st.markdown(
            f"""
            <div class="sb-action-target">
                <span>{t("actions.station_label")}</span>
                <strong>{guvenli_metin(etiketler[secilen_key], 96)}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return istasyon_map[secilen_key], secilen_key


def istasyon_aksiyonlari_ciz(ist: Dict[str, Any], ist_id: str, ist_key: str, ayar_yaricap: int) -> None:
    if not ist or not ist_key:
        return
    st.markdown(f'<div class="sb-action-caption">{t("actions.quick")}</div>', unsafe_allow_html=True)
    a1, a2, a3 = st.columns([1.45, 1.0, 1.15])
    with a1:
        with st.popover(t("actions.report")):
            if "auth_token" not in st.session_state:
                st.warning(t("actions.login"))
            else:
                b1, b2, b3 = st.columns(3)
                if b1.button(t("actions.available"), key=f"btn_ok_{ist_key}"):
                    ok, msg = yorum_gonder(ist_id, "Uygun", "Uygun", {})
                    bildirim_goster(msg, ok)
                if b2.button(t("actions.issue"), key=f"btn_fail_{ist_key}"):
                    ok, msg = yorum_gonder(ist_id, "Sorun var", "Sorun var", {})
                    bildirim_goster(msg, ok)
                if b3.button(t("actions.queue"), key=f"btn_queue_{ist_key}"):
                    ok, msg = yorum_gonder(ist_id, "Sıra var", "Sıra var", {})
                    bildirim_goster(msg, ok)
    with a2:
        is_fav = ist_key in st.session_state["favoriler"]
        if st.button(t("actions.saved") if is_fav else t("actions.save"), key=f"fav_{ist_key}"):
            favori_guncelle(ist_key, not is_fav)
            st.rerun()
    with a3:
        yakin_yerler_acik = st.button(t("actions.nearby"), key=f"btn_cevre_{ist_key}")

    if yakin_yerler_acik:
        yerler = yakin_cevre_getir(ist["enlem"], ist["boylam"], ayar_yaricap)
        if yerler:
            yer_html = "".join(
                f'<div class="sb-nearby-item"><span>{guvenli_metin(localize_text(y.get("isim")), 80)}</span><strong>{int(y.get("metre", 0))}m</strong></div>'
                for y in yerler
            )
            st.markdown(f'<div class="sb-nearby-list">{yer_html}</div>', unsafe_allow_html=True)
        else:
            st.info(t("actions.no_nearby"))


def hesap_paneli_ciz() -> None:
    with st.expander(t("account.title"), expanded=False):
        if not FIREBASE_ENABLED:
            st.info(t("account.firebase_required"))
            return

        if "auth_token" not in st.session_state:
            auth_form_ciz("account", entry_context=False)
        else:
            if not oturum_gecerli_tut():
                st.warning(t("account.session_failed"))
                st.rerun()
            st.caption(t("account.active"))
            if st.button(t("account.logout"), use_container_width=True):
                oturumu_temizle()
                st.rerun()


def alt_navigasyon_ciz(konum_hazir: bool) -> None:
    rota_aktif = st.session_state.get("rota_goster") is True
    hesap_aktif = st.session_state.get("account_panel_open") is True
    bekleme_aktif = st.session_state.get("bekleme_salonu_goster") is True
    st.markdown('<div class="sb-bottom-nav-anchor" aria-hidden="true"></div>', unsafe_allow_html=True)
    ana_col, harita_col, rota_col, hesap_col = st.columns(4, gap="small")

    with ana_col:
        if st.button(
            t("bottom.home"),
            key="bottom_home",
            icon=":material/home:",
            type="primary" if not rota_aktif and not hesap_aktif and not bekleme_aktif else "secondary",
            use_container_width=True,
        ):
            st.session_state["rota_goster"] = False
            st.session_state["account_panel_open"] = False
            st.session_state["bekleme_salonu_goster"] = False
            st.rerun()

    with harita_col:
        if st.button(
            t("bottom.map"),
            key="bottom_map",
            icon=":material/sports_esports:",
            type="primary" if bekleme_aktif else "secondary",
            use_container_width=True,
        ):
            bekleme_salonunu_ac()
            st.rerun()

    with rota_col:
        if st.button(
            t("bottom.routes"),
            key="bottom_routes",
            icon=":material/route:",
            type="primary" if rota_aktif else "secondary",
            use_container_width=True,
        ):
            if not konum_hazir:
                bildirim_goster(t("home.location_required"), basarili=False)
            else:
                st.session_state["rota_goster"] = True
                st.session_state["bekleme_salonu_goster"] = False
                st.session_state["account_panel_open"] = False
                st.rerun()

    with hesap_col:
        if st.button(
            t("bottom.account"),
            key="bottom_account",
            icon=":material/person:",
            type="primary" if hesap_aktif else "secondary",
            use_container_width=True,
        ):
            st.session_state["account_panel_open"] = not hesap_aktif
            st.session_state["bekleme_salonu_goster"] = False
            st.rerun()


def oturum_suresini_global_kontrol_et() -> None:
    if "auth_token" in st.session_state:
        oturum_gecerli_tut()


# 1. Başlangıç Ayarları
st.set_page_config(page_title="ŞarjBul", layout="centered", initial_sidebar_state="collapsed")
sentry_init()
load_css()
oturum_suresini_global_kontrol_et()
uygulama_akisini_hazirla()

if not st.session_state.get("sb_access_granted"):
    giris_ekrani_ciz()
    st.stop()

ust_bilgi_ciz()
rota_modu = st.session_state.get("rota_goster") is True

if st.session_state.get("bekleme_salonu_goster"):
    konum_hazir = (
        st.session_state.get("last_valid_lat") is not None
        and st.session_state.get("last_valid_lon") is not None
    )
    alt_navigasyon_ciz(konum_hazir)
    bekleme_salonu_ciz()
    st.stop()

istasyonlar_verisi = istasyonlari_yukle()
if not istasyonlar_verisi:
    istasyon_hata_state_ciz()
    st.stop()

st.session_state.setdefault("istasyon_son_yukleme", utc_isoformat())
veri_guncelleme_metni_ciz()

operator_secenekleri = sorted({
    str(ist.get("operator", "Bilinmiyor"))
    for ist in istasyonlar_verisi
    if str(ist.get("operator", "")).strip()
})

# 2. Konum Tespiti
user_lat, user_lon = None, None
if tarayici_konumu_okunmali_mi():
    try:
        st.session_state["browser_location_checked_at"] = utc_isoformat()
        konum_verisi = get_geolocation()
        if isinstance(konum_verisi, dict) and "coords" in konum_verisi:
            if konum_gecerli_mi(konum_verisi["coords"].get("latitude"), konum_verisi["coords"].get("longitude")):
                user_lat, user_lon = float(konum_verisi["coords"]["latitude"]), float(konum_verisi["coords"]["longitude"])
                user_lat, user_lon = konumu_sessiona_yaz(
                    user_lat,
                    user_lon,
                    KONUM_KAYNAGI_TARAYICI,
                )
    except Exception as e:
        logger.warning("Tarayıcı konumu okunamadı: %s", e, exc_info=True)

if user_lat is None: user_lat = st.session_state.get("last_valid_lat")
if user_lon is None: user_lon = st.session_state.get("last_valid_lon")

konum_hazir = user_lat is not None and user_lon is not None
manuel_konum_karti_goster = not (
    konum_hazir and st.session_state.get("konum_kaynagi") == KONUM_KAYNAGI_TARAYICI
)

alt_navigasyon_ciz(konum_hazir)
if st.session_state.get("account_panel_open"):
    st.markdown('<div id="hesap"></div>', unsafe_allow_html=True)
    hesap_paneli_ciz()
    st.stop()

if not rota_modu:
    ana_mod_secici_ciz()
    if manuel_konum_karti_goster:
        ana_konum_arama_ciz(konum_hazir, user_lat, user_lon)
    hizli_islemler_ciz()

# 3. Araç Kataloğu ve Katmanlı Arama
if rota_modu:
    (
        secilen_arac,
        batarya,
        sarj_yuzdesi,
        tuketim,
        guvenlik_marji,
        niyet,
        ayar_yaricap,
        soket_filtreleri,
        hiz_filtresi,
        operator_filtreleri,
        sadece_24_saat,
        haritayi_goster,
        menzil_filtresi,
        arama_metni,
    ) = arac_ayarlarini_sessiondan_getir()
else:
    (
        secilen_arac,
        batarya,
        sarj_yuzdesi,
        tuketim,
        guvenlik_marji,
        niyet,
        ayar_yaricap,
        soket_filtreleri,
        hiz_filtresi,
        operator_filtreleri,
        sadece_24_saat,
        haritayi_goster,
        menzil_filtresi,
        arama_metni,
    ) = arac_katalogu_ciz(operator_secenekleri)

guvenli_menzil = ((batarya * (sarj_yuzdesi / 100.0) / tuketim) * 100.0) * (1 - guvenlik_marji / 100.0)
if not rota_modu:
    rota_eylem_paneli_ciz(secilen_arac, guvenli_menzil, sarj_yuzdesi, konum_hazir)

if not konum_hazir:
    st.markdown(
        f"""
        <div class="sb-step-panel">
            <strong>{t("location.choose_for_route")}</strong>
            <span>{t("home.location_required_hint")}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

user_lat, user_lon = float(user_lat), float(user_lon)

if not st.session_state.get("rota_goster"):
    st.stop()

siralama_modu = {
    "Dengeli": "Öneri",
    "Yakın": "Mesafe",
    "Hızlı": "Hız",
    "Ekonomik": "Fiyat",
}.get(niyet, "Öneri")

# 4. Veri İşleme
durum_ozetleri = durum_ozetleri_getir()
arama_norm = arama_metni_normalize_et(arama_metni) if arama_metni else ""
aday_istasyonlar = istasyon_adaylarini_hazirla(
    istasyonlar_verisi,
    istasyon_veri_fingerprint_getir(istasyonlar_verisi),
    round(user_lat, 3),
    round(user_lon, 3),
    bool(menzil_filtresi),
    float(guvenli_menzil),
    int(sarj_yuzdesi),
    float(batarya),
    float(tuketim),
    tuple(soket_filtreleri),
    str(hiz_filtresi),
    tuple(operator_filtreleri),
    bool(sadece_24_saat),
    arama_norm,
    siralama_modu,
)
uygun_istasyonlar = istasyonlari_durum_ve_skorla(aday_istasyonlar, durum_ozetleri)

def ist_siralama(i: Dict) -> Tuple:
    risk_sirasi = 1 if i.get("ArizaDurumu") == "riskli" else 0
    if siralama_modu == "Öneri":
        return (risk_sirasi, -int(i.get("Skor", 0)), float(i["Mesafe"]))
    if siralama_modu == "Fiyat":
        return (risk_sirasi, float(i.get("_fiyat_sayi", 9999.0)), float(i["Mesafe"]))
    if siralama_modu == "Hız":
        return (risk_sirasi, -float(i.get("_hiz_sayi", 0.0)), float(i["Mesafe"]))
    return (risk_sirasi, float(i["Mesafe"]))

uygun_istasyonlar = sorted(uygun_istasyonlar, key=ist_siralama)

# 7. Favoriler
if "favoriler" not in st.session_state: st.session_state["favoriler"] = set()
if "auth_token" in st.session_state and oturum_gecerli_tut():
    uid_hash = auth_uid_hash_getir()
    favoriler_yuklu = st.session_state.get("favoriler_yuklendi") is True
    favoriler_kullanici_ayni = st.session_state.get("favoriler_uid_hash") == uid_hash
    if not favoriler_yuklu or not favoriler_kullanici_ayni:
        st.session_state["favoriler"] = set(favorileri_getir(uid_hash, st.session_state["auth_token"]))
        st.session_state["favoriler_uid_hash"] = uid_hash
        st.session_state["favoriler_yuklendi"] = True

# 8. Sonuç Kartları Çizimi
if uygun_istasyonlar:
    tahmin_gecmisini_top_adaylara_uygula(uygun_istasyonlar)
    uygun_istasyonlar = sorted(uygun_istasyonlar, key=ist_siralama)

    en_iyi = uygun_istasyonlar[0]
    en_iyi_key = str(en_iyi.get("_station_key") or clean_id_uret(istasyon_id_getir(en_iyi)))
    diger_istasyonlar = [
        istasyon
        for istasyon in uygun_istasyonlar[1:]
        if str(istasyon.get("_station_key") or clean_id_uret(istasyon_id_getir(istasyon))) != en_iyi_key
    ]
    feed_istasyonlari = [en_iyi, *diger_istasyonlar]
    istasyon_akis_ciz(feed_istasyonlari, user_lat, user_lon)

    if haritayi_goster:
        harita_ciz(uygun_istasyonlar)

    if "auth_token" in st.session_state:
        aksiyon_istasyonu, aksiyon_key = istasyon_aksiyon_hedefi_sec(feed_istasyonlari)
        ist_id = istasyon_id_getir(aksiyon_istasyonu)
        istasyon_aksiyonlari_ciz(aksiyon_istasyonu, ist_id, aksiyon_key, ayar_yaricap)

else:
    st.markdown(
        f"""
        <div class="sb-empty-state">
            <strong>{t("empty.title")}</strong>
            <span>{t("empty.hint")}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="sb-filter-reset-action">', unsafe_allow_html=True)
    if st.button(t("empty.reset_filters"), key="reset_filters_empty", type="primary", use_container_width=True):
        filtreleri_sifirla()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
