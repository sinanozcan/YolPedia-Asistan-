"""
YolPedia.eu Canlı Veri Çekici
WordPress REST API Kullanarak
"""

import requests
import json
from typing import List, Dict, Optional
from datetime import datetime
import time

class YolPediaAPI:
    """
    YolPedia.eu WordPress REST API Client
    """
    
    def __init__(self):
        self.base_url = "https://yolpedia.eu/wp-json/wp/v2"
        self.session = requests.Session()
        self.session.headers.update({
             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def get_posts(self, per_page: int = 100, page: int = 1, 
                  search: str = None, categories: List[int] = None) -> List[Dict]:
        """
        YolPedia'dan yazıları çek
        
        Args:
            per_page: Sayfa başına yazı sayısı (max 100)
            page: Sayfa numarası
            search: Arama terimi
            categories: Kategori ID'leri
        
        Returns:
            Yazı listesi
        """
        endpoint = f"{self.base_url}/posts"
        params = {
            'per_page': min(per_page, 100),
            'page': page,
            '_embed': 1,  # Resim ve kategori bilgilerini dahil et
        }
        
        if search:
            params['search'] = search
        
        if categories:
            params['categories'] = ','.join(map(str, categories))
        
        try:
            response = self.session.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API Hatası: {e}")
            return []
    
    def get_all_posts(self, max_posts: int = 1000) -> List[Dict]:
        """
        Tüm yazıları çek (sayfalama ile)
        
        Args:
            max_posts: Maksimum çekilecek yazı sayısı
        
        Returns:
            Tüm yazı listesi
        """
        all_posts = []
        page = 1
        per_page = 100
        
        print(f"📡 YolPedia'dan veri çekiliyor...")
        
        while len(all_posts) < max_posts:
            posts = self.get_posts(per_page=per_page, page=page)
            
            if not posts:
                break
            
            all_posts.extend(posts)
            print(f"  ✅ Sayfa {page}: {len(posts)} yazı çekildi (Toplam: {len(all_posts)})")
            
            # Sayfa bitti mi?
            if len(posts) < per_page:
                break
            
            page += 1
            time.sleep(0.5)  # Rate limiting - nazik ol
        
        print(f"✅ Toplam {len(all_posts)} yazı çekildi")
        return all_posts[:max_posts]
    
    def get_categories(self) -> List[Dict]:
        """
        Tüm kategorileri çek
        
        Returns:
            Kategori listesi
        """
        endpoint = f"{self.base_url}/categories"
        params = {'per_page': 100}
        
        try:
            response = self.session.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Kategori çekme hatası: {e}")
            return []
    
    def parse_post(self, post: Dict) -> Dict:
        """
        WordPress post'unu Can Dede formatına çevir
        
        Args:
            post: WordPress REST API post objesi
        
        Returns:
            Can Dede veri tabanı formatı
        """
        # HTML'i temizle
        import re
        content = post.get('content', {}).get('rendered', '')
        content = re.sub('<[^<]+?>', '', content)  # HTML tag'lerini kaldır
        content = re.sub(r'\s+', ' ', content).strip()  # Fazla boşlukları temizle
        
        return {
            'baslik': post.get('title', {}).get('rendered', ''),
            'link': post.get('link', ''),
            'icerik': content[:5000],  # İlk 5000 karakter
            'tarih': post.get('date', ''),
            'yazar': post.get('_embedded', {}).get('author', [{}])[0].get('name', 'Bilinmeyen'),
        }
    
    def export_to_json(self, posts: List[Dict], filename: str = "yolpedia_data.json"):
        """
        Çekilen verileri JSON dosyasına kaydet
        
        Args:
            posts: Post listesi
            filename: Çıktı dosya adı
        """
        parsed_posts = [self.parse_post(post) for post in posts]
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(parsed_posts, f, ensure_ascii=False, indent=2)
        
        print(f"💾 {len(parsed_posts)} yazı '{filename}' dosyasına kaydedildi")
    
    def search_posts(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Belirli bir terimi ara
        
        Args:
            query: Arama terimi
            max_results: Maksimum sonuç sayısı
        
        Returns:
            Arama sonuçları
        """
        posts = self.get_posts(search=query, per_page=max_results)
        return [self.parse_post(post) for post in posts]


# =====================================================
# KULLANIM ÖRNEKLERİ
# =====================================================

def main():
    """Ana fonksiyon - örnekler"""
    
    api = YolPediaAPI()
    
    print("=" * 60)
    print("YOLPEDIA.EU CANLI VERİ ÇEKİCİ")
    print("=" * 60)
    
    # 1. KATEGORİLERİ GÖRÜNTÜLE
    print("\n📂 Kategoriler yükleniyor...")
    categories = api.get_categories()
    print(f"✅ {len(categories)} kategori bulundu:")
    for cat in categories[:5]:
        print(f"  • {cat['name']} (ID: {cat['id']}, {cat['count']} yazı)")
    
    # 2. İLK 10 YAZIYI ÇEK
    print("\n📰 İlk 10 yazı çekiliyor...")
    posts = api.get_posts(per_page=10)
    print(f"✅ {len(posts)} yazı çekildi:")
    for post in posts[:3]:
        parsed = api.parse_post(post)
        print(f"  • {parsed['baslik'][:60]}...")
    
    # 3. BELIRLI BIR TERIMI ARA
    print("\n🔍 'Alevi' kelimesini arıyorum...")
    search_results = api.search_posts("Alevi", max_results=5)
    print(f"✅ {len(search_results)} sonuç bulundu:")
    for result in search_results:
        print(f"  • {result['baslik'][:60]}...")
    
    # 4. TÜM VERİLERİ ÇEK VE KAYDET (DİKKATLİ!)
    print("\n" + "=" * 60)
    choice = input("Tüm verileri çekip kaydetmek ister misiniz? (e/h): ")
    if choice.lower() == 'e':
        all_posts = api.get_all_posts(max_posts=500)  # İlk 500 yazı
        api.export_to_json(all_posts, "yolpedia_data.json")
        print("\n✅ Veri tabanı güncellendi!")
    else:
        print("İptal edildi.")
    
    print("\n" + "=" * 60)
    print("İşlem tamamlandı!")
    print("=" * 60)


def update_database_periodically():
    """
    Veri tabanını düzenli olarak güncelle
    Cron job veya zamanlanmış görev olarak kullanılabilir
    """
    api = YolPediaAPI()
    
    print(f"🕐 {datetime.now()} - Veri tabanı güncelleniyor...")
    
    # Tüm yazıları çek
    all_posts = api.get_all_posts(max_posts=1000)
    
    # JSON'a kaydet
    api.export_to_json(all_posts, "yolpedia_data.json")
    
    print(f"✅ {datetime.now()} - Güncelleme tamamlandı!")


if __name__ == "__main__":
    main()
    
    # Düzenli güncelleme için:
    # update_database_periodically()
