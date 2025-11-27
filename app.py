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

# --- CSS ---
st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 10px; margin-bottom: 20px; }
    .logo-img { width: 80px; margin-right: 15px; }
    .title-text { font-size: 36px; font-weight: 700; margin: 0; color: #ffffff; }
    @media (prefers-color-scheme: light) { .title-text { color: #000000; } }
    .stButton button { width: 100%; border-radius: 10px; font-weight: bold; border: 1px solid #ccc; }
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

# --- MODELİ YÜKLE ---
@st.cache_resource
def model_yukle():
    generation_config = {"temperature": 0.0, "max_output_tokens": 8192}
    try:
        return genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
    except:
        return None

model = model_yukle()

# --- NİYET OKUYUCU (YENİ ÖZELLİK) ---
# Bu fonksiyon sorunun sohbet mi yoksa ansiklopedik arama mı olduğunu anlar
def niyet_analizi(soru):
    try:
        router_model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Aşağıdaki kullanıcı girdisini analiz et.
        
        GİRDİ: "{soru}"
        
        KARAR KURALLARI:
        - Eğer bu bir bilgi aramasıysa (Örn: "Dersim nerede?", "Otman Baba kimdir?", "Alevilik nedir?"), cevap: "ARAMA"
        - Eğer bu bir sohbet, selamlama, teşekkür, botun yeteneklerini sorma veya geri bildirimse (Örn: "Merhaba", "Nasılsın", "Beni anladın mı?", "Neler yapabilirsin?", "Şunu yapma"), cevap: "SOHBET"
        
        Sadece tek kelime cevap ver: "ARAMA" veya "SOHBET"
        """
        response = router_model.generate_content(prompt)
        return response.text.strip().upper()
    except:
        return "ARAMA" # Hata olursa varsayılan olarak ara

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
    with st.spinner('Sistem başlatılıyor...'):
        st.session_state.db = veri_yukle()

# --- YARDIMCI FONKSİYONLAR ---
def tr_normalize(metin):
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

def alakali_icerik_bul(soru, tum_veriler):
    # Artık gereksiz kelime listesine çok ihtiyacımız yok çünkü niyeti AI anlıyor
    # Ama yine de temizlik iyidir.
    gereksiz = ["nedir", "kimdir", "neredir", "nasil", "niye", "hangi", "kac", "ne", "ve", "ile", "bir", "bu", "su", "mi", "mu", "hakkinda", "bilgi", "almak", "istiyorum"]
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

# --- BUTON TETİKLEYİCİ ---
def detay_tetikle():
    st.session_state.detay_istendi = True

# --- GİRİŞ ---
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
        
        # --- NİYETİ BELİRLE (Sadece yeni soruda) ---
        niyet = niyet_analizi(prompt)
        st.session_state.son_niyet = niyet # Niyeti hafızaya al
        
        user_msg = prompt
        
    elif is_detail_click:
        st.session_state.detay_istendi = False
        user_msg = st.session_state.get('son_soru', "")
        # Butona basıldıysa niyet kesinlikle ARAMA'dır
        st.session_state.son_niyet = "ARAMA"

    if is_user_input:
         with st.chat_message("user"):
            st.markdown(user_msg)

    with st.chat_message("assistant"):
        baglam = None
        kaynaklar = None
        detay_modu = False
        niyet = st.session_state.get('son_niyet', "ARAMA")
        
        # Sadece niyet "ARAMA" ise veritabanına git
        if niyet == "ARAMA":
            if 'db' in st.session_state and st.session_state.db:
                if is_detail_click and st.session_state.get('son_baglam'):
                    baglam = st.session_state.son_baglam
                    kaynaklar = st.session_state.son_kaynaklar
                    detay_modu = True
                else:
                    with st.spinner("🔎 Ansiklopedi taranıyor..."):
                        # Yapay bekleme olmadan, işlem ne kadar sürerse o kadar
                        baglam, kaynaklar = alakali_icerik_bul(user_msg, st.session_state.db)
                        st.session_state.son_baglam = baglam
                        st.session_state.son_kaynaklar = kaynaklar
        
        # Yanıtı Oluştur
        try:
            # --- SENARYO 1: SOHBET (Veritabanı yok, Kaynak yok) ---
            if niyet == "SOHBET":
                full_prompt = f"""
                Sen YolPedia ansiklopedi asistanısın.
                Kullanıcı seninle sohbet ediyor veya bot hakkında soru soruyor.
                Ona nazik, yardımsever ve doğal bir dille cevap ver.
                Ansiklopedik bilgi vermene gerek yok.
                
                KULLANICI: {user_msg}
                """
            
            # --- SENARYO 2: ARAMA (Veritabanı var) ---
            else:
                if not baglam:
                    # Aradı ama bulamadı
                    full_prompt = "Kullanıcıya nazikçe 'Üzgünüm, YolPedia arşivinde bu konuyla ilgili bilgi bulunmuyor.' de."
                else:
                    # Buldu
                    if detay_modu:
                        gorev = f"GÖREVİN: '{user_msg}' konusunu, aşağıdaki BİLGİLER'i kullanarak EN İNCE DETAYINA KADAR anlat."
                    else:
                        gorev = f"GÖREVİN: '{user_msg}' sorusuna, aşağıdaki BİLGİLER'i kullanarak KISA VE ÖZ (Özet) bir cevap ver."

                    full_prompt = f"""
                    Sen YolPedia ansiklopedi asistanısın.
                    {gorev}
                    KURALLAR:
                    1. Asla uydurma yapma.
                    2. "YolPedia'ya göre" gibi girişler yapma.
                    3. Bilgi yoksa 'Bilmiyorum' de.
                    
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
                
                # --- KAYNAKLARI SADECE "ARAMA" MODUNDAYSA VE BİLGİ VARSA GÖSTER ---
                if niyet == "ARAMA" and baglam and kaynaklar:
                    negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "rastlanmamaktadır", "üzgünüm"]
                    cevap_olumsuz = any(n in full_text.lower() for n in negatif)
                    
                    if not cevap_olumsuz:
                        kaynak_metni = "\n\n**📚 Kaynaklar:**\n"
                        essiz = {v['link']:v for v in kaynaklar}.values()
                        for k in essiz:
                            kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                        for char in kaynak_metni:
                            yield char
                            time.sleep(0.001)

            response_text = st.write_stream(stream_parser)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            
            if niyet == "ARAMA" and not detay_modu:
                st.rerun() # Buton için yenile

        except Exception as e:
            st.error(f"Hata: {e}")

# --- DETAY BUTONU ---
# Sadece "ARAMA" niyetiyse ve cevap olumluysa buton göster
son_niyet = st.session_state.get('son_niyet', "")
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    
    if son_niyet == "ARAMA" and "Hata" not in last_msg and "bulunmuyor" not in last_msg:
        if len(last_msg) < 5000:
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
        test = st.text_input("Ara:", placeholder="Örn: Otman Baba")
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
