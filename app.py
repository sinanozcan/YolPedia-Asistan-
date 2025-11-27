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
ASISTAN_ISMI = "Can | YolPedia Rehberiniz"
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
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 10px; margin-bottom: 20px; }
    .logo-img { width: 80px; margin-right: 15px; }
    .title-text { font-size: 32px; font-weight: 700; margin: 0; color: #ffffff; }
    @media (prefers-color-scheme: light) { .title-text { color: #000000; } }
    .stButton button { width: 100%; border-radius: 10px; font-weight: bold; border: 1px solid #ccc; }
</style>
""", unsafe_allow_html=True)

# --- BAŞLIK ---
st.markdown(
    f"""
    <div class="main-header">
        <img src="{LOGO_URL}" class="logo-img">
        <h1 class="title-text">{ASISTAN_ISMI}</h1>
    </div>
    """,
    unsafe_allow_html=True
)

genai.configure(api_key=API_KEY)

# --- MODELİ BUL ---
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

# --- 1. AJAN: DİL VE NİYET ANALİZİ (BİRLEŞİK) ---
def dil_ve_niyet_analizi(soru):
    try:
        prompt = f"""
        GİRDİ: "{soru}"
        
        GÖREV: Aşağıdaki formatta analiz yap.
        1. NİYET: "ARAMA" (Bilgi sorusu) veya "SOHBET" (Selam, hal hatır)
        2. DİL: Kullanıcının yazdığı dil (Turkish, German, English, French vb.)
        
        CEVAP FORMATI: NİYET|DİL
        ÖRNEK 1: "Was ist Dersim?" -> ARAMA|German
        ÖRNEK 2: "Merhaba nasılsın?" -> SOHBET|Turkish
        ÖRNEK 3: "Tell me about Otman Baba" -> ARAMA|English
        """
        response = model.generate_content(prompt)
        text = response.text.strip()
        parts = text.split("|")
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        else:
            return "ARAMA", "Turkish"
    except:
        return "ARAMA", "Turkish"

# --- 2. AJAN: ANAHTAR KELİME AYIKLAYICI ---
def anahtar_kelime_ayikla(soru):
    try:
        prompt = f"""
        GİRDİ: "{soru}"
        GÖREV: Bu cümlenin içindeki ARANAN KONUYU (Entity) bul ve sadece onu yaz.
        Soru eklerini at. Konu Türkçe bir terimse Türkçe halini koru.
        
        ÖRNEK: "Was ist eigentlich Oniki Hizmet?" -> Oniki Hizmet
        ÖRNEK: "Who is Seyit Riza?" -> Seyit Rıza
        
        CEVAP (Sadece kelime):
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
    with st.spinner('Can hazırlanıyor...'):
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
    st.session_state.messages = [
        {"role": "assistant", "content": "Merhaba Erenler! Ben Can! YolPedia'da site rehberinizim. Sizlere nasıl yardımcı olabilirim?"}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

def detay_tetikle():
    st.session_state.detay_istendi = True

# --- GİRİŞ ---
prompt = st.chat_input("Can'a bir soru sorun...")

is_user_input = prompt is not None
is_detail_click = st.session_state.get('detay_istendi', False)

if is_user_input or is_detail_click:
    
    if is_user_input:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.detay_istendi = False
        st.session_state.son_baglam = None 
        st.session_state.son_kaynaklar = None
        st.session_state.son_soru = prompt
        
        # --- ANALİZ (DİL TESPİTİ BURADA YAPILIYOR) ---
        niyet, dil = dil_ve_niyet_analizi(prompt)
        st.session_state.son_niyet = niyet
        st.session_state.son_dil = dil # Dili hafızaya at
        
        arama_kelimesi = prompt
        if niyet == "ARAMA":
            arama_kelimesi = anahtar_kelime_ayikla(prompt)
            
        user_msg = prompt
        
    elif is_detail_click:
        st.session_state.detay_istendi = False
        user_msg = st.session_state.get('son_soru', "")
        arama_kelimesi = anahtar_kelime_ayikla(user_msg)
        st.session_state.son_niyet = "ARAMA"
        # Dili değiştirmeden hafızadan kullanıyoruz

    if is_user_input:
         with st.chat_message("user"):
            st.markdown(user_msg)

    with st.chat_message("assistant"):
        baglam = None
        kaynaklar = None
        detay_modu = False
        niyet = st.session_state.get('son_niyet', "ARAMA")
        kullanici_dili = st.session_state.get('son_dil', "Turkish")
        stream = None
        
        with st.spinner("Can araştırıyor..."):
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
                # --- SOHBET MODU ---
                if niyet == "SOHBET":
                    full_prompt = f"""
                    Senin adın 'Can'. Sen YolPedia ansiklopedisinin yardımsever rehberisin.
                    
                    KURAL: Cevabı ŞU DİLDE ver: {kullanici_dili}
                    KURAL: "Merhaba ben Can" diye kendini tekrar tanıtma.
                    
                    KULLANICI MESAJI: {user_msg}
                    """
                
                # --- ARAMA MODU ---
                else:
                    bilgi_metni = baglam if baglam else "Veri tabanında bilgi yok."
                    
                    if not baglam:
                        # Bulunamadı mesajı da hedef dilde olmalı
                        full_prompt = f"Kullanıcıya nazikçe aradığı bilginin YolPedia'da olmadığını söyle. DİL: {kullanici_dili}. Başka kaynak önerme."
                    else:
                        if detay_modu:
                            gorev = f"GÖREV: '{user_msg}' konusunu, verilen metni kullanarak EN İNCE DETAYINA KADAR anlat."
                        else:
                            gorev = f"GÖREV: '{user_msg}' sorusunu, verilen metni kullanarak KISA ve ÖZ (Özet) cevapla."

                        # --- KESİN DİL EMRİ ---
                        full_prompt = f"""
                        Senin adın 'Can'.
                        {gorev}
                        
                        ÇOK ÖNEMLİ KURALLAR:
                        1. HEDEF DİL: {kullanici_dili}. (Kaynak metin Türkçe olsa bile sen çevirip {kullanici_dili} yazacaksın).
                        2. Asla uydurma yapma.
                        3. Giriş cümlesi ("YolPedia'ya göre..." gibi) yapma.
                        
                        KAYNAK METİNLER:
                        {baglam}
                        """
                
                stream = model.generate_content(full_prompt, stream=True)
                
            except Exception as e:
                st.error(f"Bağlantı Hatası: {e}")

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
                    
                    # Link Gösterimi (Negatif kelimeler hedef dile göre de olmalı ama basit tutuyoruz)
                    if niyet == "ARAMA" and baglam and kaynaklar:
                        # Çok dilli negatif kontrolü zor olduğu için uzunluğa ve niyete güveniyoruz
                        # Eğer cevap çok kısaysa (Örn: "Bilgi yok" tercümesi) link göstermeyebiliriz
                        
                        # Basit bir "Bilgi Yok" kontrolü (Genel)
                        negatif_tr = ["bulunmuyor", "bilmiyorum", "bilgi yok"]
                        cevap_olumsuz = any(n in full_text.lower() for n in negatif_tr)
                        
                        # Eğer metin doluysa (bilgi varsa) linkleri göster
                        if len(full_text) > 50 and not cevap_olumsuz:
                            # Link başlığı dile göre değişebilir
                            baslik_link = "📚 Kaynaklar / Sources:" 
                            
                            yield "\n\n" + baslik_link + "\n"
                            
                            essiz = {v['link']:v for v in kaynaklar}.values()
                            for k in essiz:
                                link_satir = f"- [{k['baslik']}]({k['link']})\n"
                                for char in link_satir:
                                    yield char
                                    time.sleep(0.001)

                response_text = st.write_stream(stream_parser)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
                if niyet == "ARAMA" and not detay_modu:
                    st.rerun()
            except Exception as e:
                pass

# --- DETAY BUTONU ---
son_niyet = st.session_state.get('son_niyet', "")
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    
    # Buton metni de dile göre olsa güzel olur ama şimdilik standart tutalım
    btn_text = "📜 Detaylandır / More Details / Mehr Details"
    
    if son_niyet == "ARAMA" and len(last_msg) > 50:
        if len(last_msg) < 5000:
            col1, col2, col3 = st.columns([1,2,1])
            with col2:
                st.button(btn_text, on_click=detay_tetikle)

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
