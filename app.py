import streamlit as st
import streamlit.components.v1 as components 
import requests
import google.generativeai as genai
import time
import json
import random
import sys
from PIL import Image
from io import BytesIO

# ================= TEKNİK TANI VE DÜZELTME =================
# Kütüphane sürümünü kontrol et
try:
    import importlib.metadata
    lib_version = importlib.metadata.version("google-generativeai")
except:
    lib_version = "Bilinmiyor"

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
MOTTO = '"Bildigimin âlimiyim, bilmedigimin tâlibiyim!"'
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"

# --- SAYFA AYARLARI ---
st.set_page_config(page_title=ASISTAN_ISMI, page_icon="🤖")

# --- CSS ---
st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 5px; margin-bottom: 5px; }
    .dede-img { width: 80px; height: 80px; border-radius: 50%; margin-right: 15px; object-fit: cover; border: 2px solid #eee; }
    .title-text { font-size: 36px; font-weight: 700; margin: 0; color: #ffffff; }
    .top-logo-container { display: flex; justify-content: center; margin-bottom: 45px; padding-top: 10px; }
    .top-logo { width: 90px; opacity: 1.0; }
    .motto-text { text-align: center; font-size: 16px; font-style: italic; color: #cccccc; margin-bottom: 25px; font-family: 'Georgia', serif; }
    @media (prefers-color-scheme: light) { .title-text { color: #000000; } .motto-text { color: #555555; } }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header"><img src="{CAN_DEDE_ICON}" class="dede-img"><h1 class="title-text">Can Dede</h1></div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)

# --- SÜRÜM KONTROL PANO (GEÇİCİ) ---
# Eğer sürüm eskiyse uyarı ver
if lib_version != "Bilinmiyor" and lib_version < "0.8.3":
    st.error(f"🚨 KRİTİK HATA: Kütüphane Sürümü Çok Eski: {lib_version}")
    st.warning("Lütfen Streamlit Cloud panelinden 'Clear Cache' yapın veya App'i silip tekrar kurun.")
    st.stop() # Kodun geri kalanını çalıştırma

# --- FONKSİYON: OTOMATİK MODEL BULUCU ---
@st.cache_resource
def calisan_modeli_bul():
    """
    Sistemde yüklü ve erişilebilir olan İLK modeli bulur.
    Tahmin yapmaz, API'ye 'Senin elinde ne var?' diye sorar.
    """
    if not API_KEYS: return None
    
    # İlk anahtarı test için kullan
    genai.configure(api_key=API_KEYS[0])
    try:
        mevcutlar = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                mevcutlar.append(m.name)
        
        # Öncelik Sıralaması (Varsa bunları seç)
        tercihler = ["gemini-1.5-flash", "models/gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
        
        # 1. Tercih listesindekilerden biri var mı?
        for t in tercihler:
            for m in mevcutlar:
                if t in m: return m # Bulduk!
        
        # 2. Yoksa listedeki ilk "gemini" içeren modeli al
        for m in mevcutlar:
            if "gemini" in m: return m
            
        # 3. O da yoksa ne varsa onu al
        if mevcutlar: return mevcutlar[0]
        
        return None
    except Exception as e:
        return None

# Model ismini hafızaya al
AKTIF_MODEL_ADI = calisan_modeli_bul()

# --- GÜVENLİ YANIT ÜRETİCİ ---
def guvenli_stream_baslat(full_prompt):
    if not AKTIF_MODEL_ADI:
        st.error("❌ HATA: Hiçbir yapay zeka modeli bulunamadı. API Keylerinizi veya Kütüphane sürümünü kontrol edin.")
        return None
    
    random.shuffle(API_KEYS)
    
    for key in API_KEYS:
        try:
            genai.configure(api_key=key)
            config = {"temperature": 0.3, "max_output_tokens": 8000}
            guvenlik = [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}]
            
            model = genai.GenerativeModel(AKTIF_MODEL_ADI, generation_config=config, safety_settings=guvenlik)
            return model.generate_content(full_prompt, stream=True)
            
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err:
                time.sleep(1)
                continue # Diğer anahtara geç
            if "404" in err:
                continue
            
    st.error("⚠️ Can Dede şu an çok yoğun. Lütfen 1 dakika sonra tekrar deneyin.")
    return None

# --- DİĞER FONKSİYONLAR (KISA VERSİYON) ---
def scroll_to_bottom():
    components.html("""<script>window.parent.document.querySelector(".main").scrollTop = 100000;</script>""", height=0)

@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return []

if 'db' not in st.session_state: st.session_state.db = veri_yukle()

def tr_normalize(text):
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

def alakali_icerik_bul(kelime, db):
    norm = tr_normalize(kelime)
    keys = [k for k in norm.split() if len(k)>2]
    res = []
    for d in db:
        p = 0
        b, i = tr_normalize(d['baslik']), tr_normalize(d['icerik'])
        if norm in b: p+=100
        elif norm in i: p+=40
        for k in keys:
            if k in b: p+=10
            elif k in i: p+=2
        if p>0: res.append({"v": d, "p": p})
    res.sort(key=lambda x:x['p'], reverse=True)
    txt = ""
    links = []
    for r in res[:5]:
        txt += f"\nBASLIK: {r['v']['baslik']}\nICERIK: {r['v']['icerik'][:8000]}\n"
        links.append(r['v'])
    return txt, links

# --- SOHBET ARAYÜZÜ ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Merhaba Erenler! Ben Can Dede. Size nasıl yardımcı olayım?"}]

for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    st.chat_message(msg["role"], avatar=icon).markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        with st.spinner("Can Dede düşünüyor..."):
            baglam = ""
            kaynaklar = []
            if st.session_state.db:
                baglam, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
            
            full_prompt = f"Sen Can Dede'sin. Kullanıcıya şu bilgilere göre cevap ver: {baglam}. Soru: {prompt}"
            if not baglam: full_prompt = f"Sen Can Dede'sin. Sohbet et. Soru: {prompt}"
            
            stream = guvenli_stream_baslat(full_prompt)
            
            if stream:
                def parser():
                    full = ""
                    for c in stream:
                        if c.text:
                            full+=c.text
                            yield c.text
                    if kaynaklar:
                        yield "\n\n**📚 Kaynaklar:**\n"
                        done = set()
                        for k in kaynaklar:
                            if k['link'] not in done:
                                yield f"- [{k['baslik']}]({k['link']})\n"
                                done.add(k['link'])
                
                resp = st.write_stream(parser)
                st.session_state.messages.append({"role": "assistant", "content": resp})
                scroll_to_bottom()
