"""
YolPedia.eu Güvenli Veri Çekici
Strateji: Düşük Hız, Yüksek Kamuflaj (Anti-Ban)
"""

import requests
import json
import time
import random
import urllib3
from github import Github
import re

# SSL Uyarılarını Gizle
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class YolPediaAPI:
    def __init__(self):
        self.base_url = "https://yolpedia.eu/wp-json/wp/v2"
        self.session = requests.Session()
        
        # == TAM KAMUFLAJ HEADERS ==
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
        })
    
    def get_all_posts_formatted(self, max_posts=3000):
        all_posts = []
        page = 1
        
        # STRATEJİ: Az iste, sıkıntı çıkmasın.
        per_page = 20 
        
        print("📡 YolPedia'ya 'insan gibi' bağlanılıyor...")
        
        while len(all_posts) < max_posts:
            try:
                endpoint = f"{self.base_url}/posts"
                params = {
                    'per_page': per_page,
                    'page': page,
                    '_embed': 1 # Resim ve yazar bilgisi için
                }
                
                # İsteği Gönder
                response = self.session.get(endpoint, params=params, timeout=30, verify=False)
                
                # == HATA YÖNETİMİ ==
                if response.status_code == 403 or response.status_code == 429:
                    print(f"⚠️ Engel (Kod: {response.status_code}). 10 saniye soğutma molası...")
                    time.sleep(10) # 10 saniye bekle
                    # Aynı sayfayı tekrar denemek için continue demiyoruz, 
                    # bu seferlik pas geçip şansımızı sonraki denemede zorlamayalım diye break de demiyoruz.
                    # Aslında en güvenlisi burada durmaktır ama biz inatçıyız:
                    # Session'ı yenileyip tekrar deneyelim:
                    self.session = requests.Session()
                    self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...'}) # User Agent değiştir
                    continue

                if response.status_code != 200:
                    print(f"⚠️ Hata: {response.status_code}")
                    break
                
                posts = response.json()
                
                # Liste boşsa veya hata mesajı döndüyse (bazen WP hata mesajını JSON döner)
                if not posts or isinstance(posts, dict): 
                    print("✅ Veri bitti veya sayfa sonu.")
                    break
                
                # Verileri İşle
                for post in posts:
                    try:
                        raw_content = post.get('content', {}).get('rendered', '')
                        # HTML Temizliği
                        clean_content = re.sub('<[^<]+?>', '', raw_content)
                        clean_content = re.sub(r'\s+', ' ', clean_content).strip()
                        
                        all_posts.append({
                            'baslik': post.get('title', {}).get('rendered', ''),
                            'link': post.get('link', ''),
                            'icerik': clean_content[:8000],
                            'tarih': post.get('date', '')
                        })
                    except: continue

                print(f"  ✅ Sayfa {page} (20 Kayıt) alındı. Toplam: {len(all_posts)}")
                page += 1
                
                # == BEKLEME SÜRESİ ==
                # Her istekten sonra rastgele 1-3 saniye bekle
                time.sleep(random.uniform(1.0, 3.0))
                
            except Exception as e:
                print(f"❌ Kritik Hata: {e}")
                time.sleep(5)
                break
        
        # GÜVENLİK: Eğer veri çekilemediyse boş dön ki eskisi silinmesin
        if len(all_posts) < 50: 
            print(f"⚠️ Yetersiz veri ({len(all_posts)}). İşlem iptal.")
            return []
            
        return all_posts

    def update_github_repo(self, new_data, github_token, repo_name="sinanozcan/YolPedia-Asistan-"):
        """Veriyi GitHub'a kalıcı olarak yazar"""
        
        if not new_data:
            return False, "⚠️ Veri çekilemediği için güncelleme iptal edildi."

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
                repo.update_file(file_path, f"🤖 Otomatik Güncelleme: {len(new_data)} Kaynak", json_content, sha)
            else:
                repo.create_file(file_path, "🤖 İlk Yükleme", json_content)
                
            return True, f"Başarılı! {len(new_data)} yazı GitHub'a kaydedildi."
            
        except Exception as e:
            return False, f"GitHub Hatası: {str(e)}"
