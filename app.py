"""
YolPedia Can Dede - AI Assistant for Alevi-Bektashi Philosophy
Refactored version with improved code quality, error handling, and maintainability
"""

import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
import json
import time
import random
import logging
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
    
    # Eşik değerini düşük tutuyoruz ki "celali" gibi tek kelimeleri kaçırmasın
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
            self.GEMINI_MODELS = ["gemini-1.5-flash", "gemini-1.5-flash-latest"]

config = AppConfig()

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
        .block-container { padding-top: 2rem; }
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

# ===================== TEXT PROCESSING (BALYOZ YÖNTEMİ) =====================

def normalize_turkish_text(text: str) -> str:
    """
    Türkçe karakter sorununu kökten çözen manuel haritalama.
    Python'un lower() fonksiyonuna güvenmiyoruz, kendimiz çeviriyoruz.
    """
    if not isinstance(text, str):
        return ""
    
    # Harf harf dönüşüm tablosu (Hem büyük hem küçük harfleri kapsar)
    replacements = {
        "I": "i", "ı": "i", "İ": "i", "i": "i",
        "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u",
        "Ş": "s", "ş": "s",
        "Ö": "o", "ö": "o",
        "Ç": "c", "ç": "c",
        "Â": "a", "â": "a",
        "Î": "i", "î": "i",
        "Û": "u", "û": "u"
    }
    
    output = []
    for char in text:
        # Varsa tablodan al, yoksa harfin kendisini al
        output.append(replacements.get(char, char))
    
    # Birleştir ve her ihtimale karşı yine de lower() ve ascii temizliği yap
    return "".join(output).lower().encode('ASCII', 'ignore').decode('utf-8')

# ===================== SESSION STATE =====================

def initialize_session_state():
    if 'db' not in st.session_state: st.session_state.db = load_knowledge_base()
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": "Merhaba, Can Dost! Ben Can Dede. Buyur Erenler, hangi modda buluşalım?"
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
    
    # Tam eşleşme (Title Priority)
    if normalized_query in title: score += 300 # Başlıkta geçiyorsa çok yüksek puan
    elif normalized_query in content: score += 50
    
    # Kelime bazlı eşleşme
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
                "puan": score # Debug için puanı ekliyoruz
            })
    
    results.sort(key=lambda x: x['puan'], reverse=True)
    return results[:config.MAX_SEARCH_RESULTS], keywords

def get_local_response(text: str) -> Optional[str]:
    norm = normalize_turkish_text(text)
    if any(x in norm for x in ["merhaba", "selam"]): return "Aşk ile, merhaba can."
    return None

def build_prompt(user_query: str, sources: List[Dict], mode: str) -> str:
    system = "Sen Can Dede'sin. Alevi-Bektaşi rehberisin."
    if "Sohbet" in mode:
        return f"{system}\nKAYNAKLAR:\n" + "\n".join([f"- {s['baslik']}: {s['icerik']}" for s in sources[:2]]) + f"\n\nSoru: {user_query}"
    else: # Research
        if not sources: return None
        return f"{system}\nSadece şu kaynaklara göre cevapla:\n" + "\n".join([f"- {s['baslik']}: {s['icerik'][:1000]}" for s in sources[:3]]) + f"\n\nSoru: {user_query}"

def generate_ai_response(user_query, sources, mode):
    local = get_local_response(user_query)
    if local:
        yield local; return

    if "Araştırma" in mode and not sources:
        yield "📚 Arşivde bu konuda (kelime eşleşmesiyle) kaynak bulamadım can."; return

    prompt = build_prompt(user_query, sources, mode)
    success = False
    
    for key in GOOGLE_API_KEYS:
        if success: break
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt, stream=True)
            for chunk in response:
                if chunk.text: yield chunk.text; success = True
            if success: break
        except: continue
    
    if not success: yield "⚠️ Teknik bir sorun oluştu can."

# ===================== UI =====================

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
        
        sources, keywords = search_knowledge_base(user_input, st.session_state.db)
        
        # DEBUG EXPANDER (Puanları Göster)
        if sources:
            with st.expander(f"🔍 Can Dede Arka Planda Bunları Buldu ({len(sources)} Kaynak)"):
                st.caption(f"Aranan Anahtar Kelimeler: {keywords}")
                for s in sources:
                    st.write(f"• **{s['baslik']}** (Uygunluk Puanı: {s['puan']})")
        
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            placeholder = st.empty()
            full_resp = ""
            for chunk in generate_ai_response(user_input, sources, selected_mode):
                full_resp += chunk
                placeholder.markdown(full_resp + "▌")
            placeholder.markdown(full_resp)
            
            # Negatif kontrol
            fail = any(x in full_resp.lower() for x in ["bulamadım", "yoktur", "üzgünüm"])
            if sources and "Araştırma" in selected_mode and not fail:
                render_sources(sources)
            
            st.session_state.messages.append({"role": "assistant", "content": full_resp})

def render_header():
    st.markdown(f"<h1 style='text-align:center'>{config.ASSISTANT_NAME}</h1>", unsafe_allow_html=True)

def render_sidebar():
    with st.sidebar:
        st.title("Mod Seçimi")
        mode = st.radio("Seçim", ["Sohbet Modu", "Araştırma Modu"])
        if st.button("🗑️ Sohbeti Sıfırla"): st.session_state.messages = []; st.rerun()
        
        if 'db' in st.session_state:
            st.info(f"📚 Kaynak Sayısı: **{len(st.session_state.db)}**")
            # TEST KUTUSU
            st.markdown("---")
            test_q = st.text_input("Test Arama:", placeholder="celali").strip()
            if test_q:
                norm_q = normalize_turkish_text(test_q)
                found = [e['baslik'] for e in st.session_state.db if norm_q in normalize_turkish_text(e.get('baslik',''))]
                if found: st.success(f"✅ {len(found)} Sonuç:\n" + "\n".join([f"- {t}" for t in found[:3]]))
                else: st.error(f"❌ '{norm_q}' bulunamadı.")
        return mode

def render_sources(sources):
    st.markdown("---"); st.markdown("**📚 Kaynaklar:**")
    for s in sources[:3]: st.markdown(f"• [{s['baslik']}]({s['link']})")

if __name__ == "__main__":
    main()
