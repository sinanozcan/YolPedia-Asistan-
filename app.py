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

# --- BUTON TETİKLEYİCİSİ ---
def detay_tetikle():
    # Sadece butona basıldığında tetiklenir, mesaj eklemez, state değiştirir
    st.session_state.detay_istendi = True

# Kullanıcı girişi
prompt = st.chat_input("Bir soru sorun...")

# Eğer kullanıcı yazdıysa veya detay butonu tetiklendiyse
is_user_input = prompt is not None
is_detail_click = st.session_state.get('detay_istendi', False)

if is_user_input or is_detail_click:
    
    # 1. Senaryo: Normal Soru
    if is_user_input:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.detay_istendi = False # Yeni soruda detay modunu kapat
        st.session_state.son_baglam = None 
        st.session_state.son_kaynaklar = None
        st.session_state.son_soru = prompt # Soruyu hafızaya al (Filtreleme için lazım)
        user_msg = prompt
        
    # 2. Senaryo: Detay Butonu
    elif is_detail_click:
        # Görünmez bir kullanıcı mesajı gibi davranıp işlem yapıyoruz ama ekrana basmıyoruz
        # Sadece asistanın detaylı cevabı gelecek
        st.session_state.detay_istendi = False # Flag'i indir
        user_msg = st.session_state.get('son_soru', "") # Orijinal soruyu hatırlayalım

    # Kullanıcı mesajını ekrana bas (Sadece yeni soruysa)
    if is_user_input:
         with st.chat_message("user"):
            st.markdown(user_msg)

    with st.chat_message("assistant"):
        if 'db' in st.session_state and st.session_state.db:
            
            baglam = None
            kaynaklar = None
            
            # Eğer detay isteniyorsa ve hafızada eski bağlam varsa, ONU KULLAN
            if is_detail_click and st.session_state.get('son_baglam'):
                baglam = st.session_state.son_baglam
                kaynaklar = st.session_state.son_kaynaklar
                detay_modu = True
            else:
                # Normal soruysa yeni arama yap
                with st.spinner("🔎 Ansiklopedi taranıyor..."):
                    time.sleep(0.3)
                    baglam, kaynaklar = alakali_icerik_bul(user_msg, st.session_state.db)
                    
                    st.session_state.son_baglam = baglam
                    st.session_state.son_kaynaklar = kaynaklar
                    detay_modu = False

            if not baglam:
                 msg = "Üzgünüm, YolPedia arşivinde bu konuyla ilgili bilgi bulunmuyor."
                 st.markdown(msg)
                 st.session_state.messages.append({"role": "assistant", "content": msg})
            else:
                try:
                    # --- ÇOK ÖZEL FİLTRELEME PROMPTU ---
                    if detay_modu:
                        gorev = f"""
                        DİKKAT: Verilen 'BİLGİLER' metni içinde arama sonuçlarından gelen birden fazla farklı konu başlığı olabilir.
                        
                        GÖREVİN: 
                        Bu metin yığını içinden SADECE VE SADECE "{user_msg}" ile doğrudan ilgili olan kısımları ayıkla ve anlat.
                        Diğer başlıkları, yan konuları veya alakasız maddeleri KESİNLİKLE ANLATMA, YOK SAY.
                        Sadece "{user_msg}" konusunu en ince detayına kadar, uzun ve kapsamlı şekilde anlat.
                        """
                    else:
                        gorev = f"""
                        GÖREVİN:
                        Sana verilen 'BİLGİLER' metnini kullanarak, SADECE "{user_msg}" sorusuna odaklanarak KISA, ÖZ VE NET bir cevap ver (Maksimum 3 paragraf).
                        Diğer yan konuları anlatma.
                        """

                    full_prompt = f"""
                    Sen YolPedia ansiklopedi asistanısın.
                    
                    {gorev}
                    
                    KURALLAR:
                    1. Cevaba "YolPedia arşivine göre" gibi girişlerle BAŞLAMA. Doğal konuş.
                    2. Asla uydurma yapma, sadece verilen metinleri kullan.
                    3. Bilgi yoksa 'Bilmiyorum' de.
                    
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
                                    time.sleep(0.04)
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
                    
                    st.rerun() # Butonu göstermek için yenile

                except Exception as e:
                    st.error(f"Hata: {e}")

# --- DETAY BUTONU ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    # Eğer hata değilse ve daha önce detaylandırılmamışsa buton göster
    if "Hata" not in last_msg and "bulunmuyor" not in last_msg:
        # Son asistan mesajı çok uzunsa (Detaylıysa) butonu gösterme
        if len(last_msg) < 1500: 
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
        st.write(f"📊 Toplam İçerik: {len(st.session_state.db)}")import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import sys
import time
import json
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

# --- CSS ---
st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 20px; margin-bottom: 30px; }
    .logo-img { width: 90px; margin-right: 20px; }
    .title-text { font-size: 42px; font-weight: 700; margin: 0; color: #ffffff; }
    @media (prefers-color-scheme: light) { .title-text { color: #000000; } }
    .stButton button { width: 100%; border-radius: 10px; font-weight: bold; margin-top: 10px; }
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

@st.cache_resource
def model_yukle():
    generation_config = {"temperature": 0.0, "max_output_tokens": 8192}
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name.lower():
                    return genai.GenerativeModel(m.name, generation_config=generation_config)
        return genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
    except:
        return None

model = model_yukle()

@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            veriler = json.load(f)
        return veriler
    except FileNotFoundError:
        return []

if 'db' not in st.session_state:
    with st.spinner('Sistem hazırlanıyor...'):
        st.session_state.db = veri_yukle()
    time.sleep(0.1)
    st.rerun()

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

# Mesajları ekrana bas
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- BUTON İŞLEVİ ---
def detay_tetikle():
    # Çift mesajı önlemek için session kontrolü
    if st.session_state.messages[-1]["role"] != "user":
        st.session_state.messages.append({"role": "user", "content": "Lütfen yukarıdaki konuyu detaylıca anlat."})
    st.session_state.detay_modu = True # Detay modunu aç

# Kullanıcı girişi
prompt = st.chat_input("Bir soru sorun...")

# Eğer kullanıcı yazdıysa veya detay butonu tetiklendiyse
if prompt or ('detay_modu' in st.session_state and st.session_state.detay_modu):
    
    # Eğer normal soruysa
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        # Yeni soru gelince detay modunu ve eski bağlamı sıfırla
        st.session_state.detay_modu = False
        st.session_state.son_baglam = None 
        st.session_state.son_kaynaklar = None
        user_msg = prompt
        
    # Eğer detay butonuysa
    else:
        user_msg = "Lütfen yukarıdaki konuyu detaylıca anlat."
        # Mesajı zaten fonksiyonda eklemiştik, tekrar ekleme
    
    # Ekrana bas (Eğer henüz basılmadıysa)
    if st.session_state.messages[-1]["content"] != user_msg:
         with st.chat_message("user"):
            st.markdown(user_msg)

    with st.chat_message("assistant"):
        if 'db' in st.session_state and st.session_state.db:
            
            # --- KRİTİK NOKTA: BAĞLAMI BELİRLE ---
            baglam = None
            kaynaklar = None
            
            # Eğer detay isteniyorsa ve hafızada eski bağlam varsa, ONU KULLAN (Yeniden arama yapma!)
            if st.session_state.get('detay_modu') and st.session_state.get('son_baglam'):
                baglam = st.session_state.son_baglam
                kaynaklar = st.session_state.son_kaynaklar
                detay_istegi = True
            else:
                # Normal soruysa yeni arama yap
                with st.spinner("🔎 Ansiklopedi taranıyor..."):
                    time.sleep(0.3)
                    baglam, kaynaklar = alakali_icerik_bul(user_msg, st.session_state.db)
                    
                    # Bulunan veriyi hafızaya at (Sonraki detay isteği için)
                    st.session_state.son_baglam = baglam
                    st.session_state.son_kaynaklar = kaynaklar
                    detay_istegi = False

            if not baglam:
                 msg = "Üzgünüm, YolPedia arşivinde bu konuyla ilgili bilgi bulunmuyor."
                 st.markdown(msg)
                 st.session_state.messages.append({"role": "assistant", "content": msg})
            else:
                try:
                    # --- DİNAMİK PROMPT ---
                    if detay_istegi:
                        gorev = "Sana verilen 'BİLGİLER' metnini kullanarak konuyu EN İNCE DETAYINA KADAR, UZUN VE KAPSAMLI şekilde anlat."
                    else:
                        gorev = "Sana verilen 'BİLGİLER' metnini kullanarak soruya KISA, ÖZ VE NET bir cevap ver (Maksimum 3-4 paragraf)."

                    full_prompt = f"""
                    Sen YolPedia ansiklopedi asistanısın.
                    GÖREVİN: {gorev}
                    KURALLAR:
                    1. Cevaba "YolPedia arşivine göre" gibi girişlerle BAŞLAMA. Doğal konuş.
                    2. Asla uydurma yapma, sadece verilen metinleri kullan.
                    3. Bilgi yoksa 'Bilmiyorum' de.
                    
                    SORU: {user_msg}
                    BİLGİLER: {baglam}
                    """
                    
                    stream = model.generate_content(full_prompt, stream=True)
                    
                    def stream_parser():
                        full_text = ""
                        for chunk in stream:
                            if chunk.text:
                                for word in chunk.text.split(" "):
                                    yield word + " "
                                    time.sleep(0.04)
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
                    
                    # İşlem bitince detay modunu kapat, butonun tekrar çıkmasını sağla
                    if st.session_state.get('detay_modu'):
                        st.session_state.detay_modu = False
                    
                    st.rerun() # Butonu göstermek için yenile

                except Exception as e:
                    st.error(f"Hata: {e}")

# --- DETAY BUTONU ---
# Son mesaj asistandansa ve içinde hata yoksa göster
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    # Hata yoksa ve bu bir "detaylandırma cevabı" değilse buton koy
    # (Yani zaten detaylı anlatmışsa tekrar buton koyma)
    if "Hata" not in last_msg and "bulunmuyor" not in last_msg:
        # Basit bir kontrol: Eğer son kullanıcı mesajı "detaylı" kelimesini içermiyorsa buton göster
        last_user_msg = st.session_state.messages[-2]["content"] if len(st.session_state.messages) > 1 else ""
        
        if "detay" not in last_user_msg.lower():
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
