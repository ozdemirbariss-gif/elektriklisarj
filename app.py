import json
import streamlit as st
import folium
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple
import streamlit.components.v1 as components
from streamlit_js_eval import get_geolocation
from streamlit_folium import st_folium

from config import (
    sentry_init, load_css, logger,
    ARAC_KATALOGU, HIZ_ESIK_MAP, KONUM_DOGRULAMA_ESIGI_KM,
    MAX_SON_YORUM, FIREBASE_ENABLED, YAKIN_CEVRE_MIN_M,
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
    istasyonlari_yukle, durum_ozetleri_getir,
    favorileri_getir, favori_guncelle, yorum_gonder, yakin_cevre_getir,
    oturum_bilgilerini_kaydet, oturum_gecerli_tut
)
from predictor import bosluk_tahmini_hesapla, tahmin_skoru_getir
from scoring import istasyon_rozetleri_getir, istasyon_skoru_hesapla


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

    if "auth_token" in st.session_state:
        st.session_state["sb_access_granted"] = True
        st.session_state["sb_guest_mode"] = False


def uygulama_girisini_ac(misafir: bool = False) -> None:
    st.session_state["sb_access_granted"] = True
    st.session_state["sb_guest_mode"] = misafir
    st.session_state["rota_goster"] = False


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
    login_tab, register_tab, reset_tab = st.tabs([t("auth.login"), t("auth.register"), t("auth.reset")])
    prefix = caller_context.strip().replace(" ", "_") or "auth"

    with login_tab:
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

    with register_tab:
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

    with reset_tab:
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
    st.markdown(
        f"""
        <section class="sb-entry-hero">
            <div class="sb-entry-mark">SarjBul</div>
            <h1>{t("auth.hero_title")}</h1>
            <p>{t("auth.hero_subtitle")}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    giris_formlari_ciz()


def ust_bilgi_ciz() -> None:
    oturumlu = "auth_token" in st.session_state
    hesap_metni = st.session_state.get("auth_email") if oturumlu else t("nav.guest")
    rota_aktif = st.session_state.get("rota_goster") is True
    adim_metni = t("nav.route_step") if rota_aktif else t("nav.vehicle_step")
    ilerleme = 100 if rota_aktif else 66
    geri_yardimi = t("nav.back_vehicle") if rota_aktif else t("nav.back_entry")

    st.markdown('<div class="sb-top-nav-anchor" aria-hidden="true"></div>', unsafe_allow_html=True)
    geri_col, durum_col, dil_col = st.columns([0.13, 0.64, 0.23], gap="small")

    with geri_col:
        if st.button("←", key="top_nav_back", help=geri_yardimi, use_container_width=True):
            if rota_aktif:
                st.session_state["rota_goster"] = False
                st.rerun()
            if oturumlu:
                oturumu_temizle()
            st.session_state["sb_access_granted"] = False
            st.session_state["sb_guest_mode"] = False
            st.session_state["rota_goster"] = False
            st.rerun()

    with durum_col:
        st.markdown(
            f"""
            <div class="sb-flow-top">
                <div class="sb-progress-track"><span style="width: {ilerleme}%"></span></div>
                <div class="sb-flow-meta">
                    <span>{adim_metni}</span>
                    <strong>{guvenli_metin(hesap_metni, 80)}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with dil_col:
        dil_secici_ciz("language_top")


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


def arac_katalogu_ciz(konum_hazir: bool, operator_secenekleri: List[str]) -> Tuple[
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

    st.markdown(
        f"""
        <div class="sb-catalog-meta">
            <div class="sb-catalog-stat"><span>{t("catalog.default_battery")}</span><strong>{float(v["batarya"]):.1f} kWh</strong></div>
            <div class="sb-catalog-stat"><span>{t("catalog.average_consumption")}</span><strong>{float(v["tuketim"]):.1f} kWh</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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

    if st.button(t("location.find_charger"), key="find_route_btn", use_container_width=True, disabled=not konum_hazir, type="primary"):
        st.session_state["rota_goster"] = True
        st.rerun()

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


def konumu_sessiona_yaz(lat: float, lon: float) -> Tuple[float, float]:
    onceki_lat = st.session_state.get("last_valid_lat")
    onceki_lon = st.session_state.get("last_valid_lon")
    if konum_gecerli_mi(onceki_lat, onceki_lon):
        fark_km = mesafe_hesapla(float(onceki_lat), float(onceki_lon), lat, lon)
        if fark_km <= KONUM_DOGRULAMA_ESIGI_KM:
            return float(onceki_lat), float(onceki_lon)

    st.session_state.update({"last_valid_lat": lat, "last_valid_lon": lon})
    return lat, lon


def manuel_konum_ciz() -> None:
    if st.session_state.get("manuel_konum_secimi") == "Seçiniz...":
        st.session_state["manuel_konum_secimi"] = ""
    manuel = st.selectbox(
        t("location.prompt"),
        ["", *SABIT_KONUMLAR.keys()],
        key="manuel_konum_secimi",
        format_func=lambda value: t("location.select") if not value else value,
    )
    if manuel in SABIT_KONUMLAR:
        secili_lat, secili_lon = SABIT_KONUMLAR[manuel]
        st.markdown(
            f"""
            <div class="sb-location-confirm">
                <strong>{guvenli_metin(manuel, 80)}</strong>
                <span>{secili_lat:.4f}°{t("location.north")}, {secili_lon:.4f}°{t("location.east")}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        mini_harita = folium.Map(
            location=[secili_lat, secili_lon],
            zoom_start=12,
            tiles="CartoDB dark_matter",
            control_scale=False,
            zoom_control=False,
        )
        folium.CircleMarker(
            location=[secili_lat, secili_lon],
            radius=9,
            color="#49FF9A",
            fill=True,
            fill_color="#49FF9A",
            fill_opacity=0.8,
            tooltip=manuel,
        ).add_to(mini_harita)
        st_folium(
            mini_harita,
            height=220,
            use_container_width=True,
            returned_objects=[],
            key=f"manual_location_map_{clean_id_uret(manuel)}",
        )
        if st.button(t("location.use_this"), key=f"use_manual_location_{clean_id_uret(manuel)}", type="primary", use_container_width=True):
            konumu_sessiona_yaz(secili_lat, secili_lon)
            st.rerun()

    with st.expander(t("location.coordinates"), expanded=False):
        lat = st.number_input(t("location.latitude"), min_value=-90.0, max_value=90.0, value=39.0000, step=0.0001, format="%.6f")
        lon = st.number_input(t("location.longitude"), min_value=-180.0, max_value=180.0, value=35.0000, step=0.0001, format="%.6f")
        if st.button(t("location.use"), use_container_width=True):
            if konum_gecerli_mi(lat, lon):
                konumu_sessiona_yaz(float(lat), float(lon))
                st.rerun()
            else:
                bildirim_goster(t("location.invalid"), basarili=False)


def harita_rengi_getir(skor: int) -> str:
    if skor >= 80:
        return "#55D28C"
    if skor >= 60:
        return "#F5CD5F"
    return "#E67878"


def harita_popup_html_olustur(istasyon: Dict[str, Any]) -> str:
    isim = kisa_deger(istasyon.get("isim"), t("common.station"), 90)
    operator = kisa_deger(istasyon.get("operator"), t("common.operator_unknown"), 70)
    skor = int(istasyon.get("Skor", 0) or 0)
    mesafe = float(istasyon.get("Mesafe", 0.0) or 0.0)
    guc = localize_text(kisa_duz_metin(istasyon.get("hiz"), t("common.power_unknown"), 42))
    durum = localize_text(kisa_duz_metin(istasyon.get("ArizaEtiketi"), t("common.live_data_none"), 60))
    renk = harita_rengi_getir(skor)
    return f"""
        <div style="min-width:190px;background:#111827;border:1px solid rgba(73,255,154,0.22);border-radius:12px;box-shadow:0 18px 40px rgba(0,0,0,0.34);color:#F7FAF7;font-family:Inter,Arial,sans-serif;padding:12px;">
            <div style="font-size:14px;font-weight:800;line-height:1.2;margin-bottom:4px;">{isim}</div>
            <div style="font-size:12px;color:rgba(247,250,247,0.62);margin-bottom:8px;">{operator}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
                <div style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:6px;">
                    <div style="font-size:10px;color:rgba(247,250,247,0.52);font-weight:700;">{t("map.score")}</div>
                    <div style="font-size:16px;font-weight:850;color:{renk};">{skor}</div>
                </div>
                <div style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:6px;">
                    <div style="font-size:10px;color:rgba(247,250,247,0.52);font-weight:700;">{t("map.distance")}</div>
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
        <div class="sb-drive-strip">
            <span>{kisa_deger(arac, max_len=36)}</span>
            <strong>{t("summary.safe_range_value", percent=sarj_yuzdesi, range=guvenli_menzil)}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def rota_linki_olustur(istasyon: Dict[str, Any], user_lat: float, user_lon: float) -> str:
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={user_lat},{user_lon}"
        f"&destination={istasyon['enlem']},{istasyon['boylam']}"
        "&travelmode=driving"
    )


def istasyon_akis_verisi_hazirla(
    istasyonlar: List[Dict[str, Any]],
    user_lat: float,
    user_lon: float,
) -> List[Dict[str, Any]]:
    toplam = len(istasyonlar)
    payload = []
    for sira, istasyon in enumerate(istasyonlar, start=1):
        son_yorumlar = []
        for yorum in istasyon.get("SonYorumlar", [])[:MAX_SON_YORUM]:
            son_yorumlar.append(
                {
                    "durum": localize_text(kisa_duz_metin(durum_metni_sadelestir(yorum.get("durum", "")), "", 32)),
                    "yorum": kisa_duz_metin(yorum.get("yorum", ""), "", 86),
                }
            )

        payload.append(
            {
                "rank": sira,
                "total": toplam,
                "featured": sira == 1,
                "eyebrow": t("feed.nearest") if sira == 1 else t("feed.nearby_option"),
                "name": kisa_duz_metin(istasyon.get("isim"), t("common.station"), 118),
                "operator": kisa_duz_metin(istasyon.get("operator"), t("common.operator_unknown"), 64),
                "address": localize_text(kisa_duz_metin(istasyon.get("adres"), t("common.address_missing"), 160)),
                "distance": f"{float(istasyon.get('Mesafe', 0.0) or 0.0):.1f} km",
                "duration": f"{int(istasyon.get('TahminiSureDk', 0) or 0)} {t('feed.minute')}",
                "arrival": f"%{float(istasyon.get('VarisSarjYuzdesi', 0.0) or 0.0):.0f}",
                "power": localize_text(kisa_duz_metin(istasyon.get("hiz"), t("common.power_unknown"), 42)),
                "socket": localize_text(kisa_duz_metin(istasyon.get("soket"), t("common.socket_unknown"), 42)),
                "price": localize_text(kisa_duz_metin(istasyon.get("fiyat"), t("common.price_missing"), 42)),
                "status": localize_text(kisa_duz_metin(istasyon.get("ArizaEtiketi"), t("common.live_data_none"), 48)),
                "score": int(istasyon.get("Skor", 0) or 0),
                "routeUrl": rota_linki_olustur(istasyon, user_lat, user_lon),
                "chips": [
                    {"text": localize_text(kisa_duz_metin(metin, "", 38)), "className": kisa_duz_metin(css_class, "", 32)}
                    for metin, css_class in istasyon.get("Rozetler", [])
                ],
                "comments": son_yorumlar,
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
            "notification": t("feed.notification"),
            "score": t("feed.score"),
            "power": t("feed.power"),
            "socket": t("feed.socket"),
            "price": t("feed.price"),
            "openRoute": t("feed.open_route"),
            "googleMaps": t("feed.google_maps"),
            "goToStation": t("feed.go_to_station", index="{index}"),
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    feed_html = """
        <section class="sb-feed-shell" id="rotayi-ac" aria-label="__FEED_ARIA__">
            <div class="sb-feed-viewport" id="station-feed" tabindex="0" aria-live="polite">
                <div class="sb-feed-track" id="station-track">
                    <div class="sb-feed-spacer" id="station-top-spacer"></div>
                    <div class="sb-feed-window" id="station-window"></div>
                    <div class="sb-feed-spacer" id="station-bottom-spacer"></div>
                </div>
            </div>
            <div class="sb-feed-controls" aria-label="__FEED_CONTROLS__">
                <div class="sb-feed-dots" id="station-dots" aria-label="__FEED_POSITION__"></div>
                <div class="sb-feed-hint" aria-hidden="true">__FEED_HINT__</div>
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
            const dots = document.getElementById("station-dots");
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

            function commentHtml(comments) {
                return comments.length
                    ? `<div class="sb-feed-comments">${comments.map((item) => `
                        <div><strong>${esc(item.durum || labels.notification)}</strong><span>${esc(item.yorum)}</span></div>
                    `).join("")}</div>`
                    : "";
            }

            function cardHtml(station, index) {
                const rank = String(station.rank).padStart(2, "0");
                return `
                    <article
                        class="sb-feed-card ${station.featured ? "is-featured" : ""}"
                        data-card-index="${index}"
                        aria-label="${esc(station.name)}"
                    >
                        <div class="sb-feed-glow"></div>
                        <div class="sb-feed-top">
                            <div class="sb-feed-title">
                                <div class="sb-feed-eyebrow">${esc(station.eyebrow)}</div>
                                <h2>${esc(station.name)}</h2>
                                <p>${esc(station.operator)}</p>
                            </div>
                            <div class="sb-feed-head-actions">
                                <div class="sb-feed-head-score">
                                    <strong>${station.score}</strong>
                                    <span>${esc(labels.score)}</span>
                                </div>
                                <div class="sb-feed-bookmark" aria-hidden="true">♡</div>
                                <div class="sb-feed-counter">
                                    <strong>${rank}</strong>
                                    <span>/ ${station.total}</span>
                                </div>
                            </div>
                        </div>
                        <div class="sb-feed-hero">
                            <strong>${esc(station.distance)}</strong>
                            <span>${esc(station.duration)} · ${esc(labels.arrival)} ${esc(station.arrival)}</span>
                        </div>
                        <div class="sb-feed-score-row">
                            <div class="sb-feed-status">${esc(station.status)}</div>
                        </div>
                        <div class="sb-feed-grid">
                            <div><span>${esc(labels.power)}</span><strong>${esc(station.power)}</strong></div>
                            <div><span>${esc(labels.socket)}</span><strong>${esc(station.socket)}</strong></div>
                            <div><span>${esc(labels.price)}</span><strong>${esc(station.price)}</strong></div>
                        </div>
                        ${chipHtml(station.chips)}
                        ${commentHtml(station.comments)}
                        <div class="sb-feed-address">${esc(station.address)}</div>
                        <a class="sb-feed-route" href="${esc(station.routeUrl)}" target="_blank" rel="noopener noreferrer">
                            <span>${esc(labels.openRoute)}</span><small>${esc(labels.googleMaps)}</small>
                        </a>
                    </article>
                `;
            }

            function renderDots() {
                const maxDots = Math.min(7, stations.length);
                const dotStart = Math.max(0, Math.min(visibleIndex - Math.floor(maxDots / 2), stations.length - maxDots));
                dots.innerHTML = Array.from({ length: maxDots }, (_, offset) => {
                    const index = dotStart + offset;
                    const classes = [
                        "sb-feed-dot",
                        index === visibleIndex ? "is-active" : "",
                        index === 0 || index === stations.length - 1 ? "is-edge" : ""
                    ].filter(Boolean).join(" ");
                    const dotLabel = labels.goToStation.replace("{index}", String(index + 1));
                    return `<button class="${classes}" type="button" data-target="${index}" aria-label="${esc(dotLabel)}"></button>`;
                }).join("");
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
                renderDots();
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

            dots.addEventListener("click", (event) => {
                const button = event.target.closest("button[data-target]");
                if (!button) return;
                scrollToIndex(Number(button.dataset.target));
            });

            window.addEventListener("resize", () => {
                updateSpacers();
                viewport.scrollTop = activeIndex * frameHeight();
                scheduleSyncMotion();
            }, { passive: true });

            renderWindow();
        </script>
        <style>
            :root {
                color-scheme: light;
                --feed-bg: #F6FAF8;
                --feed-text: #1F2D2B;
                --feed-soft: rgba(31, 45, 43, 0.68);
                --feed-muted: rgba(31, 45, 43, 0.46);
                --feed-green: #78DAB5;
                --feed-blue: #82CFF1;
                --feed-frame-height: 640px;
                --feed-controls-height: 44px;
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
                background:
                    radial-gradient(circle at 50% 8%, rgba(120, 218, 181, 0.20), transparent 34%),
                    radial-gradient(circle at 90% 70%, rgba(130, 207, 241, 0.20), transparent 30%),
                    linear-gradient(180deg, rgba(255, 255, 255, 0.50), rgba(238, 247, 244, 0.92));
                display: grid;
                grid-template-rows: var(--feed-frame-height) var(--feed-controls-height);
                height: calc(var(--feed-frame-height) + var(--feed-controls-height));
                overflow: hidden;
                position: relative;
                width: 100%;
            }

            .sb-feed-viewport {
                grid-row: 1;
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
                padding: 10px 0 18px;
                scroll-snap-align: center;
                scroll-snap-stop: always;
            }

            .sb-feed-card {
                --sb-card-opacity: 0.44;
                --sb-card-scale: 0.92;
                --sb-card-shift: 24px;
                background:
                    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.72)),
                    linear-gradient(160deg, rgba(246, 250, 248, 0.98), rgba(238, 247, 244, 0.96));
                border: 1px solid rgba(104, 132, 124, 0.15);
                border-radius: 22px;
                box-shadow: 0 24px 58px rgba(54, 77, 72, 0.12), 0 16px 42px rgba(120, 218, 181, 0.10);
                color: var(--feed-text);
                display: flex;
                flex-direction: column;
                height: calc(var(--feed-frame-height) - 28px);
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
                box-shadow: 0 18px 44px rgba(54, 77, 72, 0.10), 0 12px 32px rgba(120, 218, 181, 0.08);
            }

            .sb-feed-card.is-featured {
                box-shadow: 0 26px 62px rgba(54, 77, 72, 0.14), 0 18px 48px rgba(120, 218, 181, 0.14);
            }

            .sb-feed-glow {
                background:
                    linear-gradient(90deg, transparent, rgba(120, 218, 181, 0.54), rgba(130, 207, 241, 0.42), transparent);
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
                background: linear-gradient(135deg, rgba(120, 218, 181, 0.24), rgba(130, 207, 241, 0.20));
                border: 1px solid rgba(120, 218, 181, 0.32);
                border-radius: 16px;
                box-shadow: 0 10px 24px rgba(120, 218, 181, 0.14);
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
                border: 1px solid rgba(104, 132, 124, 0.13);
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
                box-shadow: 0 14px 28px rgba(120, 218, 181, 0.22);
                color: #17302C;
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
                background: rgba(255, 255, 255, 0.58);
                border: 1px solid rgba(104, 132, 124, 0.13);
                border-radius: 18px;
                color: var(--feed-soft);
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
                background: rgba(255, 255, 255, 0.58);
                border: 1px solid rgba(104, 132, 124, 0.13);
                border-radius: 18px;
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
                background: rgba(120, 218, 181, 0.18);
                border: 1px solid rgba(120, 218, 181, 0.34);
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
                background: rgba(130, 207, 241, 0.16);
                border-color: rgba(130, 207, 241, 0.34);
                color: #62BDE8;
            }

            .sb-feed-chip-help {
                appearance: none;
                background: rgba(255, 255, 255, 0.68);
                border: 1px solid rgba(104, 132, 124, 0.15);
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
                border: 1px solid rgba(104, 132, 124, 0.13);
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
                box-shadow: 0 18px 36px rgba(120, 218, 181, 0.24), 0 8px 24px rgba(130, 207, 241, 0.18);
                color: #17302C;
                display: flex;
                justify-content: space-between;
                margin-top: 15px;
                min-height: 58px;
                padding: 13px 15px;
                position: relative;
                text-decoration: none;
                z-index: 2;
            }

            .sb-feed-route span {
                font-family: var(--feed-font-display);
                font-size: 16px;
                font-weight: 850;
            }

            .sb-feed-route small {
                font-size: 11px;
                font-weight: 800;
                opacity: 0.66;
            }

            .sb-feed-controls {
                align-items: center;
                background: rgba(246, 250, 248, 0.88);
                border-top: 1px solid rgba(104, 132, 124, 0.10);
                display: flex;
                gap: 12px;
                grid-row: 2;
                justify-content: space-between;
                min-width: 0;
                padding: 7px 14px;
                position: relative;
                z-index: 6;
            }

            .sb-feed-dots {
                align-items: center;
                display: flex;
                gap: 8px;
                justify-content: flex-start;
                pointer-events: auto;
            }

            .sb-feed-dot {
                appearance: none;
                background: rgba(31, 45, 43, 0.32);
                border: 1px solid rgba(255, 255, 255, 0.38);
                border-radius: 999px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
                cursor: pointer;
                height: 8px;
                opacity: 0.92;
                padding: 0;
                transition: background 180ms ease, box-shadow 180ms ease, transform 180ms ease, width 180ms ease;
                width: 8px;
            }

            .sb-feed-dot.is-edge {
                opacity: 0.48;
                transform: scale(0.82);
            }

            .sb-feed-dot.is-active {
                background: linear-gradient(90deg, var(--feed-green), var(--feed-blue));
                box-shadow: 0 0 18px rgba(120, 218, 181, 0.45);
                opacity: 1;
                transform: scale(1);
                width: 30px;
            }

            .sb-feed-hint {
                background: rgba(255, 255, 255, 0.68);
                border: 1px solid rgba(104, 132, 124, 0.12);
                border-radius: 999px;
                color: var(--feed-soft);
                font-size: 11px;
                font-weight: 850;
                padding: 7px 12px;
                pointer-events: none;
                white-space: nowrap;
            }

            @keyframes sbHintFloat {
                0%, 100% { transform: translateY(0); }
                50% { transform: translateY(-2px); }
            }

            .sb-feed-hint {
                animation: sbHintFloat 2.2s ease-in-out infinite;
            }

            @media (prefers-reduced-motion: reduce) {
                .sb-feed-viewport {
                    scroll-behavior: auto;
                }

                .sb-feed-card,
                .sb-feed-dot,
                .sb-feed-hint {
                    animation: none;
                    transition: none;
                }
            }

            @media (max-width: 430px) {
                :root {
                    --feed-frame-height: 636px;
                }

                .sb-feed-slide {
                    padding: 8px 0 12px;
                }

                .sb-feed-card {
                    height: calc(var(--feed-frame-height) - 20px);
                    padding: 18px 14px 14px;
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
        </style>
    """.replace("__STATIONS_JSON__", payload_json)
    feed_html = (
        feed_html
        .replace("__LABELS_JSON__", labels_json)
        .replace("__FEED_ARIA__", guvenli_metin(t("feed.aria"), 80))
        .replace("__FEED_CONTROLS__", guvenli_metin(t("feed.controls"), 80))
        .replace("__FEED_POSITION__", guvenli_metin(t("feed.position"), 80))
        .replace("__FEED_HINT__", guvenli_metin(t("feed.swipe_hint"), 50))
    )

    st.markdown('<div class="sb-route-feed-mode" aria-hidden="true"></div>', unsafe_allow_html=True)
    components.html(
        feed_html,
        height=692,
        scrolling=False,
    )


def istasyon_aksiyonlari_ciz(ist: Dict[str, Any], ist_id: str, ist_key: str, ayar_yaricap: int) -> None:
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
try:
    konum_verisi = get_geolocation()
    if isinstance(konum_verisi, dict) and "coords" in konum_verisi:
        if konum_gecerli_mi(konum_verisi["coords"].get("latitude"), konum_verisi["coords"].get("longitude")):
            user_lat, user_lon = float(konum_verisi["coords"]["latitude"]), float(konum_verisi["coords"]["longitude"])
            user_lat, user_lon = konumu_sessiona_yaz(user_lat, user_lon)
except Exception as e:
    logger.warning("Tarayıcı konumu okunamadı: %s", e, exc_info=True)

if user_lat is None: user_lat = st.session_state.get("last_valid_lat")
if user_lon is None: user_lon = st.session_state.get("last_valid_lon")

konum_hazir = user_lat is not None and user_lon is not None

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
    ) = arac_katalogu_ciz(konum_hazir, operator_secenekleri)

guvenli_menzil = ((batarya * (sarj_yuzdesi / 100.0) / tuketim) * 100.0) * (1 - guvenlik_marji / 100.0)
if not rota_modu:
    surus_ozeti_ciz(secilen_arac, guvenli_menzil, sarj_yuzdesi)

if not konum_hazir:
    st.markdown(
        f"""
        <div class="sb-step-panel">
            <strong>{t("location.choose_for_route")}</strong>
            <span>{t("location.ready_hint")}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    manuel_konum_ciz()
    st.stop()

user_lat, user_lon = float(user_lat), float(user_lon)

if not st.session_state.get("rota_goster"):
    st.markdown(
        f"""
        <div class="sb-step-panel">
            <strong>{t("route.ready")}</strong>
            <span>{t("route.ready_hint")}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

siralama_modu = {
    "Dengeli": "Öneri",
    "Yakın": "Mesafe",
    "Hızlı": "Hız",
    "Ekonomik": "Fiyat",
}.get(niyet, "Öneri")

# 4. Veri İşleme
durum_ozetleri = durum_ozetleri_getir()
uygun_istasyonlar = []
for ist in istasyonlar_verisi:
    kus_ucusu = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    tahmini = tahmini_yol_mesafesi_km(kus_ucusu)
    if menzil_filtresi and tahmini > guvenli_menzil: continue
    if soket_filtreleri and not any(sf.upper() in str(ist.get("_soket_upper")).upper() for sf in soket_filtreleri): continue
    if hiz_filtresi != "Tümü" and float(ist.get("_hiz_sayi", 0.0)) < HIZ_ESIK_MAP.get(hiz_filtresi, 0.0): continue
    if operator_filtreleri and str(ist.get("operator")) not in operator_filtreleri: continue
    if sadece_24_saat and not ist.get("_acik_24_saat"): continue
    if arama_metni and arama_metni_normalize_et(arama_metni) not in str(ist.get("_search_text", "")): continue

    ist_key = str(ist.get("_station_key") or clean_id_uret(istasyon_id_getir(ist)))
    ariza = {**durum_ozeti_fallback(), **durum_ozetleri.get(ist_key, {})}
    tahmini_sure = tahmini_sure_dk(tahmini)
    hedef_zaman = utc_simdi() + timedelta(minutes=tahmini_sure)
    bosluk_tahmini = bosluk_tahmini_hesapla(ariza.get("son_yorumlar", []), hedef_zaman=hedef_zaman)

    ist_kopya = ist.copy()
    ist_kopya.update({
        "Mesafe": round(tahmini, 1),
        "KusUcusuMesafe": round(kus_ucusu, 1),
        "TahminiSureDk": tahmini_sure,
        "VarisSarjYuzdesi": varis_sarj_yuzdesi_hesapla(sarj_yuzdesi, batarya, tuketim, tahmini),
        "KalanGuvenliMenzil": max(0.0, guvenli_menzil - tahmini),
        "ArizaDurumu": ariza.get("durum"),
        "ArizaEtiketi": ariza.get("etiket"),
        "SonYorumlar": ariza.get("son_yorumlar", []),
        "BoslukTahmini": bosluk_tahmini,
        "TahminSkoru": tahmin_skoru_getir(bosluk_tahmini),
    })
    ist_kopya["Skor"] = istasyon_skoru_hesapla(ist_kopya)
    ist_kopya["Rozetler"] = istasyon_rozetleri_getir(ist_kopya)
    uygun_istasyonlar.append(ist_kopya)

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
    for ist in uygun_istasyonlar:
        istasyon_tahminini_guncelle(ist, ist.get("SonYorumlar", []))
    uygun_istasyonlar = sorted(
        uygun_istasyonlar,
        key=lambda i: (
            1 if i.get("ArizaDurumu") == "riskli" else 0,
            float(i.get("Mesafe", 9999.0) or 9999.0),
            -int(i.get("Skor", 0) or 0),
        ),
    )

    en_iyi = uygun_istasyonlar[0]
    en_iyi_key = str(en_iyi.get("_station_key") or clean_id_uret(istasyon_id_getir(en_iyi)))
    diger_istasyonlar = [
        istasyon
        for istasyon in uygun_istasyonlar[1:]
        if str(istasyon.get("_station_key") or clean_id_uret(istasyon_id_getir(istasyon))) != en_iyi_key
    ]
    istasyon_akis_ciz([en_iyi, *diger_istasyonlar], user_lat, user_lon)

    if haritayi_goster:
        harita_ciz(uygun_istasyonlar)

    if "auth_token" in st.session_state:
        ist_id = istasyon_id_getir(en_iyi)
        istasyon_aksiyonlari_ciz(en_iyi, ist_id, en_iyi_key, ayar_yaricap)
    else:
        st.markdown(
            f"""
            <div class="sb-step-panel">
                <strong>{t("route.guest_action")}</strong>
                <span>{t("route.guest_hint")}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
