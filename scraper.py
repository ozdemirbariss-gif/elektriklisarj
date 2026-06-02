import requests
import json

def istasyonlari_kaziyici():
    print("⏳ Şarj ağı sunucusuna bağlanılıyor...")
    
    # 🎯 BURASI ÖNEMLİ: Tarayıcının 'Ağ' (Network) sekmesinden kopyaladığın 
    # gerçek veri linkini (URL) aşağıdaki tırnak işaretlerinin içine yapıştır!
    URL = "https://www.chargeiq.com.tr/api/stations"
    
    # Sitenin bizi engellememesi için Mac tarayıcısı taklidi yapıyoruz
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        
        if response.status_code == 200:
            ham_veri = response.json()
            print(f"✅ Veri başarıyla çekildi! Toplam {len(ham_veri)} istasyon bulundu.")
            
            temiz_veri = []
            
            # NOT: Eğer hedef sitenin JSON yapısı farklıysa (örn: enlem yerine 'lat' kullanıyorsa)
            # aşağıdaki kelimeleri sitenin yapısına göre güncellemen gerekebilir.
            for istasyon in ham_veri:
                temiz_veri.append({
                    "isim": istasyon.get("station_name", "Şarj İstasyonu"),
                    "adres": istasyon.get("address", "Adres Bilgisi Yok"),
                    "enlem": float(istasyon.get("latitude")),
                    "boylam": float(istasyon.get("longitude")),
                    "hiz": "Hızlı (DC)" if istasyon.get("is_fast") else "Standart (AC)"
                })
                
            # Verileri 'istasyonlar.json' dosyasına kaydediyoruz
            with open("istasyonlar.json", "w", encoding="utf-8") as f:
                json.dump(temiz_veri, f, ensure_ascii=False, indent=2)
                
            print("💾 'istasyonlar.json' başarıyla güncellendi!")
            
        else:
            print(f"❌ Sunucu hata döndürdü. Durum Kodu: {response.status_code}")
            
    except Exception as e:
        print(f"💥 Bağlantı hatası: {e}")

if __name__ == "__main__":
    istasyonlari_kaziyici()
