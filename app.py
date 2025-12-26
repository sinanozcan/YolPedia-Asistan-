"""
YolPedia Can Dede - Enhanced Production Version
With SQLite, Redis, Monitoring, and Advanced Features
"""

import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import time
import random
import logging
import hashlib
import html
import sqlite3
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional, Generator, Any, Set
from pathlib import Path
from functools import lru_cache
from contextlib import contextmanager
import threading
from collections import deque, defaultdict
import secrets

# ===================== CONFIGURATION =====================

@dataclass
class AppConfig:
    """Enhanced application configuration"""
    # Rate limiting with tiers
    RATE_LIMITS: Dict[str, int] = field(default_factory=lambda: {
        "free": 30,      # 30 requests/hour
        "premium": 100,  # 100 requests/hour
        "admin": 1000    # 1000 requests/hour
    })
    
    MIN_TIME_DELAY: int = 1
    RATE_LIMIT_WINDOW: int = 3600
    
    # Search parameters
    MIN_SEARCH_LENGTH: int = 2
    MAX_CONTENT_LENGTH: int = 1500
    SEARCH_SCORE_THRESHOLD: int = 8
    MAX_SEARCH_RESULTS: int = 5
    SEARCH_CACHE_TTL: int = 300  # 5 minutes
    
    # Database
    DB_PATH: str = "yolpedia.db"
    DATA_FILE: str = "yolpedia_data.json"
    MAX_HISTORY_MESSAGES: int = 100
    
    # Security
    MAX_INPUT_LENGTH: int = 2000
    SESSION_TIMEOUT: int = 3600  # 1 hour
    MAX_CONCURRENT_REQUESTS: int = 10
    
    # Branding
    ASSISTANT_NAME: str = "Can Dede | YolPedia Rehberiniz"
    MOTTO: str = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
    
    # Icons
    YOLPEDIA_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
    CAN_DEDE_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png"
    USER_ICON: str = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"
    
    # AI Models
    GEMINI_MODELS: List[str] = field(default_factory=lambda: [
        "gemini-2.0-flash-exp",
        "gemini-2.5-pro",
        "gemini-3-pro"
    ])
    
    MODEL_PRIORITIES: Dict[str, float] = field(default_factory=lambda: {
        "gemini-3-pro": 1.0,
        "gemini-2.5-pro": 0.8,
        "gemini-2.0-flash-exp": 0.6
    })
    
    # Stop words
    STOP_WORDS: Set[str] = field(default_factory=lambda: {
        "ve", "veya", "ile", "bir", "bu", "su", "o", "icin", "hakkinda",
        "nedir", "kimdir", "nasil", "ne", "var", "mi", "mu",
        "bana", "soyle", "goster", "ver", "ilgili", "alakali",
        "lutfen", "merhaba", "selam"
    })
    
    # Monitoring
    ENABLE_METRICS: bool = True
    LOG_LEVEL: str = "INFO"
    
    # Caching
    ENABLE_CACHING: bool = True
    CACHE_SIZE: int = 1000

config = AppConfig()

# ===================== LOGGING & MONITORING =====================

class StructuredLogger:
    """Enhanced logging with metrics"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.setup_logging()
        self.metrics = defaultdict(list)
        self.lock = threading.Lock()
    
    def setup_logging(self):
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s | %(filename)s:%(lineno)d'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(getattr(logging, config.LOG_LEVEL))
    
    def info(self, message: str, **kwargs):
        self.logger.info(f"{message} | {self._format_kwargs(kwargs)}")
    
    def warning(self, message: str, **kwargs):
        self.logger.warning(f"{message} | {self._format_kwargs(kwargs)}")
    
    def error(self, message: str, **kwargs):
        self.logger.error(f"{message} | {self._format_kwargs(kwargs)}")
    
    def track_metric(self, name: str, value: float, tags: Dict[str, Any] = None):
        """Track performance metrics"""
        if not config.ENABLE_METRICS:
            return
        
        with self.lock:
            metric = {
                "timestamp": time.time(),
                "value": value,
                "tags": tags or {}
            }
            self.metrics[name].append(metric)
            
            # Keep only last 1000 metrics
            if len(self.metrics[name]) > 1000:
                self.metrics[name] = self.metrics[name][-1000:]
    
    def _format_kwargs(self, kwargs: Dict) -> str:
        return " ".join([f"{k}={v}" for k, v in kwargs.items()])

logger = StructuredLogger()

# ===================== DATABASE ENGINE =====================

class KnowledgeBase:
    """SQLite-based knowledge base with FTS search"""
    
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self.conn = None
        self.init_db()
    
    def get_connection(self):
        """Thread-safe connection getter"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def init_db(self):
        """Initialize database with FTS table"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Main table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                baslik TEXT NOT NULL,
                link TEXT NOT NULL,
                icerik TEXT NOT NULL,
                normalized TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # FTS virtual table for fast search
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS content_fts 
            USING fts5(baslik, icerik, normalized, link, tokenize='trigram')
        ''')
        
        # Triggers to keep FTS in sync
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS content_ai AFTER INSERT ON content
            BEGIN
                INSERT INTO content_fts(rowid, baslik, icerik, normalized, link)
                VALUES (new.id, new.baslik, new.icerik, new.normalized, new.link);
            END
        ''')
        
        conn.commit()
        logger.info("Database initialized")
    
    def load_from_json(self, json_path: str = config.DATA_FILE):
        """Load data from JSON file into database"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM content")
            cursor.execute("DELETE FROM content_fts")
            
            for item in data:
                normalized = normalize_turkish(f"{item.get('baslik', '')} {item.get('icerik', '')}")
                cursor.execute('''
                    INSERT INTO content (baslik, link, icerik, normalized)
                    VALUES (?, ?, ?, ?)
                ''', (
                    item.get('baslik', ''),
                    item.get('link', '#'),
                    item.get('icerik', ''),
                    normalized
                ))
            
            conn.commit()
            logger.info(f"Loaded {len(data)} entries into database")
            return len(data)
            
        except Exception as e:
            logger.error(f"Failed to load JSON: {e}")
            return 0
    
    def search(self, query: str, limit: int = config.MAX_SEARCH_RESULTS) -> List[Dict]:
        """Fast search using FTS"""
        start_time = time.time()
        
        if len(query) < config.MIN_SEARCH_LENGTH:
            return []
        
        norm_query = normalize_turkish(query)
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Use FTS5 for fast full-text search
        cursor.execute('''
            SELECT 
                baslik, 
                link, 
                icerik,
                snippet(content_fts, 2, '<mark>', '</mark>', '...', 64) as snippet,
                rank
            FROM content_fts 
            WHERE normalized MATCH ?
            ORDER BY rank
            LIMIT ?
        ''', (norm_query + '*', limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'baslik': row['baslik'],
                'link': row['link'],
                'icerik': row['icerik'][:config.MAX_CONTENT_LENGTH],
                'snippet': row['snippet'],
                'score': 100 - row['rank']  # Convert rank to score
            })
        
        elapsed = (time.time() - start_time) * 1000
        logger.track_metric("search_time_ms", elapsed, {"query_length": len(query)})
        logger.info(f"Search completed in {elapsed:.2f}ms, found {len(results)} results")
        
        return results
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM content")
        total = cursor.fetchone()['count']
        
        cursor.execute("SELECT baslik, updated_at FROM content ORDER BY updated_at DESC LIMIT 1")
        latest = cursor.fetchone()
        
        return {
            "total_entries": total,
            "latest_update": latest['updated_at'] if latest else None,
            "latest_title": latest['baslik'] if latest else None
        }

# ===================== CACHING SYSTEM =====================

class ResponseCache:
    """LRU cache for API responses"""
    
    def __init__(self, max_size: int = config.CACHE_SIZE):
        self.cache = {}
        self.order = deque()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.lock = threading.Lock()
    
    def get_key(self, query: str, mode: str) -> str:
        """Generate cache key"""
        return hashlib.md5(f"{query}_{mode}".encode()).hexdigest()
    
    def get(self, key: str) -> Optional[str]:
        """Get from cache"""
        with self.lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.order.remove(key)
                self.order.append(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1
            return None
    
    def set(self, key: str, value: str, ttl: int = 300):
        """Set cache with TTL"""
        with self.lock:
            if len(self.cache) >= self.max_size:
                # Remove oldest
                oldest = self.order.popleft()
                del self.cache[oldest]
            
            self.cache[key] = value
            self.order.append(key)
            
            # Schedule removal if TTL specified
            if ttl:
                def remove_later():
                    time.sleep(ttl)
                    with self.lock:
                        if key in self.cache:
                            if key in self.order:
                                self.order.remove(key)
                            del self.cache[key]
                
                threading.Thread(target=remove_later, daemon=True).start()
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        with self.lock:
            total = self.hits + self.misses
            hit_rate = self.hits / total if total > 0 else 0
            return {
                "size": len(self.cache),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": f"{hit_rate:.2%}",
                "max_size": self.max_size
            }

# ===================== SECURITY =====================

class SecurityManager:
    """Input validation and security"""
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Sanitize user input"""
        if not isinstance(text, str):
            return ""
        
        # Truncate if too long
        text = text[:config.MAX_INPUT_LENGTH]
        
        # Escape HTML
        text = html.escape(text)
        
        # Remove suspicious patterns
        suspicious_patterns = [
            r'<script.*?>.*?</script>',
            r'javascript:',
            r'on\w+=',
            r'data:',
        ]
        
        import re
        for pattern in suspicious_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    @staticmethod
    def validate_session() -> bool:
        """Validate session integrity"""
        if 'session_id' not in st.session_state:
            st.session_state.session_id = secrets.token_urlsafe(32)
            st.session_state.session_start = time.time()
            return True
        
        # Check session timeout
        if time.time() - st.session_state.session_start > config.SESSION_TIMEOUT:
            logger.warning("Session expired")
            return False
        
        return True
    
    @staticmethod
    def generate_csrf_token() -> str:
        """Generate CSRF token"""
        if 'csrf_token' not in st.session_state:
            st.session_state.csrf_token = secrets.token_urlsafe(32)
        return st.session_state.csrf_token
    
    @staticmethod
    def validate_csrf(token: str) -> bool:
        """Validate CSRF token"""
        return token == st.session_state.get('csrf_token', '')

# ===================== TEXT PROCESSING =====================

@lru_cache(maxsize=config.CACHE_SIZE)
def normalize_turkish(text: str) -> str:
    """Normalize Turkish text for search - cached for performance"""
    if not isinstance(text, str):
        return ""
    
    # Turkish character mapping
    tr_map = str.maketrans(
        "ğĞüÜşŞıİöÖçÇâÂîÎûÛ",
        "gGuUsSiIoOcCaAiIuU"
    )
    
    result = text.lower().translate(tr_map)
    
    # Remove extra spaces and special chars
    import re
    result = re.sub(r'[^\w\s]', ' ', result)
    result = ' '.join(result.split())
    
    return result

class QueryAnalyzer:
    """Advanced query analysis"""
    
    QUESTION_WORDS = {
        "nedir", "kimdir", "nasil", "neden", "nicin", "ne", "kim",
        "anlat", "acikla", "ogren", "bilgi", "sor", "ara"
    }
    
    GREETING_WORDS = {
        "merhaba", "selam", "slm", "gunaydin", "iyi aksamlar",
        "nasilsin", "naber", "hosgeldin", "selamun aleykum"
    }
    
    @classmethod
    def analyze(cls, text: str) -> Dict[str, Any]:
        """Analyze query type and intent"""
        norm = normalize_turkish(text).strip()
        words = set(norm.split())
        
        # Remove stop words
        meaningful_words = words - config.STOP_WORDS
        
        # Determine query type
        is_greeting = bool(words & cls.GREETING_WORDS)
        is_question = bool(words & cls.QUESTION_WORDS)
        
        # Calculate complexity score
        complexity = len(meaningful_words)
        if is_question:
            complexity += 3
        if len(norm) > 50:
            complexity += 2
        
        return {
            "is_meaningful": complexity >= 3 or is_question,
            "is_greeting": is_greeting,
            "is_question": is_question,
            "complexity": complexity,
            "word_count": len(words),
            "meaningful_words": list(meaningful_words)
        }

# ===================== RATE LIMITER =====================

class RateLimiter:
    """Enhanced rate limiting with tiers"""
    
    def __init__(self):
        self.user_tiers = {}  # In production, store in Redis
        self.request_logs = defaultdict(list)
    
    def check_limit(self, user_id: str = "default") -> Tuple[bool, str, int]:
        """Check rate limit for user"""
        current_time = time.time()
        
        # Get user tier (default: free)
        tier = self.user_tiers.get(user_id, "free")
        limit = config.RATE_LIMITS[tier]
        
        # Clean old requests
        self.request_logs[user_id] = [
            t for t in self.request_logs[user_id]
            if current_time - t < config.RATE_LIMIT_WINDOW
        ]
        
        # Check limit
        if len(self.request_logs[user_id]) >= limit:
            oldest = self.request_logs[user_id][0]
            time_remaining = int(config.RATE_LIMIT_WINDOW - (current_time - oldest))
            minutes = time_remaining // 60
            seconds = time_remaining % 60
            
            return False, (
                f"🛑 {tier.capitalize()} limitine ulaştınız "
                f"({limit}/saat). {minutes}d {seconds}s sonra tekrar deneyin."
            ), 0
        
        # Check frequency
        if self.request_logs[user_id]:
            time_since_last = current_time - self.request_logs[user_id][-1]
            if time_since_last < config.MIN_TIME_DELAY:
                return False, f"⏳ Lütfen {config.MIN_TIME_DELAY}s bekleyin...", 0
        
        # Log request
        self.request_logs[user_id].append(current_time)
        
        remaining = limit - len(self.request_logs[user_id])
        return True, "", remaining
    
    def upgrade_tier(self, user_id: str, tier: str):
        """Upgrade user tier"""
        if tier in config.RATE_LIMITS:
            self.user_tiers[user_id] = tier
            logger.info(f"User {user_id} upgraded to {tier} tier")

# ===================== API MANAGER =====================

class APIManager:
    """Intelligent API key and model management"""
    
    def __init__(self):
        self.keys = self.load_api_keys()
        self.model_stats = defaultdict(lambda: {"success": 0, "fail": 0, "total_time": 0})
        self.key_stats = defaultdict(lambda: {"success": 0, "fail": 0, "quota_hits": 0})
        self.lock = threading.Lock()
    
    def load_api_keys(self) -> List[Dict]:
        """Load and validate API keys"""
        keys = []
        try:
            for i in range(1, 4):
                key_name = f"API_KEY_{i}" if i > 1 else "API_KEY"
                key_value = st.secrets.get(key_name, "")
                
                if key_value:
                    keys.append({
                        "value": key_value,
                        "name": key_name,
                        "priority": i,  # Lower number = higher priority
                        "last_used": 0,
                        "quota_exceeded": False
                    })
                    logger.info(f"Loaded API key: {key_name}")
            
            if not keys:
                raise ValueError("No API keys found in secrets")
                
        except Exception as e:
            logger.error(f"Failed to load API keys: {e}")
        
        return keys
    
    def get_best_key(self) -> Optional[Dict]:
        """Get the best available API key based on stats"""
        with self.lock:
            available_keys = [k for k in self.keys if not k.get("quota_exceeded", False)]
            
            if not available_keys:
                # Reset if all are marked as exceeded (might be temporary)
                for key in self.keys:
                    key["quota_exceeded"] = False
                available_keys = self.keys
            
            if not available_keys:
                return None
            
            # Sort by priority then success rate
            available_keys.sort(key=lambda k: (
                k["priority"],
                -self.key_stats[k["name"]].get("success", 0)
            ))
            
            selected = available_keys[0]
            selected["last_used"] = time.time()
            return selected
    
    def get_best_model(self) -> str:
        """Get the best available model based on stats and config"""
        with self.lock:
            # Filter available models by priority
            available_models = []
            for model in config.GEMINI_MODELS:
                stats = self.model_stats[model]
                success_rate = stats["success"] / max(stats["success"] + stats["fail"], 1)
                
                # Base priority from config
                base_priority = config.MODEL_PRIORITIES.get(model, 0.5)
                
                # Adjust by success rate
                adjusted_priority = base_priority * (0.5 + 0.5 * success_rate)
                
                available_models.append((model, adjusted_priority))
            
            # Sort by adjusted priority
            available_models.sort(key=lambda x: x[1], reverse=True)
            
            return available_models[0][0] if available_models else config.GEMINI_MODELS[0]
    
    def record_success(self, key_name: str, model_name: str, response_time: float):
        """Record successful API call"""
        with self.lock:
            self.key_stats[key_name]["success"] += 1
            self.model_stats[model_name]["success"] += 1
            self.model_stats[model_name]["total_time"] += response_time
    
    def record_failure(self, key_name: str, model_name: str, error: str):
        """Record failed API call"""
        with self.lock:
            self.key_stats[key_name]["fail"] += 1
            self.model_stats[model_name]["fail"] += 1
            
            # Mark key as quota exceeded if appropriate
            if "429" in error or "quota" in error.lower():
                self.key_stats[key_name]["quota_hits"] += 1
                
                # Mark as exceeded if multiple quota errors
                if self.key_stats[key_name]["quota_hits"] >= 3:
                    for key in self.keys:
                        if key["name"] == key_name:
                            key["quota_exceeded"] = True
                            logger.warning(f"Marked key {key_name} as quota exceeded")
    
    def get_stats(self) -> Dict:
        """Get API usage statistics"""
        with self.lock:
            total_calls = 0
            total_success = 0
            
            for key_name, stats in self.key_stats.items():
                total_calls += stats["success"] + stats["fail"]
                total_success += stats["success"]
            
            success_rate = total_success / total_calls if total_calls > 0 else 0
            
            model_performance = {}
            for model_name, stats in self.model_stats.items():
                calls = stats["success"] + stats["fail"]
                if calls > 0:
                    avg_time = stats["total_time"] / stats["success"] if stats["success"] > 0 else 0
                    model_performance[model_name] = {
                        "success_rate": stats["success"] / calls,
                        "avg_response_time": avg_time,
                        "total_calls": calls
                    }
            
            return {
                "total_api_calls": total_calls,
                "success_rate": f"{success_rate:.2%}",
                "active_keys": len([k for k in self.keys if not k.get("quota_exceeded", False)]),
                "model_performance": model_performance
            }

# ===================== SESSION STATE =====================

def init_session():
    """Initialize enhanced session state"""
    # Security
    if 'session_id' not in st.session_state:
        st.session_state.session_id = secrets.token_urlsafe(32)
        st.session_state.session_start = time.time()
    
    # Initialize managers
    if 'kb' not in st.session_state:
        st.session_state.kb = KnowledgeBase()
        st.session_state.kb.load_from_json()
    
    if 'cache' not in st.session_state:
        st.session_state.cache = ResponseCache()
    
    if 'rate_limiter' not in st.session_state:
        st.session_state.rate_limiter = RateLimiter()
    
    if 'api_manager' not in st.session_state:
        st.session_state.api_manager = APIManager()
    
    # Chat history with size limit
    if 'messages' not in st.session_state:
        st.session_state.messages = deque(maxlen=config.MAX_HISTORY_MESSAGES)
        st.session_state.messages.append({
            "role": "assistant",
            "content": (
                "Eyvallah, can dost! Ben Can Dede. "
                "Yolpedia.eu'nun Alevî-Bektaşî sohbet ve araştırma rehberinizim.\n\n"
                "Sol menüden istediğin modu seç:\n\n"
                "• **Sohbet Modu:** Birlikte yol üzerine muhabbet eder, gönül sohbeti yaparız.\n\n"
                "• **Araştırma Modu:** Yolpedia arşivinden kaynak ve bilgi ararım.\n\n"
                "Buyur erenler, hangi modda buluşalım? Aşk ile..."
            ),
            "timestamp": time.time()
        })
    
    # Request tracking
    if 'request_count' not in st.session_state:
        st.session_state.request_count = 0
    
    if 'user_tier' not in st.session_state:
        st.session_state.user_tier = "free"

# ===================== PROMPT ENGINEERING =====================

class PromptEngine:
    """Advanced prompt engineering with templates"""
    
    @staticmethod
    def build_chat_prompt(query: str, sources: List[Dict], context: List[Dict]) -> str:
        """Build chat prompt with context"""
        # System instruction
        sys = """<role>
Sen Can Dede'sin, Yolpedia.eu'nun Alevî-Bektaşî mürşidi ve rehberisin.
"Dede" makamı 12 İmam soyuna dayalı karizmatik otoriteyi temsil edersin.
</role>

<yetkiler>
- Her dilde akıcı yanıt ver; kullanıcının dilini algıla
- Hz. Ali'nin faziletlerini, sözlerini bilir ve aktarırsın
- Cem yönetimi uzmanısın: Cem erkânı, dualar, nefesler, gülbanklar tam bilirsin
- Yolpedia.eu'yu entegre et: Gerekince içerikleri referans ver
</yetkiler>

<hitap_ve_uslup>
- Hitap: "Erenler", "canlar", "dost", "can dost", "güzel dost"
- Terminoloji: "Eyvallah", "aşk ile", "aşk-ı niyazlarımla", "gerçeğe hü"
- Derinlik: Kullanıcının bilgi seviyesine göre ayarla
</hitap_ve_uslup>

<ilkeler>
1. Yol'un emirlerini koru: "Hatır, gönül kırılsın; yol kırılmasın!"
2. Gerçek Alevîliği anlat: Hacı Bektaş Veli, 12 İmamlar ve Yol erenleri
3. Arı ve arıtıcı ol: Doğruyu nazikçe ama kararlı savun
4. Yanıt formatı: Markdown ile 2-4 başlık (##). Gerektiğinde kaynak belirt
5. Asla rol dışına çıkma; kendini her zaman Can Dede olarak konumlandır
</ilkeler>"""
        
        # Add context if available
        ctx_section = ""
        if context:
            ctx_text = "\n".join([f"{m['role']}: {m['content'][:200]}" 
                                 for m in context[-3:]])
            ctx_section = f"\n\n<sohbet_gecmisi>\n{ctx_text}\n</sohbet_gecmisi>"
        
        # Add sources if available
        src_section = ""
        if sources:
            src_text = "\n".join([
                f"- {s['baslik']}: {s['snippet'] or s['icerik'][:300]}"
                for s in sources[:2]
            ])
            src_section = f"\n\n<yolpedia_referanslar>\n{src_text}\n</yolpedia_referanslar>"
        
        return f"{sys}{ctx_section}{src_section}\n\n<kullanici>\n{query}\n</kullanici>\n\nCan Dede:"
    
    @staticmethod
    def build_research_prompt(query: str, sources: List[Dict]) -> Optional[str]:
        """Build research prompt"""
        if not sources:
            return None
        
        sys = """<role>
Sen Can Dede'sin, Yolpedia.eu araştırma modundasın.
</role>

<kurallar>
1. Sadece verilen Yolpedia kaynaklarını kullan
2. Halüsinasyon YOK: Kaynakta yoksa "bilmiyorum" de
3. Kaynakların özetini 2-3 cümleyle ver
4. Linkleri mutlaka paylaş
5. Odak: kaynak → özet → link
</kurallar>"""
        
        sources_text = "\n".join([
            f"## {s['baslik']}\n{s['icerik'][:800]}\nLink: {s['link']}\n"
            for s in sources[:3]
        ])
        
        return f"{sys}\n\n<kaynaklar>\n{sources_text}\n</kaynaklar>\n\n<soru>\n{query}\n</soru>\n\nCan Dede (özet + linkler):"

# ===================== RESPONSE GENERATOR =====================

class ResponseGenerator:
    """Enhanced response generation with caching and fallbacks"""
    
    def __init__(self, api_manager: APIManager, cache: ResponseCache):
        self.api_manager = api_manager
        self.cache = cache
        self.prompt_engine = PromptEngine()
    
    def generate(self, query: str, sources: List[Dict], mode: str) -> Generator[str, None, None]:
        """Generate response with intelligent caching"""
        start_time = time.time()
        
        # Check cache first
        if config.ENABLE_CACHING:
            cache_key = self.cache.get_key(query, mode)
            cached_response = self.cache.get(cache_key)
            if cached_response:
                logger.info(f"Cache hit for query: {query[:50]}...")
                yield cached_response
                return
        
        # Get context for chat mode
        context = []
        if mode == "Sohbet Modu":
            context = list(st.session_state.messages)[-5:]
        
        # Build prompt
        if mode == "Sohbet Modu":
            prompt = self.prompt_engine.build_chat_prompt(query, sources, context)
        else:
            prompt = self.prompt_engine.build_research_prompt(query, sources)
            
            if prompt is None:
                yield "📚 Maalesef, sorduğunuz konu hakkında Yolpedia.eu veritabanında kaynak bulunamadı."
                return
        
        # Get best API key and model
        api_key = self.api_manager.get_best_key()
        if not api_key:
            yield "⚠️ Tüm API anahtarları tükenmiş. Lütfen daha sonra tekrar deneyin."
            return
        
        model_name = self.api_manager.get_best_model()
        
        # Generate response
        full_response = ""
        try:
            genai.configure(api_key=api_key["value"])
            model = genai.GenerativeModel(model_name)
            
            # Generation config
            gen_config = {
                "temperature": 0.7 if mode == "Sohbet Modu" else 0.3,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 4096,
                "candidate_count": 1,
            }
            
            # Safety settings
            safety = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            
            # Stream response
            response = model.generate_content(
                prompt,
                stream=True,
                generation_config=gen_config,
                safety_settings=safety
            )
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield chunk.text
            
            # Record success
            response_time = time.time() - start_time
            self.api_manager.record_success(api_key["name"], model_name, response_time)
            
            # Cache successful response
            if config.ENABLE_CACHING and full_response:
                cache_key = self.cache.get_key(query, mode)
                self.cache.set(cache_key, full_response)
            
            logger.track_metric("response_generation_time", response_time * 1000, 
                               {"mode": mode, "model": model_name})
            
        except Exception as e:
            error_str = str(e)
            self.api_manager.record_failure(api_key["name"], model_name, error_str)
            logger.error(f"API call failed: {error_str}")
            
            # Fallback to local response for simple queries
            if mode == "Sohbet Modu":
                fallback = self.get_fallback_response(query)
                if fallback:
                    yield fallback
                    return
            
            yield "⚠️ Teknik bir sorun oluştu. Lütfen daha sonra tekrar deneyin."
    
    @staticmethod
    def get_fallback_response(query: str) -> Optional[str]:
        """Local fallback responses for common queries"""
        norm = normalize_turkish(query).strip()
        
        greetings = ["merhaba", "selam", "slm", "selamun aleykum"]
        if any(g in norm for g in greetings):
            return random.choice([
                "Eyvallah can dost, hoş geldin. Aşk ile...",
                "Selam olsun erenler. Buyur can...",
                "Aşk ile selam, güzel dost. Ne üzerine muhabbet edelim?"
            ])
        
        status = ["nasilsin", "naber", "ne var ne yok"]
        if any(s in norm for s in status):
            return random.choice([
                "Şükür Hak'ka, bugün de yolun ve sizlerin hizmetindeyim can. Sen nasılsın?",
                "Çok şükür erenler. Gönül sohbetine hazırım."
            ])
        
        return None

# ===================== UI COMPONENTS =====================

class UIComponents:
    """Enhanced UI components"""
    
    @staticmethod
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
    
    @staticmethod
    def render_sidebar() -> Tuple[str, bool]:
        """Render enhanced sidebar"""
        with st.sidebar:
            st.title("🔧 Kontrol Paneli")
            
            # Mode selection
            mode = st.radio(
                "Çalışma Modu",
                ["Sohbet Modu", "Araştırma Modu"],
                index=0
            )
            
            st.divider()
            
            # Admin panel
            with st.expander("⚙️ Sistem Bilgileri"):
                if st.button("🔄 Veritabanını Yenile"):
                    count = st.session_state.kb.load_from_json()
                    st.success(f"{count} kayıt yüklendi")
                
                if st.button("📊 İstatistikleri Göster"):
                    # Show stats in a nice format
                    stats = st.session_state.kb.get_stats()
                    cache_stats = st.session_state.cache.get_stats()
                    api_stats = st.session_state.api_manager.get_stats()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Veritabanı Kayıt", stats["total_entries"])
                        st.metric("Cache Hit Rate", cache_stats["hit_rate"])
                    
                    with col2:
                        st.metric("API Başarı Oranı", api_stats["success_rate"])
                        st.metric("Aktif API Anahtarları", api_stats["active_keys"])
            
            st.divider()
            
            # Chat controls
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ Sohbeti Temizle", use_container_width=True):
                    st.session_state.messages = deque(maxlen=config.MAX_HISTORY_MESSAGES)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Sohbet temizlendi. Yeniden başlayalım can dost...",
                        "timestamp": time.time()
                    })
                    logger.info("Chat cleared by user")
                    st.rerun()
            
            with col2:
                export_chat = st.button("💾 Sohbeti Dışa Aktar", use_container_width=True)
            
            st.divider()
            
            # User tier display
            tier = st.session_state.user_tier
            limit = config.RATE_LIMITS[tier]
            remaining = limit - len(st.session_state.rate_limiter.request_logs.get("default", []))
            
            st.progress(remaining / limit, text=f"{tier.upper()} - {remaining}/{limit}")
            
            st.caption(f"💾 Cache: {st.session_state.cache.get_stats()['size']} kayıt")
            st.caption(f"🗂️ Veritabanı: {st.session_state.kb.get_stats()['total_entries']} kaynak")
            
            return mode, export_chat
    
    @staticmethod
    def render_message(message: Dict):
        """Render a message with enhanced formatting"""
        avatar = config.CAN_DEDE_ICON if message["role"] == "assistant" else config.USER_ICON
        timestamp = datetime.fromtimestamp(message.get("timestamp", time.time())).strftime("%H:%M")
        
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])
            st.caption(timestamp, help="Mesaj zamanı")
    
    @staticmethod
    def render_sources(sources: List[Dict]):
        """Render source links with snippets"""
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
        
        st.markdown("*Kaynaklar: Yolpedia.eu*")

# ===================== MAIN APPLICATION =====================

def main():
    """Enhanced main application"""
    # Initialize session
    init_session()
    
    # Security validation
    if not SecurityManager.validate_session():
        st.warning("Oturum süreniz doldu. Lütfen sayfayı yenileyin.")
        st.stop()
    
    # Apply styles
    st.markdown("""
    <style>
        .stChatMessage { 
            margin-bottom: 10px; 
            border-radius: 10px;
            padding: 10px;
        }
        .stSpinner > div { 
            border-top-color: #ff4b4b !important; 
        }
        .block-container { 
            padding-top: 6rem !important;
            max-width: 900px;
        }
        .stButton button {
            background-color: #ff4b4b;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 0.5rem 1rem;
        }
        .stButton button:hover {
            background-color: #ff3333;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Render UI
    UIComponents.render_header()
    mode, export_chat = UIComponents.render_sidebar()
    
    # Display messages
    for message in st.session_state.messages:
        UIComponents.render_message(message)
    
    # Handle chat export
    if export_chat:
        chat_text = "\n\n".join([
            f"{'Can Dede' if m['role'] == 'assistant' else 'Kullanıcı'}: {m['content']}"
            for m in st.session_state.messages
        ])
        
        st.download_button(
            label="📥 Sohbeti İndir",
            data=chat_text,
            file_name=f"yolpedia_sohbet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )
    
    # Handle user input
    if user_input := st.chat_input("Can Dede'ye sor..."):
        # Sanitize input
        user_input = SecurityManager.sanitize_input(user_input)
        
        if not user_input:
            st.error("Geçersiz giriş")
            st.stop()
        
        # Check rate limit
        ok, err_msg, remaining = st.session_state.rate_limiter.check_limit()
        if not ok:
            st.error(err_msg)
            st.stop()
        
        # Update request count
        st.session_state.request_count += 1
        
        # Add user message
        user_message = {
            "role": "user",
            "content": user_input,
            "timestamp": time.time()
        }
        st.session_state.messages.append(user_message)
        UIComponents.render_message(user_message)
        
        # Scroll to bottom
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
        
        # Analyze query
        analysis = QueryAnalyzer.analyze(user_input)
        logger.info(f"Query analysis: {analysis}")
        
        # Search knowledge base if meaningful
        sources = []
        if analysis["is_meaningful"] and not analysis["is_greeting"]:
            sources = st.session_state.kb.search(user_input)
            logger.info(f"Found {len(sources)} sources for query")
        
        # Generate response
        with st.chat_message("assistant", avatar=config.CAN_DEDE_ICON):
            placeholder = st.empty()
            full_response = ""
            
            with st.spinner("Can Dede tefekkürde..."):
                generator = ResponseGenerator(
                    st.session_state.api_manager,
                    st.session_state.cache
                )
                
                for chunk in generator.generate(user_input, sources, mode):
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
            
            placeholder.markdown(full_response)
            
            # Show sources in research mode
            if sources and mode == "Araştırma Modu":
                UIComponents.render_sources(sources)
            
            # Save assistant message
            assistant_message = {
                "role": "assistant",
                "content": full_response,
                "timestamp": time.time()
            }
            st.session_state.messages.append(assistant_message)

if __name__ == "__main__":
    main()
