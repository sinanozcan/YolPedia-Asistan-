import streamlit as st
import streamlit.components.v1 as components 
import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import google.generativeai as genai
import sys
import time
import json
import random
from PIL import Image
from io import BytesIO

# ================= AYARLAR =================
# Çoklu Anahtar Listesi
API_KEYS = [
    st.secrets.get("API_KEY", ""),
    st.secrets.get("API_KEY_2", ""),
    st.secrets.get("API_KEY_3", ""),
    st.secrets.get("API_KEY_4", ""),
    st.secrets.get("API_KEY_5", "")
]
API_KEYS = [k for k in API_KEYS if k] # Boş olanları temizle

DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildigimin âlimiyim, bilmedigimin tâlibiyim!"'

# --- RESİMLER ---
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"
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
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 5px; margin-bottom: 5px; }
    .dede-img { width: 80px; height: 80px; border-radius: 50%; margin-right: 15px; object-fit: cover; border: 2px solid #eee; }
    .title-text { font-size: 36px; font-weight: 700; margin: 0; color: #ffffff; }
    .top-logo-container { display: flex; justify-content: center; margin-bottom: 45px; padding-top: 10px; }
    .top-logo { width: 90px; opacity: 1.0; }
    .motto-text { text-align: center; font-size: 16px; font-style: italic; color: #cccccc; margin-bottom: 25px; font-family: 'Georgia', serif; }
    .stChatMessage .avatar { width: 45px !important; height: 45px !important; }
    @media (prefers-color-scheme: light) { 
        .title-text { color: #000000; } 
        .motto-text { color: #555555; }
        .dede-img { border: 2px solid #ccc; }
    }
    .stButton button { width: 100%; border-radius: 10px; font-weight: bold; border: 1px solid #ccc; }
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

# --- FONKSİYON: OTOMATİK KAYDIRMA ---
def scroll_to_bottom():
    js = """
    <script>
        var body = window.parent.document.querySelector(".main");
        body.scrollTop = body.scrollHeight;
    </script>
    """
    components.html(js, height=0)

# --- GÜVENLİ VE GARANTİLİ YANIT ÜRETİCİ (V4 - OTOMATİK MODEL BULUCU) ---
def guvenli_stream_baslat(full_prompt):
    """
    Model ismini tahmin etmez. Doğrudan API'ye 'Elinizde ne var?' diye sorar
    ve 'generateContent' özelliğini destekleyen İLK modeli seçip kullanır.
    Böylece 404 hatası ve çökme imkansız hale gelir.
    """
    # 1. Anahtarları Kontrol Et
    gecerli_anahtarlar = [k for k in API_KEYS if k and len(k) > 10]
    if not gecerli_anahtarlar:
        st.error("❌ HATA: secrets.toml dosyasında geçerli API anahtarı yok.")
        return None

    random.shuffle(gecerli_anahtarlar)
    hata_logu = []

    # 2. Anahtarları Dene
    for key in gecerli_anahtarlar:
        try:
            genai.configure(api_key=key)
            
            # --- KRİTİK NOKTA: Model ismini biz uydurmuyoruz, Google'dan istiyoruz ---
            bulunan_model = None
            
            try:
                # Mevcut modelleri listele
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        # Öncelik sırasına göre tercih yap
                        if 'flash' in m.name and '1.5' in m.name: # Varsa Flash 1.5 kullan
                            bulunan_model = m.name
                            break
                        if 'pro' in m.name and '1.5' in m.name: # Yoksa Pro 1.5
                            bulunan_model = m.name
                
                # Eğer özel bir şey bulamazsa, listenin en başındakini al (örn: gemini-pro)
                if not bulunan_model:
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods:
                            bulunan_model = m.name
                            break
            except:
                # Liste alamazsa manuel yedek
                bulunan_model = "models/gemini-1.5-flash"
            
            if not bulunan_model:
                hata_logu.append(f"Anahtar: {key[:5]}... -> Hiçbir model bulunamadı.")
                continue

            # Modeli Bulduk, Ayarlayıp Çalıştıralım
            config = {"temperature": 0.3, "max_output_tokens": 8000}
            guvenlik = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
            ]
            
            api_model = genai.GenerativeModel(bulunan_model, generation_config=config, safety_settings=guvenlik)
            return api_model.generate_content(full_prompt, stream=True)

        except Exception as e:
            err_msg = str(e).lower()
            hata_logu.append(f"Hata: {err_msg[:100]}")
            
            if "429" in err_msg or "quota" in err_msg:
                time.sleep(2) # Hız limiti hatasında bekle
            continue

    # --- BURAYA GELDİYSE HİÇBİR ŞEY ÇALIŞMAMIŞTIR ---
    st.error("⚠️ Can Dede şu an bağlantı kuramadı.")
    with st.expander("Son Teknik Durum (Geliştirici İçin)"):
        st.write("Kütüphane Sürümü: google-generativeai >= 0.8.3 olmalı.")
        for log in hata_logu:
            st.code(log, language="text")
            
    return None

# --- BASİT API YÖNETİCİSİ (Yardımcı Araçlar İçin) ---
def get_model():
    # Bu fonksiyon sadece dil tespiti gibi küçük işler için hızlı bir model döndürür
    if not API_KEYS: return None
    try:
        secilen_key = random.choice(API_KEYS)
        genai.configure(api_key=secilen_key)
        # Hızlı model ismi (Library güncel olduğu için bunu tanıyacaktır)
        return genai.GenerativeModel("gemini-1.5-flash")
    except:
        return None

# --- AJANLAR ---
def niyet_analizi(soru):
    try:
        local_model = get_model()
        if not local_model: return "ARAMA"
        prompt = f"""GİRDİ: "{soru}"\nKARAR: "ARAMA" veya "SOHBET". Tek kelime."""
        response = local_model.generate_content(prompt)
        return response.text.strip().upper()
    except: return "ARAMA"

def dil_tespiti(soru):
    try:
        local_model = get_model()
        if not local_model: return "Turkish"
        prompt = f"""GİRDİ: "{soru}"\nCEVAP (Sadece dil): Turkish, English, German..."""
        response = local_model.generate_content(prompt)
        return response.text.strip()
    except: return "Turkish"

def anahtar_kelime_ayikla(soru):
    try:
        local_model = get_model()
        if not local_model: return soru
        prompt = f"""GİRDİ: "{soru}"\nGÖREV: Konuyu bul. Hitapları at.\nCEVAP:"""
        response = local_model.generate_content(prompt)
        return response.text.strip()
    except: return soru

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
    ana
