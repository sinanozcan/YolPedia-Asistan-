"""
YolPedia Can Dede - Hata Ayıklama Versiyonu
"""

import streamlit as st
import streamlit.components.v1 as components
import json
import time
import random
import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Generator
from pathlib import Path

# Önce basit bir test
st.write("🔍 Uygulama başlatılıyor...")

@dataclass
class AppConfig:
    MAX_MESSAGE_LIMIT: int = 30
    MIN_TIME_DELAY: int = 1
    RATE_LIMIT_WINDOW: int = 3600
    MIN_SEARCH_LENGTH: int = 3
    MAX_CONTENT_LENGTH: int = 1500
    SEARCH_SCORE_THRESHOLD: int = 15
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
            self.GEMINI_MODELS = [
                "gemini-2.0-flash-exp",
                "gemini-exp-1206",
                "gemini-2.5-pro",
            ]

config = AppConfig()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title=config.ASSISTANT_NAME, 
    page_icon=config.YOLPEDIA_ICON, 
    layout="centered"
)

st.write("✅ Sayfa yapılandırması tamam")

# API KEYS - GELİŞTİRİLMİŞ
def get_api_keys() -> List[str]:
    """API keylerini yükle ve test et"""
    keys = []
    try:
        # Streamlit secrets'tan dene
        for key_name in ["API_KEY", "API_KEY_2", "API_KEY_3"]:
            k = st.secrets.get(key_name, "")
            if k and len(k) > 10:  # Geçerli bir key gibi görünüyor
                keys.append(k)
                logger.info(f"✅ {key_name} bulundu")
    except Exception as e:
        logger.warning(f"⚠️ Secrets okuma hatası: {e}")
    
    # Eğer secrets'ta yoksa environment'tan dene
    if not keys:
        import os
        for key_name in ["GEMINI_API_KEY", "API_KEY"]:
            k = os.environ.get(key_name, "")
            if k and len(k) > 10:
                keys.append(k)
                logger.info(f"✅ {key_name} environment'tan bulundu")
    
    return keys

st.write("🔑 API keyleri kontrol ediliyor...")
API_KEYS = get_api_keys()

if not API_KEYS:
    st.error("⚠️ API key bulunamadı!")
    st.info("""
    **API Key Nasıl Eklenir:**
    
    1. `.streamlit/secrets.toml` dosyası oluşturun
    2. İçine şunu ekleyin:
    ```toml
    API_KEY = "your-gemini-api-key-here"
    ```
    3. Uygulamayı yeniden başlatın
    
    Veya environment variable olarak:
    ```bash
    export GEMINI_API_KEY="your-key"
    streamlit run app.py
    ```
    """)
    st.stop()
else:
    st.success(f"✅ {len(API_KEYS)} API key bulundu")

# Gemini'yi import et
try:
    import google.generativeai as genai
    st.write("✅ Google Generative AI yüklendi")
except ImportError:
    st.error("❌ google-generativeai kütüphanesi yüklü değil!")
    st.code("pip install google-generativeai")
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

# DATA - GELİŞTİRİLMİŞ
@st.cache_data(persist="disk", show_spinner=False)
def load_kb() -> List[Dict]:
    """Veri tabanını yükle - hata kontrolü ile"""
    data_file = Path(config.DATA_FILE)
    
    if not data_file.exists():
        logger.warning(f"⚠️ Veri dosyası bulunamadı: {data_file}")
        st.warning(f"⚠️ Veri dosyası bulunamadı: {data_file}")
        st.info("Boş veri tabanı ile devam ediliyor. Sohbet modu kullanılabilir.")
        return []
    
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            logger.error("❌ Veri formatı hatalı")
            st.error("⚠️ Veri formatı hatalı - liste olmalı")
            return []
        
        logger.info(f"✅ {len(data)} kayıt yüklendi")
        return data
        
    except Exception as e:
        logger.error(f"❌ Veri yükleme hatası: {e}")
        st.error(f"⚠️ Veri yükleme hatası: {e}")
        return []

st.write("📚 Veri tabanı yükleniyor...")
db = load_kb()
st.write(f"✅ {len(db)} kayıt yüklendi")

def normalize(text: str) -> str:
    if not isinstance(text, str): return ""
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

# SESSION
def init_session():
    if 'db' not in st.session_state: 
        st.session_state.db = db
    if 'messages' not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant", 
            "content": "Merhaba Erenler! Sol menüden modunu seç:\n\n• **Sohbet Modu**\n• **Araştırma Modu**"
        }]
    if 'request_count' not in st.session_state: 
        st.session_state.request_count = 0
    if 'last_reset_time' not in st.session_state: 
        st.session_state.last_reset_time = time.time()

init_session()
st.write("✅ Session başlatıldı")

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
        elif kw in content: score += 20
    return score

def search_kb(query: str, db: List[Dict]) -> Tuple[List[Dict], str]:
    if not db or len(query) < config.MIN_SEARCH_LENGTH: 
        return [], ""
    norm_q = normalize(query)
    kws = [k for k in norm_q.split() if len(k) > 2]
    results = []
    for e in db:
        sc = calc_score(e, norm_q, kws)
        if sc > config.SEARCH_SCORE_THRESHOLD:
            results.append({
                "baslik": e.get('baslik'), 
                "link": e.get('link'), 
                "icerik": e.get('icerik', '')[:config.MAX_CONTENT_LENGTH], 
                "puan": sc
            })
    results.sort(key=lambda x: x['puan'], reverse=True)
    logger.info(f"🔍 '{query}' için {len(results)} sonuç bulundu")
    return results[:config.MAX_SEARCH_RESULTS], norm_q

def get_local(text: str) -> Optional[str]:
    n = normalize(text)
    if any(g == n for g in ["merhaba", "selam"]): 
        return random.choice(["Merhaba Erenler! Hoş gelmiş!", "Selam Erenler, hoş geldin!"])
    if any(q in n for q in ["nasilsin", "naber"]): 
        return "Çok şükür erenler, bugün de yolun hizmetindeyiz."
    return None

# AI
def build_prompt(query: str, sources: List[Dict], mode: str) -> str:
    ctx = ""
    if len(st.session_state.messages) > 1:
        ctx = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in st.session_state.messages[-6:]])
    
    if "Sohbet" in mode:
        sys = (
            "Sen Can Dede'sin. Alevi-Bektaşilerin rehberi, bilge bir dede.\n"
            "Konuşmacı hangi dilde konuşuyorsa o dilde cevap ver.\n"
            "'Erenler', 'Sevgili Can', 'Canlar' gibi hitaplar kullan.\n"
            "Seküler, bilim ve hikmete dayalı cevaplar ver.\n"
            "Tekrarlardan kaçın, doğal konuş."
        )
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
        yield "📚 Maalesef kaynak bulunamadı. Sohbet modunu deneyin."
        return
    
    safety = {f"HARM_CATEGORY_{c}": "BLOCK_NONE" for c in 
              ["HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT", "DANGEROUS_CONTENT"]}
    
    for idx, key in enumerate(API_KEYS, 1):
        try:
            genai.configure(api_key=key)
            for model in config.GEMINI_MODELS:
                try:
                    m = genai.GenerativeModel(model)
                    cfg = {
                        "temperature": 0.7,
                        "top_p": 0.95,
                        "top_k": 40,
                        "max_output_tokens": 4096,
                        "candidate_count": 1,
                    }
                    resp = m.generate_content(prompt, stream=True, generation_config=cfg, safety_settings=safety)
                    has = False
                    for chunk in resp:
                        if chunk.text:
                            yield chunk.text
                            has = True
                    if has: return
                except Exception as e:
                    err = str(e)
                    logger.warning(f"Model {model} hatası: {err[:100]}")
                    if "429" in err or "quota" in err.lower(): break
                    if "404" in err: continue
                    continue
        except Exception as e:
            logger.error(f"Key {idx} hatası: {e}")
            continue
    
    yield "⚠️ Limit doldu veya model erişilemiyor. Biraz sonra dene."

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
        
        # Debug bilgisi
        st.divider()
        db_count = len(st.session_state.db)
        if db_count > 0:
            st.success(f"✅ Veri: {db_count} kayıt")
        else:
            st.warning("⚠️ Veri tabanı boş")
            st.info("Sohbet modu kullanılabilir")
        
        if st.button("🗑️ Sıfırla"):
            st.session_state.messages = [{"role": "assistant", "content": "Sıfırlandı."}]
            st.session_state.request_count = 0
            st.rerun()
        
        st.divider()
        st.caption(f"📊 {config.MAX_MESSAGE_LIMIT - st.session_state.request_count}/{config.MAX_MESSAGE_LIMIT}")
        st.caption(f"🔑 Keys: {len(API_KEYS)}")
    return mode

def render_sources(srcs):
    st.markdown("---\n**📚 Kaynaklar:**")
    for s in srcs[:3]: 
        st.markdown(f"• [{s['baslik']}]({s['link']})")

# MAIN
def main():
    st.write("🎨 Ana sayfa render ediliyor...")
    
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
            if srcs and "Araştırma" in mode: 
                render_sources(srcs)
            st.session_state.messages.append({"role": "assistant", "content": full})
        scroll()
    
    st.write("✅ Sayfa tamamen yüklendi")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"❌ HATA: {e}")
        import traceback
        st.code(traceback.format_exc())
