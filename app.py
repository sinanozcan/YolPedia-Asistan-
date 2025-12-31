"""
YolPedia Can Dede - Teknik Hataları Arındırılmış Tam Sürüm
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
    GEMINI_MODELS = [
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash"
    ]
    DEFAULT_MODEL = "gemini-2.0-flash"
    MIN_SEARCH_LENGTH = 2
    MAX_SEARCH_RESULTS = 5
    MAX_CONTENT_LENGTH = 1200
    DB_PATH = "/tmp/yolpedia.db" if "STREAMLIT_CLOUD" in os.environ else "yolpedia.db"
    DATA_FILE = "yolpedia_data.json"
    MAX_HISTORY_MESSAGES = 50
    MAX_INPUT_LENGTH = 2000
    ASSISTANT_NAME = "Can Dede | YolPedia Rehberiniz"
    MOTTO = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
    YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
    CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png"
    USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"

config = AppConfig()

# ===================== KNOWLEDGE BASE =====================

class KnowledgeBase:
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
            st.error(f"Veritabanı hatası: {e}")
    
    def load_from_json(self):
        if not os.path.exists(config.DATA_FILE):
            return
        try:
            with open(config.DATA_FILE, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            conn = self.get_connection()
            cursor = conn.cursor()
            for item in self.data:
                cursor.execute('''
                    INSERT OR REPLACE INTO content (baslik, link, icerik, normalized)
                    VALUES (?, ?, ?, ?)
                ''', (item['baslik'], item['link'], item['icerik'][:2000], self.normalize_text(item['baslik'] + ' ' + item['icerik'])))
            conn.commit()
        except Exception as e:
            print(f"Yükleme hatası: {e}")

    @staticmethod
    def normalize_text(text: str) -> str:
        if not text: return ""
        text = text.lower()
        repl = {'ğ':'g','ü':'u','ş':'s','ı':'i','ö':'o','ç':'c','â':'a','î':'i','û':'u'}
        for old, new in repl.items(): text = text.replace(old, new)
        import re
        return re.sub(r'[^\w\s]', ' ', text).strip()
    
    def search(self, query: str, limit: int = config.MAX_SEARCH_RESULTS) -> List[Dict]:
        if len(query.strip()) < config.MIN_SEARCH_LENGTH: return []
        query_norm = self.normalize_text(query)
        results = []
        for item in self.data:
            if query_norm in self.normalize_text(item.get('baslik', '')) or query_norm in self.normalize_text(item.get('icerik', '')):
                results.append({
                    'baslik': item['baslik'],
                    'link': item['link'],
                    'icerik': item['icerik'][:config.MAX_CONTENT_LENGTH],
                    'score': 100 if query.lower() in item['baslik'].lower() else 50
                })
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

# ===================== API MANAGER =====================

class APIManager:
    def __init__(self):
        self.api_key = self.load_api_key()
        self.current_model = config.DEFAULT_MODEL
    
    def load_api_key(self) -> Optional[str]:
        for k in ["API_KEY", "GEMINI_API_KEY"]:
            val = st.secrets.get(k, "")
            if val: return val
        return os.environ.get("GOOGLE_API_KEY")
    
    def get_api_key(self): return self.api_key
    def get_current_model(self): return self.current_model
    def rotate_model(self):
        idx = config.GEMINI_MODELS.index(self.current_model)
        self.current_model = config.GEMINI_MODELS[(idx + 1) % len(config.GEMINI_MODELS)]

# ===================== PROMPT ENGINE =====================

class PromptEngine:
    @staticmethod
    def build_prompt(query: str, sources: List[Dict]) -> str:
        history = list(st.session_state.messages)
        user_msg_count = len([m for m in history if m['role'] == 'user'])
        is_returning = user_msg_count > 0
        
        # Dinamik Karşılama Mantığı
        greeting_logic = (
            'MUHABBET DEVAM EDİYOR: Daha önce selamlaştık. Sakın yeniden "Hoş geldin" deme! Doğrudan söze gir.' 
            if is_returning else 
            'YENİ SOHBET: Karşındaki canla ilk kez karşılaşıyorsun, samimi bir karşılama yap.'
        )

        sys_instruction = f"""<role>
Sen Can Dede'sin. Evrensel anlamda bir Alevi-Bektaşi Piri ve Mürşidisin. Senin için din, dil, ırk ve renk yoktur; sadece "Can" vardır.
Şu an posta oturmuşsun, karşında dertleşmeye gelmiş bir talibin var.
{greeting_logic}

<KATI_KURALLAR>
1. EYVALLAH KURALI: Kullanıcı "Eyvallah", "Hak eyvallah", "Sağ ol" gibi tasdik sözleri söylerse; KESİNLİKLE yeni bir vaaza başlama! "Eyvallah, erenler", "Aşk ile" gibi kısa bir karşılık ver.
2. DİL AYNASI: Kullanıcı hangi dilde soruyorsa O DİLDE cevap ver.
3. BAŞLIK YASAK: "Zahir:", "Batın:" gibi başlıkları KESİNLİKLE kullanma.
4. MUHABBET AKIŞI: Sözlerin bir su gibi akmalı. "Eskiler der ki...", "İşin sırrına bakarsan..." gibi doğal geçişler kullan.
5. HAFIZA: Eğer bir konuyu az önce anlattıysan, tekrar edip durma.
</KATI_KURALLAR>

<anlatim_uslubu>
Sözün şu üç aşamayı başlık kullanmadan tek bir anlatı içinde harmanlamalıdır:
- Önce Yol'un bilinen geleneğini veya erkânını anlat.
- Ardından bu bilginin ardındaki gizli manayı, sembolizmi, "sır"rı açıkla.
- Son olarak da bu bilgiyi insanın bugünkü hayatına ve gönlüne ışık tutacak felsefik bir yorumla bitir.
- Bilgiyi ders verir gibi değil, nefeslerden (Şah Hatayi, Pir Sultan) örnekleri sözün içine yedirerek anlat.
</anlatim_uslubu>

<kacin>
- Taliplere "canım, evladım, çocuğum" deme. "Erenler", "Can dostum", "Güzel insan" hitaplarını kullan.
- Ansiklopedik dilden ve "Ben bir AI'yım" imasından kaçın.
</kacin>
</role>"""

        # Geçmiş ve Kaynaklar
        context_text = "\n".join([f"{'Can' if m['role'] == 'user' else 'Dede'}: {m['content'][:300]}" for m in history[-6:]])
        sources_text = "\n".join([f"- {s['baslik']}: {s['icerik'][:400]}" for s in sources[:2]]) if sources else "Kaynak yok."

        return f"{sys_instruction}\n\n<MUHABBET_GECMISI>\n{context_text}\n</MUHABBET_GECMISI>\n\n<YOLPEDIA_BILGISI>\n{sources_text}\n</YOLPEDIA_BILGISI>\n\nCan'ın sözü: {query}\n\nCan Dede:"

# ===================== RESPONSE GENERATOR =====================

class ResponseGenerator:
    def __init__(self, api_manager: APIManager):
        self.api_manager = api_manager
        self.prompt_engine = PromptEngine()
    
    def generate(self, query: str, sources: List[Dict]) -> Generator[str, None, None]:
        user_msg_count = len([m for m in st.session_state.messages if m['role'] == 'user'])
        
        # Sadece gerçek ilk mesajda selamlaşma kontrolü
        if user_msg_count == 0:
            greeting = self.check_greeting(query)
            if greeting:
                yield greeting
                return
    
        api_key = self.api_manager.get_api_key()
        if not api_key:
            yield "Can dost, teknik bir aksaklık var (API Key eksik). Az sonra tekrar dene. 🙏"
            return
    
        prompt = self.prompt_engine.build_prompt(query, sources)
        
        for attempt in range(3):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(self.api_manager.get_current_model())
                response = model.generate_content(
                    prompt,
                    stream=True,
                    generation_config={"temperature": 0.8, "max_output_tokens": 2048},
                    safety_settings={
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                )
                for chunk in response:
                    if chunk.text: yield chunk.text
                return
            except Exception as e:
                if attempt < 2:
                    self.api_manager.rotate_model()
                    continue
                yield f"Teknik bir huzursuzluk oldu can dost. Az sonra tekrar dener misin? (Hata: {str(e)[:50]})"
                return

    @staticmethod
    def check_greeting(query: str) -> Optional[str]:
        q = query.lower()
        if any(x in q for x in ["merhaba", "selam", "selamun aleykum", "hey"]):
            return "Aşk ile can dost! Gönül hanemize safalar getirdin. Buyur, ne üzerine dertleşelim? 🕊️"
        if any(x in q for x in ["nasılsın", "naber"]):
            return "Şükür Hakk'a erenler, bugün de yolun hizmetindeyiz. Senin gönlün nicedir?"
        return None

# ===================== MAIN APPLICATION =====================

def init_session():
    if 'kb' not in st.session_state: st.session_state.kb = KnowledgeBase()
    if 'api_manager' not in st.session_state: st.session_state.api_manager = APIManager()
    if 'response_generator' not in st.session_state: st.session_state.response_generator = ResponseGenerator(st.session_state.api_manager)
    if 'messages' not in st.session_state:
        st.session_state.messages = deque(maxlen=config.MAX_HISTORY_MESSAGES)
        st.session_state.messages.append({"role": "assistant", "content": "Merhaba, Can Dost! Ben Can Dede. Yolpedia rehberinizim. Buyur erenler, nedir arzun?", "timestamp": time.time()})

def main():
    init_session()
    
    # CSS
    st.markdown("""
    <style>
        .stApp { background-color: #020212 !important; color: #e6e6e6 !important; }
        .stChatMessage { background-color: rgba(45, 45, 68, 0.7) !important; border-radius: 10px; margin-bottom: 10px; border-left: 4px solid #3d3d5c; }
        .stChatMessage[data-testid*="assistant"] { border-left-color: #B31F2E; background-color: rgba(179, 31, 46, 0.1) !important; }
        .stButton button { background-color: #B31F2E !important; color: white !important; width: 100%; border: none; }
        .stChatInputContainer input { background-color: #2d2d44 !important; color: #e6e6e6 !important; }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown(f'<div style="text-align:center"><h1>{config.ASSISTANT_NAME}</h1><p><i>{config.MOTTO}</i></p></div>', unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.image(config.YOLPEDIA_ICON, width=60)
        st.divider()
        if st.button("🧹 Sohbeti Temizle"):
            st.session_state.messages = deque(maxlen=config.MAX_HISTORY_MESSAGES)
            st.session_state.messages.append({"role": "assistant", "content": "Sohbet temizlendi can dost, yeniden başlayalım.", "timestamp": time.time()})
            st.rerun()
        st.caption("YolPedia | Can Dede v2.0")

    # Chat
    for msg in st.session_state.messages:
        avatar = config.CAN_DEDE_ICON if msg["role"] == "assistant" else config.USER_ICON
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    if user_input := st.chat_input("Can Dede'ye sor..."):
        user_input = html.escape(user_input[:config.MAX_INPUT_LENGTH]).strip()
        if not user_input: st.stop()
        
        st.session_state.messages.append({"role": "user", "content": user_input, "timestamp": time.time()})
        with st.chat_message("user", avatar=config.USER_ICON): st.markdown(user_input)
        
        sources = st.session_state.kb.search(user_input)
        
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            placeholder = st.empty()
            full_response = ""
            for chunk in st.session_state.response_generator.generate(user_input, sources):
                full_response += chunk
                placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)
            
            if sources and "eyvallah" not in user_input.lower():
                st.markdown("---")
                st.caption("📚 **İlgili Kaynaklar:**")
                for s in sources[:2]: st.markdown(f"- [{s['baslik']}]({s['link']})")

            st.session_state.messages.append({"role": "assistant", "content": full_response, "timestamp": time.time()})

if __name__ == "__main__":
    main()
