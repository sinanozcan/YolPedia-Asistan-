import streamlit as st
import streamlit.components.v1 as components 
import google.generativeai as genai
import time
import json
import random

# --- AYARLAR ---
st.set_page_config(page_title="Can Dede", layout="wide")

# API KEY AL
GOOGLE_API_KEY = st.secrets.get("API_KEY", "")
if not GOOGLE_API_KEY:
    st.error("API Key Yok!")
    st.stop()

# --- VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open("yolpedia_data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except: return []

def tr_normalize(text):
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower() if isinstance(text, str) else ""

if 'db' not in st.session_state: st.session_state.db = veri_yukle()
if "messages" not in st.session_state: st.session_state.messages = [{"role": "assistant", "content": "Merhaba can, ben geldim."}]

# --- ARAMA ---
def icerik_bul(sorgu):
    if not st.session_state.db: return []
    sorgu = tr_normalize(sorgu)
    sonuclar = []
    for d in st.session_state.db:
        if sorgu in tr_normalize(d.get('baslik', '')):
            sonuclar.append(d)
    return sonuclar[:3]

# --- CEVAP (GARANTİ MODEL) ---
def cevap_uydur(prompt, context):
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        
        # MACERA YOK, ESKİ VE SAĞLAM MODELİ KULLANIYORUZ
        model = genai.GenerativeModel('gemini-pro')
        
        full_text = f"Sen Alevi dedesisin. Kaynaklar: {context}\nSoru: {prompt}"
        response = model.generate_content(full_text, stream=True)
        
        for chunk in response:
            if chunk.text: yield chunk.text
            
    except Exception as e:
        # HATAYI SAKLAMA, DİREKT GÖSTER
        yield f"⚠️ TEKNİK HATA: {str(e)}"

# --- ARAYÜZ ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

prompt = st.chat_input("Sor bakalım...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)
    
    context = icerik_bul(prompt)
    context_text = "\n".join([f"{c['baslik']}: {c['icerik']}" for c in context])
    
    with st.chat_message("assistant"):
        full_res = st.write_stream(cevap_uydur(prompt, context_text))
    
    st.session_state.messages.append({"role": "assistant", "content": full_res})
