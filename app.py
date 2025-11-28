import streamlit as st
import streamlit.components.v1 as components 
import requests
import google.generativeai as genai
import time
import json
import random
from PIL import Image
from io import BytesIO

# ================= AYARLAR =================
API_KEYS = [
    st.secrets.get("API_KEY", ""),
    st.secrets.get("API_KEY_2", ""),
    st.secrets.get("API_KEY_3", ""),
    st.secrets.get("API_KEY_4", ""),
    st.secrets.get("API_KEY_5", "")
]
# Boşlukları temizle
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
    .stChatMessage { margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header"><img src="{CAN_DEDE_ICON}" class="dede-img"><h1 class="title-text">Can Dede</h1></div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)

# --- VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: 
            data = json.load(f)
            # Basit normalizasyon
            for d in data:
                d['norm_baslik'] = d['baslik'].lower()
                d['norm_icerik'] = d['icerik'].lower()
            return data
    except: return []

if 'db' not in st.session_state: st.session_state.db = veri_yukle()

# --- ARTIK HATA YAPMAYAN MODEL SEÇİCİ ---
@st.cache_resource
def get_working_model_name():
    """
    Bu fonksiyon sistemi tarar ve çalışan İLK modeli bulur.
    Böylece 'model bulunamadı' hatası imkansız hale gelir.
    """
    if not API_KEYS: return None
    try:
        genai.configure(api_key=API_KEYS[0])
        # Sistemdeki modelleri listele
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # Flash veya Pro öncelikli, yoksa ne varsa o.
                if 'gemini' in m.name:
                    return m.name
        return "gemini-pro" # Hiçbir şey bulamazsa varsayılan
    except:
        return "gemini-pro"

MODEL_ADI = get_working_model_name()

# --- ARAMA MOTORU ---
def alakali_icerik_bul(kelime, db):
    sorgu = kelime.lower()
    sonuclar = []
    
    for d in db:
        puan = 0
        if sorgu in d['norm_baslik']: puan += 100
        elif sorgu in d['norm_icerik']: puan += 50
        
        if puan > 0:
            sonuclar.append(d)
    
    # En iyi 3 sonucu al
    sonuclar = sorted(sonuclar, key=lambda x: len(x['icerik']), reverse=True)[:3]
    
    context = ""
    kaynaklar = []
    for s in sonuclar:
        context += f"\nKonu: {s['baslik']}\nBilgi: {s['icerik'][:3000]}\n"
        kaynaklar.append({"baslik": s['baslik'], "link": s['link']})
        
    return context, kaynaklar

# --- YANIT ÜRETİCİ ---
def can_dede_cevapla(user_prompt, chat_history, context_data):
    if not API_KEYS:
        yield "Sistem hatası: API anahtarı yok."
        return

    # Basit ve net talimat
    system_prompt = f"""
    Sen Can Dede'sin. Alevi-Bektaşi kültürüne hakim, bilge bir rehbersin.
    Kullanıcıya nazikçe, "Erenler", "Can" gibi hitaplarla cevap ver.
    
    KAYNAK BİLGİLER:
    {context_data}
    
    Yukarıdaki bilgileri kullanarak soruyu cevapla. Bilgi yoksa genel bilginden nazikçe cevapla.
    """
    
    # Sohbet geçmişini modele uygun hale getir
    contents = []
    contents.append({"role": "user", "parts": [system_prompt]})
    contents.append({"role": "model", "parts": ["Tamam erenler, dinliyorum."]});
    
    for msg in chat_history[-3:]: # Sadece son 3 mesajı hatırla (Hız için)
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [msg["content"]]})
    
    contents.append({"role": "user", "parts": [user_prompt]})

    # Anahtarları sırayla dene
    random.shuffle(API_KEYS)
    for key in API_KEYS:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(MODEL_ADI) # Bulunan garanti modeli kullan
            response = model.generate_content(contents, stream=True)
            
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            return # Başarılıysa çık
            
        except Exception:
            time.sleep(0.5)
            continue # Diğer anahtara geç

    yield "Şu an sistemlerimiz çok yoğun erenler, lütfen birazdan tekrar dene."

# --- ARAYÜZ ---
def scroll_to_bottom():
    components.html("""<script>window.parent.document.querySelector(".main").scrollTop = 100000;</script>""", height=0)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Merhaba Erenler! Ben Can Dede. Buyur, nasıl yardımcı olabilirim?"}]

for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    st.chat_message(msg["role"], avatar=icon).markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    baglam, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        full_response_container = st.empty()
        full_text = ""
        
        # Yanıtı üret
        stream = can_dede_cevapla(prompt, st.session_state.messages[:-1], baglam)
        
        for chunk in stream:
            full_text += chunk
            full_response_container.markdown(full_text + "▌")
        
        # Kaynakları ekle
        if kaynaklar and "sistemlerimiz çok yoğun" not in full_text:
            link_text = "\n\n**📚 Kaynaklar:**\n"
            seen = set()
            for k in kaynaklar:
                if k['link'] not in seen:
                    link_text += f"- [{k['baslik']}]({k['link']})\n"
                    seen.add(k['link'])
            full_text += link_text
            
        full_response_container.markdown(full_text)
        st.session_state.messages.append({"role": "assistant", "content": full_text})
        scroll_to_bottom()
