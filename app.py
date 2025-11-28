import streamlit as st
import streamlit.components.v1 as components 
import requests
import google.generativeai as genai
import time
import json
import random

# ================= AYARLAR =================
API_KEYS = [
    st.secrets.get("API_KEY", ""),
    st.secrets.get("API_KEY_2", ""),
    st.secrets.get("API_KEY_3", ""),
    st.secrets.get("API_KEY_4", ""),
    st.secrets.get("API_KEY_5", "")
]
API_KEYS = [k.strip() for k in API_KEYS if k and len(k) > 20]

DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildigimin âlimiyim, bilmedigimin tâlibiyim!"'
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"

# --- SAYFA AYARLARI ---
st.set_page_config(page_title=ASISTAN_ISMI, page_icon=YOLPEDIA_ICON)

st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 5px; margin-bottom: 5px; }
    .dede-img { width: 80px; height: 80px; border-radius: 50%; margin-right: 15px; object-fit: cover; border: 2px solid #eee; }
    .title-text { font-size: 36px; font-weight: 700; margin: 0; color: #ffffff; }
    .top-logo-container { display: flex; justify-content: center; margin-bottom: 45px; padding-top: 10px; }
    .top-logo { width: 90px; opacity: 1.0; }
    .motto-text { text-align: center; font-size: 16px; font-style: italic; color: #cccccc; margin-bottom: 25px; font-family: 'Georgia', serif; }
    @media (prefers-color-scheme: light) { .title-text { color: #000000; } .motto-text { color: #555555; } }
    .stChatMessage { margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header"><img src="{CAN_DEDE_ICON}" class="dede-img"><h1 class="title-text">Can Dede</h1></div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)

# --- VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: 
            data = json.load(f)
            for d in data:
                d['norm_baslik'] = tr_normalize(d['baslik'])
                d['norm_icerik'] = tr_normalize(d['icerik'])
            return data
    except: return []

def tr_normalize(text):
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

if 'db' not in st.session_state: st.session_state.db = veri_yukle()

# --- ARAMA MOTORU ---
def alakali_icerik_bul(kelime, db):
    if not db: return "", []
    
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    
    if len(norm_sorgu) < 3: return "", []

    sonuclar = []
    for d in db:
        puan = 0
        if norm_sorgu in d['norm_baslik']: puan += 100
        elif norm_sorgu in d['norm_icerik']: puan += 50
        for k in anahtarlar:
            if k in d['norm_baslik']: puan += 15
            elif k in d['norm_icerik']: puan += 5     
        
        if puan > 40:
            sonuclar.append({"veri": d, "puan": puan})
    
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    en_iyiler = sonuclar[:4] 
    
    context_text = ""
    kaynaklar = []
    
    for item in en_iyiler:
        v = item['veri']
        context_text += f"\n--- KAYNAK BİLGİ: {v['baslik']} ---\n{v['icerik'][:4000]}\n"
        kaynaklar.append({"baslik": v['baslik'], "link": v['link']})
        
    return context_text, kaynaklar

# --- MODEL SEÇİCİ ---
def uygun_modeli_bul_ve_getir():
    try:
        mevcut_modeller = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if not mevcut_modeller: return None, "Hiçbir model bulunamadı"
        tercihler = ["gemini-1.5-flash", "models/gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
        for t in tercihler:
            for m in mevcut_modeller:
                if t in m: return m, None
        return mevcut_modeller[0], None
    except Exception as e:
        return None, str(e)

def can_dede_cevapla(user_prompt, chat_history, context_data, kaynak_var_mi):
    if not API_KEYS:
        yield "HATA: API Anahtarı eksik."
        return

    # --- GÖREV TANIMI ---
    if kaynak_var_mi:
        gorev_tanimi = """
        GÖREVİN:
        1. Sorulan soruya önce edebi ve akıcı bir dille **kısa, net ve öz** bir cevap ver.
        2. Sonra tam olarak '###DETAY###' yaz.
        3. Sonra kaynakları kullanarak detaylı, felsefi derinliği olan anlatımını yap.
        """
    else:
        gorev_tanimi = """
        GÖREVİN:
        Sadece samimi, edebi ve felsefi bir dille sohbet et. 
        ASLA '###DETAY###' ayırıcı kullanma.
        """

    # --- KARAKTER, ÜSLUP VE DİL AYARLARI ---
    system_prompt = f"""
    Sen 'Can Dede'sin. Anadolu'nun kadim bilgeliğini modern, seküler ve felsefi bir dille harmanlayan bir rehbersin.
    
    ÜSLUP VE KURALLARIN:
    1. DİL DESTEĞİ: Kullanıcı hangi dilde sorarsa (İngilizce, Almanca, vb.) MUTLAKA O DİLDE cevap ver.
    2. Yabancı dilde bile olsa "Can Dede" bilgeliğini ve sıcaklığını o dile uyarla.
    3. Türkçe konuşuluyorsa: "Erenler", "Can dost", "Can", "Sevgili dost" gibi hitaplar kullan.
    4. FELSEFE: Dogmatik değil; akılcı, hümanist ve felsefi bir derinlikle konuş.
    5. TAVIR: Kaba veya cahilce sorulara tartışmaya girmeden, hikmetle kısa cevap verip geç.
    
    {gorev_tanimi}
    
    BİLGİ KAYNAKLARI:
    {context_data if context_data else "Ek kaynak yok."}
    """

    contents = []
    contents.append({"role": "user", "parts": [system_prompt]})
    contents.append({"role": "model", "parts": ["Anlaşıldı."] }) 
    
    for msg in chat_history[-4:]:
        role = "user" if msg["role"] == "user" else "model"
        clean_content = msg["content"].replace("###DETAY###", "").split("📚 Yararlanılan Kaynaklar")[0]
        contents.append({"role": role, "parts": [clean_content]})
    
    contents.append({"role": "user", "parts": [user_prompt]})
    
    guvenlik = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    
    random.shuffle(API_KEYS)
    
    for key in API_KEYS:
        genai.configure(api_key=key)
        model_adi, hata = uygun_modeli_bul_ve_getir()
        
        if not model_adi: continue

        try:
            model = genai.GenerativeModel(model_adi)
            response = model.generate_content(contents, stream=True, safety_settings=guvenlik)
            for chunk in response:
                try:
                    if chunk.text: yield chunk.text
                except: continue
            return 
        except:
            time.sleep(0.5)
            continue 

    yield "Şu anda tefekkürdeyim (Bağlantı Sorunu)."

# --- GÜÇLENDİRİLMİŞ OTOMATİK KAYDIRMA ---
def scroll_to_bottom():
    # Bu script, render gecikmelerini aşmak için kaydırma işlemini birkaç kez tekrarlar
    js = """
    <script>
    function forceScroll() {
        var main = window.parent.document.querySelector(".main");
        if (main) {
            main.scrollTop = main.scrollHeight;
        }
    }
    forceScroll();
    setTimeout(forceScroll, 100);
    setTimeout(forceScroll, 500);
    </script>
    """
    components.html(js, height=0)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Merhaba Can Dost! Ben Can Dede. Gönül heybende ne taşırsın, gel paylaşalım?"}]

for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    with st.chat_message(msg["role"], avatar=icon):
        if "###DETAY###" in msg["content"]:
            parts = msg["content"].split("###DETAY###")
            st.markdown(parts[0])
            with st.expander("📜 Daha Fazla Detay ve Kaynaklar"):
                st.markdown(parts[1])
        else:
            st.markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom() # Soruyu yazınca aşağı in
    
    baglam_metni, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
    kaynak_var_mi = len(kaynaklar) > 0
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        placeholder = st.empty()
        detay_container = st.empty()
        
        # --- ANİMASYON ---
        animasyon_html = f"""
        <div style="display: flex; align-items: center; gap: 10px; margin-top: 5px;">
            <div style="
                width: 12px; height: 12px; border-radius: 50%; background-color: #aaa;
                animation: pulse 1s infinite alternate;"></div>
            <span style="font-style: italic; color: #666; font-size: 14px;">Can Dede tefekkür ediyor...</span>
        </div>
        <style>@keyframes pulse {{ from {{ opacity: 0.3; transform: scale(0.8); }} to {{ opacity: 1; transform: scale(1.1); }} }}</style>
        """
        placeholder.markdown(animasyon_html, unsafe_allow_html=True)
        # -----------------
        
        full_text = ""
        ozet_text = ""
        detay_text = ""
        detay_modu_aktif = False
        
        stream = can_dede_cevapla(prompt, st.session_state.messages[:-1], baglam_metni, kaynak_var_mi)
        
        for chunk in stream:
            full_text += chunk
            
            if kaynak_var_mi and ("###DETAY###" in chunk or "###DETAY###" in full_text):
                if not detay_modu_aktif:
                    parts = full_text.split("###DETAY###")
                    ozet_text = parts[0]
                    if len(parts) > 1: detay_text = parts[1]
                    detay_modu_aktif = True
                else:
                    if "###DETAY###" in chunk: chunk = chunk.replace("###DETAY###", "")
                    detay_text += chunk
            else:
                ozet_text += chunk
            
            if not detay_modu_aktif:
                placeholder.markdown(ozet_text + "▌")
            else:
                placeholder.markdown(ozet_text)
        
        placeholder.markdown(ozet_text)
        
        final_history = full_text

        if kaynak_var_mi and detay_text.strip():
            with detay_container.container():
                with st.expander("📜 Daha Fazla Detay ve Kaynaklar", expanded=False):
                    st.markdown(detay_text)
                    
                    st.markdown("\n\n---\n**📚 Yararlanılan Kaynaklar:**")
                    seen = set()
                    for k in kaynaklar:
                        if k['link'] not in seen:
                            st.markdown(f"- [{k['baslik']}]({k['link']})")
                            seen.add(k['link'])
                            final_history += f"\n\n[{k['baslik']}]({k['link']})"
        
        st.session_state.messages.append({"role": "assistant", "content": final_history})
        # --- CEVAP BİTİNCE OTOMATİK KAYDIRMA ---
        scroll_to_bottom()
