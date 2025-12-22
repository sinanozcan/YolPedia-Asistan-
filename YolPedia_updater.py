"""
YolPedia Veri Güncelleyici - Pratik Versiyon
Tek tıkla veri tabanını güncelle
"""

import requests
import json
import re
from typing import List, Dict
from datetime import datetime
import time

def temizle_html(html_text: str) -> str:
    """HTML tag'lerini ve fazla boşlukları temizle"""
    # HTML tag'lerini kaldır
    text = re.sub('<[^<]+?>', '', html_text)
    # HTML entity'leri dönüştür
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"')
    text = text.replace('&amp;', '&')
    text = text.replace('&#8217;', "'")
    # Fazla boşlukları temizle
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def yolpedia_verileri_cek(max_sayfa: int = 10) -> List[Dict]:
    """
    YolPedia'dan tüm verileri çek
    
    Args:
        max_sayfa: Maksimum kaç sayfa çekilecek (her sayfa 100 yazı)
    
    Returns:
        Çekilen yazı listesi
    """
    base_url = "https://yolpedia.eu/wp-json/wp/v2/posts"
    all_posts = []
    
    print("\n" + "=" * 60)
    print("🌐 YolPedia.eu'dan veri çekiliyor...")
    print("=" * 60)
    
    for sayfa in range(1, max_sayfa + 1):
        try:
            print(f"\n📄 Sayfa {sayfa} çekiliyor...", end=" ")
            
            response = requests.get(
                base_url,
                params={
                    'per_page': 100,
                    'page': sayfa,
                    '_embed': 1
                },
                timeout=15
            )
            
            # Başarılı mı?
            if response.status_code == 200:
                posts = response.json()
                
                if not posts:
                    print("❌ Boş sayfa - durduruluyor")
                    break
                
                all_posts.extend(posts)
                print(f"✅ {len(posts)} yazı çekildi (Toplam: {len(all_posts)})")
                
                # Rate limiting - sunucuya yük olmaması için
                time.sleep(0.5)
                
            elif response.status_code == 400:
                # Sayfalar bitti
                print("✅ Tüm sayfalar çekildi")
                break
            else:
                print(f"⚠️ Hata: {response.status_code}")
                break
                
        except requests.exceptions.Timeout:
            print("⏱️ Zaman aşımı - devam ediliyor")
            continue
        except Exception as e:
            print(f"❌ Hata: {e}")
            break
    
    print(f"\n✅ Toplam {len(all_posts)} yazı başarıyla çekildi!")
    return all_posts

def wordpress_to_candede(post: Dict) -> Dict:
    """
    WordPress formatını Can Dede formatına dönüştür
    
    Args:
        post: WordPress REST API post objesi
    
    Returns:
        Can Dede formatında kayıt
    """
    # Başlık
    baslik = post.get('title', {}).get('rendered', 'Başlıksız')
    baslik = temizle_html(baslik)
    
    # İçerik
    icerik = post.get('content', {}).get('rendered', '')
    icerik = temizle_html(icerik)
    
    # Link
    link = post.get('link', '')
    
    # Tarih (opsiyonel)
    tarih = post.get('date', '')
    
    return {
        'baslik': baslik,
        'link': link,
        'icerik': icerik[:5000],  # İlk 5000 karakter
        'tarih': tarih
    }

def veritabani_olustur(output_file: str = "yolpedia_data.json", max_sayfa: int = 10):
    """
    YolPedia'dan veri çekip JSON dosyası oluştur
    
    Args:
        output_file: Çıktı dosya adı
        max_sayfa: Maksimum sayfa sayısı
    """
    start_time = time.time()
    
    # 1. WordPress'ten veri çek
    wordpress_posts = yolpedia_verileri_cek(max_sayfa=max_sayfa)
    
    if not wordpress_posts:
        print("\n❌ Hiç veri çekilemedi!")
        return
    
    # 2. Can Dede formatına dönüştür
    print(f"\n🔄 Veriler dönüştürülüyor...", end=" ")
    candede_data = [wordpress_to_candede(post) for post in wordpress_posts]
    print("✅")
    
    # 3. JSON dosyasına kaydet
    print(f"💾 '{output_file}' dosyasına kaydediliyor...", end=" ")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(candede_data, f, ensure_ascii=False, indent=2)
    print("✅")
    
    # 4. İstatistikler
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("✅ VERİ TABANI BAŞARIYLA OLUŞTURULDU!")
    print("=" * 60)
    print(f"📊 Toplam kayıt: {len(candede_data)}")
    print(f"📁 Dosya: {output_file}")
    print(f"⏱️ Süre: {elapsed:.1f} saniye")
    print(f"📅 Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    # 5. Örnek kayıt göster
    if candede_data:
        print("\n📝 Örnek kayıt:")
        ornek = candede_data[0]
        print(f"  Başlık: {ornek['baslik'][:60]}...")
        print(f"  Link: {ornek['link']}")
        print(f"  İçerik: {ornek['icerik'][:100]}...")
    
    print("=" * 60)

def veritabani_kontrol(filename: str = "yolpedia_data.json"):
    """
    Mevcut veri tabanını kontrol et
    
    Args:
        filename: Kontrol edilecek dosya
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print("\n" + "=" * 60)
        print("📊 VERİ TABANI İSTATİSTİKLERİ")
        print("=" * 60)
        print(f"📁 Dosya: {filename}")
        print(f"📊 Toplam kayıt: {len(data)}")
        
        if data:
            ornek = data[0]
            print(f"\n📝 İlk kayıt:")
            print(f"  Başlık: {ornek.get('baslik', 'N/A')[:60]}...")
            print(f"  Link: {ornek.get('link', 'N/A')}")
            
            # Alanları kontrol et
            required = ['baslik', 'link', 'icerik']
            missing = [f for f in required if f not in ornek]
            if missing:
                print(f"\n⚠️ Eksik alanlar: {missing}")
            else:
                print(f"\n✅ Tüm gerekli alanlar mevcut")
        
        print("=" * 60)
        
    except FileNotFoundError:
        print(f"\n❌ Dosya bulunamadı: {filename}")
        print("💡 Önce 'veritabani_olustur()' çalıştırın")
    except json.JSONDecodeError:
        print(f"\n❌ JSON formatı hatalı: {filename}")
    except Exception as e:
        print(f"\n❌ Hata: {e}")

# =====================================================
# KULLANIM
# =====================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║         YOLPEDİA VERİ TABANINI GÜNCELLEYICI             ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    print("Ne yapmak istersiniz?")
    print("1. Veri tabanını güncelle (tüm verileri çek)")
    print("2. Mevcut veri tabanını kontrol et")
    print("3. Çık")
    
    secim = input("\nSeçiminiz (1/2/3): ").strip()
    
    if secim == "1":
        print("\n🚀 Güncelleme başlıyor...")
        
        # Kaç sayfa?
        print("\nBilgi: Her sayfa ~100 yazı içerir")
        print("Önerilen: 10 sayfa (yaklaşık 1000 yazı)")
        
        try:
            sayfa = input("Kaç sayfa çekilsin? (varsayılan: 10): ").strip()
            sayfa = int(sayfa) if sayfa else 10
        except:
            sayfa = 10
        
        # Çek!
        veritabani_olustur(max_sayfa=sayfa)
        
        print("\n💡 Şimdi Can Dede'yi yeniden başlatın!")
        print("   Yeni veriler otomatik olarak yüklenecek.")
        
    elif secim == "2":
        veritabani_kontrol()
        
    elif secim == "3":
        print("\n👋 Görüşürüz!")
    else:
        print("\n❌ Geçersiz seçim!")
