import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import time
from PIL import Image
from io import BytesIO

# ================= AYARLAR =================
API_KEY = st.secrets["API_KEY"]
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
        width: 60px;
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
    generation_config = {"temperature": 0.0}
    try:
        return genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
    except:
        return None

model = model_yukle()

# --- MODELİ BUL (AKILLI VE KESİN) ---
@st.cache_resource
def model_yukle():
    generation_config = {"temperature": 0.0}
    try:
        # 1. Önce Flash modelini ara (En hızlısı)
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name.lower():
                    return genai.GenerativeModel(m.name, generation_config=generation_config)
        
        # 2. Flash yoksa Pro modelini ara
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'pro' in m.name.lower():
                    return genai.GenerativeModel(m.name, generation_config=generation_config)
                    
        # 3. Hiçbiri yoksa çalışan ilk modeli al
        return genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
    except:
        return None

model = model_yukle()

# --- BAŞLANGIÇ ---
if 'db' not in st.session_state:
    with st.spinner('Sistem başlatılıyor...'):
        veriler = veri_yukle()
        if veriler:
            st.session_state.db = veriler
            # st.success(f"✅ {len(veriler)} içerik yüklendi.") # Kullanıcıyı rahatsız etmesin diye kapattık
            time.sleep(0.5)
            st.rerun()
        else:
            st.error("⚠️ Veri dosyası (JSON) bulunamadı! Lütfen GitHub'a yükleyin.")

# --- GÜÇLENDİRİLMİŞ ARAMA MOTORU ---
def tr_normalize(metin):
    # Türkçe karakterleri güvenli hale getir
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

def alakali_icerik_bul(soru, tum_veriler):
    # Gereksiz kelimeler
    gereksiz = ["nedir", "kimdir", "neredir", "nasil", "niye", "hangi", "kac", "ne", "ve", "ile", "bir", "bu", "su", "mi", "mu", "hakkinda", "bilgi"]
    
    # 1. Soruyu normalize et
    soru_norm = tr_normalize(soru)
    soru_kelimeleri = [k for k in soru_norm.split() if k not in gereksiz and len(k) > 2]
    
    puanlanmis_veriler = []
    
    for veri in tum_veriler:
        baslik_norm = tr_normalize(veri['baslik'])
        icerik_norm = tr_normalize(veri['icerik'])
        metin_full = baslik_norm + " " + icerik_norm
        
        puan = 0
        
        # --- KURAL 1: TAM CÜMLE EŞLEŞMESİ (ALTIN VURUŞ) ---
        # Kullanıcı "Otman Baba" yazdıysa ve metinde "otman baba" geçiyorsa devasa puan ver.
        if soru_norm in baslik_norm:
            puan += 50 # Başlıkta geçiyorsa kesin odur
        elif soru_norm in icerik_norm:
            puan += 20 # İçerikte geçiyorsa çok alakalıdır
            
        # --- KURAL 2: KELİME KELİME ARAMA ---
        for k in soru_kelimeleri:
            if k in baslik_norm: 
                puan += 5
            elif k in icerik_norm: 
                puan += 1
        
        if puan > 0:
            puanlanmis_veriler.append({"veri": veri, "puan": puan})
    
    # Puana göre sırala (En yüksek en üstte)
    puanlanmis_veriler.sort(key=lambda x: x['puan'], reverse=True)
    
    # En iyi 5 sonucu al
    en_iyiler = puanlanmis_veriler[:5]
    
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
                time.sleep(3.0)
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
                        
                        negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "rastlanmamaktadır", "üzgünüm"]
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

# --- YAN MENÜ (MÜFETTİŞ MODU) ---
with st.sidebar:
    st.header("⚙️ Yönetim & Kontrol")
    
    if 'db' in st.session_state:
        st.write(f"📊 Toplam İçerik: {len(st.session_state.db)}")
        
        st.divider()
        st.subheader("🕵️ Veri Müfettişi")
        st.info("Aradığın kelimenin veri tabanında olup olmadığını buradan test et.")
        test_arama = st.text_input("Kelime ara (Örn: Otman Baba)")
        
        if test_arama:
            bulunan_sayisi = 0
            for v in st.session_state.db:
                norm_baslik = tr_normalize(v['baslik'])
                norm_icerik = tr_normalize(v['icerik'])
                norm_aranan = tr_normalize(test_arama)
                
                if norm_aranan in norm_baslik or norm_aranan in norm_icerik:
                    st.text(f"✅ BULUNDU: {v['baslik']}")
                    bulunan_sayisi += 1
                    if bulunan_sayisi >= 5: break # Çok fazla listeleme
            
            if bulunan_sayisi == 0:
                st.error("❌ Bu kelime JSON dosyasında YOK! (İndirme eksik yapılmış olabilir)")
            else:
                st.success(f"Toplam {bulunan_sayisi}+ eşleşme var.")

    st.divider()
    if st.button("🔄 Önbelleği Temizle"):
        st.cache_data.clear()
        st.rerun()
