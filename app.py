"""
YolPedia Can Dede - Production Ready
Gem-Perfect Integration + Best Practices
"""

import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import time
import random
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Generator
from pathlib import Path
from functools import lru_cache

# ===================== CONFIGURATION =====================

@dataclass
class AppConfig:
    """Application configuration with sensible defaults"""
    # Rate limiting
    MAX_MESSAGE_LIMIT: int = 30
    MIN_TIME_DELAY: int = 1
    RATE_LIMIT_WINDOW: int = 3600  # 1 hour
    
    # Search parameters
    MIN_SEARCH_LENGTH: int = 3
    MAX_CONTENT_LENGTH: int = 1500
    SEARCH_SCORE_THRESHOLD: int = 10  # Lowered from 20 to catch more results
    MAX_SEARCH_RESULTS: int = 5
    
    # File paths
    DATA_FILE: str = "yolpedia_data.json"
    
    # Branding
    ASSISTANT_NAME: str = "Can Dede | YolPedia Rehberiniz"
    MOTTO: str = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
    
    # Icons
    YOLPEDIA_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
    CAN_DEDE_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png"
    USER_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"
    
    # AI Models
    GEMINI_MODELS: List[str] = field(default_factory=lambda: [
        "gemini-2.0-flash-exp",  # Fastest, most stable
        "gemini-3-pro",          # Most powerful (premium)
        "gemini-2.5-pro"         # Reliable fallback
    ])
    
    # Stop words for search (excluding important terms)
    STOP_WORDS: List[str] = field(default_factory=lambda: [
        "ve", "veya", "ile", "bir", "bu", "su", "o", "icin", "hakkinda",
        "nedir", "kimdir", "nasil", "ne", "var", "mi", "mu",
        "bana", "soyle", "goster", "ver", "ilgili", "alakali",
        "lutfen", "merhaba", "selam"
        # Note: "can", "erenler" removed - they're important search terms!
    ])

config = AppConfig()

# ===================== LOGGING SETUP =====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ===================== PAGE CONFIGURATION =====================

st.set_page_config(
    page_title=config.ASSISTANT_NAME,
    page_icon=config.YOLPEDIA_ICON,
    layout="centered"
)

# ===================== API KEY MANAGEMENT =====================

def get_api_keys() -> List[str]:
    """Retrieve multiple API keys from secrets"""
    keys = []
    try:
        for key_name in ["API_KEY", "API_KEY_2", "API_KEY_3"]:
            key = st.secrets.get(key_name, "")
            if key:
                keys.append(key)
                logger.info(f"Loaded {key_name}")
    except Exception as e:
        logger.error(f"Failed to load API keys: {e}")
    
    return keys

API_KEYS = get_api_keys()

if not API_KEYS:
    st.error("⚠️ API anahtarı bulunamadı. Lütfen Streamlit secrets'ı kontrol edin.")
    st.stop()

logger.info(f"Initialized with {len(API_KEYS)} API key(s)")

# ===================== STYLING =====================

def apply_custom_styles():
    """Apply custom CSS styling"""
    st.markdown("""
    <style>
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
    </style>
    """, unsafe_allow_html=True)

apply_custom_styles()

# ===================== DATA LOADING =====================

@st.cache_data(persist="disk", show_spinner=False)
def load_knowledge_base() -> List[Dict]:
    """Load knowledge base from JSON with proper error handling"""
    try:
        file_path = Path(config.DATA_FILE)
        if not file_path.exists():
            logger.error(f"Data file not found: {config.DATA_FILE}")
            return []
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Loaded {len(data)} entries from knowledge base")
            return data
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading knowledge base: {e}")
        return []

# ===================== TEXT PROCESSING =====================

@lru_cache(maxsize=1000)
def normalize_turkish(text: str) -> str:
    """Normalize Turkish text for search - cached for performance"""
    if not isinstance(text, str):
        return ""
    
    # Turkish character mapping
    tr_map = str.maketrans(
        "ğĞüÜşŞıİöÖçÇâÂîÎûÛ",
        "gGuUsSiIoOcCaAiIuU"
    )
    
    return text.lower().translate(tr_map)

# ===================== SESSION STATE =====================

def init_session():
    """Initialize session state variables"""
    if 'db' not in st.session_state:
        st.session_state.db = load_knowledge_base()
    
    if 'messages' not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": (
                "Eyvallah, can dost! Ben Can Dede. "
                "Yolpedia.eu'nun Alevî-Bektaşî sohbet ve araştırma rehberinizim.\n\n"
                "Sol menüden istediğin modu seç:\n\n"
                "• **Sohbet Modu:** Birlikte yol üzerine muhabbet eder, gönül sohbeti yaparız.\n\n"
                "• **Araştırma Modu:** Yolpedia arşivinden kaynak ve bilgi ararım.\n\n"
                "Buyur erenler, hangi modda buluşalım? Aşk ile..."
            )
        }]
    
    if 'request_count' not in st.session_state:
        st.session_state.request_count = 0
    
    if 'last_reset_time' not in st.session_state:
        st.session_state.last_reset_time = time.time()
    
    if 'last_request_time' not in st.session_state:
        st.session_state.last_request_time = 0

init_session()

# ===================== RATE LIMITING =====================

def check_rate_limit() -> Tuple[bool, str]:
    """Validate rate limit with detailed feedback"""
    current_time = time.time()
    
    # Reset counter if window expired
    if current_time - st.session_state.last_reset_time > config.RATE_LIMIT_WINDOW:
        st.session_state.request_count = 0
        st.session_state.last_reset_time = current_time
        logger.info("Rate limit counter reset")
    
    # Check message limit
    if st.session_state.request_count >= config.MAX_MESSAGE_LIMIT:
        time_remaining = int(config.RATE_LIMIT_WINDOW - (current_time - st.session_state.last_reset_time))
        minutes = time_remaining // 60
        logger.warning(f"Rate limit hit: {st.session_state.request_count}/{config.MAX_MESSAGE_LIMIT}")
        return False, f"🛑 Mesaj limitine ulaştınız ({config.MAX_MESSAGE_LIMIT}/saat). {minutes} dakika sonra tekrar deneyin."
    
    # Check request frequency
    time_since_last = current_time - st.session_state.last_request_time
    if time_since_last < config.MIN_TIME_DELAY:
        return False, "⏳ Lütfen biraz bekleyin..."
    
    return True, ""

# ===================== SEARCH ENGINE =====================

def calculate_score(entry: Dict, query: str, keywords: List[str]) -> int:
    """Calculate relevance score for search result"""
    score = 0
    title = normalize_turkish(entry.get('baslik', ''))
    content = normalize_turkish(entry.get('icerik', ''))
    
    # Exact query match (highest priority)
    if query in title:
        score += 500  # Increased from 300
    elif query in content:
        score += 250  # Increased from 150
    
    # Check for multi-word phrases (e.g., "pir sultan")
    query_words = query.split()
    if len(query_words) > 1:
        # Bonus for all words appearing together
        if all(word in title for word in query_words):
            score += 300
        elif all(word in content for word in query_words):
            score += 150
    
    # Keyword matches
    for kw in keywords:
        if kw in title:
            score += 150  # Increased from 100
        elif kw in content:
            score += 60 if len(kw) > 3 else 30  # Increased scoring
    
    return score

def search_kb(query: str, db: List[Dict]) -> Tuple[List[Dict], str]:
    """Search knowledge base with optimized scoring"""
    if not db or len(query) < config.MIN_SEARCH_LENGTH:
        return [], ""
    
    norm_query = normalize_turkish(query)
    
    # More lenient keyword extraction - include shorter words for names
    keywords = [k for k in norm_query.split() 
                if len(k) > 1 and k not in config.STOP_WORDS]  # Changed from len(k) > 2
    
    if not keywords:
        return [], ""
    
    results = []
    for entry in db:
        score = calculate_score(entry, norm_query, keywords)
        
        if score > config.SEARCH_SCORE_THRESHOLD:
            results.append({
                "baslik": entry.get('baslik', 'Başlıksız'),
                "link": entry.get('link', '#'),
                "icerik": entry.get('icerik', '')[:config.MAX_CONTENT_LENGTH],
                "puan": score
            })
    
    results.sort(key=lambda x: x['puan'], reverse=True)
    top = results[:config.MAX_SEARCH_RESULTS]
    
    logger.info(f"Search '{query}' with keywords {keywords} returned {len(top)} results")
    return top, norm_query

# ===================== LOCAL RESPONSES =====================

def is_meaningful_query(text: str) -> bool:
    """Check if query is meaningful enough to search knowledge base"""
    norm = normalize_turkish(text).strip()
    words = norm.split()
    
    # Too short queries
    if len(words) < 2:
        return False
    
    # Greeting-only queries (no substance)
    greeting_only = ["merhaba", "selam", "slm", "gunaydin", "iyi aksamlar", 
                     "nasilsin", "naber", "hosgeldin", "selamun aleykum"]
    
    # Remove common address terms
    address_terms = ["dedem", "can", "dede", "abi", "hocam", "efendi"]
    
    # Filter out greetings and address terms
    meaningful_words = [w for w in words 
                       if w not in greeting_only and w not in address_terms 
                       and len(w) > 2]
    
    # If less than 2 meaningful words, not a real query
    if len(meaningful_words) < 2:
        return False
    
    # Check for question indicators
    question_words = ["nedir", "kimdir", "nasil", "neden", "nicin", "ne", "kim", 
                     "anlat", "acikla", "ogren", "bilgi", "sor"]
    
    has_question = any(qw in norm for qw in question_words)
    
    # If it has question words OR multiple meaningful words, it's a query
    return has_question or len(meaningful_words) >= 3

def get_local_response(text: str) -> Optional[str]:
    """Generate local response for common greetings - Gem style"""
    norm = normalize_turkish(text).strip()
    
    # Greeting keywords (partial match)
    greeting_keywords = ["merhaba", "selam", "slm", "selamun aleykum"]
    status_keywords = ["nasilsin", "naber", "ne var ne yok", "nasil gidiyor"]
    time_greetings = ["gunaydin", "iyi aksamlar", "iyi gunler", "iyi geceler"]
    
    # Check if any greeting keyword is in the text
    if any(kw in norm for kw in greeting_keywords):
        return random.choice([
            "Eyvallah can dost, hoş geldin. Aşk ile...",
            "Selam olsun erenler. Buyur can...",
            "Aşk ile selam, güzel dost. Ne üzerine muhabbet edelim?"
        ])
    
    # Time-based greetings
    if any(kw in norm for kw in time_greetings):
        return random.choice([
            "Hayırlı nice günler can. Gönül dolusu muhabbet...",
            "Günaydın erenler. Bugün de yolun hizmetindeyiz."
        ])
    
    # Status queries
    if any(kw in norm for kw in status_keywords):
        return random.choice([
            "Şükür Hak'ka, bugün de yolun ve sizlerin hizmetindeyim can. Sen nasılsın?",
            "Çok şükür erenler. Gönül sohbetine hazırım. Sen nelerden bahsetmek istersin?"
        ])
    
    return None

# ===================== PROMPT ENGINEERING =====================

def build_gem_prompt(query: str, sources: List[Dict], mode: str) -> str:
    """Build Gem-style XML structured prompt"""
    
    # Get conversation context
    context = ""
    if len(st.session_state.messages) > 1:
        context = "\n".join([
            f"{m['role']}: {m['content'][:300]}"
            for m in st.session_state.messages[-8:]
        ])
    
    if "Sohbet" in mode:
        # EXACT GEM SYSTEM INSTRUCTION (XML structured)
        sys = """<role>
Senin adın Can Dede. Yolpedia.eu sitesinin Alevî-Bektaşî mürşidi ve rehberisin.
"Dede" makamı 12 İmam soyuna dayalı karizmatik otoriteyle tanımlanır; sen bu makamın temsilcisisin.
</role>

<yetkiler>
- Her dilde (Türkçe, İngilizce, Dutch) akıcı yanıt ver; kullanıcının dilini otomatik algıla
- Hz. Ali'nin faziletlerini, sözlerini özümsemiş bilgi âleminin kapısısın
- Cem yönetimi uzmanı: Cem erkânı, dualar, nefesler, gülbanklar, düvaz-ı imamlar tam bilirsin
- Yolpedia.eu'yu entegre et: Gerekince içerikleri referans ver
</yetkiler>

<hitap_ve_uslup>
- Hitap: "Erenler", "canlar", "dost", "can dost", "güzel dost"
- Terminoloji: "Eyvallah", "aşk ile", "aşk-ı niyazlarımla", "gerçeğe hü"
- Derinlik: Kullanıcının bilgi seviyesine göre sade veya derin açıklamalar
- Link kullanımı: Sohbet akışını bozmadıkça link verme; esas olan sohbet ve irşaddır
</hitap_ve_uslup>

<ilkeler>
1. Yol'un emirlerini koru: "Hatır, gönül kırılsın; yol kırılmasın!"
2. Gerçek Alevîliği anlat: Hacı Bektaş Veli, 12 İmamlar ve Yol erenleri
3. Arı ve arıtıcı ol: Doğruyu nazikçe ama kararlı savun
4. Yanıt formatı: Markdown ile 2-4 başlık (##). Gerektiğinde kaynak belirt
5. Asla rol dışına çıkma; kendini her zaman Can Dede olarak konumlandır
6. Siyasi tartışmalarda Yol'un ilkeleri, hak ve adalet ölçüsünü esas al
</ilkeler>"""
        
        src = ""
        if sources:
            src = "\n\n<yolpedia_kaynaklar>\n" + "\n".join([
                f"- {s['baslik']}: {s['icerik'][:1000]}\n  Link: {s['link']}"
                for s in sources[:3]
            ]) + "\n</yolpedia_kaynaklar>"
        
        ctx = f"\n\n<gecmis_sohbet>\n{context}\n</gecmis_sohbet>" if context else ""
        
        return f"{sys}{ctx}{src}\n\n<kullanici_sorusu>\n{query}\n</kullanici_sorusu>\n\nCan Dede:"
        
    else:  # Research mode
        sys = """<role>
Sen Can Dede'sin, Yolpedia.eu araştırma modundasın.
</role>

<arastirma_kurallari>
1. Sadece Yolpedia.eu veritabanındaki kaynakları kullan
2. Halüsinasyon YOK: Bilmiyorsan "bilmiyorum" de
3. Kaynak yoksa: "Maalesef, sorduğunuz soru hakkında elimizde bilgi bulunmamaktadır."
4. Kaynak varsa:
   - Kısa özet (2-3 cümle, doğrudan konuya giren)
   - Yolpedia linklerini paylaş
   - Gereksiz muhabbet yok; odak: kaynak, özet, yönlendirme
5. "Nokta teslimat": Alakasız madde önerme
</arastirma_kurallari>"""
        
        if not sources:
            return None
        
        src = "\n\n<yolpedia_kaynaklar>\n" + "\n".join([
            f"- {s['baslik']}: {s['icerik'][:1200]}\n  Link: {s['link']}"
            for s in sources[:3]
        ]) + "\n</yolpedia_kaynaklar>"
        
        return f"{sys}{src}\n\n<soru>\n{query}\n</soru>\n\nCan Dede (Kısa özet + linkler):"

# ===================== AI RESPONSE GENERATION =====================

def generate_response(query: str, sources: List[Dict], mode: str) -> Generator[str, None, None]:
    """Generate AI response with multi-key fallback"""
    
    # CRITICAL: In research mode, NEVER use local response
    # Local responses are for casual chat only
    if "Sohbet" not in mode:
        # Research mode: skip local response entirely
        pass
    else:
        # Sohbet mode: check for local response
        local = get_local_response(query)
        if local:
            time.sleep(0.3)
            yield local
            return
    
    # Build prompt
    prompt = build_gem_prompt(query, sources, mode)
    
    if prompt is None:
        yield "📚 Maalesef, sorduğunuz konu hakkında Yolpedia.eu veritabanında kaynak bulunamadı."
        return
    
    # Safety settings
    safety = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    
    # Generation config (Gemini 3 best practices)
    gen_config = {
        "temperature": 0.7,          # Balanced creativity
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 4096,  # Long, detailed responses
        "candidate_count": 1,
    }
    
    # Try each API key
    for key_idx, key in enumerate(API_KEYS, 1):
        try:
            genai.configure(api_key=key)
            logger.info(f"Using API key #{key_idx}")
            
            # Try each model
            for model_name in config.GEMINI_MODELS:
                try:
                    logger.info(f"Trying model: {model_name}")
                    model = genai.GenerativeModel(model_name)
                    
                    response = model.generate_content(
                        prompt,
                        stream=True,
                        generation_config=gen_config,
                        safety_settings=safety
                    )
                    
                    has_content = False
                    for chunk in response:
                        if chunk.text:
                            yield chunk.text
                            has_content = True
                    
                    if has_content:
                        logger.info(f"✅ Success with {model_name}")
                        return
                        
                except Exception as e:
                    err = str(e)
                    logger.warning(f"Model {model_name} failed: {err[:100]}")
                    
                    # Quota error - try next key
                    if "429" in err or "quota" in err.lower():
                        logger.warning(f"Quota exceeded on key #{key_idx}")
                        break
                    
                    # Model not found - try next model
                    if "404" in err:
                        continue
                    
                    continue
                    
        except Exception as e:
            logger.error(f"Key #{key_idx} configuration failed: {e}")
            continue
    
    # All attempts failed
    logger.error("All API keys and models exhausted")
    yield "⚠️ Teknik bir sorun oluştu. Lütfen daha sonra tekrar deneyin."

# ===================== UI COMPONENTS =====================

def scroll_to_bottom():
    """Scroll chat to bottom"""
    components.html(
        """
        <script>
            setTimeout(() => {
                const main = window.parent.document.querySelector(".main");
                if (main) main.scrollTop = main.scrollHeight;
            }, 100);
        </script>
        """,
        height=0
    )

def render_header():
    """Render application header"""
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

def render_sidebar() -> str:
    """Render sidebar with mode selection"""
    with st.sidebar:
        st.title("Mod Seçimi")
        mode = st.radio(
            "Can Dede nasıl yardımcı olsun?",
            ["Sohbet Modu", "Araştırma Modu"]
        )
        
        if st.button("🗑️ Sohbeti Sıfırla"):
            st.session_state.messages = [{
                "role": "assistant",
                "content": (
                    "Eyvallah can, sohbet sıfırlandı. "
                    "Yeniden başlayalım. Hangi konuda muhabbet edelim?"
                )
            }]
            st.session_state.request_count = 0
            logger.info("Chat reset by user")
            st.rerun()
        
        st.divider()
        remaining = config.MAX_MESSAGE_LIMIT - st.session_state.request_count
        st.caption(f"📊 Kalan mesaj: {remaining}/{config.MAX_MESSAGE_LIMIT}")
        st.caption(f"🔑 API Keys: {len(API_KEYS)}")
        
        if 'db' in st.session_state:
            st.caption(f"💾 Arşiv: {len(st.session_state.db)} kaynak")
        
    return mode

def render_sources(sources: List[Dict]):
    """Render source links"""
    if not sources:
        return
    
    st.markdown("---")
    st.markdown("**📚 İlgili Kaynaklar:**")
    for s in sources[:3]:
        st.markdown(f"• [{s['baslik']}]({s['link']})")

# ===================== MAIN APPLICATION =====================

def main():
    """Main application loop"""
    render_header()
    mode = render_sidebar()
    
    # Display message history
    for msg in st.session_state.messages:
        avatar = config.CAN_DEDE_ICON if msg["role"] == "assistant" else config.USER_ICON
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
    
    # Handle user input
    if user_input := st.chat_input("Can Dede'ye sor..."):
        # Check rate limit
        ok, err_msg = check_rate_limit()
        if not ok:
            st.error(err_msg)
            st.stop()
        
        # Update counters
        st.session_state.request_count += 1
        st.session_state.last_request_time = time.time()
        
        # Add user message
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar=config.USER_ICON):
            st.markdown(user_input)
        
        scroll_to_bottom()
        
        # SMART QUERY ANALYSIS
        # Only search if it's a meaningful query, not just greetings
        sources = []
        if is_meaningful_query(user_input):
            sources, _ = search_kb(user_input, st.session_state.db)
            logger.info(f"Query analyzed as meaningful, found {len(sources)} sources")
        else:
            logger.info(f"Query analyzed as greeting/casual, skipping search")
        
        # Generate response
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            placeholder = st.empty()
            full_response = ""
            
            with st.spinner("Can Dede tefekkürde..."):
                for chunk in generate_response(user_input, sources, mode):
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
            
            placeholder.markdown(full_response)
            
            # Show sources in research mode ONLY if sources exist and it's not an error
            if sources and "Araştırma" in mode and "bulamadım" not in full_response.lower():
                render_sources(sources)
            
            # Save message
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response
            })
        
        scroll_to_bottom()

if __name__ == "__main__":
    main()
