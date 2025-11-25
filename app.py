import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import google.generativeai as genai
import sys
import time
from PIL import Image   # <--- Yeni eklendi (Resim işlemek için)
from io import BytesIO  # <--- Yeni eklendi (Resim okumak için)

# ================= AYARLAR =================
API_KEY = st.secrets["API_KEY"]
WP_USER = st.secrets["WP_USER"]
WP_PASS = st.secrets["WP_PASS"]
WEBSITE_URL = "https://yolpedia.eu" 
LOGO_URL = "https://yolpedia.eu/wp-content/uploads/2025/11/cropped-Yolpedia-Favicon-e1620391336469.png"
# ===========================================

# --- FAVICON AYARLAMA (LINKTEN ÇEKME) ---
# Logoyu internetten çekip ikon formatına getiriyoruz
try:
    response = requests.get(LOGO_URL)
    favicon = Image.open(BytesIO(response.content))
except:
    favicon = "🤖" # Eğer logo yüklenemezse robot kalsın

# Sayfa Ayarları (page_icon kısmına favicon değişkenini koyduk)
st.set_page_config(page_title="YolPedia Asistanı", page_icon=favicon)

# --- BAŞLIK VE LOGO (ORTALANMIŞ GÖRÜNÜM) ---
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
        width: 40px;
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
        return genai.GenerativeModel(secilen_model_adi)
    except:
        return None

model = model_yukle()

# --- VERİLERİ ÇEK ---
@st.cache_resource(ttl=3600)
def site_verilerini_cek():
    veriler = [] 
    placeholder = st.empty()
    endpoints = ["posts", "pages"]
    
    kimlik = HTTPBasicAuth(WP_USER, WP_PASS)
    
    for tur in endpoints:
        page = 1
        while True:
            placeholder.text(f"⏳ {tur.upper()} taranıyor... Sayfa: {page} (Toplam: {len(veriler)})")
            api_url = f"{WEBSITE_URL}/wp-json/wp/v2/{tur}?per_page=50&page={page}"
            
            try:
                response = requests.get(api_url, auth=kimlik, timeout=30)
            except Exception as e:
                st.error(f"Bağlantı hatası: {e}")
                break
            
            if response.status_code == 400: break
            if response.status_code != 200:
                st.warning(f"{tur} {page}. sayfada hata: {response.status_code}. Atlanıyor...")
                break
            
            data_json = response.json()
            if isinstance(data_json, list):
                if not data_json: break
                for post in data_json:
                    baslik = post['title']['rendered']
                    icerik = BeautifulSoup(post['content']['rendered'], "html.parser").get_text()
                    link = post['link']
                    veriler.append({"baslik": baslik, "icerik": icerik, "link": link})
            else:
                break
            page += 1
            time.sleep(1) 
    
    placeholder.success(f"✅ Güncelleme Tamamlandı! Toplam {len(veriler)} içerik hafızada.")
    time.sleep(2)
    placeholder.empty()
    return veriler

if 'db' not in st.session_state:
    with st.spinner('Veri tabanı hazırlanıyor...'):
        st.session_state.db = site_verilerini_cek()

# --- TÜRKÇE KARAKTER DÜZELTİCİ ---
def tr_normalize(metin):
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

# --- RAG ARAMA ---
def alakali_icerik_bul(soru, tum_veriler):
    gereksiz_kelimeler = ["nedir", "kimdir", "neredir", "nasil", "niye", "hangi", "kac", "ne", "ve", "ile", "bir", "bu", "su", "mi", "mu"]
    soru_temiz = tr_normalize(soru)
    soru_kelimeleri = soru_temiz.split()
    anahtar_kelimeler = [k for k in soru_kelimeleri if k not in gereksiz_kelimeler and len(k) > 2]
    
    puanlanmis_veriler = []
    
    for veri in tum_veriler:
        baslik_norm = tr_normalize(veri['baslik'])
        icerik_norm = tr_normalize(veri['icerik'])
        metin_norm = baslik_norm + " " + icerik_norm
        puan = 0
        for kelime in anahtar_kelimeler:
            if kelime in metin_norm:
                if kelime in baslik_norm:
                    puan += 3
                else:
                    puan += 1
        if puan > 0:
            puanlanmis_veriler.append({"veri": veri, "puan": puan})
    
    puanlanmis_veriler.sort(key=lambda x: x['puan'], reverse=True)
    en_iyiler = puanlanmis_veriler[:5]
    
    bulunanlar = ""
    kaynak_listesi = []
    
    for item in en_iyiler:
        veri = item['veri']
        bulunanlar += f"\n--- BAŞLIK: {veri['baslik']} ---\nİÇERİK:\n{veri['icerik'][:1500]}...\n"
        kaynak_listesi.append({"baslik": veri['baslik'], "link": veri['link']})
        
    return bulunanlar, kaynak_listesi

# --- SOHBET ---
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
        baglam, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
        
        if not baglam:
             msg = "Sitenizde bu konuyla ilgili bilgi bulamadım."
             st.markdown(msg)
             st.session_state.messages.append({"role": "assistant", "content": msg})
        else:
            try:
                full_prompt = f"Sen bir ansiklopedi asistanısın. Aşağıdaki bilgileri kullanarak soruyu cevapla. Bilgilerde yoksa bilmiyorum de.\n\nSORU: {prompt}\n\nBİLGİLER:\n{baglam}"
                
                stream = model.generate_content(full_prompt, stream=True)
                
                def stream_parser():
                    for chunk in stream:
                        yield chunk.text
                    if kaynaklar:
                        kaynak_metni = "\n\n**📚 Kaynaklar:**\n"
                        for k in kaynaklar:
                            kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                        yield kaynak_metni
                
                response_text = st.write_stream(stream_parser)
                st.session_state.messages.append({"role": "assistant", "content": response_text})

            except Exception as e:
                err_msg = f"Bir hata oluştu: {e}"
                st.markdown(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Yönetim")
    if st.button("🔄 Verileri Şimdi Güncelle"):
        st.cache_resource.clear()
        st.rerun()
    st.divider()
    if 'db' in st.session_state:
        st.write(f"📊 Toplam İçerik: {len(st.session_state.db)}")
