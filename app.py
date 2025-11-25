import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import sys

# ================= AYARLAR =================
API_KEY = st.secrets["API_KEY"]
WEBSITE_URL = "https://yolpedia.eu" 
# ===========================================

# Sayfa Ayarları
st.set_page_config(page_title="Ansiklopedi Asistanı", page_icon="🤖")
st.title("🤖 Ansiklopedi Asistanı")

# API Yapılandırma
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
            # Flash yoksa herhangi birini al
             for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    secilen_model_adi = m.name
                    break
        return genai.GenerativeModel(secilen_model_adi)
    except:
        return None

model = model_yukle()

# --- VERİLERİ ÇEK (ÖNBELLEKLİ - SADECE 1 KEZ ÇEKER) ---
@st.cache_resource
def site_verilerini_cek():
    veriler = [] 
    page = 1
    placeholder = st.empty() # Ekranda bilgi vermek için
    
    while True:
        placeholder.text(f"⏳ Siteden veriler çekiliyor... Sayfa: {page}")
        api_url = f"{WEBSITE_URL}/wp-json/wp/v2/posts?per_page=50&page={page}"
        try:
            response = requests.get(api_url)
        except:
            break
        if response.status_code != 200 or not response.json():
            break 
        for post in response.json():
            baslik = post['title']['rendered']
            icerik = BeautifulSoup(post['content']['rendered'], "html.parser").get_text()
            veriler.append({"baslik": baslik, "icerik": icerik})
        page += 1
    
    placeholder.success(f"✅ Toplam {len(veriler)} madde hafızaya alındı!")
    return veriler

# Verileri yükle
if 'db' not in st.session_state:
    with st.spinner('Veri tabanı hazırlanıyor, lütfen bekleyin...'):
        st.session_state.db = site_verilerini_cek()

# --- TÜRKÇE KARAKTER DÜZELTİCİ ---
def tr_normalize(metin):
    # Türkçe harfleri İngilizce karşılıklarına çevirir
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

# --- RAG ARAMA (AKILLI + TÜRKÇE DOSTU) ---
def alakali_icerik_bul(soru, tum_veriler):
    gereksiz_kelimeler = ["nedir", "kimdir", "neredir", "nasil", "niye", "hangi", "kac", "ne", "ve", "ile", "bir", "bu", "su", "mi", "mu"]
    
    # Soruyu normalize et (ğ -> g, ş -> s yap ve küçült)
    soru_temiz = tr_normalize(soru)
    soru_kelimeleri = soru_temiz.split()
    
    # Stopwords temizliği
    anahtar_kelimeler = [k for k in soru_kelimeleri if k not in gereksiz_kelimeler and len(k) > 2]
    
    puanlanmis_veriler = []
    
    for veri in tum_veriler:
        # Veri tabanındaki metni de normalize et
        baslik_norm = tr_normalize(veri['baslik'])
        icerik_norm = tr_normalize(veri['icerik'])
        metin_norm = baslik_norm + " " + icerik_norm
        
        puan = 0
        
        for kelime in anahtar_kelimeler:
            if kelime in metin_norm:
                # Başlıkta geçiyorsa +3, içerikte +1 puan
                if kelime in baslik_norm:
                    puan += 3
                else:
                    puan += 1
        
        if puan > 0:
            puanlanmis_veriler.append({"veri": veri, "puan": puan})
    
    # Puana göre sırala (En yüksek puanlı en üstte)
    puanlanmis_veriler.sort(key=lambda x: x['puan'], reverse=True)
    
    en_iyiler = puanlanmis_veriler[:5]
    
    bulunanlar = ""
    for item in en_iyiler:
        veri = item['veri']
        bulunanlar += f"\n--- BAŞLIK: {veri['baslik']} (Puan: {item['puan']}) ---\nİÇERİK:\n{veri['icerik'][:1500]}...\n"
        
    return bulunanlar

# --- SOHBET ARAYÜZÜ ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Eski mesajları ekrana yaz
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Kullanıcıdan veri girişi
if prompt := st.chat_input("Bir soru sorun..."):
    # Kullanıcı mesajını ekrana bas
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Cevap üret
    with st.chat_message("assistant"):
        baglam = alakali_icerik_bul(prompt, st.session_state.db)
        
        if not baglam:
             response_text = "Sitenizde bu konuyla ilgili bilgi bulamadım."
        else:
            try:
                full_prompt = f"Sen bir asistanısın. Aşağıdaki bilgileri kullanarak soruyu cevapla. Bilgilerde yoksa bilmiyorum de.\n\nSORU: {prompt}\n\nBİLGİLER:\n{baglam}"
                response = model.generate_content(full_prompt)
                response_text = response.text
            except Exception as e:
                response_text = f"Bir hata oluştu: {e}"
        
        st.markdown(response_text)
    
    # Asistan cevabını hafızaya at
    st.session_state.messages.append({"role": "assistant", "content": response_text})



