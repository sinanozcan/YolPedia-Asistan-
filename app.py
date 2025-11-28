import streamlit as st
import streamlit.components.v1 as components
import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import google.generativeai as genai
import sys
import time
import json
import random
from PIL import Image
from io import BytesIO

# ================= AYARLAR =================
# Çoklu Anahtar Listesi (Senin Ayarların)
API_KEYS = [
    st.secrets.get("API_KEY", ""),
    st.secrets.get("API_KEY_2", ""),
    st.secrets.get("API_KEY_3", ""),
    st.secrets.get("API_KEY_4", ""),
    st.secrets.get("API_KEY_5", "")
]
API_KEYS = [k for k in API_KEYS if k]

WP_USER = st.secrets["WP_USER"]
WP_PASS = st.secrets["WP_PASS"]
WEBSITE_URL = "https://yolpedia.eu" 
DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildigimin âlimiyim, bilmedigimin tâlibiyim!"'

# --- RESİMLER (SABİT LİNKLER) ---
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://cdn-icons-png.flaticon.com/512/3177/3177440.png"
# ===========================================

# --- FAVICON ---
try:
    response = requests.get(YOLPEDIA_ICON, timeout=5)
    favicon = Image.open(BytesIO(response.content))
except:
    favicon = "🤖"

st.set_page_config(page_title=ASISTAN_ISMI, page_icon=favicon)

# --- CSS TASARIM ---
st.markdown("""
<style>
    .main-header { 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        margin-top: 5px; 
        margin-bottom: 5px; 
    }
    .dede-img { 
        width: 80px; 
        height: 80px; 
        border-radius: 50%; 
        margin-right: 15px; 
        object-fit: cover;
        border: 2px solid #eee; 
    }
    .title-text { 
        font-size: 36px; 
        font-weight: 700; 
        margin: 0; 
        color: #ffffff; 
    }
    .top-logo-container {
        display: flex;
        justify-content: center;
        margin-bottom: 15px;
        padding-top: 10px;
    }
    .top-logo {
        width: 120px;
        opacity: 1.0; 
    }
    .motto-text { 
        text-align: center; 
        font-size: 16px; 
        font-style: italic; 
        color: #cccccc; 
        margin-bottom: 25px; 
        font-family: 'Georgia', serif; 
    }
    /* Avatar Ayarı */
    .stChatMessage .avatar {
        width: 45px !important;
        height: 45px !important;
    }
    @media (prefers-color-scheme: light) { 
        .title-text { color: #000000; } 
        .motto-text { color: #555555; }
        .dede-img { border: 2px solid #ccc; }
    }
    .stButton button { width: 100%; border-radius: 10px; font-weight: bold; border: 1px solid #ccc; }
    
    .element-container { margin-bottom: 0px !important; }
</style>
""", unsafe_allow_html=True)

# --- SAYFA GÖRÜNÜMÜ ---
st.markdown(
    f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header">
        <img src="{CAN_DEDE_ICON}" class="dede-img">
        <h1 class="title-text">Can Dede</h1>
    </div>
    <div class="motto-text">{MOTTO}</div>
    """,
    unsafe_allow_html=True
)

# --- OTOMATİK KAYDIRMA ---
def otomatik_kaydir():
    js = """
    <script>
        var body = window.parent.document.querySelector(".main");
        body.scrollTop = body.scrollHeight;
    </script>
    """
    components.html(js, height=0)

# --- AKILLI API YÖNETİCİSİ (404/429 Korumalı) ---
def get_model():
    if not API_KEYS:
        return None
    secilen_key = random.choice(API_KEYS)
    genai.configure(api_key=secilen_key)
    
    generation_config = {"temperature": 0.1, "max_output_tokens": 8192}
    
    # Garanti Model Listesi
    model_listesi = [
        "gemini-1.5-flash",
        "gemini-1.5-flash-001",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-pro"
    ]

    # 1. Dinamik
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name.lower():
                    return genai.GenerativeModel(m.name, generation_config=generation_config)
    except:
        pass

    # 2. Liste
    for m_adi in model_listesi:
        try:
            return genai.GenerativeModel(m_adi, generation_config=generation_config)
        except:
            continue
            
    return None

# --- 1. AJAN: NİYET OKUYUCU ---
def niyet_analizi(soru):
    try:
        local_model = get_model()
        if not local_model: return "ARAMA"
        prompt = f"""
        GİRDİ: "{soru}"
        KARAR: "ARAMA" veya "SOHBET"
        Sadece tek kelime cevap ver.
        """
        response = local_model.generate_content(prompt)
        return response.text.strip().upper()
    except:
        return "ARAMA"

# --- 2. AJAN: DİL DEDEKTİFİ ---
def dil_tespiti(soru):
    try:
        local_model = get_model()
        if not local_model: return "Turkish"
        prompt = f"""
        GİRDİ: "{soru}"
        GÖREV: Dil tespiti (Turkish, English, German...).
        CEVAP (Sadece dil):
        """
        response = local_model.generate_content(prompt)
        return response.text.strip()
    except:
        return "Turkish"

# --- 3. AJAN: KONU AYIKLAYICI ---
def anahtar_kelime_ayikla(soru):
    try:
        local_model = get_model()
        if not local_model: return soru
        prompt = f"""
        GİRDİ: "{soru}"
        GÖREV: Konuyu bul. Hitapları at.
        CEVAP:
        """
        response = local_model.generate_content(prompt)
        return response.text.strip()
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
        {"role": "assistant", "content": "Merhaba Erenler! Ben Can Dede. YolPedia rehberinizim. Size nasıl yardımcı olabilirim?"}
    ]

# Geçmiş mesajları ekrana bas
for message in st.session_state.messages:
    role_icon = CAN_DEDE_ICON if message["role"] == "assistant" else USER_ICON
    with st.chat_message(message["role"], avatar=role_icon):
        st.markdown(message["content"])

def detay_tetikle():
    st.session_state.detay_istendi = True

# --- GİRİŞ VE İŞLEM ---
prompt = st.chat_input("Can Dede'ye sor...")

is_user_input = prompt is not None
is_detail_click = st.session_state.get('detay_istendi', False)

if is_user_input or is_detail_click:
    
    # 1. Değişkenleri Hazırla
    if is_user_input:
        # Kullanıcı mesajını hemen ekle ve göster
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar=USER_ICON):
            st.markdown(prompt)
            
        st.session_state.detay_istendi = False
        st.session_state.son_baglam = None 
        st.session_state.son_kaynaklar = None
        st.session_state.son_soru = prompt
        
        # Analizler (Arka planda)
        niyet = niyet_analizi(prompt)
        dil = dil_tespiti(prompt)
        st.session_state.son_niyet = niyet
        st.session_state.son_dil = dil
        
        arama_kelimesi = prompt
        if niyet == "ARAMA":
            arama_kelimesi = anahtar_kelime_ayikla(prompt)
        user_msg = prompt
        
    elif is_detail_click:
        st.session_state.detay_istendi = False
        user_msg = st.session_state.get('son_soru', "")
        arama_kelimesi = anahtar_kelime_ayikla(user_msg)
        st.session_state.son_niyet = "ARAMA"
        # Dil hafızadan gelir, tekrar tespite gerek yok

    # 2. Asistan Cevabı Üretimi
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        baglam = None
        kaynaklar = None
        detay_modu = False
        niyet = st.session_state.get('son_niyet', "ARAMA")
        kullanici_dili = st.session_state.get('son_dil', "Turkish")
        stream = None
        
        with st.spinner("Can Dede düşünüyor..."):
            if niyet == "ARAMA":
                if 'db' in st.session_state and st.session_state.db:
                    # Detay isteği mi yoksa yeni arama mı?
                    if is_detail_click and st.session_state.get('son_baglam'):
                        baglam = st.session_state.son_baglam
                        kaynaklar = st.session_state.son_kaynaklar
                        detay_modu = True
                    else:
                        baglam, kaynaklar = alakali_icerik_bul(arama_kelimesi, st.session_state.db)
                        st.session_state.son_baglam = baglam
                        st.session_state.son_kaynaklar = kaynaklar
            
            # Anahtarı Al
            aktif_model = get_model()
            
            if aktif_model:
                try:
                    # --- PROMPTLAR ---
                    identity_rules = f"""
                    KİMLİK: Senin adın 'Can Dede'. Alevi-Bektaşi yolunda bilge, seküler ve humanist bir rehbersin.
                    ÜSLUP: Makamın bilgeliktir. Hiyerarşik dil (Evlat, Yavrum) YASAK. Hitap: "Erenler", "Can".
                    DİL: Cevabı {kullanici_dili} dilinde ver.
                    """

                    if niyet == "SOHBET":
                        full_prompt = f"""
                        {identity_rules}
                        GÖREV: Kullanıcı ile sohbet et.
                        KURAL: "Merhaba ben Can Dede" diye kendini tekrar tanıtma.
                        MESAJ: {user_msg}
                        """
                    else:
                        bilgi_metni = baglam if baglam else "Bilgi bulunamadı."
                        
                        if not baglam:
                            full_prompt = f"""{identity_rules}
                            GÖREV: Kullanıcıya nazikçe, YolPedia arşivinde henüz bu bilginin olmadığını söyle.
                            """
                        else:
                            if detay_modu:
                                gorev = f"GÖREV: '{user_msg}' konusunu, metinlerdeki farklı görüşleri sentezleyerek EN İNCE DETAYINA KADAR anlat."
                            else:
                                gorev = f"GÖREV: '{user_msg}' sorusuna, bilgileri süzerek KISA, ÖZ ve HİKMETLİ bir cevap ver."

                            full_prompt = f"""
                            {identity_rules}
                            {gorev}
                            KURALLAR:
                            1. SENTEZ: Farklı görüşleri kucakla, taraf tutma.
                            2. DOĞALLIK: "YolPedia'ya göre" deme. Bilgi sendeymiş gibi anlat.
                            3. UYDURMA: Bilmediğin şeyi uydurma.
                            BİLGİLER: {baglam}
                            """
                    
                    stream = aktif_model.generate_content(full_prompt, stream=True)
                
                except Exception as e:
                    if "429" in str(e):
                        time.sleep(2)
                        aktif_model = get_model()
                        if aktif_model:
                             stream = aktif_model.generate_content(full_prompt, stream=True)
                    else:
                        st.error(f"Hata: {e}")
            else:
                st.error("Model bulunamadı.")

        # --- YAZDIRMA (STREAMING) ---
        if stream:
            try:
                def stream_parser():
                    full_text = ""
                    for chunk in stream:
                        try:
                            if chunk.text:
                                for char in chunk.text:
                                    yield char
                                    time.sleep(0.001) # Daktilo hızı
                                full_text += chunk.text
                        except ValueError:
                            continue
                    
                    # Link Gösterimi
                    if niyet == "ARAMA" and baglam and kaynaklar:
                        negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "not found", "keine information"]
                        cevap_olumsuz = any(n in full_text.lower() for n in negatif)
                        if not cevap_olumsuz:
                            # Başlık dile göre
                            if "German" in kullanici_dili: link_baslik = "**📚 Quellen:**"
                            elif "English" in kullanici_dili: link_baslik = "**📚 Sources:**"
                            else: link_baslik = "**📚 Kaynaklar:**"
                            
                            kaynak_metni = f"\n\n{link_baslik}\n"
                            essiz = {v['link']:v for v in kaynaklar}.values()
                            for k in essiz:
                                kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                            for char in kaynak_metni:
                                yield char
                                time.sleep(0.001)

                response_text = st.write_stream(stream_parser)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
                # OTOMATİK KAYDIRMA (Cevap bitince)
                otomatik_kaydir()

            except Exception as e:
                pass

# --- DETAY BUTONU ---
# Butonun her zaman son asistan mesajının altında çıkması için buraya koyduk
# st.rerun() olmadığı için buton hemen çıkmayabilir, ama sonraki etkileşimde görünür
# Anında görünmesi için bu bloğu yukarıdaki stream bloğunun hemen altına alabiliriz ama
# Streamlit yapısı gereği akış yukarıdan aşağıdır. En altta durması daha sağlıklıdır.

son_niyet = st.session_state.get('son_niyet', "")
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    
    if son_niyet == "ARAMA" and "Hata" not in last_msg and "bulunmuyor" not in last_msg and "not found" not in last_msg.lower():
        if len(last_msg) < 5000: # Sadece özetse göster
            dil = st.session_state.get('son_dil', "Turkish")
            if "German" in dil: btn_txt = "📜 Mehr Details"
            elif "English" in dil: btn_txt = "📜 More Details"
            else: btn_txt = "📜 Bu Konuyu Detaylandır"
            
            col1, col2, col3 = st.columns([1,2,1])
            with col2:
                st.button(btn_txt, on_click=detay_tetikle)

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
