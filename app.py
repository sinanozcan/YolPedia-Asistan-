import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import google.generativeai as genai
import sys
import time

# ================= AYARLAR =================
API_KEY = st.secrets["API_KEY"]
WP_USER = st.secrets["WP_USER"]
WP_PASS = st.secrets["WP_PASS"]
WEBSITE_URL = "https://yolpedia.eu" 
# ===========================================

st.set_page_config(page_title="Yolpedia Asistanı", page_icon="🤖")
st.title("🤖 Yolpedia Asistanı")

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

# --- VERİLERİ ÇEK (LİNKLER DAHİL) ---
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
                    link = post['link'] # <--- YENİ: Linki de alıyoruz
                    # Linki de hafızaya atıyoruz
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

# --- RAG ARAMA (LİNKLERİ DE DÖNDÜRÜR) ---
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
    kaynak_listesi = [] # Linkleri burada toplayacağız
    
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
        # Artık hem metni hem kaynakları alıyoruz
        baglam, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
        
        if not baglam:
             response_text = "Sitenizde bu konuyla ilgili bilgi bulamadım."
        else:
            try:
                full_prompt = f"Sen bir asistanısın. Aşağıdaki bilgileri kullanarak soruyu cevapla. Bilgilerde yoksa bilmiyorum de.\n\nSORU: {prompt}\n\nBİLGİLER:\n{baglam}"
                response = model.generate_content(full_prompt)
                
                # Cevabın altına kaynakları ekle
                kaynak_metni = "\n\n**📚 Kaynaklar:**\n"
                for k in kaynaklar:
                    kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                
                response_text = response.text + kaynak_metni
                
            except Exception as e:
                response_text = f"Bir hata oluştu: {e}"
        
        st.markdown(response_text)
    st.session_state.messages.append({"role": "assistant", "content": response_text})

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Yönetim")
    if st.button("🔄 Verileri Şimdi Güncelle"):
        st.cache_resource.clear()
        st.rerun()
    st.divider()
    if 'db' in st.session_state:
        st.write(f"📊 Toplam İçerik: {len(st.session_state.db)}")
