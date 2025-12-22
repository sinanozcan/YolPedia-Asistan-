"""
YolPedia Veri Güncelleyici - Güçlendirilmiş Versiyon
Timeout ve yeniden deneme özellikleri ile
"""

import requests
import json
import re
from typing import List, Dict
from datetime import datetime
import time

def temizle_html(html_text: str) -> str:
    """HTML tag'lerini ve fazla boşlukları temizle"""
    text = re.sub('<[^<]+?>', '', html_text)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"')
    text = text.replace('&amp;', '&')
    text = text.replace('&#8217;', "'")
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def yolpedia_sayfa_cek(sayfa: int, max_deneme: int = 5) -> List[Dict]:
    """
    Tek bir sayfayı çek - yeniden deneme ile
    
    Args:
        sayfa: Sayfa numarası
        max_deneme: Maksimum deneme sayısı
    
    Returns:
        Çekilen yazı listesi
    """
    base_url = "https://yolpedia.eu/wp-json/wp/v2/posts"
    
    for deneme in range(1, max_deneme + 1):
        try:
            response = requests.get(
                base_url,
                params={
                    'per_page': 100,
                    'page': sayfa,
                    '_embed': 1
                },
                timeout=30,  # 30 saniye timeout (artırıldı)
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
            )
            
            if response.status_code == 200:
                posts = response.json()
                return posts
            elif response.status_code == 400:
                # Sayfalar bitti
                return []
            else:
                print(f"⚠️ HTTP {response.status_code}")
                if deneme < max_deneme:
                    print(f"   🔄 {deneme}/{max_deneme} - 3 saniye sonra tekrar deneniyor...")
                    time.sleep(3)
                continue
                
        except requests.exceptions.Timeout:
            if deneme < max_deneme:
                print(f"   ⏱️ Zaman aşımı - {deneme}/{max_deneme} - 5 saniye sonra tekrar deneniyor...")
                time.sleep(5)
            else:
                print(f"   ❌ {max_deneme} denemeden sonra vazgeçildi")
            continue
            
        except requests.exceptions.ConnectionError:
            if deneme < max_deneme:
                print(f"   🌐 Bağlantı hatası - {deneme}/{max_deneme} - 5 saniye sonra tekrar deneniyor...")
                time.sleep(5)
            else:
                print(f"   ❌ Bağlantı kurulamadı")
            continue
            
        except Exception as e:
            print(f"   ❌ Beklenmeyen hata: {e}")
            if deneme < max_deneme:
                time.sleep(3)
            continue
    
    return []

def yolpedia_verileri_cek(max_sayfa: int = 10) -> List[Dict]:
    """
    YolPedia'dan tüm verileri çek
    
    Args:
        max_sayfa: Maksimum kaç sayfa çekilecek
    
    Returns:
        Çekilen yazı listesi
    """
    all_posts = []
    
    print("\n" + "=" * 60)
    print("🌐 YolPedia.eu'dan veri çekiliyor...")
    print("=" * 60)
    print(f"ℹ️  Her sayfa maksimum 5 kez denenecek")
    print(f"ℹ️  Timeout süresi: 30 saniye\n")
    
    basarili_sayfa = 0
    basarisiz_sayfa = 0
    
    for sayfa in range(1, max_sayfa + 1):
        print(f"📄 Sayfa {sayfa} çekiliyor...", end=" ")
        
        posts = yolpedia_sayfa_cek(sayfa, max_deneme=5)
        
        if posts:
            all_posts.extend(posts)
            basarili_sayfa += 1
            print(f"✅ {len(posts)} yazı çekildi (Toplam: {len(all_posts)})")
            time.sleep(1)  # Sunucuya nazik davran
        elif len(all_posts) > 0 and not posts:
            # Sayfa boş ve önceden veri çektik = sayfalar bitti
            print("✅ Tüm sayfalar çekildi")
            break
        else:
            basarisiz_sayfa += 1
            print(f"❌ Çekilemedi")
            
            # 3 sayfa üst üste başarısız olursa dur
            if basarisiz_sayfa >= 3:
                print("\n⚠️ Çok fazla başarısız deneme, durduruluyor...")
                break
    
    print(f"\n✅ Toplam {len(all_posts)} yazı başarıyla çekildi!")
    print(f"📊 İstatistik: {basarili_sayfa} başarılı, {basarisiz_sayfa} başarısız sayfa")
    
    return all_posts

def wordpress_to_candede(post: Dict) -> Dict:
    """WordPress formatını Can Dede formatına dönüştür"""
    baslik = post.get('title', {}).get('rendered', 'Başlıksız')
    baslik = temizle_html(baslik)
    
    icerik = post.get('content', {}).get('rendered', '')
    icerik = temizle_html(icerik)
    
    link = post.get('link', '')
    tarih = post.get('date', '')
    
    return {
        'baslik': baslik,
        'link': link,
        'icerik': icerik[:5000],
        'tarih': tarih
    }

def veritabani_olustur(output_file: str = "yolpedia_data.json", max_sayfa: int = 10):
    """YolPedia'dan veri çekip JSON dosyası oluştur"""
    start_time = time.time()
    
    # 1. WordPress'ten veri çek
    wordpress_posts = yolpedia_verileri_cek(max_sayfa=max_sayfa)
    
    if not wordpress_posts:
        print("\n❌ Hiç veri çekilemedi!")
        print("\n💡 Öneriler:")
        print("  1. İnternet bağlantınızı kontrol edin")
        print("  2. YolPedia.eu sitesinin çalıştığını kontrol edin")
        print("  3. Birkaç dakika sonra tekrar deneyin")
        print("  4. VPN kullanıyorsanız kapatmayı deneyin")
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
    """Mevcut veri tabanını kontrol et"""
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
║    YOLPEDİA VERİ GÜNCELLEYICI - GÜÇLENDİRİLMİŞ         ║
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
        print("\nBilgi: Her sayfa ~100 yazı içerir")
        print("Önerilen: 5 sayfa (yaklaşık 500 yazı) - daha hızlı")
        
        try:
            sayfa = input("Kaç sayfa çekilsin? (varsayılan: 5): ").strip()
            sayfa = int(sayfa) if sayfa else 5
        except:
            sayfa = 5
        
        veritabani_olustur(max_sayfa=sayfa)
        
        print("\n💡 Şimdi Can Dede'yi başlatın!")
        print("   Terminal'de: streamlit run app.py")
        
    elif secim == "2":
        veritabani_kontrol()
        
    elif secim == "3":
        print("\n👋 Görüşürüz!")
    else:
        print("\n❌ Geçersiz seçim!")
