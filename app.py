import streamlit as st
import streamlit.components.v1 as components 
import google.generativeai as genai
import json
import random
import time

# ================= AYARLAR =================
st.set_page_config(page_title="Can Dede | YolPedia", page_icon="🕯️", layout="wide")

# API KEY KONTROLÜ
GOOGLE_API_KEY = st.secrets.get("API_KEY", "")
if not GOOGLE_API_KEY:
    st.error("❌ API Anahtarı bulunamadı! Secrets ayarlarını kontrol et.")
    st.stop()

# --- CSS (Senin sevdiğin tasarım) ---
st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 5px; margin-bottom: 5px; }
    .dede-img { width: 80px; height: 80px; border-radius: 50%; margin-right: 15px; object-fit: cover; border: 2px solid #eee; }
    .title-text { font-size: 36px; font-weight: 700; margin: 0; color: #ffffff; }
    .subtitle-text { font-size: 18px; font-weight: 400; margin-top: 5px; color: #aaaaaa; text-align: center; }
    .top-logo-container { display: flex; justify-content: center; margin-bottom: 20px; padding-top: 10px; }
    .top-logo { width: 80px; opacity: 1.0; }
    .motto-text { text-align: center; font-size: 16px; font-style: italic; color: #cccccc; margin-bottom: 25px; font-family: 'Georgia', serif; }
    .stChatMessage { margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- İKONLAR ---
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildiğimin âlimiyim, bilmediğinin tâlibiyim!"'

# --- HEADER ---
st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header"><img src="{CAN_DEDE_ICON}" class="dede-img"><h1 class="title-text">{ASISTAN_ISMI}</h1></div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)

# --- VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open("yolpedia_data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except: return []

def tr_normalize(text):
    if not isinstance(text, str): return ""
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

if 'db' not in st.session_state: st.session_state.db = veri_yukle()
if "messages" not in st.session_state: 
    st.session_state.messages = [{"role": "assistant", "content": "Merhaba can, hoş geldin. Buyur, gönlünden ne geçiyorsa sor."}]

# --- ARAMA ---
def alakali_icerik_bul(kelime, db):
    if not db or not kelime: return []
    norm_sorgu = tr_normalize(kelime)
    sonuclar = []
    for d in db:
        puan = 0
        d_baslik = d.get('baslik', '')
        if norm_sorgu in tr_normalize(d_baslik): puan += 200
        if "gulbank" in tr_normalize(d_baslik) or "deyis" in tr_normalize(d_baslik): puan += 100
        
        if puan > 50:
            sonuclar.append({"baslik": d_baslik, "icerik": d.get('icerik', ''), "link": d.get('link', '#'), "puan": puan})
    
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    return sonuclar[:3]

# --- OTOMATİK MODEL BULUCU VE CEVAPLAYICI ---
def can_dede_cevapla(prompt, context):
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        
        # ADIM 1: SİSTEMDEKİ ÇALIŞAN MODELLERİ BUL
        # Biz isim tahmin etmiyoruz, Google'a "Eline ne var?" diye soruyoruz.
        mevcut_modeller = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                mevcut_modeller.append(m.name)
        
        if not mevcut_modeller:
            yield "⚠️ Google hesabında hiç aktif model görünmüyor. API Key veya Bölge kısıtlaması olabilir."
            return

        # ADIM 2: İLK BULDUĞUNU KULLAN (En garantisi budur)
        # Genelde 'models/gemini-pro' veya 'models/gemini-1.5-flash' ilk sırada gelir.
        secilen_model = mevcut_modeller[0] 
        
        # Model isminin başındaki 'models/' takısını temizle (bazı sürümler hata verebilir diye)
        if "/" in secilen_model:
            secilen_model = secilen_model.split("/")[-1]

        model = genai.GenerativeModel(secilen_model)
        
        # Cevabı Üret
        full_text = f"Sen Can Dedesin. Alevi-Bektaşi diliyle konuş. Kaynaklar:\n{context}\n\nSoru: {prompt}"
        response = model.generate_content(full_text, stream=True)
        
        for chunk in response:
            if chunk.text: yield chunk.text
            
    except Exception as e:
        yield f"⚠️ Hata: {str(e)}"

# --- ARAYÜZ AKIŞI ---
def scroll_to_bottom():
    components.html("""<script>window.parent.document.querySelector(".main").scrollTop = 100000;</script>""", height=0)

for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    with st.chat_message(msg["role"], avatar=icon):
        st.markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
    context_text = "\n".join([f"{k['baslik']}: {k['icerik'][:1000]}" for k in kaynaklar])
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        placeholder = st.empty()
        full_text = ""
        with st.spinner("Can Dede düşünüyor..."):
            for chunk in can_dede_cevapla(prompt, context_text):
                full_text += chunk
                placeholder.markdown(full_text + "▌")
        placeholder.markdown(full_text)
        
        if kaynaklar:
            st.markdown("---")
            for k in kaynaklar: st.markdown(f"• [{k['baslik']}]({k['link']})")
            
        st.session_state.messages.append({"role": "assistant", "content": full_text})
        scroll_to_bottom()
