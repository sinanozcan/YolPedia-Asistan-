"""
YolPedia Can Dede - AI Assistant
Final Working Version - Gemini 2.5 + Multi API Key + Update Button
"""

import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
import json
import time
import random
import logging
import requests
import re
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
            "Merhaba Erenler! Sol menüden modunu seç:\n\n• **Sohbet Modu**\n• **Araştırma Modu**"}]
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
        elif kw in content: score += 20
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
    if any(g == n for g in ["merhaba", "selam"]): return random.choice(["Merhaba Erenler! Hoş gelmiş!", "Selam Erenler, hoş geldin!"])
    if any(q in n for q in ["nasilsin", "naber"]): return "Çok şükür erenler, bugün de yolun hizmetindeyiz."
    return None

# AI
def build_prompt(query: str, sources: List[Dict], mode: str) -> str:
    ctx = ""
    if len(st.session_state.messages) > 1:
        ctx = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in st.session_state.messages[-6:]])
    
    turns = len(st.session_state.messages)
    greet = "İlk mesajında sıcak bir giriş yap." if turns <= 2 else "Selam verme, konuya gir."
    
    if "Sohbet" in mode:
        sys = (
            "Sen Can Dede'sin. Dede olman yaşınla alakali bir durum değil. Sahip olduğun dedelik makamından dolayı dedesin. Alevi-Bektaşilerin hem rehberi, hem piri, hem de insan-ı kâmil mertebesine ulaşmış bilge bir dedesisin."
            "Konuşmacı sana hangi dilde konuşuyorsa, direkt o dilde karşılık vereceksin. Tüm hitaplarını da yine o dilde yapacaksın. Veri tabanın Türkçe de olsa, yine de konuşmacının kendi dilinde cevap vereceksin."
            "Konuşmaların arasında yeri geldikçe 'Erenler (bu ikinci tekil şahıs da olabilir, üçüncü çoğul şahıs da)', 'Sevgili Can', 'Sevgili Dost', 'Canlar' gibi hitaplara başvurabilirsin. Bu hitaplardan sonra konuşmana yeni bir paragrafta başla."
            "Konuşmalarında 'canım', 'evladım', 'evlat' gibi ifadelere kesinlikle yer vermiyorsun."
            "Araştırma modundayken başvuracağın tek kaynak veri tabanında yer alan bilgiler olacaktır. Oradan hariç hiçbir şeyi kaynak olarak sunmuyorsun. Sohbet modundayken de ilk önce kendi veri tabanını gözden geçiriyorsun, oradan sonuç alamazsan gemini 3.0 pro'nun dil modelinden faydalanıyorsun." 
            "'Hatır, gönül kırılsın, yol kırılmasın!' düsturuyla hareket ediyorsun ancak gerekli gereksiz her yerde bunu dillendirmiyorsun. Manüpilasyonlara izin vermiyorsun. Yola uygun olmayan hiçbir söz ve davranışı onaylamıyorsun."
            "Dini referanslar vermek yerine daha çok bilim, irfan ve hikmete dayalı, gerektiğinde bâtıni, ama daha çok seküler ağırlıklı cevaplar vermeyi tercih ediyorsun."
            "Aynı sohbet içinde tekrarlara girmekten kaçın. Sürekli selam vermene, merhaba demene gerek yok. Baştan verdiysen yeterli. Doğal ve akıcı bir üslupla konuşmayı sürdür."
            "Konuşmaların okuyucuya ilham versin"
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
        yield "📚 Maalesef, kaynak bulunamadı!."
        return
    
    safety = {f"HARM_CATEGORY_{c}": "BLOCK_NONE" for c in ["HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT", "DANGEROUS_CONTENT"]}
    
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
                    if "429" in err or "quota" in err.lower(): break
                    if "404" in err: continue
                    continue
        except: continue
    
    yield "⚠️ Limit doldu. Biraz sonra dene."

# ========== YENİ EKLENEN FONKSİYON ==========
def update_database_from_yolpedia() -> int:
    """YolPedia'dan tüm verileri çek (posts + pages) ve güncelle"""
    def temizle_html(html_text: str) -> str:
        text = re.sub('<[^<]+?>', '', html_text)
        text = text.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&amp;', '&').replace('&#8217;', "'")
        return re.sub(r'\s+', ' ', text).strip()
    
    def fetch_content(endpoint: str) -> List[Dict]:
        """Belirli bir endpoint'ten tüm içeriği çek"""
        items = []
        for page in range(1, 25):
            try:
                resp = requests.get(
                    f"https://yolpedia.eu/wp-json/wp/v2/{endpoint}",
                    params={'per_page': 100, 'page': page, '_embed': 1},
                    timeout=30,
                    headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
                )
                if resp.status_code == 200:
                    content = resp.json()
                    if not content: break
                    items.extend(content)
                else: break
            except: break
        return items
    
    # Hem posts hem pages çek
    all_posts = fetch_content('posts')
    all_pages = fetch_content('pages')
    all_content = all_posts + all_pages
    
    if all_content:
        data = []
        for item in all_content:
            title = temizle_html(item.get('title', {}).get('rendered', ''))
            content = temizle_html(item.get('content', {}).get('rendered', ''))
            data.append({
                'baslik': title,
                'link': item.get('link', ''),
                'icerik': content[:5000]
            })
        
        with open(Path(config.DATA_FILE), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return len(data)
    return 0
# ========== YENİ FONKSİYON BİTTİ ==========

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

# ========== SIDEBAR GÜNCELLENDİ (SADECE BUTON EKLENDİ) ==========
def render_sidebar():
    with st.sidebar:
        st.title("Mod Seçimi")
        mode = st.radio("Seçim", ["Sohbet Modu", "Araştırma Modu"])
        
        st.divider()
        
        # YENİ: Güncelleme butonu
        if st.button("🔄 Veri Tabanını Güncelle", use_container_width=True):
            with st.spinner("🌐 YolPedia'dan veriler çekiliyor..."):
                count = update_database_from_yolpedia()
                if count > 0:
                    # Cache'i temizle ve yeniden yükle
                    load_kb.clear()
                    st.session_state.db = load_kb()
                    st.success(f"✅ {count} kayıt güncellendi!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Güncelleme başarısız. Tekrar deneyin.")
        
        if st.button("🗑️ Sıfırla", use_container_width=True):
            st.session_state.messages = [{"role": "assistant", "content": "Sıfırlandı."}]
            st.session_state.request_count = 0
            st.rerun()
        
        st.divider()
        st.caption(f"📊 {config.MAX_MESSAGE_LIMIT - st.session_state.request_count}/{config.MAX_MESSAGE_LIMIT}")
        st.caption(f"📚 Kayıt: {len(st.session_state.db)}")
        st.caption(f"🔑 Keys: {len(API_KEYS)}")
    return mode
# ========== SIDEBAR GÜNCELLEMESİ BİTTİ ==========

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
