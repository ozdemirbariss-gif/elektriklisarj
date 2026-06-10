import streamlit as st
import hashlib
from datetime import datetime
from streamlit_js_eval import get_geolocation

from config import (
    sentry_init, load_css, logger, MAX_ISTASYON_SAYISI, MAX_EKRAN_KART_SAYISI,
    ARAC_KATALOGU, YOL_UZAMA_KATSAYISI, HIZ_ESIK_MAP, KONUM_DOGRULAMA_ESIGI_KM,
    MAX_SON_YORUM, MAX_YORUM_KARAKTER
)
from utils import (
    guvenli_metin, arama_metni_normalize_et, clean_id_uret, istasyon_id_getir,
    auth_uid_hash_getir, tahmini_sure_dk, varis_sarj_yuzdesi_hesapla, 
    mesafe_hesapla, tahmini_yol_mesafesi_km, konum_gecerli_mi, durum_metni_sadelestir, durum_ozeti_fallback, token_suresi_doldu_mu
)
from services import (
    firebase_login, firebase_register, firebase_sifre_sifirla, oturumu_temizle,
    istasyonlari_yukle, durum_ozetleri_getir, gorunen_yorumlari_getir, 
    favorileri_getir, favori_guncelle, yorum_gonder, yakin_cevre_getir
)

# 1. Başlangıç Ayarları
st.set_page_config(page_title="ŞarjBul", layout="centered", initial_sidebar_state="collapsed")
sentry_init()
load_css()

st.title("ŞarjBul")
st.caption("Yakındaki en uygun şarj noktasını sakin, hızlı ve anlaşılır biçimde bulun.")

# 2. Kullanıcı Giriş Arayüzü
with st.expander("Hesap", expanded=False):
    if "auth_token" not in st.session_state:
        tab_giris, tab_kayit, tab_sifre = st.tabs(["Giriş", "Kayıt", "Şifre"])
        with tab_giris:
            email = st.text_input("E-posta", key="login_email")
            password = st.text_input("Şifre", type="password", key="login_password")
            if st.button("Giriş Yap", use_container_width=True):
                user_data = firebase_login(email, password)
                if user_data:
                    st.session_state.update({"auth_token": user_data["idToken"], "auth_email": user_data.get("email", ""), "auth_uid": user_data.get("localId", ""), "auth_login_time": datetime.now().isoformat()})
                    st.rerun()
                else: st.error("Giriş başarısız.")
        with tab_kayit:
            reg_email = st.text_input("E-posta", key="reg_email")
            reg_password = st.text_input("Şifre", type="password", key="reg_password")
            if st.button("Kayıt Ol", use_container_width=True):
                user_data = firebase_register(reg_email, reg_password)
                if user_data:
                    st.session_state.update({"auth_token": user_data["idToken"], "auth_email": user_data.get("email", ""), "auth_uid": user_data.get("localId", ""), "auth_login_time": datetime.now().isoformat()})
                    st.rerun()
                else: st.error("Kayıt başarısız.")
        with tab_sifre:
            reset_email = st.text_input("E-posta Adresiniz", key="reset_email")
            if st.button("Sıfırlama Bağlantısı Gönder"):
                ok, msg = firebase_sifre_sifirla(reset_email)
                st.success(msg) if ok else st.error(msg)
    else:
        if token_suresi_doldu_mu(): oturumu_temizle(); st.rerun()
        st.success("Hesap aktif.")
        if st.button("Çıkış Yap", use_container_width=True): oturumu_temizle(); st.rerun()

# 3. Filtreler ve Veri Hazırlığı
with st.expander("Arama", expanded=False):
    ayar_yaricap = st.slider("Yakın yer mesafesi (m)", 100, 800, 400, 100)
    sonuc_sayisi = st.slider("İstasyon sayısı", 1, MAX_EKRAN_KART_SAYISI, MAX_ISTASYON_SAYISI)
    soket_filtreleri = st.multiselect("Soket", ["CCS", "CHAdeMO", "Type 2", "Schuko", "GB/T"])
    hiz_filtresi = st.selectbox("Minimum güç", ["Tümü", "AC (≥7 kW)", "DC (≥50 kW)", "Hızlı DC (≥150 kW)"])

istasyonlar_verisi = istasyonlari_yukle()
if not istasyonlar_verisi: st.stop()

operator_secenekleri = sorted({str(ist.get("operator", "Bilinmiyor")) for ist in istasyonlar_verisi if str(ist.get("operator", "")).strip()})
with st.expander("Filtreler ve görünüm", expanded=False):
    operator_filtreleri = st.multiselect("Operatör", operator_secenekleri)
    sadece_24_saat = st.checkbox("Sadece 24 saat açık")
    siralama_modu = st.selectbox("Sıralama", ["Mesafe", "Fiyat", "Hız"])
    gorunum_modu = st.radio("Görünüm", ["Liste", "Harita + Liste"], horizontal=True)

# 4. Konum Tespiti
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

# 5. Araç Bilgileri
with st.expander("Araç ve menzil", expanded=False):
    secilen_arac = st.selectbox("Model", list(ARAC_KATALOGU.keys()), label_visibility="collapsed")
    v = ARAC_KATALOGU[secilen_arac]
    c1, c2, c3 = st.columns(3)
    batarya = c1.number_input("Kapasite", 1.0, 250.0, float(v["batarya"]))
    sarj_yuzdesi = c2.slider("Şarj %", 1, 100, 30)
    tuketim = c3.number_input("Tüketim", 5.0, 40.0, float(v["tuketim"]))
    guvenlik_marji = st.slider("Güvenlik payı (%)", 10, 50, 25)
    menzil_filtresi = st.checkbox("Menzile göre filtrele", True)

guvenli_menzil = ((batarya * (sarj_yuzdesi / 100.0) / tuketim) * 100.0) * (1 - guvenlik_marji / 100.0)
arama_metni = st.text_input("İstasyon ara...")

# 6. Veri İşleme
durum_ozetleri = durum_ozetleri_getir()
uygun_istasyonlar = []
for ist in istasyonlar_verisi:
    kus_ucusu = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])
    tahmini = tahmini_yol_mesafesi_km(kus_ucusu)
    if menzil_filtresi and tahmini > guvenli_menzil: continue
    if soket_filtreleri and not any(sf.upper() in str(ist.get("_soket_upper")).upper() for sf in soket_filtreleri): continue
    if hiz_filtresi != "Tümü" and float(ist.get("_hiz_sayi", 0.0)) < HIZ_ESIK_MAP.get(hiz_filtresi, 0.0): continue
    if operator_filtreleri and str(ist.get("operator")) not in operator_filtreleri: continue
    if arama_metni and arama_metni_normalize_et(arama_metni) not in str(ist.get("_search_text", "")): continue
    
    ist_key = str(ist.get("_station_key") or clean_id_uret(istasyon_id_getir(ist)))
    ariza = {**durum_ozeti_fallback(), **durum_ozetleri.get(ist_key, {})}
    
    ist_kopya = ist.copy()
    ist_kopya.update({"Mesafe": round(tahmini, 1), "KusUcusuMesafe": round(kus_ucusu, 1), "TahminiSureDk": tahmini_sure_dk(tahmini), "VarisSarjYuzdesi": varis_sarj_yuzdesi_hesapla(sarj_yuzdesi, batarya, tuketim, tahmini), "KalanGuvenliMenzil": max(0.0, guvenli_menzil - tahmini), "ArizaDurumu": ariza.get("durum"), "ArizaEtiketi": ariza.get("etiket"), "SonYorumlar": ariza.get("son_yorumlar", [])})
    uygun_istasyonlar.append(ist_kopya)

def ist_siralama(i: Dict) -> Tuple: return (1 if i.get("ArizaDurumu") == "riskli" else 0, float(i.get("_fiyat_sayi", 9999.0)) if siralama_modu == "Fiyat" else -float(i.get("_hiz_sayi", 0.0)) if siralama_modu == "Hız" else float(i["Mesafe"]))
uygun_istasyonlar = sorted(uygun_istasyonlar, key=ist_siralama)[:min(sonuc_sayisi, MAX_EKRAN_KART_SAYISI)]

# 7. Favoriler
if "favoriler" not in st.session_state: st.session_state["favoriler"] = set()
if "auth_token" in st.session_state: st.session_state["favoriler"] = set(favorileri_getir(auth_uid_hash_getir(), st.session_state["auth_token"]))

# 8. Sonuç Kartları Çizimi
if uygun_istasyonlar:
    gorunen_yorumlar = gorunen_yorumlari_getir(tuple(str(i.get("_station_key") or clean_id_uret(istasyon_id_getir(i))) for i in uygun_istasyonlar))
    if gorunum_modu == "Harita + Liste": st.map({"lat": [i["enlem"] for i in uygun_istasyonlar], "lon": [i["boylam"] for i in uygun_istasyonlar]})
    
    for sira, ist in enumerate(uygun_istasyonlar):
        ist_id = istasyon_id_getir(ist)
        ist_key = str(ist.get("_station_key") or clean_id_uret(ist_id))
        durum = ist.get("ArizaDurumu", "belirsiz")
        
        with st.container(border=True):
            if durum == "riskli": st.error(ist.get("ArizaEtiketi"))
            elif durum == "aktif": st.success(ist.get("ArizaEtiketi"))
            else: st.info(ist.get("ArizaEtiketi"))
            
            st.subheader(f"{ist['Mesafe']} km")
            st.markdown(f"**{ist['isim']}**")
            c1, c2 = st.columns(2)
            c1.write(f"Güç: {ist.get('hiz')}\nSoket: {ist.get('soket')}")
            c2.write(f"Operatör: {ist.get('operator')}\nFiyat: {ist.get('fiyat')}")
            st.caption(ist.get("adres"))

            if ist.get("SonYorumlar") or gorunen_yorumlar.get(ist_key):
                st.divider()
                for y in (ist.get("SonYorumlar") or gorunen_yorumlar.get(ist_key, []))[:MAX_SON_YORUM]:
                    st.write(f"{durum_metni_sadelestir(y.get('durum', ''))}: {str(y.get('yorum', ''))[:100]}")

        g_link = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={ist['enlem']},{ist['boylam']}&travelmode=driving"
        st.link_button("Rotayı aç", g_link)

        # Aksiyon Butonları (Durum Bildir & Kaydet)
        a1, a2 = st.columns([3, 1])
        with a1:
            with st.popover("Durum bildir"):
                if "auth_token" not in st.session_state: st.warning("Giriş yapın.")
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

        if st.button("Yakın yerler", key=f"btn_cevre_{ist_key}"):
            yerler = yakin_cevre_getir(ist["enlem"], ist["boylam"], ayar_yaricap)
            if yerler:
                for y in yerler: st.markdown(f"{y['isim']} · **{y['metre']}m**")
else: st.warning("Menzilinizde uygun istasyon bulunamadı.")
