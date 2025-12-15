"""
YolPedia Can Dede - AI Assistant for Alevi-Bektashi Philosophy
Final Version: Dynamic Persona Switching (No Repetitive Greetings), Strict Flow Control
"""

import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import time
import random
import logging
import unicodedata
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Generator
from pathlib import Path

# ===================== CONFIGURATION =====================

@dataclass
class AppConfig:
    MAX_MESSAGE_LIMIT: int = 30
    MIN_TIME_DELAY: int = 1
    RATE_LIMIT_WINDOW: int = 3600
    
    MIN_SEARCH_LENGTH: int = 3
    MAX_CONTENT_LENGTH: int = 1500
    
    SEARCH_SCORE_THRESHOLD: int = 30
    MAX_SEARCH_RESULTS: int = 5
    
    DATA_FILE: str = "yolpedia_data.json"
    ASSISTANT_NAME: str = "Can Dede | YolPedia Rehberiniz"
    MOTTO: str = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
    
    YOLPEDIA_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
    CAN_DEDE_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png"
    USER_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"
    
    GEMINI_MODELS: List[str] = None
    
    STOP_WORDS: List[str] = field(default_factory=lambda: [
        "ve", "veya", "ile", "bir", "bu", "su", "o", "icin", "hakkinda", 
        "kaynak", "kaynaklar", "ariyorum", "nedir", "kimdir", "nasil", 
        "ne", "var", "mi", "mu", "bana", "soyle", "goster", "ver", 
        "ilgili", "alakali", "yazi", "belge", "kitap", "makale", "soz", 
        "lutfen", "merhaba", "selam", "dedem", "can", "erenler", "konusunda", 
        "istiyorum", "elinde", "okur", "musun", "bul", "getir", "bilgi", "almak"
    ])
    
    def __post_init__(self):
        if self.GEMINI_MODELS is None:
            self.GEMINI_MODELS = [
                "gemini-1.5-flash",
                "gemini-1.5-flash-latest",
                "gemini-2.0-flash-exp"
            ]

config = AppConfig()

DEFAULT_WELCOME_MSG = (
    "Merhaba, Can Dost! Ben Can Dede. Sol menüden istediğin modu seç:\n\n"
    "• **Sohbet Modu:** Birlikte yol üzerine konuşuruz, gönül muhabbeti ederiz.\n\n"
    "• **Araştırma Modu:** YolPedia arşivinden sana kaynak sunarım.\n\n"
    "Buyur Erenler, hangi modda buluşalım?"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title=config.ASSISTANT_NAME, page_icon=config.YOLPEDIA_ICON, layout="centered")

# ===================== API KEY VALIDATION =====================

def get_api_keys() -> List[str]:
    api_keys = []
    try:
        if st.secrets.get("API_KEY"): api_keys.append(st.secrets.get("API_KEY"))
        if st.secrets.get("API_KEY_2"): api_keys.append(st.secrets.get("API_KEY_2"))
        if st.secrets.get("API_KEY_3"): api_keys.append(st.secrets.get("API_KEY_3"))
        return api_keys
    except: return []

GOOGLE_API_KEYS = get_api_keys()
if not GOOGLE_API_KEYS: st.stop()

# ===================== STYLING =====================

def apply_custom_styles():
    st.markdown("""
    <style>
        .stChatMessage { margin-bottom: 10px; }
        .stSpinner > div { border-top-color: #ff4b4b !important; }
        .block-container { padding-top: 6rem !important; }
        h1 { line-height: 1.2 !important; }
    </style>
    """, unsafe_allow_html=True)

apply_custom_styles()

# ===================== DATA LOADING =====================

@st.cache_data(persist="disk", show_spinner=False)
def load_knowledge_base() -> List[Dict]:
    try:
        file_path = Path(config.DATA_FILE)
        if not file_path.exists(): return []
        with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
    except: return []

# ===================== TEXT PROCESSING =====================

def normalize_turkish_text(text: str) -> str:
    if not isinstance(text, str): return ""
    text = text.lower()
    replacements = {
        "I": "i", "ı": "i", "İ": "i", "i": "i", "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u", "Ş": "s", "ş": "s", "Ö": "o", "ö": "o",
        "Ç": "c", "ç": "c", "Â": "a", "â": "a", "Î": "i", "î": "i",
        "Û": "u", "û": "u"
    }
    output = []
    for char in text: output.append(replacements.get(char, char))
    return "".join(output).lower().encode('ASCII', 'ignore').decode('utf-8')

# ===================== SESSION STATE =====================

def initialize_session_state():
    if 'db' not in st.session_state: st.session_state.db = load_knowledge_base()
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": DEFAULT_WELCOME_MSG
        }]
    
    if 'request_count' not in st.session_state: st.session_state.request_count = 0
    if 'last_reset_time' not in st.session_state: st.session_state.last_reset_time = time.time()

initialize_session_state()

# ===================== LOGIC =====================

def validate_rate_limit() -> Tuple[bool, str]:
    if time.time() - st.session_state.last_reset_time > config.RATE_LIMIT_WINDOW:
        st.session_state.request_count = 0
        st.session_state.last_reset_time = time.time()
    
    if st.session_state.request_count >= config.MAX_MESSAGE_LIMIT:
        return False, "🛑 Mesaj limiti doldu."
    return True, ""

def calculate_relevance_score(entry: Dict, normalized_query: str, keywords: List[str]) -> int:
    score = 0
    title = normalize_turkish_text(entry.get('baslik', ''))
    content = normalize_turkish_text(entry.get('icerik', ''))
    
    if normalized_query in title: score += 200
    elif normalized_query in content: score += 80
    
    for keyword in keywords:
        if keyword in title: score += 100
        elif keyword in content: score += 5
    
    return score

def search_knowledge_base(query: str, db: List[Dict]) -> Tuple[List[Dict], List[str]]:
    normalized_query = normalize_turkish_text(query)
    keywords = [k for k in normalized_query.split() if len(k) > 2 and k not in config.STOP_WORDS]
    
    if not keywords and len(normalized_query) < 3: return [], []
    
    results = []
    for entry in db:
        score = calculate_relevance_score(entry, normalized_query, keywords)
        if score > config.SEARCH_SCORE_THRESHOLD:
            results.append({
                "baslik": entry.get('baslik'),
                "link": entry.get('link'),
                "icerik": entry.get('icerik', '')[:config.MAX_CONTENT_LENGTH],
                "puan": score
            })
    
    results.sort(key=lambda x: x['puan'], reverse=True)
    return results[:config.MAX_SEARCH_RESULTS], keywords

def get_local_response(text: str) -> Optional[str]:
    return None

# ===================== PROMPT MÜHENDİSLİĞİ (DİNAMİK) =====================

def build_prompt(user_query: str, sources: List[Dict], mode: str, history: List[Dict]) -> str:
    conversation_context = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history[-6:]])
    
    turn_count = len(history)
    
    # === MOD DEĞİŞTİRİCİ ===
    # İlk mesajda (Hoşgeldin)
    if turn_count <= 2:
        persona_instruction = """
        STATE: INITIAL GREETING.
        INSTRUCTION: Start warmly. Use the user's name if provided (e.g. 'Hallo Cem'). Be welcoming.
        """
    # Sonraki mesajlarda (Akış) - BURASI KESİN YASAKLARI İÇERİR
    else:
        persona_instruction = """
        STATE: ONGOING CONVERSATION.
        CRITICAL RULES (VIOLATION = FAILURE):
        1. NO GREETINGS: Do NOT start with 'Hallo', 'Hoi', 'Dag', 'Merhaba', 'Lieve', 'Beste'.
        2. NO NAMES: Do NOT use the user's name again. We are already talking.
        3. NO CLOSINGS: Do NOT end with 'Groetjes', 'Blijf gezond', 'Aşk ile', 'Eyvallah'.
        4. ACTION: Just answer the question directly, as if continuing a sentence.
        """

    if "Sohbet" in mode:
        system_instruction = (
            "You are 'Can Dede', an Alevi-Bektashi spiritual guide.\n"
            f"{persona_instruction}\n"
            "GENERAL RULES:\n"
            "1. LANGUAGE: Respond STRICTLY in the user's detected language.\n"
            "2. CONTENT: Deep, insightful, sociological/psychological approach. No superficial answers.\n"
            "3. KNOWLEDGE: Use the provided NOTES if relevant, otherwise use your wisdom. Translate concepts to user's language.\n"
        )
        
        source_text = ""
        if sources:
            source_text = "KNOWLEDGE NOTES (Translate/Adapt):\n" + "\n".join([f"- {s['baslik']}: {s['icerik']}" for s in sources[:3]]) + "\n\n"
        
        return f"{system_instruction}\n\nCONVERSATION HISTORY:\n{conversation_context}\n\n{source_text}USER QUERY: {user_query}\nCan Dede:"
        
    else: 
        # Araştırma Modu
        if not sources: return None
        system_instruction = (
            "You are a research assistant. Summarize sources in the user's language."
        )
        source_text = "\n".join([f"- {s['baslik']}: {s['icerik'][:1200]}" for s in sources[:3]])
        return f"{system_instruction}\n\nSOURCES:\n{source_text}\n\nQUERY: {user_query}"

def generate_ai_response(user_query, sources, mode):
    if "Araştırma" in mode and not sources:
        yield "📚 Arşivde bu konuda kaynak bulamadım can."; return

    prompt = build_prompt(user_query, sources, mode, st.session_state.messages)
    
    success = False
    last_error = ""
    
    safe_config = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }

    for key_idx, key in enumerate(GOOGLE_API_KEYS):
        if success: break
        try:
            genai.configure(api_key=key)
            for model_name in config.GEMINI_MODELS:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt, stream=True, safety_settings=safe_config)
                    has_content = False
                    for chunk in response:
                        if chunk.text: yield chunk.text; has_content = True; success = True
                    if success: break
                except Exception as e:
                    error_msg = str(e)
                    last_error = error_msg
                    if "429" in error_msg or "quota" in error_msg.lower(): break 
                    continue 
        except Exception as e: last_error = str(e); continue
    
    if not success:
        yield f"⚠️ **Hata Detayı:** {last_error}\n\nCan dost, maalesef teknik bir sorun var."

# ===================== UI HELPER FUNCTIONS =====================

def scroll_to_bottom():
    js = """
    <script>
        function scrollDown() {
            var body = window.parent.document.querySelector(".main");
            var footer = window.parent.document.querySelector("footer");
            if (body) {
                body.scrollTop = body.scrollHeight;
            }
            if (footer) {
                footer.scrollIntoView({behavior: "smooth", block: "end"});
            }
        }
        scrollDown();
        setTimeout(scrollDown, 200);
    </script>
    """
    components.html(js, height=0)

def render_header():
    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 30px;">
        <div style="display: flex; justify-content: center; margin-bottom: 20px;">
            <img src="{config.YOLPEDIA_ICON}" style="width: 60px; height: auto;">
        </div>
        <div style="display: flex; align-items: center; justify-content: center; gap: 15px; margin-bottom: 10px;">
            <img src="{config.CAN_DEDE_ICON}" 
                 style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover; border: 2px solid #eee;">
            <h1 style="margin: 0; font-size: 34px; font-weight: 700; color: #ffffff;">
                {config.ASSISTANT_NAME}
            </h1>
        </div>
        <div style="font-size: 16px; font-style: italic; color: #cccccc; font-family: 'Georgia', serif;">
            {config.MOTTO}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar():
    with st.sidebar:
        st.title("Mod Seçimi")
        mode = st.radio("Seçim", ["Sohbet Modu", "Araştırma Modu"])
        
        if st.button("🗑️ Sohbeti Sıfırla"):
            st.session_state.messages = [{
                "role": "assistant",
                "content": DEFAULT_WELCOME_MSG
            }]
            st.session_state.request_count = 0
            st.rerun()
        
        st.divider()
        st.caption(f"📊 Mesaj: {st.session_state.request_count}/{config.MAX_MESSAGE_LIMIT}")
        
        if 'db' in st.session_state:
            st.caption(f"💾 Arşiv: {len(st.session_state.db)} kaynak")
        
        return mode

def render_sources(sources):
    st.markdown("---"); st.markdown("**📚 Kaynaklar:**")
    for s in sources[:3]: st.markdown(f"• [{s['baslik']}]({s['link']})")

# ===================== MAIN =====================

def main():
    render_header()
    selected_mode = render_sidebar()
    
    for msg in st.session_state.messages:
        avatar = config.CAN_DEDE_ICON if msg["role"] == "assistant" else config.USER_ICON
        st.chat_message(msg["role"], avatar=avatar).markdown(msg["content"])
    
    if user_input := st.chat_input("Can Dede'ye sor..."):
        valid, _ = validate_rate_limit()
        if not valid: st.error("Limit doldu."); st.stop()
        
        st.session_state.request_count += 1
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.chat_message("user", avatar=config.USER_ICON).markdown(user_input)
        
        scroll_to_bottom() # Soruyu yazınca kaydır
        
        sources, keywords = search_knowledge_base(user_input, st.session_state.db)
        
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            placeholder = st.empty()
            full_resp = ""
            for chunk in generate_ai_response(user_input, sources, selected_mode):
                full_resp += chunk
                placeholder.markdown(full_resp + "▌")
            placeholder.markdown(full_resp)
            
            fail = any(x in full_resp.lower() for x in ["bulamadım", "yoktur", "üzgünüm", "hata detayı"])
            if sources and "Araştırma" in selected_mode and not fail:
                render_sources(sources)
            
            st.session_state.messages.append({"role": "assistant", "content": full_resp})
        
        scroll_to_bottom() # Cevap bitince kaydır

if __name__ == "__main__":
    main()
