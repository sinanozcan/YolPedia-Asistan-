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

# --- İNATÇI VERİ ÇEKME FONKSİYONU ---
@st.cache_data(ttl=86400, show_spinner=False, persist="disk")
def site_verilerini_cek():
    veriler = [] 
    status_text = st.empty()
    endpoints = ["posts", "pages"]
    kimlik = HTTPBasicAuth(WP_USER, WP_PASS)
    
    for tur in endpoints:
        page = 1
        bos_sayfa_sayaci = 0 # Sonsuz döngüye girmesin diye koruma
        
        while True:
            status_text.text(f"⏳ {tur.upper()} taranıyor... Sayfa: {page} (Şu anki Toplam: {len(veriler)})")
            
            api_url = f"{WEBSITE_URL}/wp-json/wp/v2/{tur}?per_page=25&page={page}"
            basarili = False
            
            # --- İNATÇI MOD (RETRY MECHANISM) ---
            for deneme in range(3): # Her sayfayı 3 kez dene
                try:
                    response = requests.get(api_url, auth=kimlik, timeout=60)
                    
                    # Eğer sayfa yoksa (Bitti demektir)
                    if response.status_code == 400:
                        basarili = True # Döngüyü kırmak için başarılı sayıyoruz
                        bos_sayfa_sayaci = 100 # Ana döngüyü kırmak için
                        break
                    
                    # Başarılıysa işle
                    if response.status_code == 200:
                        data_json = response.json()
                        if isinstance(data_json, list) and len(data_json) > 0:
                            for post in data_json:
                                baslik = post['title']['rendered']
                                icerik = BeautifulSoup(post['content']['rendered'], "html.parser").get_text()
                                link = post['link']
                                veriler.append({"baslik": baslik, "icerik": icerik, "link": link})
                            basarili = True
                            break # Deneme döngüsünden çık
                        else:
                            # Liste boş geldi, içerik bitmiş olabilir
                            bos_sayfa_sayaci = 100
                            basarili = True
                            break
                    
                    # Başarısızsa (500, 502 vb.) bekle ve tekrar dene
                    time.sleep(5)
                    
                except Exception as e:
                    print(f"Hata (Deneme {deneme+1}): {e}")
                    time.sleep(5) # Hata alınca 5 saniye dinlen
            
            # 3 denemede de olmadıysa veya içerik bittiyse
            if bos_sayfa_sayaci >= 100:
                break
            
            # Eğer 3 kere denemesine rağmen başaramadıysa, bu sayfayı ATLA ve devam et
            # (Eskiden break yapıp komple duruyordu, şimdi sadece o sayfayı geçiyor)
            
            page += 1
            time.sleep(0.5) 
    
    status_text.empty()
    return veriler

# --- AKILLI YÜKLEME ---
def veri_yukle_yonetici():
    # 1. Önce JSON dosyası var mı diye bak (En Hızlısı)
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            veriler = json.load(f)
        return veriler, "dosya"
    except FileNotFoundError:
        pass # Dosya yoksa devam et

    # 2. Yoksa Cache/Disk üzerinden çek (Orta Hız)
    # Cache zaten yukarıdaki fonksiyonda hallediliyor
    veriler = site_verilerini_cek()
    return veriler, "canli"

# --- BAŞLANGIÇ ---
if 'db' not in st.session_state:
    with st.spinner('Veri tabanı yükleniyor...'):
        veriler, kaynak = veri_yukle_yonetici()
        st.session_state.db = veriler
        st.session_state.kaynak = kaynak
    
    if kaynak == "dosya":
        st.success(f"🚀 Hızlı Başlangıç! {len(veriler)} içerik dosyadan yüklendi.")
    elif kaynak == "canli":
        st.success(f"✅ Tarama Bitti! {len(veriler)} içerik hafızada.")
    
    time.sleep(1)
    st.rerun()

def tr_normalize(metin):
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

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
        bulunanlar += f"\n--- BAŞLIK: {veri['baslik']} ---\nİÇERİK:\n{veri['icerik'][:2000]}...\n"
        kaynak_listesi.append({"baslik": veri['baslik'], "link": veri['link']})
        
    return bulunanlar, kaynak_listesi

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
        with st.spinner("🔎 Ansiklopedi taranıyor..."):
            time.sleep(0.6) 
            baglam, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
        
        if not baglam:
             msg = "Sitenizde bu konuyla ilgili bilgi bulamadım."
             st.markdown(msg)
             st.session_state.messages.append({"role": "assistant", "content": msg})
        else:
            try:
                full_prompt = f"""
                Sen YolPedia ansiklopedi asistanısın.
                KURALLAR:
                1. KESİNLİKLE kendi bildiklerini kullanma.
                2. Sadece 'BİLGİLER' kısmındaki metinleri kullan.
                3. Bilgi yoksa 'Bilmiyorum' de.
                
                SORU: {prompt}
                BİLGİLER: {baglam}
                """
                stream = model.generate_content(full_prompt, stream=True)
                
                def stream_parser():
                    for chunk in stream:
                        if chunk.text:
                            for word in chunk.text.split(" "):
                                yield word + " "
                                time.sleep(0.05)
                    if kaynaklar:
                        kaynak_metni = "\n\n**📚 Kaynaklar:**\n"
                        for k in kaynaklar:
                            kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                        for line in kaynak_metni.split("\n"):
                            yield line + "\n"
                            time.sleep(0.1)
                
                response_text = st.write_stream(stream_parser)
                st.session_state.messages.append({"role": "assistant", "content": response_text})

            except Exception as e:
                st.error(f"Hata: {e}")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Yönetim")
    
    if 'kaynak' in st.session_state:
        if st.session_state.kaynak == "dosya":
            st.success("📂 Mod: Dosyadan Oku (Hızlı)")
        else:
            st.warning("🌐 Mod: Canlı Tara (Yavaş)")

    # 1. JSON İNDİRME BUTONU
    if 'db' in st.session_state and st.session_state.db:
        json_data = json.dumps(st.session_state.db, ensure_ascii=False)
        st.download_button(
            label="📥 Verileri Yedekle (JSON)",
            data=json_data,
            file_name="yolpedia_data.json",
            mime="application/json"
        )
    
    st.divider()
    
    # 2. ZORLA YENİLEME BUTONU
    if st.button("🔄 Siteyi Zorla Tara"):
        st.cache_data.clear()
        st.rerun()
        
    if 'db' in st.session_state:
        st.write(f"📊 Toplam İçerik: {len(st.session_state.db)}")
