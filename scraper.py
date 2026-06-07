import requests
import json

def istasyonlari_kaziyici():
    print("⏳ Şarj ağı sunucusuna bağlanılıyor...")
    
    # 🎯 Gerçek URL'yi buraya yapıştır
    URL = "https://www.chargeiq.com.tr/api/stations"
    
    # Tarayıcı taklidi yapıyoruz. Eğer sistem giriş (login) gerektiriyorsa, 
    # tarayıcıdan 'Authorization' veya 'Cookie' bilgilerini de buraya eklemelisin.
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        
        if response.status_code == 200:
            ham_veri = response.json()
            
            # API yanıtı bazen liste değil de {"data": [...]} şeklinde bir sözlük olabilir.
            # Bunu garanti altına almak için basit bir kontrol:
            if isinstance(ham_veri, dict) and "data" in ham_veri:
                istasyon_listesi = ham_veri["data"]
            elif isinstance(ham_veri, list):
                istasyon_listesi = ham_veri
            else:
                print("⚠️ Beklenmeyen veri formatı! Lütfen API çıktısını kontrol edin.")
                return

            print(f"✅ Veri başarıyla çekildi! Toplam {len(istasyon_listesi)} istasyon bulundu.")
            
            temiz_veri = []
            
            for istasyon in istasyon_listesi:
                enlem = istasyon.get("latitude")
                boylam = istasyon.get("longitude")
                
                # Eğer enlem veya boylam 'None' ise veya yoksa, çökmeyi engellemek için atla
                if enlem is None or boylam is None:
                    continue
                
                temiz_veri.append({
                    "isim": istasyon.get("station_name", "Şarj İstasyonu"),
                    "adres": istasyon.get("address", "Adres Bilgisi Yok"),
                    "enlem": float(enlem),
                    "boylam": float(boylam),
                    "hiz": "Hızlı (DC)" if istasyon.get("is_fast") else "Standart (AC)"
                })
                
            # Verileri JSON'a yazdır
            with open("istasyonlar.json", "w", encoding="utf-8") as f:
                json.dump(temiz_veri, f, ensure_ascii=False, indent=2)
                
            print("💾 'istasyonlar.json' başarıyla güncellendi!")
            
        elif response.status_code == 401 or response.status_code == 403:
            print(f"⛔ Erişim Reddedildi (Durum Kodu: {response.status_code}). API anahtarı veya giriş bilgisi (Token/Cookie) gerekiyor olabilir.")
        else:
            print(f"❌ Sunucu hata döndürdü. Durum Kodu: {response.status_code}")
            
    except requests.exceptions.Timeout:
        print("⏰ Bağlantı zaman aşımına uğradı. Sunucu yanıt vermiyor.")
    except Exception as e:
        print(f"💥 Beklenmeyen bağlantı veya işleme hatası: {e}")

if __name__ == "__main__":
    istasyonlari_kaziyici()
