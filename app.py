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
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
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
    /* Gölge sorununu çözen stil */
    .element-container { margin-bottom: 0px !important; }
</style>
""", unsafe_allow_html=True)

# --- BAŞLIK ---
st.markdown(
    f"""
    <div class="main-header">
        <img src="{LOGO_URL}" class="logo-img">
        <h1 class="title-text">Can Dede</h1>
    </div>
    <div style="text-align: center; color: gray; margin-bottom: 20px; font-style: italic;">
        "Bildigimin âlimiyim, bilmedigimin tâlibiyim!"
    </div>
    """,
    unsafe_allow_html=True
)

genai.configure(api_key=API_KEY)

# --- MODELİ BUL ---
@st.cache_resource
def model_yukle():
    # Yaratıcılığı çok az açtık (0.2) ki robot gibi konuşmasın, dede gibi konuşsun
    generation_config = {"temperature": 0.2, "max_output_tokens": 8192}
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
        KARAR KURALLARI:
        - Bilgi araması (Örn: "Dersim nerede?", "Alevilik nedir?", "Dedem Alevi kime denir?"): "ARAMA"
        - Sohbet, selam (Örn: "Merhaba", "Nasılsın", "Sağol"): "SOHBET"
        Sadece tek kelime cevap ver: "ARAMA" veya "SOHBET"
        """
        response = model.generate_content(prompt)
        return response.text.strip().upper()
    except:
        return "ARAMA"

# --- 2. AJAN: HİTAP TEMİZLEYİCİ (SEZGİSEL ZEKA) ---
def anahtar_kelime_ayikla(soru):
    try:
        prompt = f"""
        GİRDİ: "{soru}"
        
        GÖREV: 
        Kullanıcı bota "Dedem", "Hocam", "Can", "Kardeşim" gibi hitaplarla sesleniyor olabilir.
        Bu hitap sözcüklerini ve soru eklerini atarak, kullanıcının ASIL MERAK ETTİĞİ KONUYU (Entity) bul.
        
        ÖRNEKLER:
        "Dedem, Alevi kime denir?" -> Alevi
        "Can, Dersim neresidir?" -> Dersim
        "Hocam Oniki hizmet nedir?" -> Oniki hizmet
        "Mustafa Sazcı kimdir?" -> Mustafa Sazcı
        
        CEVAP (Sadece temizlenmiş konu):
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
    # Çok kısa kelimeleri ele
    anahtar = [k for k in soru_temiz.split() if len(k) > 2]
    
    puanlanmis = []
    for veri in tum_veriler:
        baslik_norm = tr_normalize(veri['baslik'])
        icerik_norm = tr_normalize(veri['icerik'])
        puan = 0
        
        # Tam eşleşme bonusu
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

# --- SOHBET GEÇMİŞİ ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Merhaba Erenler! Ben Can Dede. YolPedia rehberinizim. Size nasıl yardımcı olabilirim?"}
    ]

# Mesajları Ekrana Bas
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- DETAY BUTONU İŞLEVİ ---
def detay_tetikle():
    st.session_state.detay_istendi = True

# --- GİRİŞ ---
prompt = st.chat_input("Can Dede'ye sor...")

is_user_input = prompt is not None
is_detail_click = st.session_state.get('detay_istendi', False)

if is_user_input or is_detail_click:
    
    if is_user_input:
        # Kullanıcı mesajını ekle ve göster
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        st.session_state.detay_istendi = False
        st.session_state.son_baglam = None 
        st.session_state.son_kaynaklar = None
        
        # 1. NİYETİ ANLA
        niyet = niyet_analizi(prompt)
        st.session_state.son_niyet = niyet
        
        # 2. KONUYU AYIKLA (Dedem, hocam gibi lafları at)
        arama_kelimesi = prompt
        if niyet == "ARAMA":
            arama_kelimesi = anahtar_kelime_ayikla(prompt)
            
        user_msg = prompt
        
    elif is_detail_click:
        # Detay butonuna basıldıysa sadece asistan cevap verir
        st.session_state.detay_istendi = False
        # Son kullanıcı mesajını (soruyu) bul
        user_msg = ""
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "user":
                user_msg = msg["content"]
                break
        
        # Detayda da temizleme yapalım
        arama_kelimesi = anahtar_kelime_ayikla(user_msg)
        st.session_state.son_niyet = "ARAMA"

    with st.chat_message("assistant"):
        baglam = None
        kaynaklar = None
        detay_modu = False
        niyet = st.session_state.get('son_niyet', "ARAMA")
        stream = None
        
        with st.spinner("Can Dede düşünüyor..."):
            if niyet == "ARAMA":
                if 'db' in st.session_state and st.session_state.db:
                    # Eğer detay isteğiyse ve hafızada varsa onu kullan
                    if is_detail_click and st.session_state.get('son_baglam'):
                        baglam = st.session_state.son_baglam
                        kaynaklar = st.session_state.son_kaynaklar
                        detay_modu = True
                    else:
                        # Yoksa ara
                        baglam, kaynaklar = alakali_icerik_bul(arama_kelimesi, st.session_state.db)
                        st.session_state.son_baglam = baglam
                        st.session_state.son_kaynaklar = kaynaklar
            
            try:
                if niyet == "SOHBET":
                    full_prompt = f"""
                    Senin adın 'Can Dede'. Sen YolPedia'nın bilge rehberisin.
                    Kullanıcı ile sohbet et.
                    
                    KURALLAR:
                    1. ASLA kendini tekrar tanıtma ("Ben Can Dede..." deme).
                    2. Kullanıcının dili neyse o dilde cevap ver.
                    3. "Erenler" kültürüne uygun, samimi ve bilge bir dil kullan.
                    
                    MESAJ: {user_msg}
                    """
                else:
                    bilgi_metni = baglam if baglam else "Bilgi bulunamadı."
                    
                    if not baglam:
                        full_prompt = f"Kullanıcıya nazikçe 'Üzgünüm Erenler, YolPedia arşivinde bu konuda şimdilik bilgi yok.' de. Kullanıcının diliyle söyle."
                    else:
                        if detay_modu:
                            gorev = f"GÖREVİN: '{user_msg}' konusunu, aşağıdaki BİLGİLER'i kullanarak EN İNCE DETAYINA KADAR anlat."
                        else:
                            gorev = f"GÖREVİN: '{user_msg}' sorusuna, aşağıdaki BİLGİLER'i kullanarak KISA ve ÖZ (Özet) bir cevap ver."

                        full_prompt = f"""
                        Senin adın 'Can Dede'.
                        {gorev}
                        
                        KURALLAR:
                        1. ASLA "Merhaba ben Can Dede" veya "YolPedia verilerine göre" diye başlama. Direkt cevabı ver.
                        2. Kullanıcı sana "Dedem" diye hitap etmiş olabilir, sen de ona bilgece cevap ver.
                        3. Kullanıcının dili neyse o dilde yaz.
                        4. Asla uydurma yapma.
                        
                        BİLGİLER: {baglam}
                        """
                
                stream = model.generate_content(full_prompt, stream=True)
                
            except Exception as e:
                st.error(f"Hata: {e}")

        if stream:
            try:
                # Cevap tutucu
                full_response = ""
                
                # --- STREAMING İÇİN BOŞ KUTU ---
                message_placeholder = st.empty()
                
                for chunk in stream:
                    try:
                        if chunk.text:
                            for char in chunk.text:
                                full_response += char
                                # Her harfte değil, her birkaç harfte bir güncelle (Performans için)
                                # Ama efekti hissettir
                                if len(full_response) % 5 == 0: 
                                    message_placeholder.markdown(full_response + "▌")
                                    time.sleep(0.001)
                    except ValueError:
                        continue
                
                # Linkleri Ekle
                if niyet == "ARAMA" and baglam and kaynaklar:
                    negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "not found", "keine information"]
                    cevap_olumsuz = any(n in full_response.lower() for n in negatif)
                    
                    if not cevap_olumsuz:
                        kaynak_metni = "\n\n**📚 Kaynaklar / Sources:**\n"
                        essiz = {v['link']:v for v in kaynaklar}.values()
                        for k in essiz:
                            kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                        
                        # Linkleri de efekte dahil et
                        for char in kaynak_metni:
                            full_response += char
                            if len(full_response) % 5 == 0:
                                message_placeholder.markdown(full_response + "▌")
                                time.sleep(0.001)

                # Final halini imleçsiz bas
                message_placeholder.markdown(full_response)
                
                # Geçmişe kaydet
                st.session_state.messages.append({"role": "assistant", "content": full_response})
                
                # GÖLGE SORUNU ÇÖZÜMÜ: Buraya rerun KOYMUYORUZ. 
                # Sadece butonun çıkması gerekiyorsa, o da bir sonraki döngüde zaten çıkacak.
                # Ama anlık görünsün diye sadece buton için özel bir alan (empty) kullanılabilir.
                # Şimdilik rerun'ı kaldırarak gölgeyi engelliyoruz.

            except Exception as e:
                pass

# --- DETAY BUTONU (Döngünün dışında, en altta) ---
# En son mesaj asistandansa ve butonluksa göster
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    son_niyet = st.session_state.get('son_niyet', "")
    
    if son_niyet == "ARAMA" and "Hata" not in last_msg and "bulunmuyor" not in last_msg and "not found" not in last_msg.lower():
        if len(last_msg) < 5000:
            st.button("📜 Bu Konuyu Detaylandır / Details", on_click=detay_tetikle)

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
