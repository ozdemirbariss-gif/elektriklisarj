# SarjBul

SarjBul, elektrikli araclar icin yakin ve mantikli sarj duragini onerir. Streamlit arayuzu konum, menzil, soket, guc, fiyat ve kullanici bildirimlerini birlikte degerlendirir.

## Ozellikler

- Konuma gore yakin sarj istasyonu onerisi
- Arac batarya/tuketim degerleriyle menzil filtresi
- Skor, rota, hiz, fiyat, soket ve operator bilgileri
- Firebase etkinse hesap, favori ve istasyon bildirimi
- ChargeIQ, OSM, OpenChargeMap ve opsiyonel operator API kaynakli veri toplama

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Firebase secrets yoksa uygulama lokal `istasyonlar.json` dosyasi ile okunabilir demo modunda acilir. Bu modda hesap, favori ve bildirim ozellikleri kapali kalir.

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

## Veri Guncelleme

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
- `FAIL_ON_SOURCE_ERROR`: `1` ise herhangi bir kaynak hatasi scrape'i basarisiz yapar.

GitHub Actions her gun 08:00 Istanbul saatinde scrape calistirir ve yalnizca `istasyonlar.json` degistiyse commit eder.

## Akilli Tahmin Motoru

`predictor.py`, Firebase yorum gecmisinden hafif bir istatistiksel tahmin uretir. Model; son bildirimleri, hedef varis saatine benzeyen gun/saat araliklarini ve istasyonun genel gecmisini agirliklandirir.

Uygulama yeni bir ekran acmaz. Tahmin yeterli guvene ulasirsa mevcut kart rozetlerine "Bosluk ihtimali yuksek/orta" veya "Yogun olabilir" gibi kisa bir sinyal eklenir. Veri yetersizse rozet gosterilmez ve skor etkilenmez.
