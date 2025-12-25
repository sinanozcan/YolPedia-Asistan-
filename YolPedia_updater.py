"""
YolPedia.eu Akıllı Veri Çekici
Versiyon: Ninja Modu (Daha Yavaş, Daha Az Dikkat Çeken, Kararlı)
"""

import requests
import json
import time
import random  # Rastgelelik eklendi
import urllib3
from github import Github
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# SSL Uyarılarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class YolPediaAPI:
    def __init__(self):
        self.base_url = "https://yolpedia.eu/wp-json/wp/v2"
        self.session = requests.Session()
        
        # Bağlantı kopsa bile pes etme, 5 kere daha dene
        retries = Retry(
            total=5, 
            backoff_factor=1, # Her hatada bekleme süresini katla (1s, 2s, 4s...)
            status_forcelist=[500, 502, 503, 504, 429, 403]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Connection': 'keep-alive',
            'Referer': 'https://yolpedia.eu/' # Referans göster
        })
    
    def get_all_posts_formatted(self, max_posts=3000):
        all_posts = []
        page = 1
        # STRATEJİ DEĞİŞİKLİĞİ: 100 yerine 50'şer çekiyoruz. Daha çok istek ama daha az dikkat çeker.
        per_page = 50 
        
        print("📡 YolPedia'ya sızılıyor (Ninja Modu)...")
        
        while len(all_posts) < max_posts:
            try:
                endpoint = f"{self.base_url}/posts"
                params = {
                    'per_page': per_page,
                    'page': page,
                    '_embed': 1
                }
                
                # Timeout süresini artırdık (30 saniye)
                response = self.session.get(endpoint, params=params, timeout=30, verify=False)
                
                if response.status_code != 200:
                    print(f"⚠️ Engel/Hata (Kod: {response.status_code}). Bekleniyor...")
                    time.sleep(5) # Hata alınca uzun bekle
                    break # Bu döngüyü kır, eldekilerle devam etme riskini almayalım, güvenli çıkış.
                
                posts = response.json()
                if not posts:
                    print("✅ Veri bitti (Sayfa boş).")
                    break
                
                # Verileri İşle
                for post in posts:
                    raw_content = post.get('content', {}).get('rendered', '')
                    clean_content = re.sub('<[^<]+?>', '', raw_content)
                    clean_content = re.sub(r'\s+', ' ', clean_content).strip()
                    
                    all_posts.append({
                        'baslik': post.get('title', {}).get('rendered', ''),
                        'link': post.get('link', ''),
                        'icerik': clean_content[:8000],
                        'tarih': post.get('date', '')
                    })
                
                print(f"  ✅ Sayfa {page} alındı. (Toplam: {len(all_posts)})")
                
                page += 1
                
                # === NİNJA TAKTİĞİ ===
                # Sabit süre bekleme, rastgele bekle. (2 ile 4 saniye arası)
                # Bu, sunucunun "Bot bu" demesini zorlaştırır.
                sleep_time = random.uniform(2.0, 4.0)
                time.sleep(sleep_time)
                
            except Exception as e:
                print(f"❌ Kritik Hata: {e}")
                break
        
        # GÜVENLİK: Eğer çok az veri geldiyse (örn: sadece 195 tane),
        # işlemi iptal et ki 2294'lük veritabanı bozulmasın.
        if len(all_posts) < 500: # Eşiği 500'e çektim. 500'den azsa güncelleme yapmaz.
            print(f"⚠️ Çekilen veri sayısı ({len(all_posts)}) şüpheli derecede az. Veritabanı korunuyor.")
            return [] 
            
        return all_posts

    def update_github_repo(self, new_data, github_token, repo_name="sinanozcan/YolPedia-Asistan-"):
        """Veriyi GitHub'a kalıcı olarak yazar"""
        
        if not new_data:
            return False, "⚠️ Güvenlik Duvarı Engeli: Yeterli veri çekilemedi. Eski veritabanı korundu."

        try:
            g = Github(github_token)
            repo = g.get_repo(repo_name)
            file_path = "yolpedia_data.json"
            
            try:
                contents = repo.get_contents(file_path)
                sha = contents.sha
            except:
                sha = None
            
            json_content = json.dumps(new_data, ensure_ascii=False, indent=2)
            
            if sha:
                repo.update_file(file_path, f"🤖 Ninja Güncelleme: {len(new_data)} Yazı", json_content, sha)
            else:
                repo.create_file(file_path, "🤖 İlk Yükleme", json_content)
                
            return True, f"Başarılı! {len(new_data)} yazı GitHub'a kaydedildi."
            
        except Exception as e:
            return False, f"GitHub Hatası: {str(e)}"
