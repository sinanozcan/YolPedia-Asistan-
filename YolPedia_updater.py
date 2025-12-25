"""
YolPedia.eu Akıllı Veri Çekici
Özellikler: Retry (Tekrar Deneme), Anti-Ban Bekleme, Veri Koruma
"""

import requests
import json
import time
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
        
        # 1. BAĞLANTIYI GÜÇLENDİR (Koparsa 3 kere daha dene)
        retries = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504, 429])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        # 2. GERÇEKÇİ TARAYICI KİMLİĞİ
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache'
        })
    
    def get_all_posts_formatted(self, max_posts=3000):
        all_posts = []
        page = 1
        per_page = 100
        consecutive_errors = 0
        
        print("📡 YolPedia'ya sızılıyor...")
        
        while len(all_posts) < max_posts:
            try:
                endpoint = f"{self.base_url}/posts"
                params = {
                    'per_page': per_page,
                    'page': page,
                    '_embed': 1
                }
                
                # verify=False ile SSL hatasını aş
                response = self.session.get(endpoint, params=params, timeout=30, verify=False)
                
                # Eğer yasaklandıysak (403/401)
                if response.status_code in [403, 401, 406]:
                    print(f"⚠️ Engel Yedik (Kod: {response.status_code}). 5 saniye bekleyip tekrar deniyoruz...")
                    time.sleep(5)
                    consecutive_errors += 1
                    if consecutive_errors > 3: 
                        print("❌ Çok fazla engel, durduruluyor.")
                        break
                    continue
                
                if response.status_code != 200:
                    print(f"⚠️ Hata: {response.status_code}")
                    break
                
                posts = response.json()
                if not posts:
                    print("✅ Veri bitti (Sayfa boş).")
                    break
                
                # Verileri İşle
                for post in posts:
                    raw_content = post.get('content', {}).get('rendered', '')
                    clean_content = re.sub('<[^<]+?>', '', raw_content) # HTML temizle
                    clean_content = re.sub(r'\s+', ' ', clean_content).strip()
                    
                    all_posts.append({
                        'baslik': post.get('title', {}).get('rendered', ''),
                        'link': post.get('link', ''),
                        'icerik': clean_content[:8000],
                        'tarih': post.get('date', '')
                    })
                
                print(f"  ✅ Sayfa {page} alındı. (Toplam: {len(all_posts)})")
                
                # Başarılı olunca hata sayacını sıfırla
                consecutive_errors = 0
                page += 1
                
                # Güvenlik duvarını uyandırmamak için bekleme
                time.sleep(1) 
                
            except Exception as e:
                print(f"❌ Kritik Hata: {e}")
                break
        
        # === KRİTİK GÜVENLİK ÖNLEMİ ===
        # Eğer çekilen veri 100'den azsa (bir hata olduysa),
        # BOŞ LİSTE DÖNDÜR Kİ ESKİ VERİTABANI SİLİNMESİN.
        if len(all_posts) < 50: 
            print("⚠️ Çekilen veri çok az! Güvenlik nedeniyle işlem iptal ediliyor.")
            return [] # Boş döndür
            
        return all_posts

    def update_github_repo(self, new_data, github_token, repo_name="sinanozcan/YolPedia-Asistan-"):
        """Veriyi GitHub'a kalıcı olarak yazar"""
        
        # EKSTRA KORUMA: Eğer veri boşsa işlem yapma
        if not new_data or len(new_data) < 50:
            return False, "⚠️ Yetersiz veri çekildi. Mevcut veritabanı silinmemesi için işlem durduruldu."

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
                repo.update_file(file_path, f"🤖 Güncelleme: {len(new_data)} Yazı", json_content, sha)
            else:
                repo.create_file(file_path, "🤖 İlk Yükleme", json_content)
                
            return True, f"Başarılı! {len(new_data)} yazı GitHub'a kaydedildi."
            
        except Exception as e:
            return False, f"GitHub Hatası: {str(e)}"
