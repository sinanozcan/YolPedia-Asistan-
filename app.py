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
    generation_config = {"temperature": 0.0, "max_output_tokens": 8192}
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

# --- VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            veriler = json.load(f)
        return veriler
    except FileNotFoundError:
        return []

# --- BAŞLANGIÇ ---
if 'db' not in st.session_state:
    with st.spinner('Sistem hazırlanıyor...'):
        st.session_state.db = veri_yukle()
    time.sleep(0.1)
    st.rerun()

# --- GÜÇLENDİRİLMİŞ TÜRKÇE NORMALİZASYON ---
def tr_normalize(metin):
    # 1. Önce şapkalı ve Türkçe karakterleri İngilizce karşılıklarına çevir
    kaynak = "ğĞüÜşŞıİöÖçÇâÂîÎûÛ"
    hedef  = "gGuUsSiIoOcCaAiIuU"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    metin = metin.translate(ceviri_tablosu)
    # 2. Sonra hepsini küçük harfe çevir
    return metin.lower()

# --- RAG ARAMA ---
def alakali_icerik_bul(soru, tum_veriler):
    gereksiz = ["nedir", "kimdir", "neredir", "nasil", "niye", "hangi", "kac", "ne", "ve", "ile", "bir", "bu", "su", "mi", "mu", "hakkinda", "bilgi", "almak", "istiyorum", "onun", "bunun"]
    
    # Soruyu normalize et (sazcı -> sazci)
    soru_temiz = tr_normalize(soru)
    
    # Anahtar kelimeleri ayır
    anahtar = [k for k in soru_temiz.split() if k not in gereksiz and len(k) > 2]
    
    puanlanmis = []
    
    for veri in tum_veriler:
        # Veri tabanındaki başlık ve içeriği de normalize et (SAZCI -> sazci)
        baslik_norm = tr_normalize(veri['baslik'])
        icerik_norm = tr_normalize(veri['icerik'])
        
        puan = 0
        
        # 1. Tam Cümle Eşleşmesi (En Güçlü)
        if soru_temiz in baslik_norm:
            puan += 50
        elif soru_temiz in icerik_norm:
            puan += 20
            
        # 2. Kelime Kelime Arama
        for k in anahtar:
            if k in baslik_norm: 
                puan += 5
            elif k in icerik_norm: 
                puan += 1
        
        if puan > 0:
            puanlanmis.append({"veri": veri, "puan": puan})
    
    # En yüksek puanlıları en üste al
    puanlanmis.sort(key=lambda x: x['puan'], reverse=True)
    en_iyiler = puanlanmis[:5]
    
    bulunanlar = ""
    kaynaklar = []
    for item in en_iyiler:
        v = item['veri']
        bulunanlar += f"\n--- BAŞLIK: {v['baslik']} ---\nİÇERİK:\n{v['icerik'][:10000]}\n"
        kaynaklar.append({"baslik": v['baslik'], "link": v['link']})
        
    return bulunanlar, kaynaklar

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
        if 'db' in st.session_state and st.session_state.db:
            with st.spinner("🔎 Ansiklopedi taranıyor..."):
                time.sleep(0.3)
                baglam, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
            
            # Geçmiş sohbeti topla
            gecmis = ""
            for msg in st.session_state.messages[-4:]:
                rol = "Kullanıcı" if msg['role'] == 'user' else "Asistan"
                txt = msg['content'].split("**📚 Kaynaklar:**")[0]
                gecmis += f"{rol}: {txt}\n"

            try:
                full_prompt = f"""
                Sen YolPedia ansiklopedi asistanısın.
                
                GÖREVİN:
                Sana verilen 'BİLGİLER' metnini kullanarak soruyu detaylıca cevapla.
                
                KURALLAR:
                1. Asla uydurma yapma, sadece verilen metinleri kullan.
                2. Cevapların akıcı ve doğal olsun. "Belgeye göre" gibi girişler yapma.
                3. Eğer metinlerde cevap YOKSA, sadece "Üzgünüm, YolPedia arşivinde bu konuyla ilgili net bir bilgi bulunmuyor." de.
                
                GEÇMİŞ SOHBET:
                {gecmis}
                
                YENİ SORU: {prompt}
                
                BİLGİLER:
                {baglam if baglam else "Eşleşme bulunamadı."}
                """
                
                stream = model.generate_content(full_prompt, stream=True)
                
                def stream_parser():
                    full_text = ""
                    for chunk in stream:
                        if chunk.text:
                            # Harf harf akış
                            for char in chunk.text:
                                yield char
                                time.sleep(0.002)
                            full_text += chunk.text
                    
                    negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "rastlanmamaktadır", "üzgünüm", "maalesef"]
                    cevap_olumsuz = any(n in full_text.lower() for n in negatif)
                    
                    if baglam and kaynaklar and not cevap_olumsuz:
                        # Tekrar eden linkleri temizle
                        essiz = {v['link']:v for v in kaynaklar}.values()
                        
                        kaynak_metni = "\n\n**📚 Kaynaklar:**\n"
                        for k in essiz:
                            kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                        
                        for char in kaynak_metni:
                            yield char
                            time.sleep(0.001)

                response_text = st.write_stream(stream_parser)
                st.session_state.messages.append({"role": "assistant", "content": response_text})

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
        
        # --- MÜFETTİŞ (TEST ALANI) ---
        st.divider()
        st.subheader("🕵️ Veri Müfettişi")
        test = st.text_input("Ara:", placeholder="Örn: Mustafa Sazcı")
        if test:
            say = 0
            # Test ederken de aynı güçlü normalizasyonu kullan
            norm_test = tr_normalize(test)
            for v in st.session_state.db:
                nb = tr_normalize(v['baslik'])
                ni = tr_normalize(v['icerik'])
                if norm_test in nb or norm_test in ni:
                    st.success(f"✅ {v['baslik']}")
                    say += 1
                    if say >= 5: break
            if say == 0: st.error("❌ Bulunamadı")
