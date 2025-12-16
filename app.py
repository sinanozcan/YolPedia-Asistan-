"""
YolPedia Can Dede - AI Assistant
Final Working Version - Gemini 2.5 + Multi API Key
"""

import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
import json
import time
import random
import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Generator
from pathlib import Path

@dataclass
class AppConfig:
    MAX_MESSAGE_LIMIT: int = 30
    MIN_TIME_DELAY: int = 1
    RATE_LIMIT_WINDOW: int = 3600
    MIN_SEARCH_LENGTH: int = 3
    MAX_CONTENT_LENGTH: int = 1500
    SEARCH_SCORE_THRESHOLD: int = 50
    MAX_SEARCH_RESULTS: int = 5
    DATA_FILE: str = "yolpedia_data.json"
    ASSISTANT_NAME: str = "Can Dede | YolPedia Rehberiniz"
    MOTTO: str = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
    YOLPEDIA_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
    CAN_DEDE_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png"
    USER_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"
    GEMINI_MODELS: List[str] = None
    
    def __post_init__(self):
        if self.GEMINI_MODELS is None:
            self.GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]

config = AppConfig()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

st.set_page_config(page_title=config.ASSISTANT_NAME, page_icon=config.YOLPEDIA_ICON, layout="centered")

# API KEYS
def get_api_keys() -> List[str]:
    keys = []
    try:
        for key_name in ["API_KEY", "API_KEY_2", "API_KEY_3"]:
            k = st.secrets.get(key_name, "")
            if k: keys.append(k)
    except: pass
    return keys

API_KEYS = get_api_keys()
if not API_KEYS:
    st.error("⚠️ API key bulunamadı")
    st.stop()

# CSS
st.markdown("""<style>
.stChatMessage { 
    margin-bottom: 10px; 
}
.stSpinner > div { 
    border-top-color: #ff4b4b !important; 
}
.block-container { 
    padding-top: 6rem !important; 
}
h1 { 
    line-height: 1.2 !important; 
}
a { 
    color: #ff4b4b !important; 
    text-decoration: none; 
    font-weight: bold; 
}
a:hover { 
    text-decoration: underline; 
}
</style>""", unsafe_allow_html=True)

# DATA
@st.cache_data(persist="disk", show_spinner=False)
def load_kb() -> List[Dict]:
    try:
        with open(Path(config.DATA_FILE), "r", encoding="utf-8") as f:
            return json.load(f)
    except: return []

def normalize(text: str) -> str:
    if not isinstance(text, str): return ""
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

# SESSION
def init_session():
    if 'db' not in st.session_state: st.session_state.db = load_kb()
    if 'messages' not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": 
            "Merhaba, Can Dost! Sol menüden modunu seç:\n\n• **Sohbet Modu**\n• **Araştırma Modu**"}]
    if 'request_count' not in st.session_state: st.session_state.request_count = 0
    if 'last_reset_time' not in st.session_state: st.session_state.last_reset_time = time.time()

init_session()

# RATE LIMIT
def validate_rate() -> Tuple[bool, str]:
    if time.time() - st.session_state.last_reset_time > config.RATE_LIMIT_WINDOW:
        st.session_state.request_count = 0
        st.session_state.last_reset_time = time.time()
    if st.session_state.request_count >= config.MAX_MESSAGE_LIMIT:
        mins = int((config.RATE_LIMIT_WINDOW - (time.time() - st.session_state.last_reset_time)) / 60)
        return False, f"🛑 Limit doldu. {mins} dakika sonra dene."
    return True, ""

# SEARCH
def calc_score(entry: Dict, query: str, keywords: List[str]) -> int:
    score = 0
    title = normalize(entry.get('baslik', ''))
    content = normalize(entry.get('icerik', ''))
    if query in title: score += 200
    elif query in content: score += 100
    for kw in keywords:
        if kw in title: score += 40
        elif kw in content: score += 10
    return score

def search_kb(query: str, db: List[Dict]) -> Tuple[List[Dict], str]:
    if not db or len(query) < config.MIN_SEARCH_LENGTH: return [], ""
    norm_q = normalize(query)
    kws = [k for k in norm_q.split() if len(k) > 2]
    results = []
    for e in db:
        sc = calc_score(e, norm_q, kws)
        if sc > config.SEARCH_SCORE_THRESHOLD:
            results.append({"baslik": e.get('baslik'), "link": e.get('link'), 
                          "icerik": e.get('icerik', '')[:config.MAX_CONTENT_LENGTH], "puan": sc})
    results.sort(key=lambda x: x['puan'], reverse=True)
    return results[:config.MAX_SEARCH_RESULTS], norm_q

def get_local(text: str) -> Optional[str]:
    n = normalize(text)
    if any(g == n for g in ["merhaba", "selam"]): return random.choice(["Aşk ile merhaba can.", "Selam olsun."])
    if any(q in n for q in ["nasilsin", "naber"]): return "Şükür Hak'ka, hizmetteyiz."
    return None

# AI
def build_prompt(query: str, sources: List[Dict], mode: str) -> str:
    ctx = ""
    if len(st.session_state.messages) > 1:
        ctx = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in st.session_state.messages[-6:]])
    
    turns = len(st.session_state.messages)
    greet = "İlk mesajda sıcak giriş yap." if turns <= 2 else "Selam verme, konuya gir."
    
    if "Sohbet" in mode:
        sys = (f"Sen Can Dede'sin. Alevi-Bektaşi rehberisin. İnsan-ı kâmil mertebesinde bir bilgesin.\n"
               f"KURALLAR:\n"
               f"1. Kullanıcı hangi dilde yazdıysa o dilde cevapla\n"
               f"2. 'Can', 'Dost' kullan, 'Evladım' yasak\n"
               f"3. Cevabı tam bitir, yarım bırakma\n"
               f"4. {greet}\n")
        src = ""
        if sources:
            src = "BİLGİ:\n" + "\n".join([f"- {s['baslik']}: {s['icerik'][:800]}" for s in sources[:3]]) + "\n\n"
        return f"{sys}\n\n{ctx}\n\n{src}Soru: {query}\nCan Dede:"
    else:
        if not sources: return None
        src = "\n".join([f"- {s['baslik']}: {s['icerik'][:1200]}" for s in sources[:3]])
        return f"YolPedia asistanısın. Kaynaklara göre özetle:\n{src}\n\nSoru: {query}"

def generate_response(query: str, sources: List[Dict], mode: str) -> Generator[str, None, None]:
    local = get_local(query)
    if local:
        time.sleep(0.3)
        yield local
        return
    
    prompt = build_prompt(query, sources, mode)
    if prompt is None:
        yield "📚 Kaynak bulamadım."
        return
    
    safety = {f"HARM_CATEGORY_{c}": "BLOCK_NONE" for c in ["HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT", "DANGEROUS_CONTENT"]}
    
    for idx, key in enumerate(API_KEYS, 1):
        try:
            genai.configure(api_key=key)
            for model in config.GEMINI_MODELS:
                try:
                    m = genai.GenerativeModel(model)
                    cfg = {"temperature": 0.8, "top_p": 0.95, "max_output_tokens": 2048}
                    resp = m.generate_content(prompt, stream=True, generation_config=cfg, safety_settings=safety)
                    has = False
                    for chunk in resp:
                        if chunk.text:
                            yield chunk.text
                            has = True
                    if has: return
                except Exception as e:
                    err = str(e)
                    if "429" in err or "quota" in err.lower(): break
                    if "404" in err: continue
                    continue
        except: continue
    
    yield "⚠️ Limit doldu. Biraz sonra dene."

# UI
def scroll():
    components.html('<script>window.parent.document.querySelector(".main").scrollTop=100000;</script>', height=0)

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
        if st.button("🗑️ Sıfırla"):
            st.session_state.messages = [{"role": "assistant", "content": "Sıfırlandı."}]
            st.session_state.request_count = 0
            st.rerun()
        st.divider()
        st.caption(f"📊 {config.MAX_MESSAGE_LIMIT - st.session_state.request_count}/{config.MAX_MESSAGE_LIMIT}")
    return mode

def render_sources(srcs):
    st.markdown("---\n**📚 Kaynaklar:**")
    for s in srcs[:3]: st.markdown(f"• [{s['baslik']}]({s['link']})")

# MAIN
def main():
    render_header()
    mode = render_sidebar()
    for m in st.session_state.messages:
        av = config.CAN_DEDE_ICON if m["role"] == "assistant" else config.USER_ICON
        st.chat_message(m["role"], avatar=av).markdown(m["content"])
    
    if inp := st.chat_input("Can Dede'ye sor..."):
        ok, err = validate_rate()
        if not ok:
            st.error(err)
            st.stop()
        st.session_state.request_count += 1
        st.session_state.messages.append({"role": "user", "content": inp})
        st.chat_message("user", avatar=config.USER_ICON).markdown(inp)
        scroll()
        
        srcs, _ = search_kb(inp, st.session_state.db)
        
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            ph = st.empty()
            full = ""
            for ch in generate_response(inp, srcs, mode):
                full += ch
                ph.markdown(full + "▌")
            ph.markdown(full)
            if srcs and "Araştırma" in mode: render_sources(srcs)
            st.session_state.messages.append({"role": "assistant", "content": full})
        scroll()

if __name__ == "__main__":
    main()
