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
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Generator
from pathlib import Path

# ===================== CONFIGURATION =====================

@dataclass
class AppConfig:
    """Application configuration constants"""
    MAX_MESSAGE_LIMIT: int = 40
    MIN_TIME_DELAY: int = 1
    RATE_LIMIT_WINDOW: int = 3600  # 1 hour in seconds
    
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
            self.GEMINI_MODELS = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]

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

def get_api_key() -> Optional[str]:
    """Retrieve and validate API key from secrets"""
    try:
        api_key = st.secrets.get("API_KEY", "")
        if not api_key:
            logger.error("API key is empty")
            return None
        return api_key
    except Exception as e:
        logger.error(f"Failed to retrieve API key: {e}")
        return None

GOOGLE_API_KEY = get_api_key()

if not GOOGLE_API_KEY:
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

# ===================== TEXT PROCESSING =====================

def normalize_turkish_text(text: str) -> str:
    """Normalize Turkish text for better searching"""
    if not isinstance(text, str):
        return ""
    
    translation_table = str.maketrans(
        "ğĞüÜşŞıİöÖçÇ",
        "gGuUsSiIoOcC"
    )
    return text.translate(translation_table).lower()

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
        # Calculate time until reset
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
    title = entry.get('baslik', '')
    content = entry.get('icerik', '')
    
    normalized_title = normalize_turkish_text(title)
    normalized_content = normalize_turkish_text(content)
    
    # Exact match in title gets highest score
    if normalized_query in normalized_title:
        score += 200
    elif normalized_query in normalized_content:
        score += 100
    
    # Keyword matches
    for keyword in keywords:
        if keyword in normalized_title:
            score += 40
        elif keyword in normalized_content:
            score += 10
    
    # Boost for specific content types
    special_terms = ["gulbank", "deyis", "nefes", "siir"]
    if any(term in normalized_title for term in special_terms):
        score += 300
    
    return score

def search_knowledge_base(query: str, db: List[Dict]) -> Tuple[List[Dict], str]:
    """Search knowledge base for relevant content"""
    if not db or not query or len(query) < config.MIN_SEARCH_LENGTH:
        return [], ""
    
    normalized_query = normalize_turkish_text(query)
    keywords = [k for k in normalized_query.split() if len(k) > 2]
    
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
    
    logger.info(f"Search for '{query}' returned {len(top_results)} results")
    return top_results, normalized_query

# ===================== LOCAL RESPONSE HANDLER =====================

def get_local_response(text: str) -> Optional[str]:
    """Check if query can be answered with predefined local responses"""
    normalized = normalize_turkish_text(text)
    
    greetings = ["merhaba", "selam", "selamun aleykum", "gunaydin"]
    status_queries = ["nasilsin", "naber", "ne var ne yok"]
    
    if any(greeting == normalized for greeting in greetings):
        return random.choice([
            "Aşk ile merhaba can.",
            "Selam olsun, hoş geldin.",
            "Hoş geldin Can Dost."
        ])
    
    if any(query in normalized for query in status_queries):
        return "Şükür Hak'ka, hizmetteyiz can."
    
    return None

# ===================== AI RESPONSE GENERATOR =====================

def build_prompt(user_query: str, sources: List[Dict], mode: str) -> str:
    """Build the prompt for the AI model"""
    system_instruction = (
        "Sen 'Can Dede'sin. Alevi-Bektaşi felsefesini benimsemiş bir rehbersin. "
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
            f"Sen YolPedia asistanısın. Sadece verilen kaynaklara göre cevapla:\n"
            f"{source_text}\n\n"
            f"Soru: {user_query}"
        )

def generate_ai_response(
    user_query: str,
    sources: List[Dict],
    mode: str
) -> Generator[str, None, None]:
    """Generate AI response using Google Gemini API"""
    
    # Check for local response first
    local_response = get_local_response(user_query)
    if local_response:
        time.sleep(0.5)
        yield local_response
        return
    
    # Build prompt
    prompt = build_prompt(user_query, sources, mode)
    
    if prompt is None:
        yield "📚 Aradığın konuyla ilgili kaynak bulamadım can."
        return
    
    # Configure API
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
    except Exception as e:
        logger.error(f"API configuration failed: {e}")
        yield "⚠️ API anahtarı yapılandırma hatası. Lütfen yöneticiyle iletişime geç."
        return
    
    # Try models in order
    last_error = None
    for model_name in config.GEMINI_MODELS:
        try:
            logger.info(f"Attempting to use model: {model_name}")
            model = genai.GenerativeModel(model_name)
            
            # Add generation config for better reliability
            generation_config = {
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 2048,
            }
            
            response = model.generate_content(
                prompt, 
                stream=True,
                generation_config=generation_config
            )
            
            has_content = False
            for chunk in response:
                if chunk.text:
                    yield chunk.text
                    has_content = True
            
            if has_content:
                logger.info(f"Successfully generated response using {model_name}")
                return
                
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Model {model_name} failed: {e}")
            
            # Check for specific errors
            if "quota" in str(e).lower() or "limit" in str(e).lower():
                logger.error(f"API quota exceeded: {e}")
                yield "⚠️ API kullanım limiti doldu. Lütfen biraz sonra tekrar dene."
                return
            elif "invalid" in str(e).lower() or "key" in str(e).lower():
                logger.error(f"Invalid API key: {e}")
                yield "⚠️ API anahtarı geçersiz. Lütfen yöneticiyle iletişime geç."
                return
            
            continue
    
    # All models failed
    logger.error(f"All AI models failed. Last error: {last_error}")
    yield f"⚠️ Can Dost, şu anda teknik bir sorun var. Detay: {last_error[:100]}"

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
            <img src="{config.YOLPEDIA_ICON}" style="width: 80px; height: auto;">
        </div>
        <div style="display: flex; align-items: center; justify-content: center; gap: 15px; margin-bottom: 10px;">
            <img src="{config.CAN_DEDE_ICON}" 
                 style="width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 2px solid #eee;">
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
                "content": "Sohbet sıfırlandı. Buyur can."
            }]
            st.session_state.request_count = 0
            logger.info("Chat history reset by user")
            st.rerun()
        
        # Display usage stats
        st.divider()
        st.caption(f"📊 Mesaj: {st.session_state.request_count}/{config.MAX_MESSAGE_LIMIT}")
        
        # Debug info (only if API key exists)
        if GOOGLE_API_KEY:
            api_preview = GOOGLE_API_KEY[:8] + "..." + GOOGLE_API_KEY[-4:]
            st.caption(f"🔑 API: {api_preview}")
        else:
            st.error("⚠️ API key yok!")
        
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
        # Validate rate limit
        can_proceed, error_message = validate_rate_limit()
        if not can_proceed:
            st.error(error_message)
            st.stop()
        
        # Update rate limit counters
        st.session_state.request_count += 1
        st.session_state.last_request_time = time.time()
        
        # Add user message
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.chat_message("user", avatar=config.USER_ICON).markdown(user_input)
        scroll_to_bottom()
        
        # Search knowledge base
        sources, _ = search_knowledge_base(user_input, st.session_state.db)
        
        # Generate and display AI response
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            placeholder = st.empty()
            full_response = ""
            
            with st.spinner("Can Dede tefekkürde..."):
                for chunk in generate_ai_response(user_input, sources, selected_mode):
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
            
            placeholder.markdown(full_response)
            
            # Show sources in research mode
            if sources and "Araştırma" in selected_mode:
                render_sources(sources)
            
            # Save assistant message
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response
            })
            scroll_to_bottom()

if __name__ == "__main__":
    main()
