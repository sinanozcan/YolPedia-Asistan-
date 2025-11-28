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
# Anahtarları temizle
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
            for d in data:
                d['norm_baslik'] = tr_normalize(d['baslik'])
                d['norm_icerik'] = tr_normalize(d['icerik'])
            return data
    except: return []

def tr_normalize(text):
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

if 'db' not in st.session_state: st.session_state.db = veri_yukle()

# --- ARAMA MOTORU ---
def alakali_icerik_bul(kelime, db):
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    
    sonuclar = []
    for d in db:
        puan = 0
        if norm_sorgu in d['norm_baslik']: puan += 100
        elif norm_sorgu in d['norm_icerik']: puan += 50
        for k in anahtarlar:
            if k in d['norm_baslik']: puan += 15
            elif k in d['norm_icerik']: puan += 5     
        if puan > 0:
            sonuclar.append({"veri": d, "puan": puan})
    
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    en_iyiler = sonuclar[:4] 
    
    context_text = ""
    kaynaklar = []
    
    for item in en_iyiler:
        v = item['veri']
        context_text += f"\n--- BİLGİ KAYNAĞI: {v['baslik']} ---\n{v['icerik'][:4000]}\n"
        kaynaklar.append({"baslik": v['baslik'], "link": v['link']})
        
    return context_text, kaynaklar

# --- RÖNTGEN MODU: HATA DETAYLARINI YAKALA ---
# Bu fonksiyon hata loglarını session state'e kaydeder
def can_dede_cevapla(user_prompt, chat_history, context_data):
    if not API_KEYS:
        yield "HATA: API Anahtarı bulunamadı (Secrets dosyası boş)."
        return

    system_prompt = f"""
    Sen 'Can Dede'sin. Bilge, tasavvuf ehli, Alevi-Bektaşi kültürüne hakim bir rehbersin.
    BİLGİ KAYNAKLARI:
    {context_data if context_data else "Genel sohbet et."}
    """

    contents = []
    contents.append({"role": "user", "parts": [system_prompt]})
    contents.append({"role": "model", "parts": ["Anlaşıldı."]})
    for msg in chat_history[-4:]:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [msg["content"]]})
    contents.append({"role": "user", "parts": [user_prompt]})

    modeller = ["gemini-1.5-flash", "gemini-pro"]
    
    # Hata raporunu temizle
    st.session_state.son_hata_raporu = []

    for key in API_KEYS:
        genai.configure(api_key=key)
        for model_adi in modeller:
            try:
                model = genai.GenerativeModel(model_adi)
                response = model.generate_content(contents, stream=True)
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return # Başarılı oldu, çık

            except Exception as e:
                hata_kodu = str(e)
                # Hatayı kaydet
                st.session_state.son_hata_raporu.append(f"Anahtar Sonu: ...{key[-5:]} | Model: {model_adi} | HATA: {hata_kodu}")
                time.sleep(1)
                continue 

    yield "Şu anda tefekkürdeyim (Bağlantı Sorunu)."

# --- ARAYÜZ ---
def scroll_to_bottom():
    components.html("""<script>window.parent.document.querySelector(".main").scrollTop = 100000;</script>""", height=0)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Merhaba Erenler! Ben Can Dede."}]
if "son_hata_raporu" not in st.session_state:
    st.session_state.son_hata_raporu = []

for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    st.chat_message(msg["role"], avatar=icon).markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    baglam_metni, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        full_response_container = st.empty()
        full_text = ""
        
        stream = can_dede_cevapla(prompt, st.session_state.messages[:-1], baglam_metni)
        
        for chunk in stream:
            full_text += chunk
            full_response_container.markdown(full_text + "▌")
        
        # Eğer hata varsa RAPORU GÖSTER
        if "tefekkürdeyim" in full_text:
            with st.expander("🛠️ DETAYLI HATA RAPORU (BUNU BANA GÖNDER)", expanded=True):
                if not st.session_state.son_hata_raporu:
                    st.write("Hata yakalanamadı ama bağlantı kurulamadı.")
                for rapor in st.session_state.son_hata_raporu:
                    st.code(rapor, language="text")
        
        if kaynaklar and "tefekkürdeyim" not in full_text:
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
