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
    generation_config = {
        "temperature": 0.0,
        "max_output_tokens": 8192
    }
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name.lower():
                    return genai.GenerativeModel(m.name, generation_config=generation_config)
        return genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
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
    with st.spinner('Sistem başlatılıyor...'):
        veriler = veri_yukle()
        if veriler:
            st.session_state.db = veriler
            st.success(f"✅ Sistem Hazır! {len(veriler)} madde yüklendi.")
            time.sleep(1)
            st.rerun()
        else:
            st.error("⚠️ Veri dosyası (JSON) bulunamadı! Lütfen GitHub'a yükleyin.")

# --- YARDIMCI FONKSİYONLAR ---
def tr_normalize(metin):
    kaynak = "ğĞüÜşŞıİöÖçÇ"
    hedef  = "gGuUsSiIoOcC"
    ceviri_tablosu = str.maketrans(kaynak, hedef)
    return metin.translate(ceviri_tablosu).lower()

def alakali_icerik_bul(soru, tum_veriler):
    gereksiz = ["nedir", "kimdir", "neredir", "nasil", "niye", "hangi", "kac", "ne", "ve", "ile", "bir", "bu", "su", "mi", "mu", "hakkinda", "bilgi", "almak", "istiyorum", "onun", "bunun", "suranin"]
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

if prompt := st.chat_input("Bir soru sorun..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if 'db' in st.session_state and st.session_state.db:
            with st.spinner("🔎 Ansiklopedi taranıyor..."):
                time.sleep(0.3)
                baglam, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
            
            # --- HAFIZA OLUŞTURMA (SON 4 MESAJ) ---
            gecmis_sohbet = ""
            # Son 4 mesajı al (2 soru, 2 cevap) ki bağlam kopmasın ama token dolmasın
            for msg in st.session_state.messages[-4:]:
                rol = "Kullanıcı" if msg['role'] == 'user' else "Asistan"
                # Kaynak linklerini hafızaya alma, kafasını karıştırır
                temiz_icerik = msg['content'].split("**📚 Kaynaklar:**")[0] 
                gecmis_sohbet += f"{rol}: {temiz_icerik}\n"
            
            # Bağlam boş olsa bile geçmişe bakarak cevap verebilir mi kontrol et
            # (Örn: "Merhaba" dediğinde bağlam boştur ama cevap vermelidir)
            
            try:
                # --- AKILLI VE HAFIZALI PROMPT ---
                full_prompt = f"""
                Sen YolPedia ansiklopedi asistanısın.
                
                GÖREVİN:
                Sana verilen 'BİLGİLER' metnini kullanarak soruyu en detaylı şekilde cevapla.
                Aşağıdaki 'GEÇMİŞ SOHBET' kısmına bakarak konuşmanın akışını takip et.
                
                KURALLAR:
                1. Asla uydurma yapma, sadece verilen metinleri kullan.
                2. Cevapları kısa tutma, detaylı anlat.
                3. Eğer soru sohbete dayalıysa (Örn: 'Merhaba', 'Nasılsın'), kibarca yanıt ver ve ansiklopediden ne sorabileceğini söyle.
                4. Eğer ansiklopedik bir soruysa ve metinlerde cevap YOKSA, "Üzgünüm, YolPedia arşivinde bu konuyla ilgili net bir bilgi bulunmuyor." de.
                
                GEÇMİŞ SOHBET:
                {gecmis_sohbet}
                
                YENİ SORU: {prompt}
                
                YENİ SORU İÇİN BULUNAN BİLGİLER:
                {baglam if baglam else "Veri tabanında bu kelimeyle ilgili özel bir eşleşme bulunamadı."}
                """
                
                stream = model.generate_content(full_prompt, stream=True)
                
                def stream_parser():
                    full_text = ""
                    for chunk in stream:
                        if chunk.text:
                            for word in chunk.text.split(" "):
                                yield word + " "
                                time.sleep(0.03)
                            full_text += chunk.text
                    
                    negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "rastlanmamaktadır", "üzgünüm", "maalesef"]
                    cevap_olumsuz = any(n in full_text.lower() for n in negatif)
                    
                    # Eğer bağlam bulunduysa ve cevap olumluysa linkleri ekle
                    if baglam and kaynaklar and not cevap_olumsuz:
                        kaynak_metni = "\n\n**📚 Kaynaklar:**\n"
                        # Tekrar eden linkleri temizle
                        essiz_kaynaklar = {v['link']:v for v in kaynaklar}.values()
                        
                        for k in essiz_kaynaklar:
                            kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                        
                        for line in kaynak_metni.split("\n"):
                            yield line + "\n"
                            time.sleep(0.1)

                response = st.write_stream(stream_parser)
                st.session_state.messages.append({"role": "assistant", "content": response})

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
        
        # --- MÜFETTİŞ ---
        st.divider()
        st.subheader("🕵️ Veri Müfettişi")
        test_arama = st.text_input("Veri tabanında ara:", placeholder="Örn: Otman Baba")
        
        if test_arama:
            bulunan_sayisi = 0
            norm_aranan = tr_normalize(test_arama)
            for v in st.session_state.db:
                norm_baslik = tr_normalize(v['baslik'])
                norm_icerik = tr_normalize(v['icerik'])
                if norm_aranan in norm_baslik or norm_aranan in norm_icerik:
                    st.success(f"✅ {v['baslik']}")
                    bulunan_sayisi += 1
                    if bulunan_sayisi >= 5: break
            if bulunan_sayisi == 0:
                st.error("❌ Bu kelime veritabanında yok!")
        # ----------------
        st.divider()
        if st.checkbox("Tüm Başlıkları Gör"):
            for item in st.session_state.db:
                st.text(item['baslik'])
