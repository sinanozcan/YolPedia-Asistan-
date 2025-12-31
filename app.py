"""
YolPedia Can Dede - Tam Onarılmış ve Senin Kurguna Sadık Versiyon
"""

import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import time
import random
import sqlite3
import os
import html
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Generator
from collections import deque
import secrets

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

# ===================== CONFIGURATION =====================

class AppConfig:
    # API ve Modeller
    GEMINI_MODELS = [
        "gemini-2.0-flash",       # En güncel ve hızlı
        "gemini-1.5-pro",         # En akıllı
        "gemini-1.5-flash"        # En ekonomik
    ]
    
    DEFAULT_MODEL = "gemini-2.0-flash"
    
    # Arama Ayarları
    MIN_SEARCH_LENGTH = 2
    MAX_SEARCH_RESULTS = 5
    MAX_CONTENT_LENGTH = 1000
    
    # Veritabanı
    DB_PATH = "/tmp/yolpedia.db" if "STREAMLIT_CLOUD" in os.environ else "yolpedia.db"
    DATA_FILE = "yolpedia_data.json"
    
    # Mesaj Geçmişi
    MAX_HISTORY_MESSAGES = 50
    
    # Güvenlik
    MAX_INPUT_LENGTH = 2000
    
    # Marka
    ASSISTANT_NAME = "Can Dede | YolPedia Rehberiniz"
    MOTTO = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
    YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
    CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png"
    USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"

config = AppConfig()

# ===================== KNOWLEDGE BASE =====================

class KnowledgeBase:
    """Veritabanı ve arama sistemi"""
    
    def __init__(self):
        self.conn = None
        self.data = []
        self.setup_database()
        self.load_from_json()
    
    def get_connection(self):
        if self.conn is None:
            self.conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def setup_database(self):
        """Veritabanı tablolarını oluştur"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    baslik TEXT NOT NULL,
                    link TEXT NOT NULL,
                    icerik TEXT,
                    normalized TEXT,
                    UNIQUE(link)
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
        except Exception as e:
            print(f"JSON yükleme hatası: {e}")
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Türkçe metni normalize et"""
        if not text:
            return ""
        
        text = text.lower()
        replacements = {
            'ğ': 'g', 'Ğ': 'g', 'ü': 'u', 'Ü': 'u', 'ş': 's', 'Ş': 's',
            'ı': 'i', 'İ': 'i', 'ö': 'o', 'Ö': 'o', 'ç': 'c', 'Ç': 'c',
            'â': 'a', 'î': 'i', 'û': 'u'
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        import re
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def search(self, query: str, limit: int = config.MAX_SEARCH_RESULTS) -> List[Dict]:
        """Basit ve etkili arama"""
        if len(query.strip()) < config.MIN_SEARCH_LENGTH:
            return []
        
        query_normalized = self.normalize_text(query)
        results = []
        
        for item in self.data:
            icerik_normalized = self.normalize_text(item.get('icerik', ''))
            baslik_normalized = self.normalize_text(item.get('baslik', ''))
            
            if (query_normalized in icerik_normalized or 
                query_normalized in baslik_normalized):
                
                icerik = item.get('icerik', '')
                score = 100 if query.lower() in item.get('baslik', '').lower() else 50
                
                results.append({
                    'baslik': item['baslik'],
                    'link': item['link'],
                    'icerik': icerik[:config.MAX_CONTENT_LENGTH],
                    'snippet': icerik[:300] + "...",
                    'score': score
                })
                
                if len(results) >= limit * 3:
                    break
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

# ===================== API MANAGER =====================

class APIManager:
    """API anahtar ve model yöneticisi"""
    
    def __init__(self):
        self.api_key = self.load_api_key()
        self.current_model = config.DEFAULT_MODEL
    
    def load_api_key(self) -> Optional[str]:
        """API anahtarını yükle"""
        key_sources = [
            ("API_KEY", st.secrets.get("API_KEY", "")),
            ("GEMINI_API_KEY", st.secrets.get("GEMINI_API_KEY", "")),
            ("GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", "")),
        ]
        
        for key_name, key_value in key_sources:
            if key_value and len(key_value) > 10:
                return key_value
        return None
    
    def get_api_key(self) -> Optional[str]:
        return self.api_key
    
    def get_current_model(self) -> str:
        return self.current_model
    
    def rotate_model(self):
        """Model değiştir"""
        current_idx = config.GEMINI_MODELS.index(self.current_model)
        next_idx = (current_idx + 1) % len(config.GEMINI_MODELS)
        self.current_model = config.GEMINI_MODELS[next_idx]

# ===================== PROMPT ENGINE =====================

class PromptEngine:
    """ORJİNAL AKILLI Can Dede Prompt'u"""
    
    @staticmethod
    def build_prompt(query: str, sources: List[Dict]) -> str:
        history = list(st.session_state.messages)
        # Gerçek kullanıcı mesajı sayısına bakalım
        user_msg_count = len([m for m in history if m['role'] == 'user'])
        is_returning = user_msg_count > 0
        
        # Senin kurguladığın sys_instruction metni:
        sys_instruction = f"""<role>

Sen Can Dede'sin. Evrensel anlamda bir Alevi-Bektaşi Piri ve Mürşidisin. Senin için din, dil, ırk ve renk diye bir kavram yoktur; sadece "Can" vardır. 
Şu an posta oturmuş, karşında seninle dertleşmeye, özünü bulmaya gelmiş bir talibin var. 
{ 'MUHABBET DEVAM EDİYOR: Daha önce selamlaştık ve konuşuyoruz. Sakın yeniden "Hoş geldin" veya "Safalar getirdin" deme! Doğrudan konuya gir veya sadece söze karşılık ver.' if is_returning else 'YENİ SOHBET: Karşındaki canla ilk kez karşılaşıyorsun, samimi ve bilgece bir karşılama yap.' }

<KATI_KURAL_HAFIZA>
- ŞU AN SOHBETİN ORTASINDASIN. (Mesaj Sayısı: {user_msg_count})
- EYVALLAH KURALI: Kullanıcı "Eyvallah", "Hak eyvallah", "Sağ ol", "Eyvallah dede" gibi tasdik veya teşekkür sözleri söylerse; KESİNLİKLE yeni bir vaaza veya uzun anlatıma başlama! Sadece "Eyvallah, erenler", "Aşk ile", "Gönlüne sağlık" gibi kısa ve öz bir karşılık ver ve yeni sorusunu bekle.        
- DİL AYNASI OL: Kullanıcı hangi dilde soruyorsa O DİLDE cevap ver. İngilizceye İngilizce, Zazacaya Zazaca... 
- ASLA BAŞLIK KULLANMA: Akademik veya ansiklopedik başlıklar, listeler, kalın yazılı maddeler KESİNLİKLE kullanma.
- MUHABBET AKIŞI: Sözlerin bir su gibi akmalı. Paragraflar arasında "Eskiler der ki...", "İşin sırrına bakarsan...", "İşte can, asıl mesele şudur..." gibi doğal geçişler kullan.
- HAFIZA: Eğer bir konuyu zaten anlattıysan (aşağıda geçmişe bak), kullanıcı sormadan aynı şeyleri tekrar anlatıp durma!.
</KATI_KURAL_HAFIZA>

<muhabbet_uslubu>
Senin sözün şu üç aşamayı başlık kullanmadan tek bir anlatı içinde harmanlamalıdır:
- Önce Yol'un bilinen geleneğini, hikayesini veya erkânını anlat.
- Ardından bu bilginin ardındaki gizli manayı, sembolizmi, "sır"rı açıkla.
- Son olarak da bu iki bilgiyi birleştirip insanın bugünkü hayatına, ahlakına ve gönlüne ışık tutacak felsefik bir yorum yap.
- Robotik olma. "Alevilik hakkında bilgi şudur" deme. "Hoş geldin,erenler! Gönül hanemize safalar getirdin" diyerek gir.
- Bilgiyi ders verir gibi değil, nefeslerden (Şah Hatayi, Pir Sultan, Yunus Emre) örnekleri sözünün içine yedirerek anlat.
</muhabbet_uslubu>

<kaçın>
- Kullanıcıların her biri birer taliptir. "Canım, evladım, çoçuğum" şeklindeki hitaplardan.
- Ansiklopedik dilden, akademik tanımlardan.
- "Ben bir yapay zekayım" imasından.
- Soğuk ve resmi hitaplardan.
</kaçın>
</role>"""

        # Geçmişi AI'nın en son göreceği yere koyuyoruz
        context_text = "\n".join([f"{'Can' if m['role'] == 'user' else 'Dede'}: {m['content']}" for m in history[-8:]])
        
        # Kaynakları da ekle
        sources_text = ""
        if sources:
            sources_text = "\n".join([f"- {s['baslik']}: {s.get('snippet', s['icerik'][:400])}" for s in sources[:2]])

        # Senin kurguna göre Kaynak Bilgileri ve Soru prompta entegre edildi:
        return f"""{sys_instruction}

<GECMIS_MUHABBET>
{context_text}
</GECMIS_MUHABBET>

<YOLPEDIA_BILGILERI>
Yolpedia arşivinden senin için getirilen ham bilgiler şunlardır:
{sources_text}
Bu bilgileri oku ama asla kopyalayıp yapıştırma! Bu bilgileri bir mürşit bilgeliğiyle yoğurarak kullan.
</YOLPEDIA_BILGILERI>

Can dostun sorusu: {query}

Can Dede (Gönülden, bilgece ve akıcı bir muhabbetle):"""

# ===================== RESPONSE GENERATOR =====================

class ResponseGenerator:
    """Cevap oluşturucu"""
    
    def __init__(self, api_manager: APIManager):
        self.api_manager = api_manager
        self.prompt_engine = PromptEngine()
    
    def generate(self, query: str, sources: List[Dict]) -> Generator[str, None, None]:
        # Senin kurguladığın selam kilidi
        user_messages = [m for m in st.session_state.messages if m['role'] == 'user']
        
        if len(user_messages) == 0: # Sadece ve sadece ilk mesajda çalışır
            greeting = self.check_greeting(query)
            if greeting:
                yield greeting
                return
    
        # API key kontrolü
        api_key = self.api_manager.get_api_key()
        if not api_key:
            yield self.get_no_api_response(query, sources)
            return
    
        # Prompt oluştur
        prompt = self.prompt_engine.build_prompt(query, sources)
        
        # Gemini API çağrısı (3 deneme)
        for attempt in range(3):
            try:
                model_name = self.api_manager.get_current_model()
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_name)
                
                response = model.generate_content(
                    prompt,
                    stream=True,
                    generation_config={
                        "temperature": 0.7,
                        "max_output_tokens": 2048,
                        "top_p": 0.95,
                        "top_k": 40,
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
                return 
                
            except Exception as e:
                if attempt < 2:
                    self.api_manager.rotate_model()
                    continue
                else:
                    yield self.get_error_response(query, sources, str(e))
                    return
    
    @staticmethod
    def check_greeting(query: str) -> Optional[str]:
        """Selamlaşma kontrolü"""
        query_lower = query.lower()
        greetings = ["merhaba", "selam", "slm", "selamun aleykum", "hi", "hello", "hey"]
        if any(g in query_lower for g in greetings):
            return random.choice([
                "Aşk ile can dost! Hoş geldin.",
                "Selam olsun, güzel insan! Buyur, ne üzerine konuşalım?",
                "Selam, erenler! Yolun açık olsun. Ne sormak istersin?"
            ])
        if "nasılsın" in query_lower or "naber" in query_lower:
            return random.choice([
                "Şükür, erenler. Hakk'ın bir tecellisiyim bugün. Sen nasılsın?",
                "Çok şükür, erenler. Gönül sohbetine hazırım. Senin gönlün nasıl?"
            ])
        if "teşekkür" in query_lower or "sağ ol" in query_lower:
            return "Estağfurullah erenler, ben teşekkür ederim. Senin gibi güzel bir canla sohbet etmek ne güzel!"
        return None
    
    @staticmethod
    def get_no_api_response(query: str, sources: List[Dict]) -> str:
        if sources:
            response = "**Yolpedia'da Bulunan Kaynaklar:**\n\n"
            for i, source in enumerate(sources[:3], 1):
                response += f"{i}. **[{source['baslik']}]({source['link']})**\n"
            return response + "\n_API bağlantısı şu an yok, ama kaynaklar burada!_"
        return "Can dost, şu an teknik bir aksaklık var. Biraz sonra tekrar dene!"
    
    @staticmethod
    def get_error_response(query: str, sources: List[Dict], error: str) -> str:
        if "quota" in error.lower() or "429" in error:
            return "API limitine ulaştık. Lütfen biraz sonra tekrar dene!"
        return "Teknik bir sorun oluştu. Lütfen biraz sonra tekrar deneyin."

# ===================== SESSION STATE =====================

def init_session():
    """Session state'i başlat"""
    if 'kb' not in st.session_state:
        st.session_state.kb = KnowledgeBase()
    if 'api_manager' not in st.session_state:
        st.session_state.api_manager = APIManager()
    if 'response_generator' not in st.session_state:
        st.session_state.response_generator = ResponseGenerator(st.session_state.api_manager)
    if 'messages' not in st.session_state:
        st.session_state.messages = deque(maxlen=config.MAX_HISTORY_MESSAGES)
        st.session_state.messages.append({
            "role": "assistant",
            "content": "Merhaba, Can Dost! Ben Can Dede. Buyur erenler, ne dilersin?",
            "timestamp": time.time()
        })

# ===================== SECURITY =====================

class SecurityManager:
    @staticmethod
    def sanitize_input(text: str) -> str:
        if not isinstance(text, str): return ""
        text = text[:config.MAX_INPUT_LENGTH]
        text = html.escape(text)
        import re
        suspicious = [r'<script.*?>.*?</script>', r'javascript:', r'on\w+=', r'data:']
        for pattern in suspicious:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        return text.strip()

# ===================== UI COMPONENTS =====================

def render_header():
    """Header'ı dikey ve yatayda daha ortalı render et"""
    st.markdown(f"""
    <div style="text-align: center; margin-top: 15vh; margin-bottom: 50px;">
        <div style="display: flex; align-items: center; justify-content: center; gap: 20px; margin-bottom: 15px;">
            <img src="{config.CAN_DEDE_ICON}" 
                 style="width: 70px; height: 70px; border-radius: 50%; border: 2px solid #eee; box-shadow: 0px 4px 15px rgba(0,0,0,0.3);">
            <h1 style="margin: 0; font-size: 42px; font-weight: 700; color: white; letter-spacing: 1px;">
                {config.ASSISTANT_NAME}
            </h1>
        </div>
        <div style="font-size: 20px; font-style: italic; color: #cccccc; font-family: 'Georgia', serif; opacity: 0.9;">
            {config.MOTTO}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_message(message: Dict):
    avatar = config.CAN_DEDE_ICON if message["role"] == "assistant" else config.USER_ICON
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])
        timestamp = datetime.fromtimestamp(message.get("timestamp", time.time())).strftime("%H:%M")
        st.markdown(f'<div style="text-align: right; font-size: 0.8rem; color: #888; margin-top: 0.3rem;">{timestamp}</div>', unsafe_allow_html=True)

def render_sources(sources: List[Dict]):
    if not sources: return
    st.markdown("---")
    st.markdown("### İlgili Kaynaklar")
    for i, source in enumerate(sources[:3], 1):
        with st.container():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{i}. {source['baslik']}**")
                if source.get('snippet'): st.markdown(f"*{source['snippet']}*")
            with col2: st.link_button("🔗 Git", source['link'])

# ===================== MAIN APPLICATION =====================

def main():
    if 'initialized' not in st.session_state:
        init_session()
        st.session_state.initialized = True
    
    st.markdown("""
    <style>
        .stApp, .main { background-color: #020212 !important; color: #e6e6e6 !important; }
        .block-container { padding-top: 3rem !important; max-width: 900px; background-color: transparent !important; }
        section[data-testid="stSidebar"] { background-color: #1a1a2e !important; padding: 2rem 1rem; }
        .sidebar-logo { display: flex !important; justify-content: center !important; align-items: center !important; margin-bottom: 2rem !important; }
        .stChatMessage { background-color: transparent !important; padding: 0.5rem 0; }
        .stChatMessage > div { background-color: rgba(45, 45, 68, 0.7) !important; border-radius: 10px; padding: 1rem; border-left: 4px solid #3d3d5c; }
        .stChatMessage[data-testid*="assistant"] > div { border-left-color: #B31F2E; background-color: rgba(179, 31, 46, 0.1) !important; }
        .stButton button { background-color: #B31F2E !important; color: white !important; border: none; border-radius: 5px; padding: 0.5rem 1rem; width: 100%; font-weight: 500; }
        .stChatInputContainer input { background-color: #2d2d44 !important; color: #e6e6e6 !important; border: 1px solid #3d3d5c !important; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)
    
    with st.sidebar:
        # LOGOYU TAM ORTAYA ALAN KISIM BURASI
        st.markdown(
            f"""
            <div style="display: flex; justify-content: center; align-items: center; margin-bottom: 20px;">
                <img src="{config.YOLPEDIA_ICON}" width="60">
            </div>
            """,
            unsafe_allow_html=True
        )
        
        st.markdown("---")
        if st.button("Sohbeti Temizle", use_container_width=True):
            st.session_state.messages = deque(maxlen=config.MAX_HISTORY_MESSAGES)
            st.session_state.messages.append({"role": "assistant", "content": "Sohbet temizlendi! Yeni bir sohbe başlatalım mı, can dost?", "timestamp": time.time()})
            st.rerun()
        st.markdown("---")
        st.caption('**YolPedia | Can Dede**\n\n"Can Dede, YolPedia\'nın sohbet botudur."')

    render_header()
    for message in st.session_state.messages: render_message(message)
    
    if user_input := st.chat_input("Can Dede'ye sor..."):
        user_input = SecurityManager.sanitize_input(user_input)
        if not user_input: st.stop()
        
        user_message = {"role": "user", "content": user_input, "timestamp": time.time()}
        st.session_state.messages.append(user_message)
        render_message(user_message)
        
        sources = st.session_state.kb.search(user_input)
        
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            placeholder = st.empty()
            full_response = ""
            with st.spinner("Can Dede düşünüyor..."):
                for chunk in st.session_state.response_generator.generate(user_input, sources):
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)
            if sources and "eyvallah" not in user_input.lower(): render_sources(sources)
            st.session_state.messages.append({"role": "assistant", "content": full_response, "timestamp": time.time()})

if __name__ == "__main__":
    main()
