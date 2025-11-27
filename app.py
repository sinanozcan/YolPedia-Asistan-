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

# --- CSS (Görünüm İyileştirmeleri) ---
st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 20px; margin-bottom: 30px; }
    .logo-img { width: 90px; margin-right: 20px; }
    .title-text { font-size: 42px; font-weight: 700; margin: 0; color: #ffffff; }
    @media (prefers-color-scheme: light) { .title-text { color: #000000; } }
    /* Butonları ortala */
    .stButton button { width: 100%; border-radius: 10px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- BAŞLIK ---
st.markdown(
    f"""
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

# --- YARDIMCI FONKSİYONLAR ---
def tr_normalize(metin):
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
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

# --- BUTON KONTROLÜ İÇİN ---
def detay_iste():
    # Bu fonksiyon butona basılınca sanki kullanıcı yazmış gibi mesaj ekler
    st.session_state.messages.append({"role": "user", "content": "Lütfen yukarıdaki konuyu detaylıca, tüm yönleriyle anlat."})

# Kullanıcı girişi
prompt = st.chat_input("Bir soru sorun...")

# Eğer kullanıcı yazdıysa
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    
# Cevap üretme kısmı (Hem normal prompt hem de buton tetiklemesi için)
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    user_msg = st.session_state.messages[-1]["content"]
    
    with st.chat_message("user"):
        st.markdown(user_msg)

    with st.chat_message("assistant"):
        if 'db' in st.session_state and st.session_state.db:
            
            # Detay isteği mi yoksa normal soru mu?
            detay_istegi = "detay" in user_msg.lower() or "uzun" in user_msg.lower() or "ayrıntı" in user_msg.lower()
            
            with st.spinner("🔎 Ansiklopedi taranıyor..."):
                time.sleep(0.3)
                # Bağlamı son kullanıcı mesajına göre değil, sohbetin ana konusuna göre bulmak daha iyi olabilir
                # Ama şimdilik son mesaja göre arayalım
                baglam, kaynaklar = alakali_icerik_bul(user_msg, st.session_state.db)
                
                # Eğer bağlam boşsa ve bu bir detay isteğiyse, önceki bağlamı hatırlamaya çalışabiliriz (İleri seviye)
                # Basitlik için yeniden arama yapıyoruz.

            if not baglam:
                 msg = "Üzgünüm, YolPedia arşivinde bu konuyla ilgili bilgi bulunmuyor."
                 st.markdown(msg)
                 st.session_state.messages.append({"role": "assistant", "content": msg})
            else:
                try:
                    # --- DİNAMİK PROMPT AYARI ---
                    if detay_istegi:
                        # DETAY MODU
                        gorev_metni = "Sana verilen 'BİLGİLER' metnini kullanarak konuyu EN İNCE DETAYINA KADAR, UZUN VE KAPSAMLI şekilde anlat."
                    else:
                        # ÖZET MODU (VARSAYILAN)
                        gorev_metni = "Sana verilen 'BİLGİLER' metnini kullanarak soruya KISA, ÖZ VE NET bir cevap ver (Maksimum 3-4 paragraf). Okuyucuyu sıkma."

                    # Geçmişi topla
                    gecmis_sohbet = ""
                    for msg in st.session_state.messages[-5:]: # Son 5 mesaj
                        rol = "Kullanıcı" if msg['role'] == 'user' else "Asistan"
                        temiz_icerik = msg['content'].split("**📚 Kaynaklar:**")[0] 
                        gecmis_sohbet += f"{rol}: {temiz_icerik}\n"

                    full_prompt = f"""
                    Sen YolPedia ansiklopedi asistanısın.
                    
                    GÖREVİN: {gorev_metni}
                    
                    KURALLAR:
                    1. Cevaba "YolPedia arşivine göre" gibi girişlerle BAŞLAMA. Doğal konuş.
                    2. Asla uydurma yapma, sadece verilen metinleri kullan.
                    3. Eğer metinlerde cevap YOKSA, sadece "Üzgünüm, YolPedia arşivinde bu konuyla ilgili net bir bilgi bulunmuyor." de.
                    
                    GEÇMİŞ SOHBET:
                    {gecmis_sohbet}
                    
                    SORU: {user_msg}
                    
                    BİLGİLER:
                    {baglam}
                    """
                    
                    stream = model.generate_content(full_prompt, stream=True)
                    
                    def stream_parser():
                        full_text = ""
                        for chunk in stream:
                            if chunk.text:
                                for word in chunk.text.split(" "):
                                    yield word + " "
                                    time.sleep(0.04) # Biraz hızlandırdık
                                full_text += chunk.text
                        
                        negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "rastlanmamaktadır", "üzgünüm"]
                        cevap_olumsuz = any(n in full_text.lower() for n in negatif)
                        
                        if not cevap_olumsuz and kaynaklar:
                            kaynak_metni = "\n\n**📚 Kaynaklar:**\n"
                            essiz = {v['link']:v for v in kaynaklar}.values()
                            for k in essiz:
                                kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                            for line in kaynak_metni.split("\n"):
                                yield line + "\n"
                                time.sleep(0.05)

                    response_text = st.write_stream(stream_parser)
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    
                    # --- CEVAP BİTTİKTEN SONRA BUTON GÖSTER (Eğer özetse) ---
                    if not detay_istegi and not any(n in response_text.lower() for n in ["bulunmuyor", "bilmiyorum"]):
                        st.rerun() # Butonun görünmesi için sayfayı yenile

                except Exception as e:
                    st.error(f"Hata: {e}")

# --- DETAY BUTONU (SOHBETİN ALTINA) ---
# Eğer son mesaj asistandansa ve içinde "Detaylı" isteği yoksa butonu göster
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    # Hata mesajı değilse buton göster
    if "Hata" not in last_msg and "bulunmuyor" not in last_msg:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            if st.button("📜 Bu Konuyu Detaylandır", on_click=detay_iste):
                pass # on_click fonksiyonu yukarıda işi hallediyor

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Yönetim")
    if st.button("🔄 Önbelleği Temizle"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    if 'db' in st.session_state:
        st.write(f"📊 Toplam İçerik: {len(st.session_state.db)}")
