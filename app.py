import streamlit as st
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

# --- SAYFA YAPILANDIRMA ---
st.set_page_config(page_title="YolPedia Asistanı", page_icon="🤖")

# --- CSS STİLLERİ ---
st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 10px; margin-bottom: 20px; }
    .logo-img { width: 80px; margin-right: 15px; }
    .title-text { font-size: 36px; font-weight: 700; margin: 0; color: #ffffff; }
    @media (prefers-color-scheme: light) { .title-text { color: #000000; } }
    /* Detay butonu stili */
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
        st.session_state.db = veri_yukle()
    # Sayfayı yenileme kodu burada kalsın ama aşağıda UI çizildikten sonra çalışacak

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

# --- YAN MENÜ (EN BAŞA ALDIK Kİ KAYBOLMASIN) ---
with st.sidebar:
    st.header("⚙️ Yönetim")
    
    if st.button("🔄 Önbelleği Temizle"):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    
    if 'db' in st.session_state:
        st.write(f"📊 Toplam İçerik: {len(st.session_state.db)}")
        
        # --- VERİ MÜFETTİŞİ (GERİ GELDİ) ---
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
        # -----------------------------------
        
        st.divider()
        if st.checkbox("Tüm Başlıkları Gör"):
            for item in st.session_state.db:
                st.text(item['baslik'])

# --- SOHBET ARAYÜZÜ ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mesajları Ekrana Bas
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- BUTON TETİKLEYİCİ ---
def detay_tetikle():
    st.session_state.detay_istendi = True

# --- GİRİŞ ALANI ---
prompt = st.chat_input("Bir soru sorun...")

is_user_input = prompt is not None
is_detail_click = st.session_state.get('detay_istendi', False)

# --- İŞLEM MANTIĞI ---
if is_user_input or is_detail_click:
    
    # 1. Yeni Soru
    if is_user_input:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.detay_istendi = False
        st.session_state.son_baglam = None 
        st.session_state.son_kaynaklar = None
        st.session_state.son_soru = prompt
        user_msg = prompt
        
    # 2. Detay Butonu
    elif is_detail_click:
        st.session_state.detay_istendi = False
        user_msg = st.session_state.get('son_soru', "")
        # Butona basıldığını belirten gizli bir mesaj eklemiyoruz, direkt cevap üretiyoruz

    # Kullanıcı mesajını ekrana bas (Sadece yeniyse)
    if is_user_input:
         with st.chat_message("user"):
            st.markdown(user_msg)

    with st.chat_message("assistant"):
        if 'db' in st.session_state and st.session_state.db:
            
            baglam = None
            kaynaklar = None
            detay_modu = False
            
            # Detay isteği mi?
            if is_detail_click and st.session_state.get('son_baglam'):
                baglam = st.session_state.son_baglam
                kaynaklar = st.session_state.son_kaynaklar
                detay_modu = True
            else:
                # Normal arama
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
                        DİKKAT: Metin yığını içinde birden fazla konu olabilir.
                        GÖREVİN: Sadece ve sadece "{user_msg}" ile ilgili olan kısımları cımbızla çek ve DETAYLI, UZUN bir şekilde anlat.
                        Diğer başlıkları görmezden gel.
                        """
                    else:
                        gorev = f"""
                        GÖREVİN: Sana verilen metinleri kullanarak "{user_msg}" sorusuna KISA VE ÖZ (ÖZET) bir cevap ver.
                        Detaylara boğma, sadece en önemli bilgileri ver.
                        """

                    full_prompt = f"""
                    Sen YolPedia ansiklopedi asistanısın.
                    {gorev}
                    KURALLAR:
                    1. "YolPedia arşivine göre" gibi girişler yapma. Doğal konuş.
                    2. Asla uydurma yapma.
