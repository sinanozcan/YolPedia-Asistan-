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
# Geliştirilmiş Arama Algoritması - Can Dede için

from typing import List, Dict, Tuple
import re

def normalize(text: str) -> str:
    """Türkçe karakterleri normalize et"""
    if not isinstance(text, str): 
        return ""
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

def extract_keywords(query: str, min_length: int = 3) -> List[str]:
    """
    Daha akıllı keyword çıkarma
    - Stop words'leri filtrele
    - Minimum uzunluk kontrolü
    """
    # Türkçe stop words
    stop_words = {
        'bir', 'bu', 'şu', 've', 'ile', 'için', 'mi', 'mu', 'mı', 'mü',
        'da', 'de', 'ta', 'te', 'ki', 'dır', 'dir', 'tir', 'tır',
        'olan', 'olan', 'ne', 'nasıl', 'neden', 'niye', 'hakkında'
    }
    
    norm_query = normalize(query)
    words = norm_query.split()
    
    # Stop words ve kısa kelimeleri filtrele
    keywords = [w for w in words if len(w) >= min_length and w not in stop_words]
    
    return keywords

def calc_score_advanced(entry: Dict, query: str, keywords: List[str]) -> int:
    """
    Geliştirilmiş skor hesaplama
    - Tam eşleşmeye daha yüksek puan
    - Kelime sırasına önem ver
    - Başlıkta birden fazla kelime varsa bonus
    """
    score = 0
    title = normalize(entry.get('baslik', ''))
    content = normalize(entry.get('icerik', ''))
    norm_query = normalize(query)
    
    # 1. TAM SORGU EŞLEŞMESİ (en yüksek öncelik)
    if norm_query in title:
        score += 500  # Çok yüksek puan
    elif norm_query in content:
        score += 250
    
    # 2. TÜM KELİMELER BAŞLIKTA VAR MI? (çok önemli)
    if keywords:
        title_word_count = sum(1 for kw in keywords if kw in title)
        if title_word_count == len(keywords):
            score += 300  # Tüm kelimeler başlıkta
        elif title_word_count > 0:
            score += 100 * title_word_count  # Kısmi eşleşme
    
    # 3. KELİME SIRASI KORUNUYOR MU? (yakınlık bonusu)
    if len(keywords) >= 2:
        # İlk iki kelimenin ardışık olup olmadığını kontrol et
        phrase = ' '.join(keywords[:2])
        if phrase in title:
            score += 150  # Kelimeler yan yana
        elif phrase in content:
            score += 75
    
    # 4. BİREYSEL KELİME EŞLEŞMELERİ (düşük puan)
    for kw in keywords:
        if kw in title:
            score += 30  # Azaltıldı (önceden 40)
        elif kw in content:
            score += 10  # Azaltıldı (önceden 20)
    
    return score

def search_kb_advanced(query: str, db: List[Dict], 
                       threshold: int = 50,  # Eşik artırıldı
                       max_results: int = 5) -> Tuple[List[Dict], str]:
    """
    Geliştirilmiş arama fonksiyonu
    
    Args:
        query: Kullanıcı sorgusu
        db: Veri tabanı
        threshold: Minimum skor eşiği (artırıldı: 15 → 50)
        max_results: Maksimum sonuç sayısı
    
    Returns:
        (sonuçlar, normalize edilmiş sorgu)
    """
    if not db or len(query) < 3:
        return [], ""
    
    norm_query = normalize(query)
    keywords = extract_keywords(query)
    
    # Hiç keyword yoksa, sorguyu tek keyword olarak kullan
    if not keywords:
        keywords = [norm_query]
    
    results = []
    for entry in db:
        score = calc_score_advanced(entry, query, keywords)
        
        if score >= threshold:
            results.append({
                "baslik": entry.get('baslik'),
                "link": entry.get('link'),
                "icerik": entry.get('icerik', '')[:1500],
                "puan": score
            })
    
    # Puana göre sırala
    results.sort(key=lambda x: x['puan'], reverse=True)
    
    return results[:max_results], norm_query


# =====================================================
# KULLANIM ÖRNEĞİ - TEST
# =====================================================

if __name__ == "__main__":
    # Test veri seti
    test_db = [
        {
            "baslik": "Malatya Katliamı (1978)",
            "link": "https://yolpedia.eu/malatya-katliami",
            "icerik": "1978 yılında Malatya'da gerçekleşen katliam..."
        },
        {
            "baslik": "Maraş Katliamı",
            "link": "https://yolpedia.eu/maras-katliami",
            "icerik": "Kahramanmaraş'ta yaşanan olaylar..."
        },
        {
            "baslik": "Pir Sultan Abdal - Malatya'da Doğan Ermiş",
            "link": "https://yolpedia.eu/pir-sultan",
            "icerik": "Malatya yöresinde yaşayan Pir Sultan..."
        },
        {
            "baslik": "Çorum Katliamı",
            "link": "https://yolpedia.eu/corum",
            "icerik": "1980 yılında Çorum'da yaşanan olaylar..."
        }
    ]
    
    # Test sorguları
    queries = [
        "Malatya Katliamı",
        "Malatya katliamı nedir",
        "1978 olayları"
    ]
    
    print("=" * 60)
    print("ARAMA SONUÇLARI TESTİ")
    print("=" * 60)
    
    for query in queries:
        print(f"\n📍 Sorgu: '{query}'")
        print("-" * 60)
        
        results, _ = search_kb_advanced(query, test_db, threshold=50)
        
        if results:
            for i, r in enumerate(results, 1):
                print(f"{i}. [{r['puan']} puan] {r['baslik']}")
        else:
            print("❌ Sonuç bulunamadı")
    
    print("\n" + "=" * 60)
    print("SKOR DETAYLARI")
    print("=" * 60)
    
    # Detaylı skor analizi
    query = "Malatya Katliamı"
    keywords = extract_keywords(query)
    print(f"\nSorgu: '{query}'")
    print(f"Keywords: {keywords}")
    print("\nHer kayıt için skor:")
    
    for entry in test_db:
        score = calc_score_advanced(entry, query, keywords)
        print(f"  • {entry['baslik']}: {score} puan")

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
        st.caption(f"🔑 Keys: {len(API_KEYS)}")
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
