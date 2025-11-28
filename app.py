import streamlit as st
import streamlit.components.v1 as components 
import requests
import google.generativeai as genai
import time
import json
import random
from PIL import Image
from io import BytesIO

# ================= AYARLAR =================
# Çoklu Anahtar Listesi
API_KEYS = [
    st.secrets.get("API_KEY", ""),
    st.secrets.get("API_KEY_2", ""),
    st.secrets.get("API_KEY_3", ""),
    st.secrets.get("API_KEY_4", ""),
    st.secrets.get("API_KEY_5", "")
]
# Boşlukları temizle ve sadece dolu anahtarları al
API_KEYS = [k.strip() for k in API_KEYS if k and len(k) > 20]

DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildigimin âlimiyim, bilmedigimin tâlibiyim!"'

# --- RESİMLER ---
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"
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
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 5px; margin-bottom: 5px; }
    .dede-img { width: 80px; height: 80px; border-radius: 50%; margin-right: 15px; object-fit: cover; border: 2px solid #eee; }
    .title-text { font-size: 36px; font-weight: 700; margin: 0; color: #ffffff; }
    .top-logo-container { display: flex; justify-content: center; margin-bottom: 45px; padding-top: 10px; }
    .top-logo { width: 90px; opacity: 1.0; }
    .motto-text { text-align: center; font-size: 16px; font-style: italic; color: #cccccc; margin-bottom: 25px; font-family: 'Georgia', serif; }
    .stChatMessage .avatar { width: 45px !important; height: 45px !important; }
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

# --- FONKSİYON: OTOMATİK KAYDIRMA ---
def scroll_to_bottom():
    js = """
    <script>
        var body = window.parent.document.querySelector(".main");
        body.scrollTop = body.scrollHeight;
    </script>
    """
    components.html(js, height=0)

# --- GÜVENLİ VE GERİYE DÖNÜK UYUMLU YANIT ÜRETİCİ (V6) ---
def guvenli_stream_baslat(full_prompt):
    """
    Bu versiyon hem yeni (1.5) hem eski (1.0) modelleri dener.
    Eğer kütüphane güncellenememişse 'gemini-pro' devreye girer ve hayat kurtarır.
    """
    # 1. Anahtarları Kontrol Et
    if not API_KEYS:
        st.error("❌ HATA: secrets.toml dosyasında geçerli API anahtarı yok.")
        return None

    random.shuffle(API_KEYS)
    hata_logu = []

    # LİSTE GÜNCELLENDİ: 'gemini-pro' eklendi. Bu model her sürümde çalışır.
    hedef_modeller = [
        "gemini-1.5-flash", 
        "gemini-1.5-pro", 
        "gemini-pro" # <--- İŞTE KURTARICI MODEL BU
    ]

    # 2. Anahtarları Dene
    for key in API_KEYS:
        genai.configure(api_key=key)
        
        for model_adi in hedef_modeller:
            try:
                # Güvenlik ayarlarını esnet
                guvenlik = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
                ]
                
                config = {"temperature": 0.3, "max_output_tokens": 8000}
                model_instance = genai.GenerativeModel(model_adi, generation_config=config, safety_settings=guvenlik)
                
                # İsteği gönder
                return model_instance.generate_content(full_prompt, stream=True)

            except Exception as e:
                err_msg = str(e).lower()
                hata_logu.append(f"Key: ...{key[-4:]} | Model: {model_adi} -> {err_msg[:40]}...")
                
                # Kota hatasıysa (429) bu anahtarı yakma, diğer anahtara geç
                if "429" in err_msg or "quota" in err_msg:
                    time.sleep(1)
                    break 
                
                # 404 (Bulunamadı) hatasıysa aynı anahtarla SIRADAKİ MODELE (gemini-pro) geç
                continue

    # --- BURAYA GELDİYSE HİÇBİR ŞEY ÇALIŞMAMIŞTIR ---
    st.warning("⚠️ Can Dede şu an bağlantı kuramıyor.")
    with st.expander("Geliştirici Logları"):
        for log in hata_logu:
            st.code(log, language="text")
            
    return None

# --- YARDIMCI FONKSİYONLAR ---
def get_model():
    if not API_KEYS: return None
    try:
        genai.configure(api_key=random.choice(API_KEYS))
        # Buraya da eski model desteği ekledik
        try:
            return genai.GenerativeModel("gemini-1.5-flash")
        except:
            return genai.GenerativeModel("gemini-pro")
    except: return None

def niyet_analizi(soru):
    try:
        local_model = get_model()
        if not local_model: return "ARAMA"
        prompt = f"""GİRDİ: "{soru}"\nKARAR: "ARAMA" veya "SOHBET". Tek kelime."""
        response = local_model.generate_content(prompt)
        return response.text.strip().upper()
    except: return "ARAMA"

def dil_tespiti(soru):
    try:
        local_model = get_model()
        if not local_model: return "Turkish"
        prompt = f"""GİRDİ: "{soru}"\nCEVAP (Sadece dil): Turkish, English, German..."""
        response = local_model.generate_content(prompt)
        return response.text.strip()
    except: return "Turkish"

def anahtar_kelime_ayikla(soru):
    try:
        local_model = get_model()
        if not local_model: return soru
        prompt = f"""GİRDİ: "{soru}"\nGÖREV: Konuyu bul. Hitapları at.\nCEVAP:"""
        response = local_model.generate_content(prompt)
        return response.text.strip()
    except: return soru

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

# --- METİN İŞLEME ---
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

# --- SOHBET BAŞLANGICI ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Merhaba, Erenler! Ben Can Dede. YolPedia'da rehberinizim. Rızanız da olursa, size delil olmaya gayret edeceğim."}
    ]

for message in st.session_state.messages:
    role_icon = CAN_DEDE_ICON if message["role"] == "assistant" else USER_ICON
    with st.chat_message(message["role"], avatar=role_icon):
        st.markdown(message["content"])

def detay_tetikle():
    st.session_state.detay_istendi = True

# --- GİRİŞ ALANI ---
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

    if is_user_input:
         with st.chat_message("user", avatar=USER_ICON):
            st.markdown(user_msg)
            scroll_to_bottom() # Sorunca kaydır

    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        baglam = None
        kaynaklar = None
        detay_modu = False
        niyet = st.session_state.get('son_niyet', "ARAMA")
        kullanici_dili = st.session_state.get('son_dil', "Turkish")
        stream = None
        
        with st.spinner("Can Dede düşünüyor..."):
            # 1. Veritabanı Araması
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
            
            # 2. Prompt Hazırlama
            if niyet == "SOHBET":
                full_prompt = f"""
                Senin adın 'Can Dede'. Sen YolPedia'nın rehberi ve sanal dedesisin.
                Kullanıcı ile sohbet et.
                KURALLAR:
                1. "Merhaba, erenler. Ben Can Dede" diye kendini tekrar tanıtma.
                2. Kullanıcının dili neyse ({kullanici_dili}) o dilde cevap ver.
                3. ASLA "Evlat" deme. Hitabın "Erenler", "Can Dost" veya "Sevgili Can" olsun.
                MESAJ: {user_msg}
                """
            else:
                bilgi_metni = baglam if baglam else "Bilgi bulunamadı."
                if not baglam:
                    full_prompt = f"Kullanıcıya nazikçe 'Üzgünüm Erenler, YolPedia arşivinde bu konuda bilgi yok.' de. DİL: {kullanici_dili}."
                else:
                    if detay_modu:
                        gorev = f"GÖREV: '{user_msg}' konusunu, metinlerdeki farklı görüşleri sentezleyerek EN İNCE DETAYINA KADAR anlat."
                    else:
                        gorev = f"GÖREV: '{user_msg}' sorusuna, bilgileri süzerek KISA, ÖZ ve HİKMETLİ bir cevap ver."

                    full_prompt = f"""
                    Sen 'Can Dede'sin. HEDEF DİL: {kullanici_dili}. {gorev}
                    KURALLAR:
                    1. "Yol bir, sürek binbir" ilkesiyle anlat.
                    2. ASLA "Evlat" deme. "Erenler" veya "Can" de.
                    3. Giriş cümlesi yapma.
                    BİLGİLER: {baglam}
                    """
            
            # 3. YENİ GÜVENLİ FONKSİYONU ÇAĞIR
            stream = guvenli_stream_baslat(full_prompt)

        # 4. Yanıtı Yazdır
        if stream:
            try:
                def stream_parser():
                    full_text = ""
                    for chunk in stream:
                        try:
                            text_chunk = chunk.text
                            if text_chunk:
                                full_text += text_chunk
                                yield text_chunk
                        except ValueError: continue
                    
                    # Kaynakları Ekleme
                    if niyet == "ARAMA" and baglam and kaynaklar:
                        negatif = ["bulunmuyor", "bilmiyorum", "bilgi yok", "not found", "keine information"]
                        cevap_olumsuz = any(n in full_text.lower() for n in negatif)
                        if not cevap_olumsuz:
                            if "German" in kullanici_dili: link_baslik = "**📚 Quellen:**"
                            elif "English" in kullanici_dili: link_baslik = "**📚 Sources:**"
                            else: link_baslik = "**📚 Kaynaklar:**"
                            
                            kaynak_metni = f"\n\n{link_baslik}\n"
                            essiz = {v['link']:v for v in kaynaklar}.values()
                            for k in essiz:
                                kaynak_metni += f"- [{k['baslik']}]({k['link']})\n"
                            yield kaynak_metni

                response_text = st.write_stream(stream_parser)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                scroll_to_bottom()

            except Exception as e:
                st.error("Bir teknik hata oluştu, lütfen tekrar deneyin.")

# --- DETAY BUTONU ---
son_niyet = st.session_state.get('son_niyet', "")
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    last_msg = st.session_state.messages[-1]["content"]
    
    if son_niyet == "ARAMA" and "Hata" not in last_msg and "bulunmuyor" not in last_msg and "not found" not in last_msg.lower():
        if len(last_msg) < 5000:
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
