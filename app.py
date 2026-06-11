import streamlit as st
import hashlib
from datetime import timedelta
from typing import Any, Dict, List, Tuple
from streamlit_js_eval import get_geolocation

from config import (
    sentry_init, load_css, logger, MAX_ISTASYON_SAYISI, MAX_EKRAN_KART_SAYISI,
    ARAC_KATALOGU, YOL_UZAMA_KATSAYISI, HIZ_ESIK_MAP, KONUM_DOGRULAMA_ESIGI_KM,
    MAX_SON_YORUM, MAX_YORUM_KARAKTER, FIREBASE_ENABLED
)
from utils import (
    guvenli_metin, arama_metni_normalize_et, clean_id_uret, istasyon_id_getir,
    auth_uid_hash_getir, tahmini_sure_dk, varis_sarj_yuzdesi_hesapla, 
    mesafe_hesapla, tahmini_yol_mesafesi_km, konum_gecerli_mi, durum_metni_sadelestir, durum_ozeti_fallback, token_suresi_doldu_mu,
    utc_simdi, utc_isoformat
)
from services import (
    firebase_login, firebase_register, firebase_sifre_sifirla, oturumu_temizle,
    istasyonlari_yukle, durum_ozetleri_getir, gorunen_yorumlari_getir, tahmin_yorumlari_getir,
    favorileri_getir, favori_guncelle, yorum_gonder, yakin_cevre_getir
)
from predictor import bosluk_tahmini_hesapla, tahmin_rozetleri_getir, tahmin_skoru_getir


def guvenli_html(deger: Any, max_len: int = 140) -> str:
    return guvenli_metin(deger, max_len)


def kisa_deger(deger: Any, varsayilan: str = "Bilinmiyor", max_len: int = 80) -> str:
    text = str(deger or "").strip() or varsayilan
    return guvenli_html(text, max_len)


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


def rozet_html(rozetler: List[Tuple[str, str]]) -> str:
    return "".join(
        f'<span class="sb-chip {css_class}">{guvenli_html(metin, 40)}</span>'
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
                <div class="sb-kicker">Güvenli menzil</div>
                <div class="sb-summary-value">{guvenli_menzil:.0f} km</div>
                <div class="sb-summary-sub">Filtre hesabı</div>
            </div>
            <div class="sb-summary-item">
                <div class="sb-kicker">Şarj durumu</div>
                <div class="sb-summary-value">%{sarj_yuzdesi}</div>
                <div class="sb-summary-sub">Mevcut batarya</div>
            </div>
            <div class="sb-summary-item">
                <div class="sb-kicker">Veri havuzu</div>
                <div class="sb-summary-value">{istasyon_sayisi}</div>
                <div class="sb-summary-sub">Normalize kayıt</div>
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
            <strong>%{sarj_yuzdesi} · {guvenli_menzil:.0f} km güvenli menzil</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def en_iyi_secim_ciz(istasyon: Dict[str, Any], rota_linki: str) -> None:
    st.markdown(
        f"""
        <div class="sb-best-card">
            <div class="sb-best-top">
                <div>
                    <div class="sb-kicker">Şimdi şarj için en iyi durak</div>
                    <div class="sb-best-title">{kisa_deger(istasyon.get("isim"), max_len=96)}</div>
                </div>
                <div class="sb-score"><strong>{int(istasyon.get("Skor", 0))}</strong><span>PUAN</span></div>
            </div>
            <div class="sb-best-grid">
                <div class="sb-mini-stat"><div class="sb-mini-label">Mesafe</div><div class="sb-mini-value">{float(istasyon.get("Mesafe", 0.0)):.1f} km</div></div>
                <div class="sb-mini-stat"><div class="sb-mini-label">Süre</div><div class="sb-mini-value">{int(istasyon.get("TahminiSureDk", 0))} dk</div></div>
                <div class="sb-mini-stat"><div class="sb-mini-label">Varış</div><div class="sb-mini-value">%{float(istasyon.get("VarisSarjYuzdesi", 0.0)):.0f}</div></div>
            </div>
            <a class="sb-route-button sb-route-primary" href="{guvenli_html(rota_linki, 260)}" target="_blank" rel="noopener noreferrer">
                <span class="sb-route-main">Rotayı aç</span>
                <span class="sb-route-sub">Google Maps ile yol tarifi</span>
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def istasyon_karti_ciz(istasyon: Dict[str, Any], sira: int, rota_linki: str) -> None:
    st.markdown(
        f"""
        <div class="sb-station-card">
            <div class="sb-station-top">
                <div>
                    <div class="sb-kicker">#{sira + 1} seçenek</div>
                    <div class="sb-station-title">{kisa_deger(istasyon.get("isim"), max_len=110)}</div>
                </div>
                <div class="sb-score"><strong>{int(istasyon.get("Skor", 0))}</strong><span>PUAN</span></div>
            </div>
            <div class="sb-station-grid">
                <div class="sb-mini-stat"><div class="sb-mini-label">Mesafe</div><div class="sb-mini-value">{float(istasyon.get("Mesafe", 0.0)):.1f} km</div></div>
                <div class="sb-mini-stat"><div class="sb-mini-label">Güç</div><div class="sb-mini-value">{kisa_deger(istasyon.get("hiz"), max_len=36)}</div></div>
                <div class="sb-mini-stat"><div class="sb-mini-label">Soket</div><div class="sb-mini-value">{kisa_deger(istasyon.get("soket"), max_len=42)}</div></div>
                <div class="sb-mini-stat"><div class="sb-mini-label">Operatör</div><div class="sb-mini-value">{kisa_deger(istasyon.get("operator"), max_len=42)}</div></div>
                <div class="sb-mini-stat"><div class="sb-mini-label">Varış şarjı</div><div class="sb-mini-value">%{float(istasyon.get("VarisSarjYuzdesi", 0.0)):.0f}</div></div>
                <div class="sb-mini-stat"><div class="sb-mini-label">Fiyat</div><div class="sb-mini-value">{kisa_deger(istasyon.get("fiyat"), max_len=42)}</div></div>
            </div>
            <div class="sb-chip-row">{rozet_html(istasyon.get("Rozetler", []))}</div>
            <div class="sb-address">{kisa_deger(istasyon.get("adres"), max_len=180)}</div>
            <a class="sb-route-button" href="{guvenli_html(rota_linki, 260)}" target="_blank" rel="noopener noreferrer">
                <span class="sb-route-main">Rotayı aç</span>
                <span class="sb-route-sub">Google Maps ile yol tarifi</span>
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def istasyon_aksiyonlari_ciz(ist: Dict[str, Any], ist_id: str, ist_key: str, ayar_yaricap: int) -> None:
    st.markdown('<div class="sb-action-caption">Hızlı işlemler</div>', unsafe_allow_html=True)
    a1, a2, a3 = st.columns([1.45, 1.0, 1.15])
    with a1:
        with st.popover("Durum bildir"):
            if "auth_token" not in st.session_state:
                st.warning("Giriş yapın.")
            else:
                b1, b2, b3 = st.columns(3)
                if b1.button("Uygun", key=f"btn_ok_{ist_key}"):
                    ok, msg = yorum_gonder(ist_id, "Uygun", "Uygun", {})
                    st.success(msg) if ok else st.error(msg)
                if b2.button("Sorun", key=f"btn_fail_{ist_key}"):
                    ok, msg = yorum_gonder(ist_id, "Sorun var", "Sorun var", {})
                    st.success(msg) if ok else st.error(msg)
                if b3.button("Sıra", key=f"btn_queue_{ist_key}"):
                    ok, msg = yorum_gonder(ist_id, "Sıra var", "Sıra var", {})
                    st.success(msg) if ok else st.error(msg)
    with a2:
        is_fav = ist_key in st.session_state["favoriler"]
        if st.button("Kayıtlı" if is_fav else "Kaydet", key=f"fav_{ist_key}"):
            favori_guncelle(ist_key, not is_fav)
            st.rerun()
    with a3:
        yakin_yerler_acik = st.button("Yakın yerler", key=f"btn_cevre_{ist_key}")

    if yakin_yerler_acik:
        yerler = yakin_cevre_getir(ist["enlem"], ist["boylam"], ayar_yaricap)
        if yerler:
            yer_html = "".join(
                f'<div class="sb-nearby-item"><span>{guvenli_html(y.get("isim"), 80)}</span><strong>{int(y.get("metre", 0))}m</strong></div>'
                for y in yerler
            )
            st.markdown(f'<div class="sb-nearby-list">{yer_html}</div>', unsafe_allow_html=True)
        else:
            st.info("Yakında gösterilecek yer bulunamadı.")


def hesap_paneli_ciz() -> None:
    with st.expander("Hesap", expanded=False):
        if not FIREBASE_ENABLED:
            st.info("Hesap, favori ve bildirim özellikleri için Firebase bağlantısı yapılandırılmalı.")
            return

        if "auth_token" not in st.session_state:
            tab_giris, tab_kayit, tab_sifre = st.tabs(["Giriş", "Kayıt", "Şifre"])
            with tab_giris:
                email = st.text_input("E-posta", key="login_email")
                password = st.text_input("Şifre", type="password", key="login_password")
                if st.button("Giriş Yap", use_container_width=True):
                    user_data = firebase_login(email, password)
                    if user_data:
                        st.session_state.update({"auth_token": user_data["idToken"], "auth_email": user_data.get("email", ""), "auth_uid": user_data.get("localId", ""), "auth_login_time": utc_isoformat()})
                        st.rerun()
                    else:
                        st.error("Giriş başarısız.")
            with tab_kayit:
                reg_email = st.text_input("E-posta", key="reg_email")
                reg_password = st.text_input("Şifre", type="password", key="reg_password")
                if st.button("Kayıt Ol", use_container_width=True):
                    user_data = firebase_register(reg_email, reg_password)
                    if user_data:
                        st.session_state.update({"auth_token": user_data["idToken"], "auth_email": user_data.get("email", ""), "auth_uid": user_data.get("localId", ""), "auth_login_time": utc_isoformat()})
                        st.rerun()
                    else:
                        st.error("Kayıt başarısız.")
            with tab_sifre:
                reset_email = st.text_input("E-posta Adresiniz", key="reset_email")
                if st.button("Sıfırlama Bağlantısı Gönder"):
                    ok, msg = firebase_sifre_sifirla(reset_email)
                    st.success(msg) if ok else st.error(msg)
        else:
            st.success("Hesap aktif.")
            if st.button("Çıkış Yap", use_container_width=True):
                oturumu_temizle()
                st.rerun()


def oturum_suresini_global_kontrol_et() -> None:
    if "auth_token" in st.session_state and token_suresi_doldu_mu():
        oturumu_temizle()
        st.session_state["favoriler"] = set()


# 1. Başlangıç Ayarları
st.set_page_config(page_title="ŞarjBul", layout="centered", initial_sidebar_state="collapsed")
sentry_init()
load_css()
oturum_suresini_global_kontrol_et()

st.markdown(
    """
    <section class="sb-hero-card">
        <div class="sb-hero-media" aria-label="Gece elektrikli araç şarj istasyonu"></div>
        <div class="sb-hero-body">
            <div class="sb-hero-kicker">Yakındaki şarj rotan</div>
            <h1>ŞarjBul</h1>
            <p>Bana en mantıklı şarj durağını göster.</p>
        </div>
    </section>
    """,
    unsafe_allow_html=True,
)

istasyonlar_verisi = istasyonlari_yukle()
if not istasyonlar_verisi: st.stop()

# 2. Konum Tespiti
user_lat, user_lon = None, None
try:
    konum_verisi = get_geolocation()
    if isinstance(konum_verisi, dict) and "coords" in konum_verisi:
        if konum_gecerli_mi(konum_verisi["coords"].get("latitude"), konum_verisi["coords"].get("longitude")):
            user_lat, user_lon = float(konum_verisi["coords"]["latitude"]), float(konum_verisi["coords"]["longitude"])
            st.session_state.update({"last_valid_lat": user_lat, "last_valid_lon": user_lon})
except Exception: pass

if user_lat is None: user_lat = st.session_state.get("last_valid_lat")
if user_lon is None: user_lon = st.session_state.get("last_valid_lon")

if user_lat is None or user_lon is None:
    manuel = st.selectbox("Lütfen Mevcut Konumunuzu Seçin:", ["Seçiniz...", "İstanbul (Kadıköy)", "Ankara (Çankaya)", "İzmir (Alsancak)"])
    SABIT_K = {"İstanbul (Kadıköy)": (40.9901, 29.0284), "Ankara (Çankaya)": (39.9208, 32.8541), "İzmir (Alsancak)": (38.4374, 27.1422)}
    if manuel in SABIT_K:
        st.session_state.update({"last_valid_lat": SABIT_K[manuel][0], "last_valid_lon": SABIT_K[manuel][1]})
        st.rerun()
    st.stop()

# 3. Sessiz Varsayılanlar ve Gelişmiş Ayarlar
operator_secenekleri = sorted({str(ist.get("operator", "Bilinmiyor")) for ist in istasyonlar_verisi if str(ist.get("operator", "")).strip()})
secilen_arac = list(ARAC_KATALOGU.keys())[0]
niyet = "Dengeli"
ayar_yaricap = 400
sonuc_sayisi = min(3, MAX_EKRAN_KART_SAYISI)
soket_filtreleri: List[str] = []
hiz_filtresi = "Tümü"
operator_filtreleri: List[str] = []
sadece_24_saat = False
haritayi_goster = False
menzil_filtresi = True
arama_metni = ""

with st.expander("Gelişmiş ayarlar", expanded=False):
    niyet = st.radio("Tercih", ["Dengeli", "Yakın", "Hızlı", "Ekonomik"], horizontal=True)
    secilen_arac = st.selectbox("Araç", list(ARAC_KATALOGU.keys()))
    v = ARAC_KATALOGU[secilen_arac]
    c1, c2, c3 = st.columns(3)
    batarya = c1.number_input("Kapasite", 1.0, 250.0, float(v["batarya"]))
    sarj_yuzdesi = c2.slider("Şarj %", 1, 100, 30)
    tuketim = c3.number_input("Tüketim", 5.0, 40.0, float(v["tuketim"]))
    guvenlik_marji = st.slider("Güvenlik payı (%)", 10, 50, 25)
    menzil_filtresi = st.checkbox("Menzile göre filtrele", True)
    arama_metni = st.text_input("İstasyon ara")
    sonuc_sayisi = st.slider("Gösterilecek seçenek", 1, MAX_EKRAN_KART_SAYISI, min(2, MAX_EKRAN_KART_SAYISI))
    soket_filtreleri = st.multiselect("Soket", ["CCS", "CHAdeMO", "Type 2", "Schuko", "GB/T"])
    hiz_filtresi = st.selectbox("Minimum güç", ["Tümü", "AC (≥7 kW)", "DC (≥50 kW)", "Hızlı DC (≥150 kW)"])
    operator_filtreleri = st.multiselect("Operatör", operator_secenekleri)
    sadece_24_saat = st.checkbox("Sadece 24 saat açık")
    ayar_yaricap = st.slider("Yakın yer mesafesi (m)", 100, 800, 400, 100)
    haritayi_goster = st.checkbox("Haritayı göster")

if "batarya" not in locals():
    v = ARAC_KATALOGU[secilen_arac]
    batarya = float(v["batarya"])
    sarj_yuzdesi = 30
    tuketim = float(v["tuketim"])
    guvenlik_marji = 25

guvenli_menzil = ((batarya * (sarj_yuzdesi / 100.0) / tuketim) * 100.0) * (1 - guvenlik_marji / 100.0)
surus_ozeti_ciz(secilen_arac, guvenli_menzil, sarj_yuzdesi)

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

uygun_istasyonlar = sorted(uygun_istasyonlar, key=ist_siralama)[:min(sonuc_sayisi, MAX_EKRAN_KART_SAYISI)]

# 7. Favoriler
if "favoriler" not in st.session_state: st.session_state["favoriler"] = set()
if "auth_token" in st.session_state: st.session_state["favoriler"] = set(favorileri_getir(auth_uid_hash_getir(), st.session_state["auth_token"]))

# 8. Sonuç Kartları Çizimi
if uygun_istasyonlar:
    station_keys = tuple(str(i.get("_station_key") or clean_id_uret(istasyon_id_getir(i))) for i in uygun_istasyonlar)
    gorunen_yorumlar = gorunen_yorumlari_getir(station_keys)
    tahmin_yorumlari = tahmin_yorumlari_getir(station_keys)
    for ist in uygun_istasyonlar:
        ist_key = str(ist.get("_station_key") or clean_id_uret(istasyon_id_getir(ist)))
        yorum_kaynagi = tahmin_yorumlari.get(ist_key) or gorunen_yorumlar.get(ist_key) or ist.get("SonYorumlar", [])
        istasyon_tahminini_guncelle(ist, yorum_kaynagi)
    uygun_istasyonlar = sorted(uygun_istasyonlar, key=ist_siralama)

    en_iyi = uygun_istasyonlar[0]
    en_iyi_key = str(en_iyi.get("_station_key") or clean_id_uret(istasyon_id_getir(en_iyi)))
    en_iyi_link = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={en_iyi['enlem']},{en_iyi['boylam']}&travelmode=driving"
    en_iyi_secim_ciz(en_iyi, en_iyi_link)

    if haritayi_goster:
        st.map({"lat": [i["enlem"] for i in uygun_istasyonlar], "lon": [i["boylam"] for i in uygun_istasyonlar]})

    if en_iyi.get("SonYorumlar") or gorunen_yorumlar.get(en_iyi_key):
        with st.expander("Son bildirimler", expanded=False):
            for y in (en_iyi.get("SonYorumlar") or gorunen_yorumlar.get(en_iyi_key, []))[:MAX_SON_YORUM]:
                st.write(f"{durum_metni_sadelestir(y.get('durum', ''))}: {str(y.get('yorum', ''))[:100]}")

    alternatifler = uygun_istasyonlar[1:]
    if alternatifler:
        with st.expander("Diğer seçenekler", expanded=False):
            for sira, ist in enumerate(alternatifler, start=1):
                ist_id = istasyon_id_getir(ist)
                ist_key = str(ist.get("_station_key") or clean_id_uret(ist_id))
                g_link = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={ist['enlem']},{ist['boylam']}&travelmode=driving"
                istasyon_karti_ciz(ist, sira, g_link)

                if ist.get("SonYorumlar") or gorunen_yorumlar.get(ist_key):
                    with st.expander("Son bildirimler", expanded=False):
                        for y in (ist.get("SonYorumlar") or gorunen_yorumlar.get(ist_key, []))[:MAX_SON_YORUM]:
                            st.write(f"{durum_metni_sadelestir(y.get('durum', ''))}: {str(y.get('yorum', ''))[:100]}")

                istasyon_aksiyonlari_ciz(ist, ist_id, ist_key, ayar_yaricap)

    with st.expander("Öneriyi kaydet veya bildir", expanded=False):
        ist_id = istasyon_id_getir(en_iyi)
        istasyon_aksiyonlari_ciz(en_iyi, ist_id, en_iyi_key, ayar_yaricap)

else:
    st.markdown(
        """
        <div class="sb-empty-state">
            <strong>Menzil içinde uygun istasyon bulamadık.</strong>
            <span>Gelişmiş ayarlardan menzil filtresini gevşetmeyi veya arama metnini temizlemeyi deneyin.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

hesap_paneli_ciz()
