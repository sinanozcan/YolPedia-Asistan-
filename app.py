"""
YolPedia Can Dede - BASİT ve ÇALIŞAN VERSİYON
Tek Mod: Sohbet + Kaynak Gösterme
"""

import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import time
import random
import logging
import hashlib
import html
import sqlite3
import os

# ===================== CUSTOM PAGE CONFIG =====================

st.set_page_config(
    page_title="Can Dede | YolPedia Rehberiniz",
    page_icon="https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png",
    layout="centered",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://yolpedia.eu/yardim',
        'Report a bug': 'https://yolpedia.eu/iletisim',
        'About': '''
        ## YolPedia Can Dede
        **Alevî-Bektaşî Sohbet ve Araştırma Asistanı**
        📚 yolpedia.eu
        "Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"
        '''
    }
)

from datetime import datetime
from typing import List, Dict, Tuple, Optional, Generator, Any, Set
from collections import deque, defaultdict
import threading
import secrets

# ===================== CONFIGURATION =====================

class AppConfig:
    # API Settings
    GEMINI_MODEL = "gemini-1.5-flash"  # En ekonomik ve hızlı
    
    # Search
    MIN_SEARCH_LENGTH = 2
    MAX_SEARCH_RESULTS = 5
    MAX_CONTENT_LENGTH = 1000
    
    # Database
    DB_PATH = "/tmp/yolpedia.db" if "STREAMLIT_CLOUD" in os.environ else "yolpedia.db"
    DATA_FILE = "yolpedia_data.json"
    
    # Branding
    ASSISTANT_NAME = "Can Dede | YolPedia Rehberiniz"
    MOTTO = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
    YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
    CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png"
    USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"

config = AppConfig()

# ===================== KNOWLEDGE BASE =====================

class KnowledgeBase:
    """Basit ve çalışan knowledge base"""
    
    def __init__(self):
        self.conn = None
        self.data = []
        self.setup_database()
        self.load_from_json()
    
    def get_connection(self):
        if self.conn is None:
            self.conn = sqlite3.connect(config.DB_PATH)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def setup_database(self):
        """Basit veritabanı kurulumu"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    baslik TEXT NOT NULL,
                    link TEXT NOT NULL,
                    icerik TEXT,
                    normalized TEXT
                )
            ''')
            
            conn.commit()
        except Exception as e:
            print(f"Veritabanı kurulum hatası: {e}")
    
    def load_from_json(self):
        """JSON'dan verileri yükle"""
        try:
            if os.path.exists(config.DATA_FILE):
                with open(config.DATA_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                print(f"✅ {len(self.data)} kayıt yüklendi")
                
                # Veritabanına da yükle
                conn = self.get_connection()
                cursor = conn.cursor()
                
                for item in self.data:
                    try:
                        cursor.execute('''
                            INSERT OR REPLACE INTO content (baslik, link, icerik, normalized)
                            VALUES (?, ?, ?, ?)
                        ''', (
                            item['baslik'],
                            item['link'],
                            item['icerik'][:config.MAX_CONTENT_LENGTH],
                            self.normalize_text(item['baslik'] + ' ' + item['icerik'])
                        ))
                    except Exception as e:
                        print(f"Kayıt ekleme hatası: {e}")
                
                conn.commit()
            else:
                print(f"⚠️ JSON dosyası bulunamadı: {config.DATA_FILE}")
        except Exception as e:
            print(f"JSON yükleme hatası: {e}")
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Basit normalizasyon"""
        if not text:
            return ""
        text = text.lower()
        # Türkçe karakterleri düzelt
        replacements = {
            'ğ': 'g', 'Ğ': 'g',
            'ü': 'u', 'Ü': 'u',
            'ş': 's', 'Ş': 's',
            'ı': 'i', 'İ': 'i',
            'ö': 'o', 'Ö': 'o',
            'ç': 'c', 'Ç': 'c',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
    
    def search(self, query: str, limit: int = config.MAX_SEARCH_RESULTS) -> List[Dict]:
        """BASİT ve GARANTİLİ ARAMA"""
        if len(query.strip()) < 2:
            return []
        
        query_lower = query.lower().strip()
        results = []
        
        # Önce memory'de ara (daha hızlı)
        for item in self.data:
            content_lower = item.get('icerik', '').lower()
            baslik_lower = item.get('baslik', '').lower()
            
            if query_lower in content_lower or query_lower in baslik_lower:
                # Snippet oluştur
                icerik = item.get('icerik', '')
                idx = icerik.lower().find(query_lower)
                snippet = ""
                
                if idx != -1:
                    start = max(0, idx - 100)
                    end = min(len(icerik), idx + len(query_lower) + 150)
                    snippet = icerik[start:end]
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(icerik):
                        snippet = snippet + "..."
                else:
                    snippet = icerik[:300] + "..." if len(icerik) > 300 else icerik
                
                results.append({
                    'baslik': item['baslik'],
                    'link': item['link'],
                    'icerik': icerik[:config.MAX_CONTENT_LENGTH],
                    'snippet': snippet,
                    'score': 100 if query_lower in baslik_lower else 50
                })
                
                if len(results) >= limit * 2:  # 2 katı kadar topla
                    break
        
        # Skora göre sırala ve limit uygula
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]
    
    def get_stats(self) -> Dict:
        """Basit istatistikler"""
        return {
            "total_entries": len(self.data),
            "unique_titles": len(set(item.get('baslik', '') for item in self.data)),
            "last_update": "Memory-based"
        }

# ===================== API YÖNETİMİ =====================

class APIManager:
    """Basit API yöneticisi"""
    
    def __init__(self):
        self.api_key = self.load_api_key()
    
    def load_api_key(self) -> Optional[str]:
        """API key'i yükle"""
        # 1. Önce secrets'tan
        try:
            if "API_KEY" in st.secrets:
                key = st.secrets["API_KEY"]
                if key and len(key) > 10:
                    print("✅ API Key secrets'tan yüklendi")
                    return key
        except:
            pass
        
        # 2. Environment variable'dan
        if "GOOGLE_API_KEY" in os.environ:
            key = os.environ["GOOGLE_API_KEY"]
            if key and len(key) > 10:
                print("✅ API Key env'den yüklendi")
                return key
        
        # 3. Manuel kontrol
        print("⚠️ API Key bulunamadı!")
        return None
    
    def get_api_key(self) -> Optional[str]:
        return self.api_key

# ===================== PROMPT ENGINE =====================

class PromptEngine:
    """Tek prompt - her şey için"""
    
    @staticmethod
    def build_prompt(query: str, sources: List[Dict]) -> str:
        """TEK VE BASİT PROMPT"""
        
        prompt = f"""Sen Can Dede'sin. Alevi-Bektaşi geleneğinden bir mürşitsin.
Samimi, doğal ve gönülden konuş. Başlık kullanma, maddeleme yapma.

Kullanıcı soruyor: "{query}"
"""
        
        # Kaynak varsa ekle
        if sources:
            prompt += "\n\nŞu kaynaklardan da yararlanabilirsin:\n"
            for i, source in enumerate(sources[:2], 1):
                prompt += f"\n{i}. {source['baslik']}\n"
                if source.get('snippet'):
                    prompt += f"   Özet: {source['snippet']}\n"
                prompt += f"   Link: {source['link']}\n"
            
            prompt += "\nKaynaklardaki bilgileri kullan ama kendi üslubunla anlat."
        
        prompt += "\n\nCevabını doğal bir sohbet diliyle ver:"
        
        return prompt

# ===================== RESPONSE GENERATOR =====================

class ResponseGenerator:
    """Basit response generator"""
    
    def __init__(self, api_manager: APIManager):
        self.api_manager = api_manager
        self.prompt_engine = PromptEngine()
    
    def generate(self, query: str, sources: List[Dict]) -> Generator[str, None, None]:
        """Response oluştur"""
        
        # 1. Basit selam kontrolü
        greeting = self.check_greeting(query)
        if greeting:
            yield greeting
            return
        
        # 2. API key kontrolü
        api_key = self.api_manager.get_api_key()
        if not api_key:
            yield self.get_no_api_response(query, sources)
            return
        
        # 3. Prompt oluştur
        prompt = self.prompt_engine.build_prompt(query, sources)
        
        # 4. Gemini'yi çağır
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(config.GEMINI_MODEL)
            
            response = model.generate_content(
                prompt,
                stream=True,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 2048,
                },
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
            
            full_response = ""
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield chunk.text
            
        except Exception as e:
            error_msg = str(e)
            print(f"API Hatası: {error_msg}")
            yield self.get_error_response(query, sources, error_msg)
    
    @staticmethod
    def check_greeting(query: str) -> Optional[str]:
        """Selam kontrolü"""
        query_lower = query.lower()
        
        greetings = ["merhaba", "selam", "slm", "selamun aleykum", "hi", "hello"]
        if any(g in query_lower for g in greetings):
            return random.choice([
                "Aşk ile can dost! Hoş geldin. 🕊️",
                "Selam olsun güzel insan! Buyur, ne üzerine konuşalım?",
                "Selam canım! Yolun açık olsun. Ne sormak istersin?"
            ])
        
        if "nasılsın" in query_lower or "naber" in query_lower:
            return random.choice([
                "Şükür canım, Hakk'ın bir tecellisiyim bugün. Sen nasılsın?",
                "Çok şükür dostum. Gönül sohbetine hazırım. Senin gönlün nasıl?"
            ])
        
        return None
    
    @staticmethod
    def get_no_api_response(query: str, sources: List[Dict]) -> str:
        """API olmadan cevap"""
        if sources:
            response = "🔍 **Yolpedia'da Bulunan Kaynaklar:**\n\n"
            for i, source in enumerate(sources[:3], 1):
                response += f"{i}. **[{source['baslik']}]({source['link']})**\n"
                if source.get('snippet'):
                    response += f"   _{source['snippet']}_\n\n"
            response += "\n_API bağlantısı şu an yok, ama kaynaklar burada!_"
            return response
        
        return "Can dost, şu an teknik bir aksaklık var. Biraz sonra tekrar dene! 🙏"
    
    @staticmethod
    def get_error_response(query: str, sources: List[Dict], error: str) -> str:
        """Hata durumunda cevap"""
        if "quota" in error.lower() or "429" in error:
            return "🔄 API limitine ulaştık. Lütfen biraz sonra tekrar dene!"
        
        if sources:
            return f"⚠️ Teknik sorun: {error[:100]}\n\n**Bulunan kaynaklar:**\n" + \
                   "\n".join([f"- [{s['baslik']}]({s['link']})" for s in sources[:2]])
        
        return f"⚠️ Teknik bir sorun oluştu: {error[:100]}"

# ===================== SESSION STATE =====================

def init_session():
    """Basit session initializer"""
    if 'kb' not in st.session_state:
        st.session_state.kb = KnowledgeBase()
    
    if 'api_manager' not in st.session_state:
        st.session_state.api_manager = APIManager()
    
    if 'response_generator' not in st.session_state:
        st.session_state.response_generator = ResponseGenerator(st.session_state.api_manager)
    
    if 'messages' not in st.session_state:
        st.session_state.messages = deque(maxlen=50)
        st.session_state.messages.append({
            "role": "assistant",
            "content": (
                "Merhaba can dost! Ben Can Dede. 🤗\n\n"
                "Yolpedia'daki sohbet ve araştırma rehberinizim.\n\n"
                "Bana istediğini sorabilirsin:\n"
                "• Yol üzerine sohbet ederiz\n"
                "• Yolpedia'dan kaynak araştırması yaparım\n"
                "• Gönül muhabbeti yaparız\n\n"
                "Buyur, ne üzerine konuşalım?"
            ),
            "timestamp": time.time()
        })

# ===================== UI =====================

def render_header():
    """Basit header"""
    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 30px;">
        <div style="display: flex; align-items: center; justify-content: center; gap: 15px; margin-bottom: 10px;">
            <img src="{config.CAN_DEDE_ICON}" 
                 style="width: 50px; height: 50px; border-radius: 50%; border: 2px solid #eee;">
            <h1 style="margin: 0; font-size: 34px; font-weight: 700; color: white;">
                {config.ASSISTANT_NAME}
            </h1>
        </div>
        <div style="font-size: 16px; font-style: italic; color: #cccccc; font-family: 'Georgia', serif;">
            {config.MOTTO}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_message(message: Dict):
    """Mesajı göster"""
    avatar = config.CAN_DEDE_ICON if message["role"] == "assistant" else config.USER_ICON
    
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])
        
        # Timestamp
        timestamp = datetime.fromtimestamp(message.get("timestamp", time.time())).strftime("%H:%M")
        st.markdown(f"""
        <div style="text-align: right; font-size: 0.8rem; color: #888; margin-top: 0.3rem;">
            {timestamp}
        </div>
        """, unsafe_allow_html=True)

def render_sources(sources: List[Dict]):
    """Kaynakları göster"""
    if not sources:
        return
    
    st.markdown("---")
    st.markdown("### 📚 İlgili Kaynaklar")
    
    for i, source in enumerate(sources[:3], 1):
        with st.container():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{i}. {source['baslik']}**")
                if source.get('snippet'):
                    st.markdown(f"*{source['snippet']}*")
            with col2:
                st.link_button("🔗 Git", source['link'])

# ===================== MAIN =====================

def main():
    """ANA UYGULAMA - TEK MOD"""
    
    # Session'ı başlat
    if 'initialized' not in st.session_state:
        init_session()
        st.session_state.initialized = True
    
    # CSS
    st.markdown("""
    <style>
        .stApp, .main { background-color: #020212 !important; color: white !important; }
        .block-container { background-color: #222222 !important; }
        .stChatMessage { background-color: #222222 !important; border: 1px solid #3d3d5c !important; }
        section[data-testid="stSidebar"] { background-color: #222222 !important; }
        .stButton button { background-color: #cc0000 !important; color: white !important; }
        .stChatInputContainer input { background-color: #2d2d44 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)
    
    # SIDEBAR
    with st.sidebar:
        st.image(config.YOLPEDIA_ICON, width=40)
        st.markdown("---")
        
        # İstatistikler
        with st.expander("📊 İstatistikler"):
            if 'kb' in st.session_state:
                stats = st.session_state.kb.get_stats()
                st.metric("Toplam Kayıt", stats["total_entries"])
        
        # Temizle butonu
        if st.button("🧹 Sohbeti Temizle"):
            st.session_state.messages = deque(maxlen=50)
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Sohbet temizlendi! Yeni bir konuşma başlatalım mı can dost?",
                "timestamp": time.time()
            })
            st.rerun()
    
    # HEADER
    render_header()
    
    # MESAJLAR
    for message in st.session_state.messages:
        render_message(message)
    
    # KULLANICI GİRİŞİ
    if user_input := st.chat_input("Can Dede'ye sor..."):
        # Kullanıcı mesajını ekle
        user_message = {
            "role": "user",
            "content": user_input,
            "timestamp": time.time()
        }
        st.session_state.messages.append(user_message)
        render_message(user_message)
        
        # Kaynak ara
        sources = []
        if len(user_input.strip()) >= 2:
            sources = st.session_state.kb.search(user_input)
        
        # Cevap oluştur
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            placeholder = st.empty()
            full_response = ""
            
            with st.spinner("Can Dede düşünüyor..."):
                for chunk in st.session_state.response_generator.generate(user_input, sources):
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
            
            placeholder.markdown(full_response)
            
            # Kaynakları göster
            if sources:
                render_sources(sources)
            
            # Asistan mesajını kaydet
            assistant_message = {
                "role": "assistant",
                "content": full_response,
                "timestamp": time.time()
            }
            st.session_state.messages.append(assistant_message)

if __name__ == "__main__":
    main()
