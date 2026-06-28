# SarjBul

SarjBul, elektrikli araclar icin yakin ve mantikli sarj duragini onerir. Streamlit arayuzu konum, menzil, soket, guc, fiyat ve kullanici bildirimlerini birlikte degerlendirir.

## Ozellikler

- Konuma gore yakin sarj istasyonu onerisi
- Arac batarya/tuketim degerleriyle menzil filtresi
- Skor, rota, hiz, fiyat, soket ve operator bilgileri
- Firebase etkinse hesap, favori ve istasyon bildirimi
- Firebase Auth refresh token yenileme ile daha uzun oturum deneyimi
- Folium haritasinda skor rengine gore istasyon noktalarini ve popup detaylarini gosterme
- Konum izni yoksa genis sehir listesi veya manuel koordinat girisi
- Arayuz genelinde aninda degisen Turkce ve Ingilizce dil destegi
- ChargeIQ, OSM, OpenChargeMap ve opsiyonel operator API kaynakli veri toplama

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Firebase secrets yoksa uygulama lokal `stations.json` dosyasi ile okunabilir demo modunda acilir. Bu modda hesap, favori ve bildirim ozellikleri kapali kalir.

## Bagimliliklar

`requirements.txt` yalnizca kodda dogrudan kullanilan paketleri icerir ve Streamlit Cloud build'lerinin tekrarlanabilir olmasi icin exact version pin kullanir. Firebase islemleri REST API uzerinden yapildigi icin `firebase-admin` gerekli degildir.

## Secrets

Firebase ve Sentry kullanmak icin `.streamlit/secrets.toml.example` dosyasini `.streamlit/secrets.toml` olarak kopyalayip kendi degerlerinle doldur.

```toml
[firebase]
db_url = "https://PROJECT_ID-default-rtdb.firebaseio.com"
api_key = "FIREBASE_WEB_API_KEY"

[sentry]
dsn = ""
traces_sample_rate = 0.10
```

`firebase.db_url` ve `firebase.api_key` hesap, favori ve bildirim ozellikleri icin gereklidir. `sentry` blogu opsiyoneldir.

## Firebase Veri Yollari

- `istasyonlar`: normalize edilecek istasyon kayitlari
- `yorumlar/{station_id}`: giris yapmis kullanici durum bildirimleri
- `station_status/{station_id}`: yorumlardan uretilmis son durum ozeti
- `favoriler/{auth.uid}`: kullanicinin kaydettigi istasyonlar
- `kullanici_yorum_meta/{auth.uid}`: yorum bekleme suresi icin son gonderim zamani

## Firebase Guvenlik Kurallari

Repo kokundeki `database.rules.json` Realtime Database icin kilitli varsayilan kurallari icerir:

- Kok `.read` ve `.write` kapali.
- `istasyonlar` ve `station_status` okunabilir, yazma kapali ya da auth ile sinirli.
- `yorumlar` sadece giris yapmis kullanicilar tarafindan okunur/yazilir; yorumdaki `uid` degeri `auth.uid` ile eslesmek zorundadir.
- `favoriler/{auth.uid}` ve `kullanici_yorum_meta/{auth.uid}` sadece ilgili kullanici tarafindan okunup yazilir.

Firebase Console > Realtime Database > Rules ekranina `database.rules.json` icerigini yukleyin. Firebase CLI kullaniyorsan:

```bash
firebase deploy --only database
```

Onceki surumlerde favori ve yorum meta kayitlari `uid_hash` ile tutulduysa, bu verileri ilgili kullanicinin `auth.uid` anahtarina tasiyin. Yeni kurallar hash tabanli IDOR riskini kapatmak icin `auth.uid` ile bire bir path eslesmesi bekler.

Firebase Console tarafinda ayrica App Check'i etkinlestirin ve Authentication > Settings altindan e-posta enumerasyon korumasini acin. Bagimlilik denetimi icin:

```bash
python -m pip install pip-audit
pip-audit -r requirements.txt
```

## Streamlit Cloud Deploy

1. Repoyu GitHub'a gonder.
2. Streamlit Cloud'da yeni app olusturup ana dosya olarak `app.py` sec.
3. `requirements.txt` dosyasinin repoda oldugundan emin ol.
4. Secrets alanina yukaridaki TOML semasini ekle.
5. Firebase Auth domain ayarlarinda Streamlit Cloud domainini izinli alanlara ekle.

## Veri Guncelleme

`scraper.py` komut satiri entrypoint'idir; GitHub Actions ve manuel calistirma bu dosya uzerinden yapilir. `scrapers/` klasoru kaynak bazli scraper modullerini icerir. `scraper.py`, bu modulleri cagirarak veriyi toplar, duplicate temizligi yapar ve `stations.json` dosyasini gunceller.

```bash
python scraper.py
```

Kaynaklari sinirlamak icin:

```bash
python scraper.py --sources chargeiq,osm,openchargemap
```

Kalite kapilari ortam degiskenleriyle ayarlanabilir:

- `MIN_SCRAPER_SOURCE_COUNT`: Cikti yazmak icin gereken minimum basarili kaynak sayisi.
- `MIN_SCRAPER_RECORD_COUNT`: Cikti yazmak icin gereken minimum kayit sayisi.
- `MIN_SCRAPER_PREVIOUS_RATIO`: Mevcut `stations.json` kaydina gore kabul edilen minimum oran.
- `FAIL_ON_SOURCE_ERROR`: `1` ise herhangi bir kaynak hatasi scrape'i basarisiz yapar.

GitHub Actions her gun 08:00 Istanbul saatinde scrape calistirir ve yalnizca `stations.json` degistiyse commit eder. Kaynak hatasi veya onceki veriye gore buyuk kayit dususu olursa workflow basarisiz olur; boylece eski veri sessizce kalmaz.

## Akilli Tahmin Motoru

`predictor.py`, Firebase yorum gecmisinden hafif bir istatistiksel tahmin uretir. Model; son bildirimleri, hedef varis saatine benzeyen gun/saat araliklarini ve istasyonun genel gecmisini agirliklandirir.

Uygulama yeni bir ekran acmaz. Tahmin yeterli guvene ulasirsa mevcut kart rozetlerine "Bosluk ihtimali yuksek/orta" veya "Yogun olabilir" gibi kisa bir sinyal eklenir. Veri yetersizse rozet gosterilmez ve skor etkilenmez.
