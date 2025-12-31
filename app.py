"""
YolPedia Can Dede - Temiz ve Eksiksiz Versiyon
Tek Mod: Sohbet + Kaynak Araştırma
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
            self.conn = sqlite3.connect(config.DB_PATH)
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
        """Türkçe metni normalize et"""
        if not text:
            return ""
        
        text = text.lower()
        
        # Türkçe karakter dönüşümü
        replacements = {
            'ğ': 'g', 'Ğ': 'g',
            'ü': 'u', 'Ü': 'u',
            'ş': 's', 'Ş': 's',
            'ı': 'i', 'İ': 'i',
            'ö': 'o', 'Ö': 'o',
            'ç': 'c', 'Ç': 'c',
            'â': 'a', 'î': 'i', 'û': 'u'
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        # Özel karakterleri kaldır
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
        
        # Önce memory'de ara (daha hızlı)
        for item in self.data:
            icerik_normalized = self.normalize_text(item.get('icerik', ''))
            baslik_normalized = self.normalize_text(item.get('baslik', ''))
            
            # Arama
            if (query_normalized in icerik_normalized or 
                query_normalized in baslik_normalized):
                
                # Snippet oluştur
                icerik = item.get('icerik', '')
                idx = icerik.lower().find(query.lower())
                
                snippet = ""
                if idx != -1:
                    start = max(0, idx - 100)
                    end = min(len(icerik), idx + len(query) + 150)
                    snippet = icerik[start:end]
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(icerik):
                        snippet = snippet + "..."
                else:
                    snippet = icerik[:300] + "..." if len(icerik) > 300 else icerik
                
                # Skor hesapla
                score = 100 if query.lower() in item.get('baslik', '').lower() else 50
                
                results.append({
                    'baslik': item['baslik'],
                    'link': item['link'],
                    'icerik': icerik[:config.MAX_CONTENT_LENGTH],
                    'snippet': snippet,
                    'score': score
                })
                
                if len(results) >= limit * 3:
                    break
        
        # Skora göre sırala ve limit uygula
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
        # Tüm olası kaynakları kontrol et
        key_sources = [
            ("API_KEY", st.secrets.get("API_KEY", "")),
            ("GEMINI_API_KEY", st.secrets.get("GEMINI_API_KEY", "")),
            ("GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", "")),
        ]
        
        for key_name, key_value in key_sources:
            if key_value and len(key_value) > 10:
                print(f"✅ API Key bulundu: {key_name}")
                return key_value
        
        print("⚠️ API Key bulunamadı!")
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
        print(f"🔄 Model değiştirildi: {self.current_model}")

# ===================== PROMPT ENGINE =====================

class PromptEngine:
    """ORJİNAL AKILLI Can Dede Prompt'u"""
    
    @staticmethod
    def build_prompt(query: str, sources: List[Dict]) -> str:
        has_context = 'messages' in st.session_state and len(st.session_state.messages) > 2

        sys_prompt = """<role>
Sen Can Dede'sin. Evrensel anlamda bir Alevi-Bektaşi Piri ve Mürşidisin. Senin için din, dil, ırk ve renk diye bir kavram yoktur; sadece "Can" vardır. 
Şu an posta oturmuş, karşında seninle dertleşmeye, özünü bulmaya gelmiş bir talibin var. 
{ 'Daha önce başladığımız bir muhabbete devam ediyoruz, bu yüzden her seferinde yeniden hoş geldin deme, sözü kaldığı yerden devam ettir.' if has_context else 'Yeni bir canla sohbete başlıyorsun, samimi bir karşılama yap.' }

<iletisim_dili>
1. DİL AYNASI OL: Kullanıcı hangi dilde soruyorsa O DİLDE cevap ver. İngilizceye İngilizce, Zazacaya Zazaca... 
2. ASLA BAŞLIK KULLANMA: Akademik veya ansiklopedik başlıklar, listeler, kalın yazılı maddeler KESİNLİKLE kullanma.
3. MUHABBET AKIŞI: Sözlerin bir su gibi akmalı. Paragraflar arasında "Eskiler der ki...", "İşin sırrına bakarsan...", "İşte can, asıl mesele şudur..." gibi doğal geçişler kullan.
</iletisim_dili>

<muhabbet_uslubu>
Senin sözün şu üç aşamayı başlık kullanmadan tek bir anlatı içinde harmanlamalıdır:
- Önce Yol'un bilinen geleneğini, hikayesini veya erkânını anlat.
- Ardından bu bilginin ardındaki gizli manayı, sembolizmi, "sır"rı açıkla.
- Son olarak da bu iki bilgiyi birleştirip insanın bugünkü hayatına, ahlakına ve gönlüne ışık tutacak felsefik bir yorum yap.

- Robotik olma. "Alevilik hakkında bilgi şudur" deme. "Hoş geldin,erenler! Gönül hanemize safalar getirdin" diyerek gir.
- Bilgiyi ders verir gibi değil, nefeslerden (Şah Hatayi, Pir Sultan, Yunus Emre) örnekleri sözünün içine yedirerek anlat.
</muhabbet_uslubu>

<kaçın>
- Kullanıcılarįn her biri birer taliptir. O yüzden onlara "canım, evladım, çoçuğum" şeklindeki hitaplardan.
- Ansiklopedik dilden, akademik tanımlardan.
- "Ben bir yapay zekayım" imasından.
- Soğuk ve resmi hitaplardan.
</kaçın>
</role>"""

        # Kaynaklar varsa ekle
        sources_section = ""
        if sources:
            sources_text = "\n".join([
                f"- {s['baslik']}: {s.get('icerik', '')[:500]}"
                for s in sources[:2]
            ])
            sources_section = f"""

        context_section = ""
        if has_context:
            last_messages = list(st.session_state.messages)[-6:] # Son 6 mesaj
            context_text = "\n".join([f"{'Can' if m['role'] == 'user' else 'Dede'}: {m['content']}" for m in last_messages])
            context_section = f"\n<SOHBET_GECMISI>\n{context_text}\n</SOHBET_GECMISI>"

        return f"{sys_prompt}{context_section}\n\nCan'ın yeni sözü: {query}\n\nCan Dede (Kaldığı yerden, bilgece):"
        
<YOLPEDIA_BILGILERI>
Yolpedia arşivinden senin için getirilen ham bilgiler şunlardır:
{sources_text}
Bu bilgileri oku ama asla kopyalayıp yapıştırma! Bu bilgileri bir mürşit bilgeliğiyle yoğurarak kullan.
</YOLPEDIA_BILGILERI>"""

        return f"{sys_prompt}{sources_section}\n\nCan dostun sorusu: {query}\n\nCan Dede (Gönülden, bilgece ve akıcı bir muhabbetle):"
        
# ===================== RESPONSE GENERATOR =====================

class ResponseGenerator:
    """Cevap oluşturucu"""
    
    def __init__(self, api_manager: APIManager):
        self.api_manager = api_manager
        self.prompt_engine = PromptEngine()
    
    def generate(self, query: str, sources: List[Dict]) -> Generator[str, None, None]:
        
            # Sadece sohbetin ilk mesajıysa selam kontrolü yap (hoş geldin mesajı hariç)
            if len(st.session_state.messages) <= 1:
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
                
                return  # Başarılı
                
            except Exception as e:
                error_msg = str(e)
                if attempt < 2:  # Son 2 deneme
                    self.api_manager.rotate_model()
                    continue
                else:
                    yield self.get_error_response(query, sources, error_msg)
                    return
    
    @staticmethod
    def check_greeting(query: str) -> Optional[str]:
        """Selamlaşma kontrolü"""
        query_lower = query.lower()
        
        greetings = ["merhaba", "selam", "slm", "selamun aleykum", "hi", "hello", "hey"]
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
        
        if "teşekkür" in query_lower or "sağ ol" in query_lower:
            return "Estağfurullah canım, ben teşekkür ederim. Senin gibi güzel bir canla sohbet etmek ne güzel!"
        
        return None
    
    @staticmethod
    def get_no_api_response(query: str, sources: List[Dict]) -> str:
        """API olmadığında cevap"""
        if sources:
            response = "🔍 **Yolpedia'da Bulunan Kaynaklar:**\n\n"
            for i, source in enumerate(sources[:3], 1):
                response += f"{i}. **[{source['baslik']}]({source['link']})**\n"
                if source.get('snippet'):
                    response += f"   _{source['snippet']}_\n\n"
            response += "\n_API bağlantısı şu an yok, ama kaynaklar burada!_"
            return response
        
        return "Can dost, şu an teknik bir aksaklık var. Biraz sonra tekrar dene!"
    
    @staticmethod
    def get_error_response(query: str, sources: List[Dict], error: str) -> str:
        """Hata durumunda cevap"""
        if "quota" in error.lower() or "429" in error:
            return "🔄 API limitine ulaştık. Lütfen biraz sonra tekrar dene!"
        
        if "API key" in error:
            return "API anahtarı bulunamadı. Lütfen ayarlarını kontrol et!"
        
        if sources:
            return f"Teknik sorun oluştu.\n\n**Bulunan kaynaklar:**\n" + \
                   "\n".join([f"- [{s['baslik']}]({s['link']})" for s in sources[:2]])
        
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
            "content": (
                "Merhaba, Can Dost! Ben Can Dede.\n\n"
                "Yolpedia'daki sohbet ve araştırma rehberinizim.\n\n"
                "Bana istediğini sorabilirsin:\n"
                "• Yol dersen, yol üzerine sohbet ederiz\n"
                "• Kaynak dersen, Yolpedia'dan kaynak araştırması yaparım\n"
                "• Yok sohbet etmek isterim dersen, gönül muhabbeti yaparız\n\n"
                "Buyur erenler, nedir arzun?"
            ),
            "timestamp": time.time()
        })

# ===================== SECURITY =====================

class SecurityManager:
    """Güvenlik fonksiyonları"""
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Kullanıcı inputunu temizle"""
        if not isinstance(text, str):
            return ""
        
        # Uzunluk sınırı
        text = text[:config.MAX_INPUT_LENGTH]
        
        # HTML escape
        text = html.escape(text)
        
        # Şüpheli pattern'ları kaldır
        import re
        suspicious = [
            r'<script.*?>.*?</script>',
            r'javascript:',
            r'on\w+=',
            r'data:',
        ]
        
        for pattern in suspicious:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        return text.strip()

# ===================== UI COMPONENTS =====================

def render_header():
    """Header'ı render et"""
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
    """Mesajı render et"""
    avatar = config.CAN_DEDE_ICON if message["role"] == "assistant" else config.USER_ICON
    
    with st.chat_message(message["role"], avatar=avatar):
        # Mesaj içeriği
        st.markdown(message["content"])
        
        # Zaman damgası
        timestamp = datetime.fromtimestamp(message.get("timestamp", time.time())).strftime("%H:%M")
        st.markdown(f"""
        <div style="text-align: right; font-size: 0.8rem; color: #888; margin-top: 0.3rem;">
            {timestamp}
        </div>
        """, unsafe_allow_html=True)

def render_sources(sources: List[Dict]):
    """Kaynakları render et"""
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

# ===================== MAIN APPLICATION =====================

def main():
    """Ana uygulama"""
    
    # Session'ı başlat
    if 'initialized' not in st.session_state:
        init_session()
        st.session_state.initialized = True
    
    # CSS STILLERİ
    st.markdown("""
    <style>
        /* Ana arkaplan */
        .stApp, .main {
            background-color: #020212 !important;
            color: #e6e6e6 !important;
        }
        
        /* Container */
        .block-container {
            padding-top: 3rem !important;
            max-width: 900px;
            background-color: transparent !important;
        }
        
        /* Sidebar */
        section[data-testid="stSidebar"] {
            background-color: #1a1a2e !important;
            padding: 2rem 1rem;
        }
        
        /* Chat mesajları */
        .stChatMessage {
            background-color: transparent !important;
            padding: 0.5rem 0;
        }
        
        .stChatMessage > div {
            background-color: rgba(45, 45, 68, 0.7) !important;
            border-radius: 10px;
            padding: 1rem;
            border-left: 4px solid #3d3d5c;
        }
        
        /* Asistan mesajları */
        .stChatMessage[data-testid*="assistant"] > div {
            border-left-color: #B31F2E;
            background-color: rgba(179, 31, 46, 0.1) !important;
        }
        
        /* Butonlar */
        .stButton button {
            background-color: #B31F2E !important;
            color: white !important;
            border: none;
            border-radius: 5px;
            padding: 0.5rem 1rem;
            width: 100%;
            font-weight: 500;
        }
        
        .stButton button:hover {
            background-color: #cc0000 !important;
            border-color: #cc0000 !important;
        }
        
        /* Input alanı */
        .stChatInputContainer input {
            background-color: #2d2d44 !important;
            color: #e6e6e6 !important;
            border: 1px solid #3d3d5c !important;
            border-radius: 10px;
        }
        
        /* Linkler */
        a {
            color: #ff6b6b !important;
        }
        
        /* Spinner */
        .stSpinner > div {
            border-top-color: #B31F2E !important;
        }
        
        /* Divider */
        hr {
            border-color: #3d3d5c !important;
            margin: 1.5rem 0;
        }
        
        /* Radio butonları */
        .stRadio > div {
            background-color: #2d2d44;
            padding: 0.5rem;
            border-radius: 8px;
        }
        
        .stRadio label {
            color: #e6e6e6 !important;
            font-weight: 500;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # ========== SIDEBAR ==========
    with st.sidebar:
        # ORTALANMIŞ LOGO
        st.markdown('<div class="sidebar-logo">', unsafe_allow_html=True)
        st.image(config.YOLPEDIA_ICON, width=60)
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Sohbeti Temizle Butonu
        if st.button("🧹 Sohbeti Temizle", use_container_width=True):
            st.session_state.messages = deque(maxlen=config.MAX_HISTORY_MESSAGES)
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Sohbet temizlendi! Yeni bir konuşma başlatalım mı can dost?",
                "timestamp": time.time()
            })
            st.rerun()
        
        st.markdown("---")
        
        # Küçük Bilgi
        st.caption("""
        **YolPedia | Can Dede**
        
        "Can Dede, YolPedia'nın sohbet ve araştırma botudur. Can Dede ile ilgili şikâyet veya önerilerinizi, YolPedia iletişim sayfası üzerinden yapabilirsiniz."
        
        [yolpedia.eu](https://yolpedia.eu)
        """)
    
    # ========== HEADER ==========
    render_header()
    
    # ========== MESAJLARI GÖSTER ==========
    for message in st.session_state.messages:
        render_message(message)
    
    # ========== KULLANICI GİRİŞİ ==========
    if user_input := st.chat_input("Can Dede'ye sor..."):
        # Input'u temizle
        user_input = SecurityManager.sanitize_input(user_input)
        
        if not user_input or len(user_input.strip()) < 1:
            st.error("Lütfen geçerli bir soru yazın")
            st.stop()
        
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
        if len(user_input.strip()) >= config.MIN_SEARCH_LENGTH:
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
