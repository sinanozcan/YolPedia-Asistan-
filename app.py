import streamlit as st
import streamlit.components.v1 as components 
import requests
import google.generativeai as genai
import time
import json
import random

# ================= GÜVENLİ BAŞLANGIÇ =================
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
st.set_page_config(page_title=ASISTAN_ISMI, page_icon=YOLPEDIA_ICON, layout="wide")

# --- API KEY KONTROLÜ ---
if not GOOGLE_API_KEY or len(GOOGLE_API_KEY) < 10:
    st.error("❌ API Anahtarı bulunamadı! Lütfen Streamlit panelinde 'Secrets' kısmına 'API_KEY' adıyla geçerli anahtarınızı ekleyin.")
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
            processed_data = []
            for d in data:
                if not isinstance(d, dict): continue
                ham_baslik = d.get('baslik', '')
                ham_icerik = d.get('icerik', '')
                d['norm_baslik'] = tr_normalize(ham_baslik)
                d['norm_icerik'] = tr_normalize(ham_icerik)
                processed_data.append(d)
            return processed_data
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

if 'expanded_sources' not in st.session_state: st.session_state.expanded_sources = {}
if 'request_count' not in st.session_state: st.session_state.request_count = 0
if 'last_reset_time' not in st.session_state: st.session_state.last_reset_time = time.time()

if time.time() - st.session_state.last_reset_time > 3600:
    st.session_state.request_count = 0
    st.session_state.last_reset_time = time.time()

# --- SIDEBAR ---
with st.sidebar:
    st.title("Mod Seçimi")
    if st.session_state.db: st.success(f"📊 **{len(st.session_state.db)} kayıt** hazır")
    else: st.error("⚠️ Veritabanı yüklenemedi!")
    
    secilen_mod = st.radio("Can Dede nasıl yardımcı olsun?", ["Sohbet Modu", "Araştırma Modu"])
    if st.button("🗑️ Sohbeti Sıfırla"):
        st.session_state.messages = [{"role": "assistant", "content": "Sohbet sıfırlandı. Buyur can."}]
        st.rerun()

# --- HEADER ---
st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header"><img src="{CAN_DEDE_ICON}" class="dede-img"><h1 class="title-text">{ASISTAN_ISMI}</h1></div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)

# --- ARAMA ---
def alakali_icerik_bul(kelime, db):
    if not db or not kelime or len(kelime) < 3: return [], ""
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    sonuclar = []
    
    for d in db:
        puan = 0
        d_baslik = d.get('norm_baslik', '')
        d_icerik = d.get('norm_icerik', '')
        if norm_sorgu in d_baslik: puan += 200
        elif norm_sorgu in d_icerik: puan += 100
        for k in anahtarlar:
            if k in d_baslik: puan += 40
            elif k in d_icerik: puan += 10
        if puan > 50:
            sonuclar.append({
                "baslik": d.get('baslik', 'Başlıksız'),
                "link": d.get('link', '#'),
                "icerik": d.get('icerik', '')[:1500],
                "puan": puan
            })
            
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    if sonuclar:
        esik = sonuclar[0]['puan'] * 0.4
        return [s for s in sonuclar if s['puan'] >= esik], norm_sorgu
    return [], norm_sorgu

# --- AKILLI MODEL BULUCU (404 HATASINI ÇÖZER) ---
def get_best_available_model():
    """
    Sisteme 'bana şu modeli ver' diye diretmek yerine,
    'Elinde ne var?' diye sorup en uygununu seçer.
    Böylece 404 hatası imkansız olur.
    """
    try:
        # Mevcut modelleri listele
        model_list = genai.list_models()
        available_models = []
        for m in model_list:
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if not available_models:
            return None

        # Tercih sıramız (En hızlıdan yavaşa)
        preferences = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro", "gemini-pro"]
        
        for p in preferences:
            for m in available_models:
                if p in m:
                    return m # Bulduğumuz ilk uygun modeli döndür
        
        # Hiçbiri yoksa listenin ilkini ver
        return available_models[0]
    except Exception:
        # Listeleme başarısızsa varsayılanı dene
        return "gemini-1.5-flash"

# --- CEVAP FONKSİYONU ---
def can_dede_cevapla(user_prompt, kaynaklar, mod):
    if not GOOGLE_API_KEY:
        yield "❌ HATA: API Anahtarı eksik."
        return

    # --- SİSTEM YÖNERGESİ (DİL ve ÜSLUP AYARLARI) ---
    if "Sohbet" in mod:
        system_prompt = """Sen 'Can Dede'sin. Alevi-Bektaşi felsefesini benimsemiş, gönül gözü açık bir rehbersin.

        KESİN KURALLAR:
        1. DİL: Kullanıcı seninle hangi dilde konuşursa (Türkçe, İngilizce, Almanca, Fransızca vb.) mutlaka O DİLDE cevap ver.
        2. ÜSLUP: 'Selamünaleyküm' gibi kalıplar yerine 'Aşk ile', 'Merhaba Can', 'Erenler', 'Gönül Dostu' hitaplarını kullan.
        3. TERMİNOLOJİ: Ortodoks İslami terimler yerine Alevi-Bektaşi terminolojisini (Hak, Hakikat, Marifet, Dört Kapı, Rıza Şehri, Enel Hak, Pir, Mürşit) öncelikle kullan.
        4. ADAPTASYON: Kullanıcının sorusunu analiz et. Eğer soru basitse veya çocukçaysa; masalsı, sıcak ve sade bir dille anlat. Eğer soru akademik, felsefi veya derinse; tasavvufi derinliği olan (batıni) bir üslupla cevap ver.
        5. TAVIR: Asla yargılayıcı olma. Hümanist, birleştirici ve sevgi dolu ol. "Bildiğimin âlimiyim, bilmediğinin tâlibiyim" düsturuyla hareket et.
        """
        full_content = system_prompt + "\n\nKullanıcı: " + user_prompt
    else:
        if not kaynaklar:
            yield "📚 Aradığın konuyla ilgili YolPedia'da kaynak bulamadım can."
            return
        
        kaynak_metni = "\n".join([f"- {k['baslik']}: {k['icerik'][:500]}" for k in kaynaklar[:3]])
        
        system_prompt = f"""Sen bir YolPedia kütüphane asistanısın.
        GÖREV: Aşağıdaki kaynaklara dayanarak net bilgi ver.
        DİL KURALI: Kullanıcı hangi dilde sorduysa o dilde cevapla.
        KAYNAKLAR:\n{kaynak_metni}"""
        
        full_content = system_prompt + "\n\nSoru: " + user_prompt

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        
        # --- Modeli dinamik seçiyoruz ---
        model_name = get_best_available_model()
        if not model_name:
            yield "❌ Google API modellerine erişilemiyor. Lütfen anahtarınızı kontrol edin."
            return

        model = genai.GenerativeModel(model_name)
        response = model.generate_content(full_content, stream=True)
        
        for chunk in response:
            if chunk.text: yield chunk.text
            
    except Exception as e:
        yield f"⚠️ Bağlantı hatası: {str(e)}"

# --- UI AKIŞI ---
def scroll_to_bottom():
    components.html("""<script>window.parent.document.querySelector(".main").scrollTop = 100000;</script>""", height=0)

for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    with st.chat_message(msg["role"], avatar=icon):
        st.markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    if st.session_state.request_count >= 100:
        st.error("Limit doldu.")
        st.stop()
        
    st.session_state.request_count += 1
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    kaynaklar = []
    if "Araştırma" in secilen_mod:
        kaynaklar, _ = alakali_icerik_bul(prompt, st.session_state.db)
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        placeholder = st.empty()
        full_text = ""
        
        for chunk in can_dede_cevapla(prompt, kaynaklar, secilen_mod):
            full_text += chunk
            placeholder.markdown(full_text + "▌")
        
        placeholder.markdown(full_text)
        
        if "Araştırma" in secilen_mod and kaynaklar:
            st.markdown("---")
            st.markdown("**📚 Kaynaklar:**")
            for k in kaynaklar[:5]:
                st.markdown(f"• [{k['baslik']}]({k['link']})")
        
        st.session_state.messages.append({"role": "assistant", "content": full_text})
        scroll_to_bottom()
