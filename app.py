"""
YolPedia Can Dede - Teknik Onarılmış Versiyon
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
    GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    DEFAULT_MODEL = "gemini-2.0-flash"
    MIN_SEARCH_LENGTH = 2
    MAX_SEARCH_RESULTS = 5
    MAX_CONTENT_LENGTH = 1000
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
            cursor.execute('''CREATE TABLE IF NOT EXISTS content (id INTEGER PRIMARY KEY AUTOINCREMENT, baslik TEXT NOT NULL, link TEXT NOT NULL, icerik TEXT, normalized TEXT, UNIQUE(link))''')
            conn.commit()
        except Exception as e: print(f"DB Error: {e}")
    
    def load_from_json(self):
        try:
            if os.path.exists(config.DATA_FILE):
                with open(config.DATA_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                conn = self.get_connection()
                cursor = conn.cursor()
                for item in self.data:
                    cursor.execute('''INSERT OR REPLACE INTO content (baslik, link, icerik, normalized) VALUES (?, ?, ?, ?)''', 
                                 (item['baslik'], item['link'], item['icerik'][:config.MAX_CONTENT_LENGTH], self.normalize_text(item['baslik'] + ' ' + item['icerik'])))
                conn.commit()
        except Exception as e: print(f"Load Error: {e}")
    
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
        q_norm = self.normalize_text(query)
        results = []
        for item in self.data:
            if q_norm in self.normalize_text(item.get('icerik', '')) or q_norm in self.normalize_text(item.get('baslik', '')):
                results.append({
                    'baslik': item['baslik'], 'link': item['link'], 
                    'icerik': item.get('icerik', '')[:config.MAX_CONTENT_LENGTH],
                    'snippet': item.get('icerik', '')[:300], 'score': 100 if query.lower() in item['baslik'].lower() else 50
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
        return None
    
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
        is_returning = user_msg_count > 0 # Teknik Onarım: has_context hatası için değişken sabitlendi.
        
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
- Kullanıcıların her biri birer taliptir. O yüzden onlara "canım, evladım, çocuğum" şeklindeki hitaplardan.
- Ansiklopedik dilden, akademik tanımlardan.
- "Ben bir yapay zekayım" imasından.
- Soğuk ve resmi hitaplardan.
</kaçın>
</role>"""

        context_text = "\n".join([f"{'Can' if m['role'] == 'user' else 'Dede'}: {m['content']}" for m in history[-8:]])
        
        sources_text = ""
        if sources:
            sources_text = "\n".join([f"- {s['baslik']}: {s.get('snippet', s['icerik'][:300])}" for s in sources[:2]])

        # Teknik Onarım: Kopuk kaynak blokları tek bir formatta birleştirildi.
        return f"{sys_instruction}\n\n<GECMIS_MUHABBET>\n{context_text}\n</GECMIS_MUHABBET>\n\n<YOLPEDIA_BILGISI>\n{sources_text}\n\nNOT: Bu bilgileri mürşit bilgeliğiyle yoğurarak kullan, kopyalama.\n</YOLPEDIA_BILGISI>\n\nCan'ın yeni sözü: {query}\n\nCan Dede (Sohbetin akışını bozmadan, bilgece):"

# ===================== RESPONSE GENERATOR =====================

class ResponseGenerator:
    def __init__(self, api_manager: APIManager):
        self.api_manager = api_manager
        self.prompt_engine = PromptEngine()
    
    def generate(self, query: str, sources: List[Dict]) -> Generator[str, None, None]:
        user_messages = [m for m in st.session_state.messages if m['role'] == 'user']
        
        if len(user_messages) == 0:
            greeting = self.check_greeting(query)
            if greeting:
                yield greeting
                return
    
        api_key = self.api_manager.get_api_key()
        if not api_key:
            yield "Can dost, teknik bir aksaklık var (API Key). Az sonra tekrar dene. 🙏"
            return
    
        prompt = self.prompt_engine.build_prompt(query, sources)
        
        for attempt in range(3):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(self.api_manager.get_current_model())
                response = model.generate_content(
                    prompt,
                    stream=True,
                    generation_config={"temperature": 0.7, "max_output_tokens": 2048, "top_p": 0.95, "top_k": 40},
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
                yield "Teknik bir huzursuzluk oldu. Az sonra tekrar dener misin? 🙏"
                return

    @staticmethod
    def check_greeting(query: str) -> Optional[str]:
        q = query.lower()
        if any(x in q for x in ["merhaba", "selam", "slm", "hey"]):
            return "Aşk ile can dost! Hoş geldin. Buyur, ne üzerine konuşalım?"
        if any(x in q for x in ["nasılsın", "naber"]):
            return "Şükür erenler, bugün de yolun hizmetindeyiz. Senin gönlün nicedir?"
        if any(x in q for x in ["teşekkür", "sağ ol"]):
            return "Estağfurullah erenler, senin gibi güzel bir canla sohbet etmek ne güzel!"
        return None

# ===================== SESSION STATE =====================

def init_session():
    if 'kb' not in st.session_state: st.session_state.kb = KnowledgeBase()
    if 'api_manager' not in st.session_state: st.session_state.api_manager = APIManager()
    if 'response_generator' not in st.session_state: st.session_state.response_generator = ResponseGenerator(st.session_state.api_manager)
    if 'messages' not in st.session_state:
        st.session_state.messages = deque(maxlen=config.MAX_HISTORY_MESSAGES)
        st.session_state.messages.append({"role": "assistant", "content": "Merhaba erenler, nedir arzun?", "timestamp": time.time()})

# ===================== MAIN APPLICATION =====================

def main():
    if 'initialized' not in st.session_state:
        init_session()
        st.session_state.initialized = True

    # CSS 
    st.markdown("""<style>
        .stApp { background-color: #020212 !important; color: #e6e6e6 !important; }
        .stChatMessage { background-color: rgba(45, 45, 68, 0.7) !important; border-radius: 10px; border-left: 4px solid #3d3d5c; margin-bottom: 10px; }
        .stChatMessage[data-testid*="assistant"] { border-left-color: #B31F2E; background-color: rgba(179, 31, 46, 0.1) !important; }
        .stButton button { background-color: #B31F2E !important; color: white !important; width: 100%; border: none; }
        .stChatInputContainer input { background-color: #2d2d44 !important; color: #e6e6e6 !important; }
    </style>""", unsafe_allow_html=True)
    
    with st.sidebar:
        st.image(config.YOLPEDIA_ICON, width=60)
        st.divider()
        if st.button("🧹 Sohbeti Temizle"):
            st.session_state.messages = deque(maxlen=config.MAX_HISTORY_MESSAGES)
            st.session_state.messages.append({"role": "assistant", "content": "Sohbet temizlendi can dost.", "timestamp": time.time()})
            st.rerun()

    st.markdown(f'<div style="text-align:center"><h1>{config.ASSISTANT_NAME}</h1><p><i>{config.MOTTO}</i></p></div>', unsafe_allow_html=True)

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar=config.CAN_DEDE_ICON if msg["role"] == "assistant" else config.USER_ICON):
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
                for s in sources[:2]: st.markdown(f"• [{s['baslik']}]({s['link']})")
            
            st.session_state.messages.append({"role": "assistant", "content": full_response, "timestamp": time.time()})

if __name__ == "__main__":
    main()
