import streamlit as st
import streamlit.components.v1 as components
import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import google.generativeai as genai
import sys
import time
import json
from PIL import Image
from io import BytesIO

# ================= AYARLAR =================
API_KEY = st.secrets["API_KEY"]
WP_USER = st.secrets["WP_USER"]
WP_PASS = st.secrets["WP_PASS"]
WEBSITE_URL = "https://yolpedia.eu" 
DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildigimin âlimiyim, bilmedigimin tâlibiyim!"'

# --- RESİMLER ---
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/cropped-Yolpedia-Favicon-e1620391336469.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
# ===========================================

# --- FAVICON ---
try:
    response = requests.get(YOLPEDIA_ICON, timeout=5)
    favicon = Image.open(BytesIO(response.content))
except:
    favicon = "🤖"

st.set_page_config(page_title=ASISTAN_ISMI, page_icon=favicon)

# --- CSS TASARIM ---
st.markdown("""
<style>
    .main-header { 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        margin-top: 5px; 
        margin-bottom: 5px; 
    }
    .dede-img { 
        width: 80px; 
        height: 80px; 
        border-radius: 50%; 
        margin-right: 15px; 
        object-fit: cover;
        border: 2px solid #eee; 
    }
    .title-text { 
        font-size: 36px; 
        font-weight: 700; 
        margin: 0; 
        color: #ffffff; 
    }
    .top-logo-container {
        display: flex;
        justify-content: center;
        margin-bottom: 15px;
        padding-top: 10px;
    }
    .top-logo {
        width: 50px;
        opacity: 0.8; 
    }
    .motto-text { 
        text-align: center; 
        font-size: 16px; 
        font-style: italic; 
        color: #cccccc; 
        margin-bottom: 25px; 
        font-family: 'Georgia', serif; 
    }
    @media (prefers-color-scheme: light) { 
        .title-text { color: #000000; } 
        .motto-text { color: #555555; }
        .dede-img { border: 2px solid #ccc; }
    }
    .stButton button { width: 100%; border-radius: 10px; font-weight: bold; border: 1px solid #ccc; }
    
    /* Gölge sorununu çözen stil */
    .element-container { margin-bottom: 0px !important; }
</style>
""", unsafe_allow_html=True)

# --- SAYFA GÖRÜNÜMÜ ---
st.markdown(
    f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header">
        <img src="{CAN_DEDE_ICON}" class="dede-img">
        <h1 class="title-text">Can Dede</h1>
    </div>
    <div class="motto-text">{MOTTO}</div>
    """,
    unsafe_allow_html=True
)

# --- OTOMATİK KAYDIRMA ---
def otomatik_kaydir():
    js = """
    <script>
        var body = window.parent.document.querySelector(".main");
        body.scrollTop = body.scrollHeight;
    </script>
    """
    components.html(js, height=0)

genai.configure(api_key=API_KEY)

# --- MODELİ BUL ---
@st.cache_resource
def model_yukle():
    generation_config = {"temperature": 0.1, "max_output_tokens": 8192}
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name.lower():
                    return genai.GenerativeModel(m.name, generation_config=generation_config)
        return genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
    except:
        return None

model = model_yukle()

# --- 1. AJAN: NİYET OKUYUCU ---
def niyet_analizi(soru):
    try:
        prompt = f"""
        GİRDİ: "{soru}"
        KARAR:
        - Bilgi araması: "ARAMA"
        - Sohbet: "SOHBET"
        CEVAP: "ARAMA" veya "SOHBET"
        """
        response = model.generate_content(prompt)
        return response.text.strip().upper()
    except:
        return "ARAMA"

# --- 2. AJAN: DİL DEDEKTİFİ ---
def dil_tespiti(soru):
    try:
        # Basit dil tespiti
        prompt = f"""
        GİRDİ: "{soru}"
        GÖREV: Bu cümlenin yazıldığı dili tespit et. (Turkish, English, German, French...)
        CEVAP (Sadece dil adı):
        """
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return "Turkish"

# --- 3. AJAN: KONU AYIKLAYICI ---
def anahtar_kelime_ayikla(soru):
    try:
        prompt = f"""
        GİRDİ: "{soru}"
        GÖREV: Kullanıcının ASIL MERAK ETTİĞİ KONUYU bul. 
        Hitapları (Dedem, Can, Hocam) ve soru eklerini at.
        CEVAP:
        """
        response = model.generate_content(prompt)
        text = response.text.strip()
        return text if len(text) > 1 else soru
    except:
        return soru

# --- VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            veriler = json.load(f)
        return veriler
    except FileNotFoundError:
        return []

if 'db' not in st.session_state:
    with st.spinner('Can Dede hazırlanıyor...'):
        st.session_state.db = veri_yukle()

# --- YARDIMCI FONKSİYONLAR ---
def tr_normalize(metin):
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

def alakali_icerik_bul(temiz_kelime, tum_veriler):
    soru_temiz = tr_normalize(temiz_kelime)
    anahtar = [k for k in soru_temiz.split() if len(k) > 2]
    
    puanlanmis = []
    for veri in tum_veriler:
        baslik_norm = tr_normalize(veri['baslik'])
        icerik_norm = tr_normalize(veri['icerik'])
        puan = 0
        if soru_temiz in baslik_norm: puan += 100
        elif soru_temiz in icerik_norm: puan += 40
        for k in anahtar:
            if k in baslik_norm: puan += 10
            elif k in icerik_norm: puan += 2
        if puan > 0:
            puanlanmis.append({"veri": veri, "puan": puan})
    
    puanlanmis.sort(key=lambda x: x['puan'], reverse=True)
    en_iyiler = puanlanmis[:7]
    
    bulunanlar = ""
    kaynaklar = []
    for item in en_iyiler:
        v = item['veri']
        bulunanlar += f"\n--- BAŞLIK: {v['baslik']} ---\nİÇERİK:\n{v['icerik'][:12000]}\n"
        kaynaklar.append({"baslik": v['baslik'], "link": v['link']})
        
    return bulunanlar, kaynaklar

# --- SOHBET GEÇMİŞİ ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Merhaba Erenler! Ben Can Dede. YolPedia rehberinizim. Size nasıl yardımcı olabilirim?"}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

def detay_tetikle():
    st.session_state.detay_istendi = True

# --- GİRİŞ ---
prompt = st.chat_input("Can Dede'ye sor...")

is_user_input = prompt is not None
is_detai
