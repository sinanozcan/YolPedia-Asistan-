import streamlit as st
import streamlit.components.v1 as components # <--- YENİ: Kaydırma için gerekli
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
LOGO_URL = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png"
DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildigimin âlimiyim, bilmedigimin tâlibiyim!"'
# ===========================================

# --- FAVICON ---
try:
    response = requests.get(LOGO_URL, timeout=5)
    favicon = Image.open(BytesIO(response.content))
except:
    favicon = "🤖"

st.set_page_config(page_title=ASISTAN_ISMI, page_icon=favicon)

# --- CSS ---
st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 10px; margin-bottom: 5px; }
    .logo-img { width: 80px; margin-right: 15px; }
    .title-text { font-size: 32px; font-weight: 700; margin: 0; color: #ffffff; }
    .motto-text { text-align: center; font-size: 16px; font-style: italic; color: #cccccc; margin-bottom: 20px; font-family: 'Georgia', serif; }
    @media (prefers-color-scheme: light) { .title-text { color: #000000; } .motto-text { color: #555555; } }
    .stButton button { width: 100%; border-radius: 10px; font-weight: bold; border: 1px solid #ccc; }
    .element-container { margin-bottom: 0px !important; }
</style>
""", unsafe_allow_html=True)

# --- OTOMATİK KAYDIRMA FONKSİYONU ---
def otomatik_kaydir():
    # JavaScript ile sayfayı en alta iteler
    js = """
    <script>
        var body = window.parent.document.querySelector(".main");
        body.scrollTop = body.scrollHeight;
    </script>
    """
    components.html(js, height=0)

# --- BAŞLIK ---
st.markdown(
    f"""
    <div class="main-header">
        <img src="{LOGO_URL}" class="logo-img">
        <h1 class="title-text">Can Dede</h1>
    </div>
    <div class="motto-text">{MOTTO}</div>
    """,
    unsafe_allow_html=True
)

genai.configure(api_key=API_KEY)

# --- MODELİ BUL ---
@st.cache_resource
def model_yukle():
    generation_config = {"temperature": 0.1, "max_output_tokens": 8192}
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name.lower():
                    return genai.GenerativeModel(m.name, generation_config=generation_config)
        return genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
    except:
        return None

model = model_yukle()

# --- 1. AJAN: NİYET OKUYUCU ---
def niyet_analizi(soru):
    try:
        prompt = f"""
        GİRDİ: "{soru}"
        KARAR:
        - Bilgi araması: "ARAMA"
        - Sohbet: "SOHBET"
        CEVAP: "ARAMA" veya "SOHBET"
        """
        response = model.generate_content(prompt)
        return response.text.strip().upper()
    except:
        return "ARAMA"

# --- 2. AJAN: HİTAP TEMİZLEYİCİ ---
def anahtar_kelime_ayikla(soru):
    try:
        prompt = f"""
        GİRDİ: "{soru}"
        GÖREV: Kullanıcının ASIL MERAK ETTİĞİ KONUYU bul. Hitapları at.
        CEVAP:
        """
        response = model.generate_content(prompt)
        text = response.text.strip()
        return text if len(text) > 1 else soru
    except:
        return soru

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
    with st.spinner('Can Dede hazırlanıyor...'):
        st.session_state.db = veri_yukle()

# --- YARDIMCI FONKSİYONLAR ---
def tr_normalize(metin):
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

def alakali_icerik_bul(temiz_kelime, tum_veriler):
    soru_temiz = tr_normalize(temiz_kelime)
    anahtar = [k for k in soru_temiz.split() if len(k) > 2]
    
    puanlanmis = []
    for veri in tum_veriler:
        baslik_norm = tr_normalize(veri['baslik'])
        icerik_norm = tr_normalize(veri['icerik'])
        puan = 0
        if soru_temiz in baslik_norm: puan += 100
        elif soru_temiz in icerik_norm: puan += 40
        for k in anahtar:
            if k in baslik_norm: puan += 10
            elif k in icerik_norm: puan += 2
        if puan > 0:
            puanlanmis.append({"veri": veri, "puan": puan})
    
    puanlanmis.sort(key=lambda x: x['puan'], reverse=True)
    en_iyiler = puanlanmis[:7]
    
    bulunanlar = ""
    kaynaklar = []
    for item in en_iyiler:
        v = item['veri']
        bulunanlar += f"\n--- BAŞLIK: {v['baslik']} ---\nİÇERİK:\n{v['icerik'][:12000]}\n"
        kaynaklar.append({"baslik": v['baslik'], "link": v['link']})
        
    return bulunanlar, kaynaklar

# --- SOHBET GEÇMİŞİ ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Merhaba Erenler! Ben Can Dede. YolPedia rehberinizim. Hakikat yolunda merak ettiklerinizi sorabilirsiniz."}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

def detay_tetikle():
    st.session_state.detay_istendi = True

# --- GİRİŞ ---
prompt = st.chat_input("Can Dede'ye sor...")

is_user_input = prompt is not None
is_detail_click = st.session_state.get('detay_istendi', False)

if is_user_input or is_detail_click:
    
    if is_user_input:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.detay_istendi = False
        st.session_state.son_baglam = None 
        st.session_state.son_kaynaklar = None
        st.session_state.son_soru = prompt
        
        niyet = niyet_analizi(prompt)
        st.session_state.son_niyet = niyet
        
        arama_kelimesi = prompt
        if niyet == "ARAMA":
            arama_kelimesi = anahtar_kelime_ayikla(prompt)
        user_msg = prompt
        
    elif is_detail_click:
        st.session_state.detay_istendi = False
        user_msg = st.session_state.get('son_soru', "")
        arama_kelimesi = anahtar_kelime_ayikla(user_msg)
        st.session_state.son_niyet = "ARAMA"

    if is_user_input:
         with st.chat_message("user"):
            st.markdown(user_msg)
            # Soru sorulduğu an aşağı kaydır
            otomatik_kaydir()

    with st.chat_message("assistant"):
        baglam = None
        kaynaklar = None
        detay_modu = False
        niyet = st.session_state.get('son_niyet', "ARAMA")
        stream = None
        
        with st.spinner("Can Dede düşünüyor..."):
            if niyet == "ARAMA":
                if 'db' in st.session_state and st.session_state.db:
                    if is_detail_click and st.session_state.get('son_baglam'):
                        baglam = st.session_state.son_baglam
                        kaynaklar = st.session_state.son_kaynaklar
                        detay_modu = True
                    else:
                        baglam, kaynaklar = alakali_icerik_bul(arama_kelimesi, st.session_state.db)
                        st.session_state.son_baglam = baglam
                        st.session_state.son_kaynaklar = kaynaklar
            
            try:
                if niyet == "SOHBET":
                    full_prompt = f"""
                    Senin adın 'Can Dede'. Sen YolPedia'nın bilge rehberisin.
                    Kullanıcı ile sohbet et.
                    KURALLAR:
                    1. "Merhaba ben Can Dede" diye kendini tekrar tanıtma.
                    2. Kullanıcının dili neyse o dilde cevap ver.
                    3. ASLA "Evlat" deme. Hitabın "Erenler" veya "Can" olsun.
                    MESAJ: {user_msg}
                    """
                else:
                    bilgi_metni = baglam if baglam else "Bilgi bulunamadı."
                    
                    if not baglam:
                        full_prompt = f"Kullanıcıya nazikçe 'Üzgünüm Erenler, YolPedia arşivinde bu konuda bilgi yok.' de. DİL: Kullanıcı dili."
                    else:
                        if detay_modu:
                            gorev = f"GÖREVİN: '{user_msg}' konusunu, metinlerdeki farklı görüşleri sentezleyerek EN İNCE DETAYINA KADAR anlat."
                        else:
                            gorev = f"GÖREVİN: '{user_msg}' sorusuna, bilgileri süzerek KISA, ÖZ ve HİKMETLİ bir cevap ver."

                        full_prompt = f"""
                        Sen 'Can Dede'sin.
                        {gorev}
                        KURALLAR:
                        1. "Yol bir, sürek binbir" ilkesiyle anlat.
                        2. ASLA "Evlat" deme. "Erenler" veya "Can" de.
                        3. Kullanıcının dili neyse o dilde cevap ver.
                        4. Giriş cümlesi yapma.
                        BİLGİLER: {baglam}
                        """
                
                stream = model.generate_content(full_prompt, stream=True)
                
            except Exception as e:
                st.error(f"Hata: {e}")

        if stream:
            try:
                def stream_parser():
                    full_text = ""
                    for chunk in stream:
                        try:
                            if chunk.text:
                                for char in chunk.text:
                                    yield char
                                    time.sleep(0.001)
                                full_text += chunk.text
                        except ValueError:
                            continue
                    
                    if niyet == "ARAMA" and baglam and kaynaklar:
                        negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "not found"]
                        cevap_olumsuz = any(n in full_text.lower() for n in negatif)
                        if not cevap_olumsuz:
                            kaynak_metni = "\n\n**📚 Kaynaklar / Sources:**\n"
                            essiz = {v['link']:v for v in kaynaklar}.values()
                            for k in essiz:
                                kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                            for char in kaynak_metni:
                                yield char
                                time.sleep(0.001)

                response_text = st.write_stream(stream_parser)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
                # CEVAP BİTİNCE SAYFAYI KAYDIR
                otomatik_kaydir()

            except Exception as e:
                pass

# --- DETAY BUTONU ---
son_niyet = st.session_state.get('son_niyet', "")
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    
    if son_niyet == "ARAMA" and "Hata" not in last_msg and "bulunmuyor" not in last_msg and "not found" not in last_msg.lower():
        if len(last_msg) < 5000:
            col1, col2, col3 = st.columns([1,2,1])
            with col2:
                if st.button("📜 Bu Konuyu Detaylandır / Details", on_click=detay_tetikle):
                    pass # Tıklanınca rerun olacak ve yukarıdaki kod çalışacak

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
