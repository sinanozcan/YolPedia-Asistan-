import streamlit as st
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
LOGO_URL = "https://yolpedia.eu/wp-content/uploads/2025/11/cropped-Yolpedia-Favicon-e1620391336469.png"
DATA_FILE = "yolpedia_data.json"
# ===========================================

# --- FAVICON ---
try:
    response = requests.get(LOGO_URL, timeout=5)
    favicon = Image.open(BytesIO(response.content))
except:
    favicon = "🤖"

st.set_page_config(page_title="YolPedia Asistanı", page_icon=favicon)

# --- BAŞLIK VE LOGO ---
st.markdown(
    f"""
    <style>
    .main-header {{
        display: flex;
        align-items: center;
        justify-content: center;
        margin-top: 20px;
        margin-bottom: 30px;
    }}
    .logo-img {{
        width: 90px;
        margin-right: 20px;
    }}
    .title-text {{
        font-size: 42px;
        font-weight: 700;
        margin: 0;
        color: #ffffff;
    }}
    @media (prefers-color-scheme: light) {{
        .title-text {{ color: #000000; }}
    }}
    </style>
    <div class="main-header">
        <img src="{LOGO_URL}" class="logo-img">
        <h1 class="title-text">YolPedia Asistanı</h1>
    </div>
    """,
    unsafe_allow_html=True
)

genai.configure(api_key=API_KEY)

# --- MODELİ BUL ---
@st.cache_resource
def model_yukle():
    secilen_model_adi = None
    generation_config = {"temperature": 0.0}
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name.lower():
                    secilen_model_adi = m.name
                    break
        if not secilen_model_adi:
             for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    secilen_model_adi = m.name
                    break
        return genai.GenerativeModel(secilen_model_adi, generation_config=generation_config)
    except:
        return None

model = model_yukle()

# --- VERİ YÜKLEME FONKSİYONU (ÖNCE BUNU TANIMLIYORUZ) ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            veriler = json.load(f)
        return veriler
    except FileNotFoundError:
        return []

# --- BAŞLANGIÇ KONTROLÜ (ŞİMDİ ÇAĞIRIYORUZ) ---
if 'db' not in st.session_state:
    with st.spinner('Sistem başlatılıyor...'):
        # Fonksiyon artık yukarıda tanımlı olduğu için hata vermez
        veriler = veri_yukle()
        if veriler:
            st.session_state.db = veriler
            st.success(f"✅ Sistem Hazır! {len(veriler)} madde yüklendi.")
            time.sleep(1)
            st.rerun()
        else:
            st.error("⚠️ Veri dosyası (JSON) bulunamadı! Lütfen GitHub'a yükleyin.")

# --- YARDIMCI FONKSİYONLAR ---
def tr_normalize(metin):
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

def alakali_icerik_bul(soru, tum_veriler):
    gereksiz = ["nedir", "kimdir", "neredir", "nasil", "niye", "hangi", "kac", "ne", "ve", "ile", "bir", "bu", "su", "mi", "mu", "hakkinda", "bilgi", "almak", "istiyorum"]
    soru_temiz = tr_normalize(soru)
    anahtar = [k for k in soru_temiz.split() if k not in gereksiz and len(k) > 2]
    
    puanlanmis = []
    for veri in tum_veriler:
        baslik_norm = tr_normalize(veri['baslik'])
        icerik_norm = tr_normalize(veri['icerik'])
        metin_norm = baslik_norm + " " + icerik_norm
        puan = 0
        
        # Tam Eşleşme Bonusu
        if soru_temiz in baslik_norm: puan += 50
        elif soru_temiz in icerik_norm: puan += 20
        
        for k in anahtar:
            if k in baslik_norm: puan += 3
            elif k in icerik_norm: puan += 1
        if puan > 0:
            puanlanmis.append({"veri": veri, "puan": puan})
    
    puanlanmis.sort(key=lambda x: x['puan'], reverse=True)
    en_iyiler = puanlanmis[:5]
    
    bulunanlar = ""
    kaynaklar = []
    for item in en_iyiler:
        v = item['veri']
        bulunanlar += f"\n--- BAŞLIK: {v['baslik']} ---\nİÇERİK:\n{v['icerik'][:2500]}...\n"
        kaynaklar.append({"baslik": v['baslik'], "link": v['link']})
        
    return bulunanlar, kaynaklar

# --- SOHBET ARAYÜZÜ ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Bir soru sorun..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if 'db' in st.session_state and st.session_state.db:
            with st.spinner("🔎 Ansiklopedi taranıyor..."):
                time.sleep(0.3)
                baglam, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
            
            if not baglam:
                msg = "Üzgünüm, YolPedia arşivinde bu konuyla ilgili bilgi bulunmuyor."
                st.markdown(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
            else:
                try:
                    full_prompt = f"""Sen YolPedia asistanısın.
                    KURALLAR:
                    1. Sadece aşağıdaki 'BİLGİLER' metinlerini kullan.
                    2. Eğer sorunun cevabı metinlerde YOKSA, sadece şunu yaz: "Üzgünüm, YolPedia arşivinde bu konuyla ilgili net bir bilgi bulunmuyor."
                    3. Asla uydurma yapma.
                    
                    SORU: {prompt}
                    BİLGİLER: {baglam}"""
                    
                    stream = model.generate_content(full_prompt, stream=True)
                    
                    def stream_parser():
                        full_text = ""
                        for chunk in stream:
                            if chunk.text:
                                for word in chunk.text.split(" "):
                                    yield word + " "
                                    time.sleep(0.03)
                                full_text += chunk.text
                        
                        negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "rastlanmamaktadır", "üzgünüm", "maalesef"]
                        cevap_olumsuz = any(n in full_text.lower() for n in negatif)
                        
                        if not cevap_olumsuz:
                            if kaynaklar:
                                km = "\n\n**📚 Kaynaklar:**\n"
                                for k in kaynaklar:
                                    km += f"- [{k['baslik']}]({k['link']})\n"
                                for line in km.split("\n"):
                                    yield line + "\n"
                                    time.sleep(0.1)

                    response = st.write_stream(stream_parser)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(f"Hata: {e}")
        else:
            st.error("Veri tabanı yüklenemedi.")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Yönetim")
    
    if st.button("🔄 Önbelleği Temizle"):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    
    if 'db' in st.session_state:
        st.write(f"📊 Toplam İçerik: {len(st.session_state.db)}")
        if st.checkbox("Yüklü Başlıkları Gör"):
            for item in st.session_state.db:
                st.text(item['baslik'])
