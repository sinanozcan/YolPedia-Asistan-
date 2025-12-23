"""
YolPedia.eu Canlı Veri Çekici
WordPress REST API Kullanarak - GÜÇLENDİRİLMİŞ VERSİYON
"""

import requests
import json
from typing import List, Dict, Optional
from datetime import datetime
import time
import urllib3

# SSL Uyarılarını Sustur (Güvenlik duvarını aşmak için gerekli)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class YolPediaAPI:
    """
    YolPedia.eu WordPress REST API Client
    """
    
    def __init__(self):
        self.base_url = "https://yolpedia.eu/wp-json/wp/v2"
        self.session = requests.Session()
        
        # GÜNCELLEME: Tam Teçhizatlı Tarayıcı Kimliği
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://yolpedia.eu/',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive'
        })
    
    def get_posts(self, per_page: int = 100, page: int = 1, 
                  search: str = None, categories: List[int] = None) -> List[Dict]:
        
        endpoint = f"{self.base_url}/posts"
        params = {
            'per_page': min(per_page, 100),
            'page': page,
            '_embed': 1,
        }
        
        if search: params['search'] = search
        if categories: params['categories'] = ','.join(map(str, categories))
        
        try:
            # GÜNCELLEME: verify=False ile SSL kontrolünü atlıyoruz
            response = self.session.get(endpoint, params=params, timeout=15, verify=False)
            
            # Hata varsa ekrana bas (Debugging)
            if response.status_code != 200:
                print(f"⚠️ Hata Kodu: {response.status_code}")
                print(f"⚠️ Cevap: {response.text[:200]}")
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Bağlantı Hatası: {e}")
            return []
    
    def get_all_posts(self, max_posts: int = 2500) -> List[Dict]:
        all_posts = []
        page = 1
        per_page = 100
        
        print(f"📡 YolPedia'dan veri çekiliyor...")
        
        while len(all_posts) < max_posts:
            try:
                posts = self.get_posts(per_page=per_page, page=page)
                
                if not posts:
                    print(f"⚠️ Sayfa {page} boş döndü veya erişilemedi.")
                    break
                
                all_posts.extend(posts)
                print(f"  ✅ Sayfa {page}: {len(posts)} yazı çekildi (Toplam: {len(all_posts)})")
                
                if len(posts) < per_page:
                    break
                
                page += 1
                time.sleep(1) # Sunucuyu kızdırmamak için bekleme süresini artırdık
                
            except Exception as e:
                print(f"❌ Döngüde hata: {e}")
                break
        
        print(f"✅ Toplam {len(all_posts)} yazı başarıyla çekildi")
        return all_posts[:max_posts]
    
    def parse_post(self, post: Dict) -> Dict:
        import re
        content = post.get('content', {}).get('rendered', '')
        # HTML temizliği
        content = re.sub('<[^<]+?>', '', content)
        content = re.sub(r'\s+', ' ', content).strip()
        
        return {
            'baslik': post.get('title', {}).get('rendered', ''),
            'link': post.get('link', ''),
            'icerik': content[:8000], # İçerik limitini artırdım
            'tarih': post.get('date', ''),
            'yazar': post.get('_embedded', {}).get('author', [{}])[0].get('name', 'Bilinmeyen'),
        }
    
    def export_to_json(self, posts: List[Dict], filename: str = "yolpedia_data.json"):
        if not posts:
            print("⚠️ Kaydedilecek veri yok! Dosya üzerine yazılmadı.")
            return

        parsed_posts = [self.parse_post(post) for post in posts]
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(parsed_posts, f, ensure_ascii=False, indent=2)
        
        print(f"💾 {len(parsed_posts)} yazı '{filename}' dosyasına kaydedildi")
