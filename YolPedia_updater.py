"""
YolPedia.eu Canlı Veri Çekici ve GitHub Güncelleyici
Versiyon: Hata Ayıklama Modu (Debug Mode)
"""

import requests
import json
import time
import urllib3
from github import Github
import re

# SSL Uyarılarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class YolPediaAPI:
    def __init__(self):
        self.base_url = "https://yolpedia.eu/wp-json/wp/v2"
        self.session = requests.Session()
        # Tarayıcı taklidi (Mac/Chrome)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Connection': 'keep-alive',
            'Referer': 'https://google.com/' # Referans Google gibi görünsün
        })
    
    def get_all_posts_formatted(self, max_posts=3000):
        """Tüm yazıları çeker ve formatlar"""
        all_posts = []
        page = 1
        
        print("📡 Bağlantı testi yapılıyor...")
        
        # 1. ÖNCE BAĞLANTIYI TEST ET (Hata varsa direkt patlasın ki görelim)
        try:
            test_endpoint = f"{self.base_url}/posts"
            test_resp = self.session.get(test_endpoint, params={'per_page': 1}, timeout=20, verify=False)
            
            if test_resp.status_code == 403:
                raise Exception("⛔ ERİŞİM ENGELLENDİ (403)! Sitenin güvenlik duvarı Streamlit IP'sini engelliyor.")
            elif test_resp.status_code != 200:
                raise Exception(f"⚠️ Site Hatası! Kod: {test_resp.status_code} - Mesaj: {test_resp.text[:100]}")
                
        except Exception as e:
            # Bağlantı hatasını direkt yukarı fırlat
            raise Exception(f"Bağlantı Kurulamadı: {str(e)}")

        print("📡 Veri çekimi başlıyor...")
        
        # 2. VERİLERİ ÇEK (Yavaş Mod)
        while len(all_posts) < max_posts:
            try:
                endpoint = f"{self.base_url}/posts"
                # _embed=1 bazen sunucuyu yorar, onu kaldırdım daha hafif olsun diye
                params = {
                    'per_page': min(50, max_posts - len(all_posts)), # Sayfa başı isteği 50'ye düşürdüm (Daha az dikkat çeker)
                    'page': page
                }
                
                response = self.session.get(endpoint, params=params, timeout=20, verify=False)
                
                if response.status_code != 200: 
                    print(f"Sayfa {page} alınamadı. Durdu.")
                    break
                
                posts = response.json()
                if not posts: break
                
                for post in posts:
                    # HTML Temizliği
                    raw_content = post.get('content', {}).get('rendered', '')
                    clean_content = re.sub('<[^<]+?>', '', raw_content)
                    clean_content = re.sub(r'\s+', ' ', clean_content).strip()
                    
                    all_posts.append({
                        'baslik': post.get('title', {}).get('rendered', ''),
                        'link': post.get('link', ''),
                        'icerik': clean_content[:8000],
                        'tarih': post.get('date', '')
                    })
                
                print(f"✅ Sayfa {page} alındı. Toplam: {len(all_posts)}")
                page += 1
                time.sleep(1.5) # Bekleme süresini artırdım (Güvenlik duvarını kızdırmamak için)
                
            except Exception as e:
                # Döngü içinde hata olursa eldeki veriyi kurtar
                print(f"Hata oluştu, çekilen verilerle devam ediliyor: {e}")
                break
                
        return all_posts

    def update_github_repo(self, new_data, github_token, repo_name="sinanozcan/YolPedia-Asistan-"):
        """Veriyi GitHub'a kalıcı olarak yazar"""
        try:
            g = Github(github_token)
            repo = g.get_repo(repo_name)
            file_path = "yolpedia_data.json"
            
            try:
                contents = repo.get_contents(file_path)
                sha = contents.sha
            except:
                sha = None # Dosya yoksa ilk kez oluştur
            
            json_content = json.dumps(new_data, ensure_ascii=False, indent=2)
            
            if sha:
                repo.update_file(file_path, "🤖 Otomatik Güncelleme", json_content, sha)
            else:
                repo.create_file(file_path, "🤖 İlk Yükleme", json_content)
                
            return True, f"Başarılı! {len(new_data)} yazı GitHub'a kaydedildi."
            
        except Exception as e:
            return False, f"GitHub Hatası: {str(e)}"
