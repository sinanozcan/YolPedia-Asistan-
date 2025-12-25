"""
YolPedia.eu Canlı Veri Çekici ve GitHub Güncelleyici
"""

import requests
import json
import time
import urllib3
from github import Github # GitHub kütüphanesi
import os

# SSL Uyarılarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class YolPediaAPI:
    def __init__(self):
        self.base_url = "https://yolpedia.eu/wp-json/wp/v2"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        })
    
    def get_all_posts_formatted(self, max_posts=3000):
        """Tüm yazıları çeker ve formatlar"""
        all_posts = []
        page = 1
        per_page = 100
        
        print("📡 Veriler çekiliyor...")
        
        while len(all_posts) < max_posts:
            try:
                endpoint = f"{self.base_url}/posts"
                params = {'per_page': min(100, max_posts - len(all_posts)), 'page': page, '_embed': 1}
                response = self.session.get(endpoint, params=params, timeout=20, verify=False)
                
                if response.status_code != 200: break
                
                posts = response.json()
                if not posts: break
                
                for post in posts:
                    # HTML Temizliği
                    import re
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
                
            except Exception as e:
                print(f"Hata: {e}")
                break
                
        return all_posts

    def update_github_repo(self, new_data, github_token, repo_name="sinanozcan/YolPedia-Asistan-"):
        """Veriyi GitHub'a kalıcı olarak yazar"""
        try:
            g = Github(github_token)
            repo = g.get_repo(repo_name)
            file_path = "yolpedia_data.json"
            
            # Eski dosyanın SHA imzasını al (Güncelleme için gerekli)
            contents = repo.get_contents(file_path)
            
            # Yeni veriyi JSON formatına çevir
            json_content = json.dumps(new_data, ensure_ascii=False, indent=2)
            
            # GitHub'a Commit et (Kaydet)
            repo.update_file(
                path=file_path,
                message="🤖 Can Dede: Otomatik Veritabanı Güncellemesi",
                content=json_content,
                sha=contents.sha
            )
            return True, f"Başarılı! {len(new_data)} yazı GitHub'a kaydedildi."
            
        except Exception as e:
            return False, f"GitHub Hatası: {str(e)}"
