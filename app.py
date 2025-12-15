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
import unicodedata
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Generator
from pathlib import Path

# ===================== CONFIGURATION =====================

@dataclass
class AppConfig:
    """Application configuration constants"""
    MAX_MESSAGE_LIMIT: int = 30
    MIN_TIME_DELAY: int = 1
    RATE_LIMIT_WINDOW: int = 3600
    
    MIN_SEARCH_LENGTH: int = 3
    MAX_CONTENT_LENGTH: int = 1500
    
    # Eşik değeri
    SEARCH_SCORE_THRESHOLD: int = 30
    MAX_SEARCH_RESULTS: int = 5
    
    DATA_FILE: str = "yolpedia_data.json"
    ASSISTANT_NAME: str = "Can Dede | YolPedia Rehberiniz"
    MOTTO: str = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
    
    YOLPEDIA_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
    CAN_DEDE_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png"
    USER_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"
    
    GEMINI_MODELS: List[str] = None
    
    # GÜNCELLEME: Stop Words Listesi Genişletildi
    # Kullanıcının sohbet ederken kurduğu "bilgi almak istiyorum" gibi cümleleri temizliyoruz.
    STOP_WORDS: List[str] = field(default_factory=lambda: [
        "ve", "veya", "ile", "bir", "bu", "su", "o", "icin", "hakkinda", 
        "kaynak", "kaynaklar", "ariyorum", "nedir", "kimdir", "nasil", 
        "ne", "var", "mi", "mu", "bana", "soyle", "goster", "ver", 
        "ilgili", "alakali", "yazi", "belge", "kitap", "makale", "soz", 
        "lutfen", "merhaba", "selam", "dedem", "can", "erenler", "konusunda", 
        "istiyorum", "elinde", "okur", "musun", "bul", "getir",
        "bilgi", "almak", "edinmek", "ogrenmek", "hakkindaki", "hakkindaki"
    ])
    
    def __post_init__(self):
        if self.GEMINI_MODELS is None:
            self.GEMINI_MODELS = [
                "gemini-1.5-flash",          
                "gemini-1.5-flash-latest",   
                "gemini-2.0-flash-exp",      
            ]

config = AppConfig()

# ===================== LOGGING SETUP =====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===================== PAGE CONFIGURATION =====================

st.set_page_config(
    page_title=config.ASSISTANT_NAME,
    page_icon=config.YOLPEDIA_ICON,
    layout="centered"
)

# ===================== API KEY VALIDATION =====================

def get_api_keys() -> List[str]:
    """Retrieve and validate multiple API keys from secrets"""
    api_keys = []
    try:
        primary_key = st.secrets.get("API_KEY", "")
        if primary_key:
            api_keys.append(primary_key)
        
        secondary_key = st.secrets.get("API_KEY_2", "")
        if secondary_key:
            api_keys.append(secondary_key)
            
        third_key = st.secrets.get("API_KEY_3", "")
        if third_key:
            api_keys.append(third_key)
        
        if not api_keys:
            logger.error("No API keys found")
            return []
        
        logger.info(f"Loaded {len(api_keys)} API key(s)")
        return api_keys
        
    except Exception as e:
        logger.error(f"Failed to retrieve API keys: {e}")
        return []

GOOGLE_API_KEYS = get_api_keys()

if not GOOGLE_API_KEYS:
    st.error("⚠️ API anahtarı bulunamadı. Lütfen Streamlit secrets'ı kontrol edin.")
    st.stop()

# ===================== STYLING =====================

def apply_custom_styles():
    """Apply custom CSS styles"""
    st.markdown("""
    <style>
        .stChatMessage {
            margin-bottom: 10px;
        }
        .stSpinner > div {
            border-top-color: #ff4b4b !important;
        }
        .block-container {
            padding-top: 2rem;
        }
        h1 {
            line-height: 1.2 !important;
        }
    </style>
    """, unsafe_allow_html=True)

apply_custom_styles()

# ===================== DATA LOADING =====================

@st.cache_data(persist="disk", show_spinner=False)
def load_knowledge_base() -> List[Dict]:
    """Load knowledge base from JSON file with proper error handling"""
    try:
        file_path = Path(config.DATA_FILE)
        if not file_path.exists():
            logger.error(f"Data file not found: {config.DATA_FILE}")
            st.error(f"❌ Veri dosyası bulunamadı: {config.DATA_FILE}")
            return []
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Successfully loaded {len(data)} entries from knowledge base")
            return data
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        st.error(f"❌ JSON formatı hatalı: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading data: {e}")
        st.error(f"❌ Veri yüklenirken beklenmeyen hata: {e}")
        return []

# ===================== TEXT PROCESSING (UNICODE NORMALIZATION) =====================

def normalize_turkish_text(text: str) -> str:
    """
    Profesyonel Normalizasyon: Unicode NFKD yöntemi ile tüm şapkaları ve işaretleri söker.
    """
    if not isinstance(text, str):
        return ""
    
    text = text.lower()
    
    # Türkçe özel karakterleri manuel düzelt
    replacements = {
        "ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c",
        "İ": "i", "Ğ": "g", "Ü": "u", "Ş": "s", "Ö": "o", "Ç": "c"
    }
    for src, dest in replacements.items():
        text = text.replace(src, dest)
    
    # Unicode Normalizasyonu
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    
    return text

# ===================== SESSION STATE INITIALIZATION =====================

def initialize_session_state():
    """Initialize all session state variables"""
    if 'db' not in st.session_state:
        st.session_state.db = load_knowledge_base()
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": (
                "Merhaba, Can Dost! Ben Can Dede. Sol menüden istediğin modu seç:\n\n"
                "• **Sohbet Modu:** Birlikte yol üzerine konuşuruz, gönül muhabbeti ederiz.\n\n"
                "• **Araştırma Modu:** YolPedia arşivinden sana kaynak sunarım.\n\n"
                "Buyur Erenler, hangi modda buluşalım?"
            )
        }]
    
    if 'request_count' not in st.session_state:
        st.session_state.request_count = 0
    
    if 'last_reset_time' not in st.session_state:
        st.session_state.last_reset_time = time.time()
    
    if 'last_request_time' not in st.session_state:
        st.session_state.last_request_time = 0

initialize_session_state()

# ===================== RATE LIMITING =====================

def check_and_reset_rate_limit():
    """Check if rate limit window has expired and reset if needed"""
    current_time = time.time()
    if current_time - st.session_state.last_reset_time > config.RATE_LIMIT_WINDOW:
        st.session_state.request_count = 0
        st.session_state.last_reset_time = current_time
        logger.info("Rate limit counter reset")

def validate_rate_limit() -> Tuple[bool, str]:
    """Validate if user can make another request"""
    check_and_reset_rate_limit()
    
    if st.session_state.request_count >= config.MAX_MESSAGE_LIMIT:
        logger.warning(f"Rate limit exceeded: {st.session_state.request_count}")
        time_until_reset = int(config.RATE_LIMIT_WINDOW - (time.time() - st.session_state.last_reset_time))
        minutes = time_until_reset // 60
        return False, f"🛑 Mesaj limitine ulaştınız ({config.MAX_MESSAGE_LIMIT} mesaj/saat). {minutes} dakika sonra tekrar deneyin."
    
    time_since_last = time.time() - st.session_state.last_request_time
    if time_since_last < config.MIN_TIME_DELAY:
        return False, "⏳ Lütfen biraz yavaşlayın, can..."
    
    return True, ""

# ===================== SEARCH ENGINE =====================

def calculate_relevance_score(entry: Dict, normalized_query: str, keywords: List[str]) -> int:
    """Calculate relevance score for a knowledge base entry"""
    score = 0
    
    normalized_title = normalize_turkish_text(entry.get('baslik', ''))
    normalized_content = normalize_turkish_text(entry.get('icerik', ''))
    
    if normalized_query in normalized_title:
        score += 200
    elif normalized_query in normalized_content:
        score += 80 
    
    for keyword in keywords:
        if keyword in normalized_title:
            score += 100 
        elif keyword in normalized_content:
            score += 5 
    
    special_terms = ["gulbank", "deyis", "nefes", "siir"]
    if any(term in normalized_title for term in special_terms):
        score += 300
    
    return score

def search_knowledge_base(query: str, db: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """Search knowledge base for relevant content with STOP WORDS filtering"""
    if not db or not query or len(query) < config.MIN_SEARCH_LENGTH:
        return [], []
    
    normalized_query = normalize_turkish_text(query)
    
    # Stop Words listesindeki kelimeleri çıkartıyoruz
    keywords = [
        k for k in normalized_query.split() 
        if len(k) > 2 and k not in config.STOP_WORDS
    ]
    
    if not keywords:
        return [], []
        
    results = []
    for entry in db:
        score = calculate_relevance_score(entry, normalized_query, keywords)
        
        if score > config.SEARCH_SCORE_THRESHOLD:
            results.append({
                "baslik": entry.get('baslik', 'Başlıksız'),
                "link": entry.get('link', '#'),
                "icerik": entry.get('icerik', '')[:config.MAX_CONTENT_LENGTH],
                "puan": score
            })
    
    results.sort(key=lambda x: x['puan'], reverse=True)
    top_results = results[:config.MAX_SEARCH_RESULTS]
    
    logger.info(f"Search for '{query}' returned {len(top_results)} results. Keywords: {keywords}")
    return top_results, keywords

# ===================== LOCAL RESPONSE HANDLER =====================

def get_local_response(text: str) -> Optional[str]:
    """Check if query can be answered with predefined local responses"""
    normalized = normalize_turkish_text(text)
    
    greetings = ["merhaba", "selam", "selamun aleykum", "gunaydin"]
    status_queries = ["nasilsin", "naber", "ne var ne yok"]
    
    if any(g in normalized for g in greetings):
         return random.choice([
            "Aşk ile, merhaba güzel can.",
            "Selam olsun. Hoş geldin, sevgili dost.",
            "Hoş geldin, can dost."
        ])
    
    if any(q in normalized for q in status_queries):
        return "Şükür Hak'ka, yolun hizmetindeyiz erenler."
    
    return None

# ===================== AI RESPONSE GENERATOR =====================

def build_prompt(user_query: str, sources: List[Dict], mode: str) -> str:
    """Build the prompt for the AI model"""
    system_instruction = (
        "Sen 'Can Dede'sin. Alevi-Bektaşi felsefesini benimsemiş, insan-ı kâmil bir rehbersin. "
        "Üslubun 'Aşk ile', 'Can', 'Erenler' şeklinde samimi ve sıcak olsun."
    )
    
    if "Sohbet" in mode:
        if sources:
            source_text = "\n".join([
                f"- {src['baslik']}: {src['icerik']}"
                for src in sources[:2]
            ])
            return (
                f"{system_instruction}\n\n"
                f"KAYNAKLAR (Bunları kullanarak cevapla):\n{source_text}\n\n"
                f"Kullanıcı: {user_query}"
            )
        else:
            return f"{system_instruction}\n\nKullanıcı: {user_query}"
            
    else:  # Research mode
        if not sources:
            return None
        
        source_text = "\n".join([
            f"- {src['baslik']}: {src['icerik'][:800]}"
            for src in sources[:3]
        ])
        return (
            f"Sen YolPedia asistanısın. Aşağıdaki KAYNAKLARI kullanarak kullanıcının sorusunu cevapla.\n"
            f"Kaynaklarda konuyla ilgili bilgi varsa özetle ve kullanıcıya aktar.\n"
            f"KAYNAKLAR:\n{source_text}\n\n"
            f"Soru: {user_query}"
        )

def generate_ai_response(
    user_query: str,
    sources: List[Dict],
    mode: str
) -> Generator[str, None, None]:
    """
    Generate AI response using Google Gemini API with VISIBLE robust key rotation.
    """
    
    local_response = get_local_response(user_query)
    if local_response:
        time.sleep(0.5)
        yield local_response
        return
    
    if "Araştırma" in mode and not sources:
        yield "📚 Üzgünüm can, YolPedia arşivinde bu konuyla ilgili yeterli kaynak bulunamadı. Başka bir konuda yardımcı olabilir miyim?"
        return

    prompt = build_prompt(user_query, sources, mode)
    if prompt is None:
        yield "📚 Aradığın konuyla ilgili kaynak bulamadım can."
        return
    
    success = False
    last_error_details = ""
    status_box = st.empty()

    for key_index, current_api_key in enumerate(GOOGLE_API_KEYS):
        
        if success:
            break
            
        try:
            genai.configure(api_key=current_api_key)
            
            for model_name in config.GEMINI_MODELS:
                try:
                    model = genai.GenerativeModel(model_name)
                    generation_config = {
                        "temperature": 0.3,
                        "max_output_tokens": 1500,
                    }
                    
                    response = model.generate_content(
                        prompt, 
                        stream=True,
                        generation_config=generation_config
                    )
                    
                    has_content = False
                    for chunk in response:
                        if chunk.text:
                            status_box.empty()
                            yield chunk.text
                            has_content = True
                    
                    if has_content:
                        success = True
                        break 
                        
                except Exception as model_error:
                    error_msg = str(model_error).lower()
                    
                    if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                        time.sleep(1)
                        last_error_details = f"Anahtar {key_index+1} Kotası Dolu (429)"
                        break 
                    
                    logger.warning(f"Model hatası: {model_name} -> {model_error}")
                    continue

        except Exception as key_error:
            last_error_details = str(key_error)
            continue
            
    if not success:
        status_box.error("❌ Tüm denemeler başarısız oldu.")
        yield f"⚠️ Can dost, elimdeki {len(GOOGLE_API_KEYS)} farklı anahtarın hepsini denedim ama Google kapıları kapalı tutuyor. \n\n**Son Hata Detayı:** {last_error_details}\n\nLütfen 2-3 dakika bekleyip tekrar dene."
    else:
        status_box.empty()

# ===================== UI HELPER FUNCTIONS =====================

def scroll_to_bottom():
    """Scroll chat to bottom using JavaScript"""
    components.html(
        """
        <script>
            window.parent.document.querySelector(".main").scrollTop = 100000;
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
    """Render sidebar and return selected mode"""
    with st.sidebar:
        st.title("Mod Seçimi")
        selected_mode = st.radio(
            "Can Dede nasıl yardımcı olsun?",
            ["Sohbet Modu", "Araştırma Modu"]
        )
        
        if st.button("🗑️ Sohbeti Sıfırla"):
            st.session_state.messages = [{
                "role": "assistant",
                "content": "Sohbet sıfırlandı. Buyur can. Sendeyim yine."
            }]
            st.session_state.request_count = 0
            logger.info("Chat history reset by user")
            st.rerun()
        
        st.divider()
        st.caption(f"📊 Mesaj: {st.session_state.request_count}/{config.MAX_MESSAGE_LIMIT}")
        
        # Teşhis Paneli - Veritabanı Bilgisi
        if 'db' in st.session_state:
            total_sources = len(st.session_state.db)
            st.info(f"📚 Arşivdeki Toplam Kaynak: **{total_sources}**")
            
            st.markdown("---")
            st.caption("🔍 **Test Paneli:** Veritabanında bir kelimenin varlığını yapay zeka olmadan kontrol et.")
            test_query = st.text_input("Kelime Ara:", placeholder="Örn: celali").strip()
            
            if test_query:
                normalized_test = normalize_turkish_text(test_query)
                matches = []
                for entry in st.session_state.db:
                    title_norm = normalize_turkish_text(entry.get('baslik', ''))
                    if normalized_test in title_norm:
                        matches.append(entry['baslik'])
                
                if matches:
                    st.success(f"✅ Bulundu ({len(matches)} Adet):")
                    for match in matches[:3]: # İlk 3 tanesini göster
                        st.caption(f"• {match}")
                else:
                    st.error(f"❌ '{test_query}' arşivde bulunamadı.")
                    st.caption(f"Aranan (Normalize): {normalized_test}")
        else:
             st.warning("⚠️ Veritabanı yüklenemedi!")
        
    return selected_mode

def render_sources(sources: List[Dict]):
    """Render source references"""
    if not sources:
        return
    
    st.markdown("---")
    st.markdown("**📚 Kaynaklar:**")
    for source in sources[:3]:
        st.markdown(f"• [{source['baslik']}]({source['link']})")

# ===================== MAIN APPLICATION =====================

def main():
    """Main application flow"""
    # Render UI components
    render_header()
    selected_mode = render_sidebar()
    
    # Display chat history
    for message in st.session_state.messages:
        icon = config.CAN_DEDE_ICON if message["role"] == "assistant" else config.USER_ICON
        with st.chat_message(message["role"], avatar=icon):
            st.markdown(message["content"])
    
    # Handle user input
    user_input = st.chat_input("Can Dede'ye sor...")
    
    if user_input:
        can_proceed, error_message = validate_rate_limit()
        if not can_proceed:
            st.error(error_message)
            st.stop()
        
        st.session_state.request_count += 1
        st.session_state.last_request_time = time.time()
        
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.chat_message("user", avatar=config.USER_ICON).markdown(user_input)
        scroll_to_bottom()
        
        # Arama yap ve bulunan keywords'leri de al
        sources, found_keywords = search_knowledge_base(user_input, st.session_state.db)
        
        # GÜNCELLEME: Can Dede cevap vermeden önce bulduklarını kullanıcıya göster (GÜVEN İNŞASI)
        if sources:
             with st.expander(f"🔍 Can Dede Arka Planda Bunları Buldu ({len(sources)} Kaynak)"):
                 st.caption(f"Aranan Anahtar Kelimeler: {found_keywords}")
                 for s in sources:
                     st.write(f"- {s['baslik']}")
        
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            placeholder = st.empty()
            full_response = ""
            
            with st.spinner("Can Dede tefekkürde..."):
                for chunk in generate_ai_response(user_input, sources, selected_mode):
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
            
            placeholder.markdown(full_response)
            
            # GÜNCELLEME: Can Dede "Bulamadım" derse kaynakları gizle!
            failure_phrases = ["bilgi bulamadım", "kaynak bulamadım", "yeterli kaynak", "üzgünüm"]
            is_failure = any(phrase in full_response.lower() for phrase in failure_phrases)
            
            if sources and "Araştırma" in selected_mode and not is_failure:
                render_sources(sources)
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response
            })
            scroll_to_bottom()

if __name__ == "__main__":
    main()
