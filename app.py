import streamlit as st
import streamlit.components.v1 as components 
import requests
import google.generativeai as genai
import time
import json
import random

# ================= AYARLAR =================
MAX_MESSAGE_LIMIT = 40
MIN_TIME_DELAY = 1

GOOGLE_API_KEY = None
try:
    GOOGLE_API_KEY = st.secrets.get("API_KEY", "")
except Exception:
    GOOGLE_API_KEY = ""

DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildiğimin âlimiyim, bilmediğinin tâlibiyim!"'
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"

# --- SAYFA AYARLARI ---
st.set_page_config(page_title=ASISTAN_ISMI, page_icon=YOLPEDIA_ICON, layout="centered")

if not GOOGLE_API_KEY:
    st.error("❌ API Anahtarı eksik!")
    st.stop()

# --- CSS (Sadece Sohbet Balonları İçin) ---
st.markdown("""
<style>
    .stChatMessage { margin-bottom: 10px; }
    .stSpinner > div { border-top-color: #ff4b4b !important; }
    /* Streamlit'in üst boşluğunu alalım */
    .block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# --- VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: 
            return json.load(f)
    except: return []

def tr_normalize(text):
    if not isinstance(text, str): return ""
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

if 'db' not in st.session_state: st.session_state.db = veri_yukle()

if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant", 
        "content": "Merhaba, Can Dost! Ben Can Dede. Sol menüden istediğin modu seç:\n\n• **Sohbet Modu:** Birlikte yol üzerine konuşuruz, gönül muhabbeti ederiz.\n\n• **Araştırma Modu:** YolPedia arşivinden sana kaynak sunarım.\n\nBuyur Erenler, hangi modda buluşalım?"
    }]

if 'request_count' not in st.session_state: st.session_state.request_count = 0
if 'last_reset_time' not in st.session_state: st.session_state.last_reset_time = time.time()
if 'last_request_time' not in st.session_state: st.session_state.last_request_time = 0

if time.time() - st.session_state.last_reset_time > 3600:
    st.session_state.request_count = 0
    st.session_state.last_reset_time = time.time()

# --- SIDEBAR ---
with st.sidebar:
    st.title("Mod Seçimi")
    secilen_mod = st.radio("Can Dede nasıl yardımcı olsun?", ["Sohbet Modu", "Araştırma Modu"])
    if st.button("🗑️ Sohbeti Sıfırla"):
        st.session_state.messages = [{"role": "assistant", "content": "Sohbet sıfırlandı. Buyur can."}]
        st.rerun()

# --- HEADER (HTML İLE KESİN HİZALAMA) ---
# Burası CSS ile değil, saf HTML tablosu mantığıyla hizalandı. Kayması imkansız.
st.markdown(f"""
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; margin-bottom: 20px;">
        <div style="display: flex; align-items: center; justify-content: center; gap: 15px;">
            <img src="{CAN_DEDE_ICON}" style="width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 2px solid #eee;">
            <h1 style="font-size: 34px; font-weight: 700; margin: 0; padding: 0; color: #ffffff; line-height: 1;">{ASISTAN_ISMI}</h1>
        </div>
        <div style="margin-top: 5px; font-size: 16px; font-style: italic; color: #cccccc; font-family: 'Georgia', serif;">
            {MOTTO}
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- ARAMA ---
def alakali_icerik_bul(kelime, db):
    if not db or not kelime or len(kelime) < 3: return [], ""
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    sonuclar = []
    
    for d in db:
        puan = 0
        d_baslik = d.get('baslik', '')
        d_icerik = d.get('icerik', '')
        if norm_sorgu in tr_normalize(d_baslik): puan += 200
        elif norm_sorgu in tr_normalize(d_icerik): puan += 100
        for k in anahtarlar:
            if k in tr_normalize(d_baslik): puan += 40
            elif k in tr_normalize(d_icerik): puan += 10
        
        if any(x in tr_normalize(d_baslik) for x in ["gulbank", "deyis", "nefes", "siir"]):
            puan += 300

        if puan > 50:
            sonuclar.append({"baslik": d.get('baslik', 'Başlıksız'), "link": d.get('link', '#'), "icerik": d.get('icerik', '')[:1500], "puan": puan})
            
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    return sonuclar[:5], norm_sorgu

# --- YEREL CEVAP ---
def yerel_cevap_kontrol(text):
    text = tr_normalize(text)
    selamlar = ["merhaba", "selam", "selamun aleykum", "gunaydin"]
    hal_hatir = ["nasilsin", "naber", "ne var ne yok"]
    if any(s == text for s in selamlar): return random.choice(["Aşk ile merhaba can.", "Selam olsun, hoş geldin."])
    if any(h in text for h in hal_hatir): return "Şükür Hak'ka, hizmetteyiz can."
    return None

# --- CEVAP MOTORU ---
def can_dede_cevapla(user_prompt, kaynaklar, mod):
    if not GOOGLE_API_KEY:
        yield "❌ HATA: API Anahtarı eksik."
        return

    yerel = yerel_cevap_kontrol(user_prompt)
    if yerel:
        time.sleep(0.5); yield yerel; return

    system_prompt = "Sen 'Can Dede'sin. Alevi-Bektaşi felsefesini benimsemiş bir rehbersin. Üslubun 'Aşk ile', 'Can', 'Erenler' şeklinde olsun."
    if "Sohbet" in mod:
        if kaynaklar:
             kaynak_metni = "\n".join([f"- {k['baslik']}: {k['icerik']}" for k in kaynaklar[:2]])
             full_content = system_prompt + f"\n\nKAYNAKLAR (Bunları kullan):\n{kaynak_metni}\n\nKullanıcı: " + user_prompt
        else:
             full_content = system_prompt + "\n\nKullanıcı: " + user_prompt
    else:
        if not kaynaklar: yield "📚 Aradığın konuyla ilgili kaynak bulamadım can."; return
        kaynak_metni = "\n".join([f"- {k['baslik']}: {k['icerik'][:800]}" for k in kaynaklar[:3]])
        full_content = f"Sen YolPedia asistanısın. Sadece bu kaynaklara göre cevapla:\n{kaynak_metni}\n\nSoru: {user_prompt}"

    genai.configure(api_key=GOOGLE_API_KEY)
    
    modeller = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    
    basarili = False
    for m_isim in modeller:
        try:
            model = genai.GenerativeModel(m_isim)
            response = model.generate_content(full_content, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
                    basarili = True
            if basarili: break 
        except Exception:
            continue 

    if not basarili:
        yield "⚠️ Can Dost, Google bağlantısında geçici bir sorun var. Birazdan tekrar dene."

# --- UI AKIŞI ---
def scroll_to_bottom():
    components.html("""<script>window.parent.document.querySelector(".main").scrollTop = 100000;</script>""", height=0)

for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    with st.chat_message(msg["role"], avatar=icon):
        st.markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    if st.session_state.request_count >= MAX_MESSAGE_LIMIT:
        st.error("🛑 Limit doldu."); st.stop()
    
    if time.time() - st.session_state.last_request_time < MIN_TIME_DELAY:
        st.warning("⏳ Yavaş can..."); st.stop()
        
    st.session_state.request_count += 1
    st.session_state.last_request_time = time.time()
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    kaynaklar, _ = alakali_icerik_bul(prompt, st.session_state.db)
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        placeholder = st.empty()
        full_text = ""
        with st.spinner("Can Dede tefekküre daldı..."):
            for chunk in can_dede_cevapla(prompt, kaynaklar, secilen_mod):
                full_text += chunk
                placeholder.markdown(full_text + "▌")
        placeholder.markdown(full_text)
        
        if kaynaklar and "Araştırma" in secilen_mod:
            st.markdown("---")
            st.markdown("**📚 Kaynaklar:**")
            for k in kaynaklar[:3]: st.markdown(f"• [{k['baslik']}]({k['link']})")
            
        st.session_state.messages.append({"role": "assistant", "content": full_text})
        scroll_to_bottom()
        
