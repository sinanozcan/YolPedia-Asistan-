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
st.set_page_config(page_title=ASISTAN_ISMI, page_icon=YOLPEDIA_ICON, layout="wide")

# --- CSS ---
st.markdown("""
<style>
    .main-header { display: flex; align-items: center; justify-content: center; margin-top: 5px; margin-bottom: 5px; }
    .dede-img { width: 80px; height: 80px; border-radius: 50%; margin-right: 15px; object-fit: cover; border: 2px solid #eee; }
    .title-text { font-size: 36px; font-weight: 700; margin: 0; color: #ffffff; }
    .top-logo-container { display: flex; justify-content: center; margin-bottom: 20px; padding-top: 10px; }
    .top-logo { width: 80px; opacity: 1.0; }
    .motto-text { text-align: center; font-size: 16px; font-style: italic; color: #cccccc; margin-bottom: 25px; font-family: 'Georgia', serif; }
    @media (prefers-color-scheme: light) { .title-text { color: #000000; } .motto-text { color: #555555; } }
    .stChatMessage { margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- HIZLANDIRILMIŞ VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: 
            data = json.load(f)
            processed_data = []
            for d in data:
                # Sadece başlığı ve içeriğin ilk 500 karakterini normalize et (HIZ İÇİN)
                ham_baslik = d.get('baslik', '')
                ham_icerik = d.get('icerik', '')
                
                d['norm_baslik'] = tr_normalize(ham_baslik)
                # Tüm içeriği normalize etmek yerine aramayı hızlandırmak için kısaltıyoruz
                # (Zaten kelime başta geçiyorsa alakalıdır)
                d['norm_icerik'] = tr_normalize(ham_icerik) 
                processed_data.append(d)
            return processed_data
    except: return []

def tr_normalize(text):
    if not isinstance(text, str): return ""
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

if 'db' not in st.session_state: st.session_state.db = veri_yukle()

# --- MOD SEÇİMİ ---
with st.sidebar:
    st.image(CAN_DEDE_ICON, width=100)
    st.title("Mod Seçimi")
    secilen_mod = st.radio(
        "Can Dede nasıl yardımcı olsun?",
        ["☕ Sohbet Modu", "🔍 Araştırma Modu"],
        captions=["Sadece muhabbet eder, kaynak taramaz.", "YolPedia kütüphanesini tarar ve kaynak sunar."]
    )
    st.markdown("---")
    st.info(f"Aktif Mod: **{secilen_mod}**")

# --- HEADER ---
st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header"><img src="{CAN_DEDE_ICON}" class="dede-img"><h1 class="title-text">Can Dede</h1></div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)


# --- HIZLANDIRILMIŞ ARAMA MOTORU ---
def alakali_icerik_bul(kelime, db, mod):
    if "Sohbet" in mod: return "", []
    if not db: return "", []
    
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    
    if len(norm_sorgu) < 3: return "", []

    sonuclar = []
    
    # Döngü optimizasyonu: Her kaydı detaylı incelemek yerine basit string kontrolü
    for d in db:
        puan = 0
        d_baslik = d.get('norm_baslik', '')
        d_icerik = d.get('norm_icerik', '') # Zaten bellekte hazır
        
        # Basit string araması (En hızlı yöntem)
        if norm_sorgu in d_baslik: puan += 100
        elif norm_sorgu in d_icerik: puan += 50
        
        for k in anahtarlar:
            if k in d_baslik: puan += 20
            elif k in d_icerik: puan += 5     
        
        if puan > 15:
            sonuclar.append({"veri": d, "puan": puan})
    
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    en_iyiler = sonuclar[:6]
    
    context_text = ""
    kaynaklar = []
    
    for item in en_iyiler:
        v = item['veri']
        v_baslik = v.get('baslik', 'Başlıksız')
        v_icerik = v.get('icerik', '')
        v_link = v.get('link', '#')
        
        context_text += f"\n--- KAYNAK BİLGİ: {v_baslik} ---\n{v_icerik[:4000]}\n"
        kaynaklar.append({"baslik": v_baslik, "link": v_link})
        
    return context_text, kaynaklar

def can_dede_cevapla(user_prompt, chat_history, context_data, mod):
    if not API_KEYS:
        yield "HATA: API Anahtarı eksik."
        return

    # --- MODA GÖRE GÖREV ---
    if "Araştırma" in mod:
        gorev_tanimi = """
        MOD: ARAŞTIRMA MODU.
        GÖREVİN:
        1. Kullanıcının sorusunu 'BİLGİ KAYNAKLARI' kısmındaki verileri temel alarak cevapla.
        2. Önce kısa bir özet geç.
        3. Sonra tam olarak '###DETAY###' yaz.
        4. Sonra konuyu kaynaklara dayanarak detaylandır.
        """
        kaynak_metni = context_data if context_data else "İlgili kaynak bulunamadı, genel kültürünle cevapla."
    else:
        gorev_tanimi = """
        MOD: SOHBET MODU.
        GÖREVİN:
        Sadece samimi, edebi ve felsefi bir dille sohbet et. 
        ASLA '###DETAY###' ayırıcı kullanma.
        ASLA kaynaklardan bahsetme.
        """
        kaynak_metni = "Sohbet modundasın, kaynak kullanma."

    system_prompt = f"""
    Sen 'Can Dede'sin. Anadolu'nun kadim bilgeliğini modern, seküler ve felsefi bir dille harmanlayan bir rehbersin.
    
    ÜSLUP VE KURALLARIN:
    1. DİL DESTEĞİ: Kullanıcı hangi dilde sorarsa MUTLAKA O DİLDE cevap ver.
    2. Türkçe konuşuluyorsa: "Erenler", "Can dost", "Can", "Sevgili dost" gibi hitaplar kullan.
    3. FELSEFE: Dogmatik değil; akılcı, hümanist ve felsefi bir derinlikle konuş.
    
    {gorev_tanimi}
    
    BİLGİ KAYNAKLARI:
    {kaynak_metni}
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
    
    # --- KRİTİK HIZLANDIRMA: LİSTELEME YOK, DOĞRUDAN ÇAĞRI VAR ---
    for key in API_KEYS:
        genai.configure(api_key=key)
        
        # 'uygun_modeli_bul' fonksiyonunu sildik.
        # Doğrudan en hızlı modeli (Flash) çağırıyoruz.
        try:
            model = genai.GenerativeModel("gemini-1.5-flash") # En hızlı model
            response = model.generate_content(contents, stream=True, safety_settings=guvenlik)
            for chunk in response:
                try:
                    if chunk.text: yield chunk.text
                except: continue
            return 
        except Exception:
            # Flash yoksa Pro'yu dene (Yedek)
            try:
                model = genai.GenerativeModel("gemini-pro")
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

def scroll_to_bottom():
    js = """
    <script>
    function forceScroll() {
        var main = window.parent.document.querySelector(".main");
        if (main) { main.scrollTop = main.scrollHeight; }
    }
    forceScroll();
    setTimeout(forceScroll, 100);
    setTimeout(forceScroll, 500);
    </script>
    """
    components.html(js, height=0)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Merhaba Can Dost! Ben Can Dede. Sol menüden modunu seç, gönlünden geçeni sor."}]

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
    scroll_to_bottom()
    
    baglam_metni, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db, secilen_mod)
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        placeholder = st.empty()
        detay_container = st.empty()
        
        # Animasyon
        animasyon_html = f"""
        <div style="display: flex; align-items: center; gap: 10px; margin-top: 5px;">
            <div style="
                width: 12px; height: 12px; border-radius: 50%; background-color: #aaa;
                animation: pulse 1s infinite alternate;"></div>
            <span style="font-style: italic; color: #666; font-size: 14px;">Can Dede tefekkür ediyor... ({secilen_mod})</span>
        </div>
        <style>@keyframes pulse {{ from {{ opacity: 0.3; transform: scale(0.8); }} to {{ opacity: 1; transform: scale(1.1); }} }}</style>
        """
        placeholder.markdown(animasyon_html, unsafe_allow_html=True)
        
        full_text = ""
        ozet_text = ""
        detay_text = ""
        detay_modu_aktif = False
        
        stream = can_dede_cevapla(prompt, st.session_state.messages[:-1], baglam_metni, secilen_mod)
        
        for chunk in stream:
            full_text += chunk
            if "Araştırma" in secilen_mod and ("###DETAY###" in chunk or "###DETAY###" in full_text):
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

        if "Araştırma" in secilen_mod and kaynaklar:
            with detay_container.container():
                with st.expander("📜 Daha Fazla Detay ve Kaynaklar", expanded=True):
                    if detay_text.strip():
                        st.markdown(detay_text)
                        st.markdown("\n---\n")
                    
                    st.markdown("**📚 İlgili YolPedia Kaynakları:**")
                    seen = set()
                    for k in kaynaklar:
                        if k['link'] not in seen:
                            st.markdown(f"- [{k['baslik']}]({k['link']})")
                            seen.add(k['link'])
                            final_history += f"\n\n[{k['baslik']}]({k['link']})"
        
        st.session_state.messages.append({"role": "assistant", "content": final_history})
        scroll_to_bottom()
