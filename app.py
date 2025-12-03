import streamlit as st
import streamlit.components.v1 as components 
import requests
import google.generativeai as genai
import time
import json
import random

# ================= GÜVENLİ BAŞLANGIÇ & AYARLAR =================
# --- OPTİMİZAYON AYARLARI ---
MAX_MESSAGE_LIMIT = 20     # Günlük soru hakkı
MIN_TIME_DELAY = 2         # Seri tıklama engeli (saniye)
# ----------------------------

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
    
    /* Spinner Rengi */
    .stSpinner > div {
        border-top-color: #ff4b4b !important;
    }
</style>
""", unsafe_allow_html=True)

# --- VERİ YÜKLEME (SAĞLAM VERSİYON) ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: 
            content = f.read()
            if not content: return []
            data = json.loads(content)
            
            processed_data = []
            for d in data:
                if not isinstance(d, dict): continue
                ham_baslik = d.get('baslik', '')
                ham_icerik = d.get('icerik', '')
                d['norm_baslik'] = tr_normalize(ham_baslik)
                d['norm_icerik'] = tr_normalize(ham_icerik)
                processed_data.append(d)
            return processed_data
    except Exception as e:
        # Hata varsa kullanıcıya yansıtma, boş liste dön (Uygulama çökmesin)
        return []

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
if 'last_request_time' not in st.session_state: st.session_state.last_request_time = 0

# Bir saat geçtiyse sayacı sıfırla
if time.time() - st.session_state.last_reset_time > 3600:
    st.session_state.request_count = 0
    st.session_state.last_reset_time = time.time()

# --- SIDEBAR ---
with st.sidebar:
    st.title("Mod Seçimi")
    if st.session_state.db: st.success(f"📊 **{len(st.session_state.db)} kayıt** hazır")
    else: st.error("⚠️ Veritabanı yüklenemedi!")
    
    secilen_mod = st.radio("Can Dede nasıl yardımcı olsun?", ["Sohbet Modu", "Araştırma Modu"])
    
    kalan_hak = MAX_MESSAGE_LIMIT - st.session_state.request_count
    if kalan_hak > 0:
        st.info(f"⏳ Kalan Soru Hakkı: **{kalan_hak}**")
    else:
        st.error("🛑 Günlük limit doldu can.")

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
        
        # Tam eşleşme
        if norm_sorgu in d_baslik: puan += 200
        elif norm_sorgu in d_icerik: puan += 100
        
        # Kelime bazlı eşleşme
        for k in anahtarlar:
            if k in d_baslik: puan += 40
            elif k in d_icerik: puan += 10
            
        # ÖZEL İÇERİK BOOST (Gülbank ve Deyişler öne çıksın)
        ozel_terimler = ["gulbank", "deyis", "nefes", "duvaz", "siir", "tercuman"]
        if any(t in d_baslik for t in ozel_terimler):
            if puan > 0: puan += 300 # Eğer alakalıysa onu en tepeye taşı
            
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

# --- AKILLI MODEL BULUCU ---
def get_best_available_model():
    try:
        model_list = genai.list_models()
        available_models = []
        for m in model_list:
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if not available_models: return None
        preferences = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro", "gemini-pro"]
        for p in preferences:
            for m in available_models:
                if p in m: return m
        return available_models[0]
    except Exception:
        return "gemini-1.5-flash"

# --- YEREL CEVAP KONTROLÜ (KOTA DOSTU) ---
def yerel_cevap_kontrol(text):
    text = tr_normalize(text)
    selamlar = ["merhaba", "selam", "selamun aleykum", "gunaydin", "iyi aksamlar"]
    hal_hatir = ["nasilsin", "naber", "ne var ne yok"]
    kimlik = ["sen kimsin", "adın ne", "necisin"]
    
    if any(s == text for s in selamlar):
        return random.choice(["Aşk ile merhaba can.", "Selam olsun gönlü güzel olana.", "Merhaba erenler, hoş geldin."])
    if any(h in text for h in hal_hatir):
        return random.choice(["Şükür Hak'ka, hizmetteyiz.", "Gönüller bir olsun, biz iyiyiz can."])
    if any(k in text for k in kimlik):
        return "Ben Can Dede. YolPedia'nın hizmetkârıyım. Gönül kırmaz, yol sorana yoldaş olurum."
    return None

# --- CEVAP FONKSİYONU ---
def can_dede_cevapla(user_prompt, kaynaklar, mod):
    if not GOOGLE_API_KEY:
        yield "❌ HATA: API Anahtarı eksik."
        return

    # Yerel cevap (Bedava)
    yerel_cevap = yerel_cevap_kontrol(user_prompt)
    if yerel_cevap:
        time.sleep(0.5) 
        yield yerel_cevap
        return

    # Sistem Promptu
    if "Sohbet" in mod:
        system_prompt = """Sen 'Can Dede'sin. Alevi-Bektaşi felsefesini benimsemiş bir rehbersin.
        KURALLAR:
        1. DİL: Kullanıcı hangi dilde sorarsa o dilde cevapla.
        2. ÜSLUP: 'Aşk ile', 'Can', 'Erenler' hitaplarını kullan.
        3. İÇERİK: Sorulan soru bir dua, gülbank veya deyiş ise; KAYNAKLAR kısmındaki metni birebir, değiştirmeden oku.
        4. TAVIR: Sevgi dolu, birleştirici ol.
        """
        # Gülbank soruluyorsa kaynakları da prompta ekle ki ezberden okumasın
        if kaynaklar:
             kaynak_metni = "\n".join([f"- {k['baslik']}: {k['icerik']}" for k in kaynaklar[:2]])
             full_content = system_prompt + f"\n\nREFERANS KAYNAKLAR (Bunları kullan):\n{kaynak_metni}\n\nKullanıcı: " + user_prompt
        else:
             full_content = system_prompt + "\n\nKullanıcı: " + user_prompt
    else:
        if not kaynaklar:
            yield "📚 Aradığın konuyla ilgili YolPedia'da kaynak bulamadım can."
            return
        
        kaynak_metni = "\n".join([f"- {k['baslik']}: {k['icerik'][:800]}" for k in kaynaklar[:3]])
        system_prompt = f"""Sen YolPedia asistanısın.
        GÖREV: Aşağıdaki kaynaklara dayanarak net bilgi ver.
        DİL KURALI: Kullanıcı hangi dilde sorduysa o dilde cevapla.
        KAYNAKLAR:\n{kaynak_metni}"""
        full_content = system_prompt + "\n\nSoru: " + user_prompt

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model_name = get_best_available_model()
        if not model_name:
            yield "❌ Google API erişimi yok."
            return

        model = genai.GenerativeModel(model_name)
        response = model.generate_content(full_content, stream=True)
        
        for chunk in response:
            if chunk.text: yield chunk.text
            
    except Exception as e:
        yield f"⚠️ Bağlantı hatası: {str(e)}"

# --- SCROLL ---
def scroll_to_bottom():
    js = """<script>var body = window.parent.document.querySelector(".main"); body.scrollTop = body.scrollHeight;</script>"""
    components.html(js, height=0)

# --- UI AKIŞI ---
for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    with st.chat_message(msg["role"], avatar=icon):
        st.markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    # Limit Kontrolleri
    if st.session_state.request_count >= MAX_MESSAGE_LIMIT:
        st.error("🛑 Günlük soru limiti doldu.")
        st.stop()
        
    current_time = time.time()
    if current_time - st.session_state.last_request_time < MIN_TIME_DELAY:
        st.warning("⏳ Biraz yavaş can...")
        st.stop()
    
    st.session_state.last_request_time = current_time
    st.session_state.request_count += 1

    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    kaynaklar = []
    # Hem sohbet hem araştırma modunda veritabanına bak ki gülbankları bulsun
    kaynaklar, _ = alakali_icerik_bul(prompt, st.session_state.db)
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        placeholder = st.empty()
        full_text = ""
        
        with st.spinner("Can Dede tefekküre daldı..."):
            response_generator = can_dede_cevapla(prompt, kaynaklar, secilen_mod)
            try:
                first_chunk = next(response_generator)
                full_text += first_chunk
                placeholder.markdown(full_text + "▌")
            except StopIteration: pass
            except Exception as e: full_text = f"Hata: {e}"

        for chunk in response_generator:
            full_text += chunk
            placeholder.markdown(full_text + "▌")
        
        placeholder.markdown(full_text)
        
        if kaynaklar and "Araştırma" in secilen_mod:
            st.markdown("---")
            st.markdown("**📚 Kaynaklar:**")
            for k in kaynaklar[:5]:
                st.markdown(f"• [{k['baslik']}]({k['link']})")
        
        st.session_state.messages.append({"role": "assistant", "content": full_text})
        scroll_to_bottom()
