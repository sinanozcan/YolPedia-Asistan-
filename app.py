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
    /* Buton stili */
    .stButton button {{
        width: 100%;
        border-radius: 12px;
        font-weight: bold;
        border: 1px solid #ddd;
        padding: 10px;
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

# --- BAŞLANGIÇ KONTROLÜ ---
if 'db' not in st.session_state:
    with st.spinner('Sistem hazırlanıyor...'):
        st.session_state.db = veri_yukle()
    time.sleep(0.1)
    st.rerun()

# --- YARDIMCI FONKSİYONLAR ---
def tr_normalize(metin):
    kaynak = "ğĞüÜşŞıİöÖçÇâÂîÎûÛ"
    hedef  = "gGuUsSiIoOcCaAiIuU"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

def alakali_icerik_bul(soru, tum_veriler):
    gereksiz = ["nedir", "kimdir", "neredir", "nasil", "niye", "hangi", "kac", "ne", "ve", "ile", "bir", "bu", "su", "mi", "mu", "hakkinda", "bilgi", "almak", "istiyorum", "onun", "bunun", "suranin", "detayli", "anlat", "detaylandir"]
    soru_temiz = tr_normalize(soru)
    anahtar = [k for k in soru_temiz.split() if k not in gereksiz and len(k) > 2]
    
    puanlanmis = []
    for veri in tum_veriler:
        baslik_norm = tr_normalize(veri['baslik'])
        icerik_norm = tr_normalize(veri['icerik'])
        puan = 0
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
        bulunanlar += f"\n--- BAŞLIK: {v['baslik']} ---\nİÇERİK:\n{v['icerik'][:10000]}\n"
        kaynaklar.append({"baslik": v['baslik'], "link": v['link']})
        
    return bulunanlar, kaynaklar

# --- SOHBET ARAYÜZÜ ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- BUTON TETİKLEYİCİSİ ---
def detay_tetikle():
    st.session_state.detay_istendi = True

# Kullanıcı girişi
prompt = st.chat_input("Bir soru sorun...")

is_user_input = prompt is not None
is_detail_click = st.session_state.get('detay_istendi', False)

if is_user_input or is_detail_click:
    
    if is_user_input:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.detay_istendi = False
        st.session_state.son_baglam = None 
        st.session_state.son_kaynaklar = None
        st.session_state.son_soru = prompt
        user_msg = prompt
        
    elif is_detail_click:
        st.session_state.detay_istendi = False
        user_msg = st.session_state.get('son_soru', "")

    if is_user_input:
         with st.chat_message("user"):
            st.markdown(user_msg)

    with st.chat_message("assistant"):
        if 'db' in st.session_state and st.session_state.db:
            
            baglam = None
            kaynaklar = None
            detay_modu = False
            
            if is_detail_click and st.session_state.get('son_baglam'):
                baglam = st.session_state.son_baglam
                kaynaklar = st.session_state.son_kaynaklar
                detay_modu = True
            else:
                with st.spinner("🔎 Ansiklopedi taranıyor..."):
                    time.sleep(0.3)
                    baglam, kaynaklar = alakali_icerik_bul(user_msg, st.session_state.db)
                    st.session_state.son_baglam = baglam
                    st.session_state.son_kaynaklar = kaynaklar

            if not baglam:
                 msg = "Üzgünüm, YolPedia arşivinde bu konuyla ilgili bilgi bulunmuyor."
                 st.markdown(msg)
                 st.session_state.messages.append({"role": "assistant", "content": msg})
            else:
                try:
                    # --- PROMPTLAR ---
                    if detay_modu:
                        gorev = f"""
                        GÖREVİN: 
                        Bu metin yığını içinden SADECE "{user_msg}" ile ilgili olan kısımları cımbızla çek ve EN İNCE DETAYINA KADAR, UZUN VE KAPSAMLI şekilde anlat.
                        """
                    else:
                        gorev = f"""
                        GÖREVİN:
                        Sana verilen metinleri kullanarak "{user_msg}" sorusuna KISA, ÖZ VE NET bir cevap ver (Maksimum 3-4 paragraf).
                        """

                    # --- SERT KURALLAR ---
                    full_prompt = f"""
                    Sen YolPedia ansiklopedi asistanısın.
                    {gorev}
                    
                    KESİN KURALLAR:
                    1. GİRİŞ CÜMLESİ YASAK: Cevaba "Merhaba", "Asistan olarak", "YolPedia verilerine göre", "İşte detaylar" gibi cümlelerle ASLA BAŞLAMA.
                    2. DOĞRUDAN KONUYA GİR: Cevap direkt olarak "{user_msg} nedir/kimdir" sorusunun yanıtıyla başlamalı.
                    3. Asla uydurma yapma.
                    4. Bilgi yoksa 'Bilmiyorum' de.
                    
                    BİLGİLER:
                    {baglam}
                    """
                    
                    stream = model.generate_content(full_prompt, stream=True)
                    
                    def stream_parser():
                        full_text = ""
                        for chunk in stream:
                            if chunk.text:
                                for char in chunk.text:
                                    yield char
                                    time.sleep(0.001)
                                full_text += chunk.text
                        
                        negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "rastlanmamaktadır", "üzgünüm"]
                        cevap_olumsuz = any(n in full_text.lower() for n in negatif)
                        
                        if not cevap_olumsuz and kaynaklar:
                            kaynak_metni = "\n\n**📚 Kaynaklar:**\n"
                            essiz = {v['link']:v for v in kaynaklar}.values()
                            for k in essiz:
                                kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                            for char in kaynak_metni:
                                yield char
                                time.sleep(0.001)

                    response_text = st.write_stream(stream_parser)
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    
                    st.rerun()

                except Exception as e:
                    st.error(f"Hata: {e}")

# --- DETAY BUTONU ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    
    if "Hata" not in last_msg and "bulunmuyor" not in last_msg:
        if len(last_msg) < 2000:
            col1, col2, col3 = st.columns([1,2,1])
            with col2:
                st.button("📜 Bu Konuyu Detaylandır", on_click=detay_tetikle)

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Yönetim")
    if st.button("🔄 Önbelleği Temizle"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    if 'db' in st.session_state:
        st.write(f"📊 Toplam İçerik: {len(st.session_state.db)}")
        st.divider()
        st.subheader("🕵️ Veri Müfettişi")
        test = st.text_input("Ara:", placeholder="Örn: Mustafa Sazcı")
        if test:
            say = 0
            norm_test = tr_normalize(test)
            for v in st.session_state.db:
                nb = tr_normalize(v['baslik'])
                ni = tr_normalize(v['icerik'])
                if norm_test in nb or norm_test in ni:
                    st.success(f"✅ {v['baslik']}")
                    say += 1
                    if say >= 5: break
            if say == 0: st.error("❌ Bulunamadı")
