import streamlit as st
import pandas as pd
import json
import math
import requests
from datetime import datetime
from streamlit_js_eval import get_geolocation

# --- 📱 MOBİL VE PREMIUM SAYFA AYARLARI ---
st.set_page_config(
    page_title="ŞarjBul",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 🎨 PREMIUM CSS
st.markdown('''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }

        .stApp { background-color: #f8f9fa !important; }
        .block-container { padding: 1.5rem 1rem !important; max-width: 440px !important; }

        .title-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            border: 2px solid #0f172a;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
        }
        .title-cell {
            background-color: #0f172a;
            color: #ffffff !important;
            font-family: 'Inter', '-apple-system', sans-serif;
            font-weight: 800;
            font-size: 24px;
            letter-spacing: 0.5px;
            text-align: center;
            padding: 14px;
            text-transform: uppercase;
        }
        .subtitle-cell {
            background-color: #ffffff;
            color: #475569 !important;
            font-family: 'Inter', '-apple-system', sans-serif;
            font-size: 13px;
            font-weight: 500;
            text-align: center;
            padding: 10px;
            border-top: 1px solid #e2e8f0;
            letter-spacing: 0.2px;
        }

        .stSelectbox label p, .stSlider label p, .stNumberInput label p, .stTextInput label p {
            color: #0f172a !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #e2e8f0 !important;
        }

        .premium-card {
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-top: 5px solid #0f172a !important;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
            margin-bottom: 20px;
        }

        .istasyon-isim { font-size: 20px; font-weight: 700; color: #0f172a !important; margin: 0 0 6px 0; letter-spacing: -0.3px; }
        .mesafe-text { font-size: 14px; font-weight: 700; color: #1e40af !important; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px; }
        .detay-text { font-size: 13px; color: #475569 !important; margin: 0; font-weight: 500; }
        .adres-text { font-size: 12px; color: #64748b !important; margin-top: 14px; line-height: 1.5; border-top: 1px solid #f1f5f9; padding-top: 14px; }

        .panel-bolucu { border-top: 1px solid #f1f5f9; margin: 18px 0; }
        .panel-alt-baslik { font-size: 13px; font-weight: 700; color: #0f172a !important; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.3px; }
        .avantaj-item { font-size: 12px; color: #475569 !important; margin-bottom: 8px; display: flex; justify-content: space-between; font-weight: 500; }
        .avantaj-badge { color: #1e40af !important; font-weight: 700; }

        .uyari-sarj {
            background: #fffbeb !important;
            border: 1px solid #f59e0b !important;
            border-left: 5px solid #d97706 !important;
            padding: 12px 16px;
            border-radius: 12px;
            color: #92400e !important;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 15px;
        }

        .nav-link-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            border-radius: 10px;
            height: 46px;
            font-weight: 600;
            background-color: #0f172a;
            color: #ffffff !important;
            border: 1px solid #0f172a;
            box-sizing: border-box;
            font-size: 14px;
        }

        .stButton>button {
            border-radius: 10px;
            height: 46px;
            font-weight: 600;
            background-color: #0f172a;
            color: #ffffff !important;
            width: 100%;
        }
        .rapor-calisiyor>button { border-color: #2563eb !important; color: #2563eb !important; background: #eff6ff !important; }
        .rapor-arizali>button { border-color: #dc2626 !important; color: #dc2626 !important; background: #fef2f2 !important; }
    </style>
''', unsafe_allow_html=True)

# ==========================================
# 🔐 DÜZELTMEe 8: Firebase URL artık st.secrets'tan okunuyor
# secrets.toml içinde: [firebase] db_url = "https://..."
# ==========================================
try:
    FIREBASE_DB_URL = st.secrets["firebase"]["db_url"]
except (KeyError, FileNotFoundError):
    st.error("Firebase bağlantı bilgisi bulunamadı. Lütfen secrets.toml dosyasını kontrol edin.")
    st.stop()


# ==========================================
# 🛠️ YARDIMCI FONKSİYONLAR
# ==========================================
def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def zaman_oncesi(tarih_str):
    try:
        eski_zaman = datetime.strptime(tarih_str, "%d.%m %H:%M")
        simdi = datetime.now()
        eski_zaman = eski_zaman.replace(year=simdi.year)
        fark = simdi - eski_zaman
        saniye = fark.total_seconds()
        if saniye < 0:
            return "Az önce"
        dakika = int(saniye / 60)
        saat = int(dakika / 60)
        gun = int(saat / 24)
        if dakika < 1:
            return "Az önce"
        elif dakika < 60:
            return f"{dakika} dakika önce"
        elif saat < 24:
            return f"{saat} saat önce"
        else:
            return f"{gun} gün önce"
    except:
        return tarih_str


# ==========================================
# 🔴 DÜZELTMEe 1 (yorum_tarihi_parse): Yıl + gün/ay birlikte parse ediliyor
# Artık yılbaşı geçişlerinde sıralama hatası oluşmaz
# ==========================================
def yorum_tarihi_parse(tarih_str):
    try:
        simdi = datetime.now()
        # Gün.ay saat:dakika → Önce bu yıl dene, gelecekteyse geçen yıla çek
        dt = datetime.strptime(tarih_str, "%d.%m %H:%M").replace(year=simdi.year)
        if dt > simdi:
            dt = dt.replace(year=simdi.year - 1)
        return dt
    except:
        return datetime.min


# ==========================================
# 🔴 DÜZELTMEe 2: Yorum gönderme sonrası sadece ilgili önbellek temizleniyor
# ==========================================
def yorum_gonder(istasyon_id, kullanici, yorum_metni, durum):
    clean_id = "".join(c for c in istasyon_id if c.isalnum() or c in (' ', '_', '-')).rstrip()
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
    yeni_yorum = {
        "kullanici": kullanici.strip() if kullanici else "Anonim Sürücü",
        "yorum": yorum_metni.strip() if yorum_metni else f"İstasyon durumu bildirildi: {durum}",
        "durum": durum,
        "tarih": datetime.now().strftime("%d.%m %H:%M")
    }
    try:
        # DÜZELTMEe 9: timeout 2.0 → 4.0 saniyeye çıkarıldı
        r = requests.post(url, json=yeni_yorum, timeout=4.0)
        if r.status_code in (200, 201):
            # Sadece etkilenen iki fonksiyonun önbelleklerini temizle
            yorumlari_getir.clear()
            arizali_istasyon_setini_getir.clear()
            return True
    except Exception:
        pass
    return False


# ==========================================
# ⚡ OPTİMİZASYON: 30 saniyelik cache + timeout 4s
# ==========================================
@st.cache_data(ttl=30)
def arizali_istasyon_setini_getir():
    url = f"{FIREBASE_DB_URL}yorumlar.json"
    arizali_set = set()
    try:
        # DÜZELTMEe 9: timeout 4 saniye
        res = requests.get(url, timeout=4.0)
        if res.status_code == 200 and res.json():
            tum_veri = res.json()
            for clean_id, yorum_paketleri in tum_veri.items():
                if yorum_paketleri and isinstance(yorum_paketleri, dict):
                    sirali_yorumlar = sorted(
                        yorum_paketleri.values(),
                        key=lambda x: yorum_tarihi_parse(x.get('tarih', ''))
                    )
                    son5 = sirali_yorumlar[-5:]
                    arizali_sayisi = sum(
                        1 for y in son5
                        if "Arızalı" in y.get("durum", "")
                    )
                    if arizali_sayisi >= 3:
                        arizali_set.add(clean_id)
    except Exception:
        pass
    return arizali_set


# ==========================================
# 🗺️ OVERPASS API: Yakın çevre bilgisi (ücretsiz, OpenStreetMap)
# ttl=86400 → günde 1 kez çekiliyor, istasyon koordinatları değişmez
# ==========================================
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

KATEGORI_EMOJILER = {
    "cafe": ("☕", "Kafe"),
    "restaurant": ("🍽️", "Restoran"),
    "fast_food": ("🍔", "Fast Food"),
    "supermarket": ("🛒", "Süpermarket"),
    "convenience": ("🏪", "Market"),
    "fuel": ("⛽", "Akaryakıt"),
    "parking": ("🅿️", "Otopark"),
    "hotel": ("🏨", "Otel"),
    "mall": ("🏬", "AVM"),
    "pharmacy": ("💊", "Eczane"),
    "atm": ("🏧", "ATM"),
    "toilets": ("🚻", "Tuvalet"),
}

OVERPASS_HEADERS = {
    "User-Agent": "SarjBul/1.0 (EV charging finder app)",
    "Accept": "application/json",
}

@st.cache_data(ttl=86400)
def yakin_cevre_getir(enlem, boylam, yaricap_m=400):
    """
    Overpass API ile verilen koordinat çevresindeki ilgi noktalarını çeker.
    yaricap_m: metre cinsinden arama yarıçapı (varsayılan 400m)
    """
    sorgu = f"""
    [out:json][timeout:12];
    (
      node["amenity"~"cafe|restaurant|fast_food|parking|pharmacy|atm|toilets"](around:{yaricap_m},{enlem},{boylam});
      node["shop"~"supermarket|convenience|mall"](around:{yaricap_m},{enlem},{boylam});
      node["tourism"="hotel"](around:{yaricap_m},{enlem},{boylam});
    );
    out body;
    """
    try:
        res = requests.post(OVERPASS_URL, data={"data": sorgu},
                            headers=OVERPASS_HEADERS, timeout=12.0)
        if res.status_code != 200:
            return []

        elemanlar = res.json().get("elements", [])
        sonuclar = []

        for el in elemanlar:
            tags = el.get("tags", {})
            isim = tags.get("name", "")
            amenity = tags.get("amenity", tags.get("shop", tags.get("tourism", "")))

            if amenity not in KATEGORI_EMOJILER:
                continue

            # Mesafe hesapla
            el_lat = el.get("lat", enlem)
            el_lon = el.get("lon", boylam)
            km = mesafe_hesapla(enlem, boylam, el_lat, el_lon)
            metre = int(km * 1000)

            emoji, kategori_adi = KATEGORI_EMOJILER[amenity]
            goruntu_isim = isim if isim else kategori_adi

            sonuclar.append({
                "isim": goruntu_isim,
                "kategori": kategori_adi,
                "emoji": emoji,
                "metre": metre,
            })

        # Mesafeye göre sırala, kategori başına en yakın 1 tane al (fazla kalabalık olmasın)
        gorulmus_kategoriler = set()
        filtrelenmis = []
        for s in sorted(sonuclar, key=lambda x: x["metre"]):
            if s["kategori"] not in gorulmus_kategoriler:
                gorulmus_kategoriler.add(s["kategori"])
                filtrelenmis.append(s)
            if len(filtrelenmis) >= 5:  # En fazla 5 yer göster
                break

        return filtrelenmis

    except Exception:
        return []


@st.cache_data(ttl=30)
def yorumlari_getir(istasyon_id):
    clean_id = "".join(c for c in istasyon_id if c.isalnum() or c in (' ', '_', '-')).rstrip()
    url = f"{FIREBASE_DB_URL}yorumlar/{clean_id}.json"
    try:
        # DÜZELTMEe 9: timeout 4 saniye
        res = requests.get(url, timeout=4.0)
        if res.status_code == 200 and res.json():
            return list(res.json().values())
    except Exception:
        pass
    return []


# ==========================================
# 📁 ÇEVRİMDIŞI ÖNBELLEK VERİSİ
# ==========================================
if "offline_istasyonlar" not in st.session_state:
    try:
        with open("istasyonlar.json", "r", encoding="utf-8") as f:
            st.session_state.offline_istasyonlar = json.load(f)
    except Exception:
        st.error("istasyonlar.json dosyası bulunamadı.")
        st.stop()

istasyonlar_verisi = st.session_state.offline_istasyonlar


# ==========================================
# 🏛️ BAŞLIK ALANI
# ==========================================
st.markdown('''
    <table class="title-table">
        <tr><td class="title-cell">ŞarjBul</td></tr>
        <tr><td class="subtitle-cell">En yakın aktif şarj rotanız</td></tr>
    </table>
''', unsafe_allow_html=True)


# ==========================================
# 📡 GPS ENTEGRASYONU
# ==========================================
user_lat, user_lon = None, None

try:
    konum_verisi = get_geolocation()
    if isinstance(konum_verisi, dict) and 'coords' in konum_verisi:
        user_lat = konum_verisi['coords'].get('latitude')
        user_lon = konum_verisi['coords'].get('longitude')
    if user_lat is not None and user_lon is not None:
        st.session_state["last_valid_lat"] = user_lat
        st.session_state["last_valid_lon"] = user_lon
except Exception:
    pass

if user_lat is None or user_lon is None:
    user_lat = st.session_state.get("last_valid_lat")
    user_lon = st.session_state.get("last_valid_lon")

if user_lat is None or user_lon is None:
    st.markdown("""
    <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; border-left: 5px solid #2563eb; padding: 16px; border-radius: 12px; margin-bottom: 15px;">
        <div style="color: #1e40af; font-weight: 700; font-size: 14px; margin-bottom: 4px; text-transform: uppercase;">Konum İzni Bekleniyor</div>
        <div style="color: #1e3a8a; font-size: 13px; font-weight: 500; line-height: 1.4;">
            Lütfen tarayıcınızın konum erişim talebini onaylayın. Uygulama içi tarayıcılardaysanız (X, Instagram), linki kopyalayıp Safari veya Chrome'da açın.
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


# ==========================================
# 🚗 ARAÇ SEÇİM MENÜSÜ
# ==========================================
with st.expander("Araç ve Menzil Ayarları", expanded=False):
    ARAC_KATALOGU = {
        "Tesla Model Y Long Range": {"batarya": 75.0, "tuketim": 16.9},
        "Togg T10X Uzun Menzil": {"batarya": 88.5, "tuketim": 16.9},
        "BYD Atto 3": {"batarya": 60.4, "tuketim": 16.0},
        "Renault Megane E-Tech": {"batarya": 60.0, "tuketim": 15.5},
        "Özel Araç (Manuel)": {"batarya": 60.0, "tuketim": 17.0}
    }

    secilen_arac = st.selectbox("Model", list(ARAC_KATALOGU.keys()), label_visibility="collapsed")
    varsayilan_degerler = ARAC_KATALOGU[secilen_arac]

    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        batarya = st.number_input("Kapasite", value=varsayilan_degerler["batarya"])
    with col_b2:
        sarj_yuzdesi = st.slider("Şarj %", min_value=1, max_value=100, value=30)
    with col_b3:
        tuketim = st.number_input("Tüketim", value=varsayilan_degerler["tuketim"])

    st.markdown("---")

    # 🔴 DÜZELTMEe 6: Güvenlik marjı slider'ı eklendi (gerçek sürüş mesafesi kuş uçuşundan %20-40 uzun olabilir)
    guzenik_marji = st.slider(
        "Güvenlik Marjı (Yol mesafesi tahmini)",
        min_value=10, max_value=50, value=25,
        help="Kuş uçuşu mesafesi gerçek yol mesafesinden daha kısadır. %25 marj önerilir."
    )

    menzil_filtresi_aktif = st.checkbox(
        "Menzil Filtresini Uygula (Sadece ulaşabileceğim istasyonları göster)",
        value=True
    )

# DÜZELTMEe 6: Güvenlik marjı hesaba katılıyor — gerçek menzil daraltılıyor
ham_menzil = ((batarya * (sarj_yuzdesi / 100.0)) / tuketim) * 100.0
maks_menzil = ham_menzil * (1 - guzenik_marji / 100.0)


# ==========================================
# 🧠 EN YAKIN AKTİF İSTASYONLARI BULMA
# 🔴 DÜZELTMEe 7: Tek değil, en yakın 3 aktif istasyon listeleniyor
# ==========================================
uygun_istasyonlar = []
aktif_arizali_set = arizali_istasyon_setini_getir()

for ist in istasyonlar_verisi:
    km = mesafe_hesapla(user_lat, user_lon, ist["enlem"], ist["boylam"])

    if (not menzil_filtresi_aktif) or (km <= maks_menzil):
        clean_id = "".join(c for c in ist["isim"] if c.isalnum() or c in (' ', '_', '-')).rstrip()
        if clean_id not in aktif_arizali_set:
            ist_kopya = ist.copy()
            ist_kopya["Mesafe"] = round(km, 1)
            uygun_istasyonlar.append(ist_kopya)

# Mesafeye göre sırala, en yakın 3'ü al
uygun_istasyonlar.sort(key=lambda x: x["Mesafe"])
en_yakin_3 = uygun_istasyonlar[:3]


# ==========================================
# 🎯 KART VE SEÇENEKLERİN GÖSTERİMİ
# ==========================================
if en_yakin_3:
    for sira, istasyon in enumerate(en_yakin_3):
        # İlk kart ana öneri, diğerleri yedek olarak etiketleniyor
        etiket = "🥇 En Yakın İstasyon" if sira == 0 else f"#{sira + 1} Yedek İstasyon"

        # Overpass API'den yakın çevre bilgisi çek (önbellekli, günde 1 kez)
        # İlk yüklemede spinner göster, sonraki açılışlarda cache'den anında gelir
        with st.spinner("Yakın çevre yükleniyor..."):
            yakin_yerler = yakin_cevre_getir(istasyon["enlem"], istasyon["boylam"])

        if yakin_yerler:
            yakin_html = '<div class="panel-bolucu"></div><div class="panel-alt-baslik">Yakındaki Yerler</div>'
            for yer in yakin_yerler:
                yakin_html += f'''
                <div class="avantaj-item">
                    <span>{yer["emoji"]} {yer["isim"]}</span>
                    <span class="avantaj-badge">{yer["metre"]}m</span>
                </div>'''
        else:
            yakin_html = ""

        st.markdown(f"""
        <div class="premium-card">
            <div style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;">{etiket}</div>
            <div class="mesafe-text">{istasyon['Mesafe']} km uzaklıkta</div>
            <div class="istasyon-isim">{istasyon['isim']}</div>
            <div class="detay-text">Şarj Hızı: {istasyon['hiz']}</div>
            <div class="adres-text">{istasyon['adres']}</div>
            {yakin_html}
        </div>
        """, unsafe_allow_html=True)

        # DÜZELTMEe 6: Güvenlik marjı uyarısı — kullanıcı bilgilendirilmiş
        if menzil_filtresi_aktif:
            st.markdown(f"""
            <div class="uyari-sarj">
                ⚠️ Gösterilen menzil, <b>%{guzenik_marji} güvenlik marjı</b> uygulanmış hesaplı menzildir ({ham_menzil:.0f} km teorik → {maks_menzil:.0f} km güvenli). Gerçek yol mesafesi kuş uçuşundan daha uzundur.
            </div>
            """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            g_link = (
                f"https://www.google.com/maps/dir/?api=1"
                f"&origin={user_lat},{user_lon}"
                f"&destination={istasyon['enlem']},{istasyon['boylam']}"
                f"&travelmode=driving"
            )
            st.markdown(f'<a href="{g_link}" target="_blank" class="nav-link-btn">Navigasyonu Başlat</a>', unsafe_allow_html=True)

        with c2:
            with st.popover("Durum Bildir"):
                col_btn1, col_btn2 = st.columns(2)

                # 🔴 DÜZELTMEe 3: Walrus operatörü kaldırıldı, isim doğrudan ve güvenli şekilde kullanılıyor
                istasyon_isim = istasyon.get('isim', '').strip()

                with col_btn1:
                    st.markdown('<div class="rapor-calisiyor">', unsafe_allow_html=True)
                    if st.button("Sorunsuz", key=f"btn_ok_{sira}"):
                        if istasyon_isim:
                            if yorum_gonder(istasyon_isim, "Anonim Sürücü", "", "Sorunsuz / Boş"):
                                st.rerun()
                        else:
                            st.warning("İstasyon adı bulunamadı.")
                    st.markdown('</div>', unsafe_allow_html=True)

                with col_btn2:
                    st.markdown('<div class="rapor-arizali">', unsafe_allow_html=True)
                    if st.button("Arızalı", key=f"btn_fail_{sira}"):
                        if istasyon_isim:
                            if yorum_gonder(istasyon_isim, "Anonim Sürücü", "", "Arızalı / Kapalı"):
                                st.rerun()
                        else:
                            st.warning("İstasyon adı bulunamadı.")
                    st.markdown('</div>', unsafe_allow_html=True)

                st.markdown("---")
                nick = st.text_input("Kullanıcı Adı", max_chars=12, key=f"inp_nick_{sira}")
                yorum_txt = st.text_input("Durum Notu", key=f"inp_txt_{sira}")
                if st.button("Detaylı Gönder", key=f"btn_detail_{sira}"):
                    if istasyon_isim:
                        if yorum_gonder(istasyon_isim, nick, yorum_txt, "Durum Güncellemesi"):
                            st.rerun()
                    else:
                        st.warning("İstasyon adı bulunamadı.")

                st.markdown("---")
                yorumlar = yorumlari_getir(istasyon_isim)
                if yorumlar:
                    for y in sorted(yorumlar, key=lambda x: yorum_tarihi_parse(x.get('tarih', '')), reverse=True)[:2]:
                        zaman_etiketi = zaman_oncesi(y.get('tarih', ''))
                        st.markdown(f"**{y.get('kullanici', 'Anonim')}** ({y.get('durum', 'Güncelleme')}) • *{zaman_etiketi}*")
                        st.caption(f"> {y.get('yorum', '')}")

        st.markdown("<br>", unsafe_allow_html=True)

else:
    st.markdown("""
    <div style="background-color: #fff1f2; border: 1px solid #fecdd3; border-left: 5px solid #e11d48; padding: 16px; border-radius: 12px;">
        <div style="color: #9f1239; font-weight: 700; font-size: 14px; margin-bottom: 4px; text-transform: uppercase;">Menzil Aşımı / İstasyon Bulunamadı</div>
        <div style="color: #4c0519; font-size: 13px; font-weight: 500; line-height: 1.4;">
            Mevcut şarj yüzdeniz ile ulaşılabilecek aktif bir istasyon bulunamadı.
            <br><br>
            <b>Çözüm:</b> "Araç ve Menzil Ayarları" panelini açıp <b>"Menzil Filtresini Uygula"</b> seçeneğini kapatabilir veya güvenlik marjını düşürebilirsiniz.
        </div>
    </div>
    """, unsafe_allow_html=True)
