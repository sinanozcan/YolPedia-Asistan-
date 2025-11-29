import streamlit as st
import streamlit.components.v1 as components 
import requests
import google.generativeai as genai
import time
import json
import random

# ================= AYARLAR =================
API_KEYS = [
    st.secrets.get("API_KEY", ""),
    st.secrets.get("API_KEY_2", ""),
    st.secrets.get("API_KEY_3", ""),
    st.secrets.get("API_KEY_4", ""),
    st.secrets.get("API_KEY_5", "")
]
API_KEYS = [k.strip() for k in API_KEYS if k and len(k) > 20]

DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"

# --- SAYFA AYARLARI ---
st.set_page_config(page_title=ASISTAN_ISMI, page_icon=YOLPEDIA_ICON, layout="wide")

# --- API KEY KONTROLÜ ---
if not API_KEYS:
    st.error("❌ Geçerli API anahtarı bulunamadı. Lütfen secrets.toml dosyasını kontrol edin.")
    st.stop()

# --- CSS ---
st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 5px; margin-bottom: 5px; }
    .dede-img { width: 80px; height: 80px; border-radius: 50%; margin-right: 15px; object-fit: cover; border: 2px solid #eee; }
    .title-text { font-size: 36px; font-weight: 700; margin: 0; color: #ffffff; }
    .subtitle-text { font-size: 18px; font-weight: 400; margin-top: 5px; color: #aaaaaa; text-align: center; }
    .top-logo-container { display: flex; justify-content: center; margin-bottom: 20px; padding-top: 10px; }
    .top-logo { width: 80px; opacity: 1.0; }
    .motto-text { text-align: center; font-size: 16px; font-style: italic; color: #cccccc; margin-bottom: 25px; font-family: 'Georgia', serif; }
    @media (prefers-color-scheme: light) { 
        .title-text { color: #000000; } 
        .subtitle-text { color: #555555; }
        .motto-text { color: #555555; } 
    }
    .stChatMessage { margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: 
            data = json.load(f)
            if not isinstance(data, list):
                st.error(f"❌ {DATA_FILE} geçersiz format (liste olmalı).")
                return []
            
            processed_data = []
            for d in data:
                if not isinstance(d, dict):
                    continue
                    
                ham_baslik = d.get('baslik', '')
                ham_icerik = d.get('icerik', '')
                
                d['norm_baslik'] = tr_normalize(ham_baslik)
                d['norm_icerik'] = tr_normalize(ham_icerik)
                processed_data.append(d)
            
            if processed_data:
                st.sidebar.success(f"✅ {len(processed_data)} kayıt yüklendi")
            else:
                st.sidebar.warning("⚠️ Veri yüklendi ama hiçbir kayıt işlenemedi!")
            return processed_data
            
    except FileNotFoundError:
        st.sidebar.warning(f"⚠️ {DATA_FILE} bulunamadı. Araştırma modu çalışmayacak.")
        return []
    except json.JSONDecodeError:
        st.sidebar.error(f"❌ {DATA_FILE} geçersiz JSON formatında.")
        return []
    except Exception as e:
        st.sidebar.error(f"❌ Veri yükleme hatası: {str(e)}")
        return []

def tr_normalize(text):
    if not isinstance(text, str): 
        return ""
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

# Session state başlatma
if 'db' not in st.session_state: 
    st.session_state.db = veri_yukle()

if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant", 
        "content": "Merhaba! Nasıl yardımcı olabilirim?"
    }]

# RATE LIMITING
if 'request_count' not in st.session_state:
    st.session_state.request_count = 0
if 'last_reset_time' not in st.session_state:
    st.session_state.last_reset_time = time.time()

if time.time() - st.session_state.last_reset_time > 3600:
    st.session_state.request_count = 0
    st.session_state.last_reset_time = time.time()

# --- MOD SEÇİMİ (SIDEBAR) ---
with st.sidebar:
    st.image(CAN_DEDE_ICON, width=100)
    st.title("Mod Seçimi")
    
    if st.session_state.db:
        st.success(f"📊 **{len(st.session_state.db)} kayıt** hazır")
    else:
        st.error("⚠️ Veritabanı yüklenemedi!")
    
    kalan_limit = 50 - st.session_state.request_count
    if kalan_limit > 30:
        st.info(f"💬 Kalan: **{kalan_limit}/50** (saatlik)")
    elif kalan_limit > 10:
        st.warning(f"⚠️ Kalan: **{kalan_limit}/50**")
    else:
        st.error(f"🔴 Kalan: **{kalan_limit}/50**")
    
    secilen_mod = st.radio(
        "Can Dede nasıl yardımcı olsun?",
        ["☕ Sohbet Modu", "🔍 Araştırma Modu"],
        captions=[
            "Samimi sohbet eder, felsefi konuşur.", 
            "Kütüphane memuru gibi kaynak sunar."
        ]
    )
    st.markdown("---")
    st.info(f"Aktif: **{secilen_mod}**")
    
    if st.button("🗑️ Sohbeti Sıfırla"):
        st.session_state.messages = [{
            "role": "assistant", 
            "content": "Sohbet sıfırlandı. Yeni konuşma başlayalım!"
        }]
        st.rerun()

# --- HEADER ---
st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header">
        <img src="{CAN_DEDE_ICON}" class="dede-img">
        <div>
            <h1 class="title-text">Can Dede</h1>
            <div class="subtitle-text">YolPedia Rehberiniz</div>
        </div>
    </div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)

# --- ARAMA MOTORU (OPTIMIZE EDİLMİŞ) ---
def alakali_icerik_bul(kelime, db):
    if not db or not kelime or not isinstance(kelime, str): 
        return [], ""
    
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    
    if len(norm_sorgu) < 3: 
        return [], ""

    sonuclar = []
    
    for d in db:
        if not isinstance(d, dict):
            continue
            
        puan = 0
        d_baslik = d.get('norm_baslik', '')
        d_icerik = d.get('norm_icerik', '')
        
        # TAM EŞLEŞME - Yüksek puan
        if norm_sorgu in d_baslik: 
            puan += 150
        elif norm_sorgu in d_icerik: 
            puan += 80
        
        # ANAHTAR KELİME EŞLEŞME
        for k in anahtarlar:
            if k in d_baslik: 
                puan += 30
            elif k in d_icerik: 
                puan += 8
        
        # SADECE YÜKSEK PUANLI SONUÇLAR (alakasız kaynakları elemek için)
        if puan > 25:  # Eşik yükseltildi
            sonuclar.append({
                "veri": d, 
                "puan": puan,
                "baslik": d.get('baslik', 'Başlıksız'),
                "link": d.get('link', '#'),
                "icerik": d.get('icerik', '')[:1500]  # Kısaltıldı
            })
    
    # En iyi 5 sonucu al (6->5)
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    return sonuclar[:5], norm_sorgu

# --- MODEL SEÇİCİ ---
def uygun_modeli_bul_ve_getir():
    try:
        mevcut_modeller = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if not mevcut_modeller: 
            return None, "Hiçbir model bulunamadı"
            
        tercihler = ["gemini-1.5-flash", "models/gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
        for t in tercihler:
            for m in mevcut_modeller:
                if t in m: 
                    return m, None
        return mevcut_modeller[0], None
    except Exception as e:
        return None, str(e)

# --- CAN DEDE CEVAP (OPTIMIZE EDİLMİŞ) ---
def can_dede_cevapla(user_prompt, chat_history, kaynaklar, mod):
    if not API
