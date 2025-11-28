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
st.set_page_config(page_title=ASISTAN_ISMI, page_icon="🤖")

# --- CSS ---
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
    /* Detay kutusunu biraz daha belirgin yapalım */
    .streamlit-expanderHeader { font-weight: bold; color: #555; }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
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
    except FileNotFoundError:
        return []
    except Exception:
        return []

def tr_normalize(text):
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

if 'db' not in st.session_state:
    st.session_state.db = veri_yukle()
    if not st.session_state.db:
        st.warning(f"⚠️ Uyarı: '{DATA_FILE}' veritabanı bulunamadı. Sadece sohbet modu aktif.")

# --- ARAMA MOTORU ---
def alakali_icerik_bul(kelime, db):
    if not db: return "", []
    
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    
    sonuclar = []
    for d in db:
        puan = 0
        if norm_sorgu in d['norm_baslik']: puan += 100
        elif norm_sorgu in d['norm_icerik']: puan += 50
        for k in anahtarlar:
            if k in d['norm_baslik']: puan += 15
            elif k in d['norm_icerik']: puan += 5     
        if puan > 0:
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

def can_dede_cevapla(user_prompt, chat_history, context_data):
    if not API_KEYS:
        yield "HATA: API Anahtarı eksik."
        return

    # --- ÖNEMLİ: İKİ AŞAMALI CEVAP İSTEYEN PROMPT ---
    system_prompt = f"""
    Sen 'Can Dede'sin. Bilge, tasavvuf ehli bir rehbersin.
    
    GÖREVİN:
    1. Sorulan soruya önce **kısa, net ve öz** bir cevap ver (Tek paragraf veya maddeleme).
    2. Eğer sana verilen "BİLGİ KAYNAKLARI" varsa veya konu derinlemesine açıklama gerektiriyorsa,
       kısa cevabın bittiği yere tam olarak "###DETAY###" yaz (tırnaklar olmadan).
    3. "###DETAY###" yazısından sonra detaylı açıklamayı ve hikmetli anlatımını yap.
    
    BİLGİ KAYNAKLARI:
    {context_data if context_data else "Ek kaynak yok, sadece sohbet et."}
    """

    contents = []
    contents.append({"role": "user", "parts": [system_prompt]})
    contents.append({"role": "model", "parts": ["Anlaşıldı. Önce özet, gerekirse '###DETAY###' ile devam edeceğim."]})
    for msg in chat_history[-4:]:
        role = "user" if msg["role"] == "user" else "model"
        # Geçmiş mesajlarda ayırıcı varsa temizle ki bağlam karışmasın
        clean_content = msg["content"].replace("###DETAY###", "").split("📚 Yararlanılan Kaynaklar")[0]
        contents.append({"role": role, "parts": [clean_content]})
    contents.append({"role": "user", "parts": [user_prompt]})
    
    guvenlik_ayarlari = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    
    random.shuffle(API_KEYS)
    st.session_state.son_hata_raporu = []

    for key in API_KEYS:
        genai.configure(api_key=key)
        model_adi, hata = uygun_modeli_bul_ve_getir()
        
        if not model_adi:
            st.session_state.son_hata_raporu.append(f"Anahtar: ...{key[-5:]} | Hata: {hata}")
            continue

        try:
            model = genai.GenerativeModel(model_adi)
            response = model.generate_content(contents, stream=True, safety_settings=guvenlik_ayarlari)
            for chunk in response:
                try:
                    if chunk.text: yield chunk.text
                except ValueError: continue
            return 
        except Exception as e:
            st.session_state.son_hata_raporu.append(f"Model: {model_adi} | HATA: {str(e)}")
            time.sleep(0.5)
            continue 

    yield "Şu anda tefekkürdeyim (Bağlantı Sorunu)."

# --- ARAYÜZ ---
def scroll_to_bottom():
    components.html("""<script>window.parent.document.querySelector(".main").scrollTop = 100000;</script>""", height=0)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Merhaba Erenler! Ben Can Dede. Buyur, ne sormak istersin?"}]
if "son_hata_raporu" not in st.session_state:
    st.session_state.son_hata_raporu = []

# Mesajları Ekrana Basma
for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    with st.chat_message(msg["role"], avatar=icon):
        # Eğer mesajda "###DETAY###" varsa ayrıştırıp göster (Eski mesajlar için)
        if "###DETAY###" in msg["content"]:
            parts = msg["content"].split("###DETAY###")
            st.markdown(parts[0]) # Özet kısım
            with st.expander("📜 Daha Fazla Detay ve Kaynaklar"):
                st.markdown(parts[1]) # Detay kısım
        else:
            st.markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    baglam_metni, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db)
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        # Alan tutucular
        ozet_placeholder = st.empty()
        detay_container = st.empty()
        
        full_text = ""
        ozet_text = ""
        detay_text = ""
        detay_modu = False
        
        stream = can_dede_cevapla(prompt, st.session_state.messages[:-1], baglam_metni)
        
        # Akış Döngüsü
        for chunk in stream:
            full_text += chunk
            
            # Ayırıcıyı kontrol et
            if "###DETAY###" in chunk or "###DETAY###" in full_text:
                if not detay_modu:
                    # İlk kez detay moduna geçiliyorsa metni böl
                    parts = full_text.split("###DETAY###")
                    ozet_text = parts[0]
                    if len(parts) > 1: detay_text = parts[1]
                    detay_modu = True
                else:
                    # Zaten detay modundaysak sadece detay kısmına ekle
                    # (Basitlik için burada gelen chunk'ı direkt ekliyoruz, hassas bölme gerekmez)
                    if "###DETAY###" in chunk:
                         chunk = chunk.replace("###DETAY###", "")
                    detay_text += chunk
            else:
                ozet_text += chunk
            
            # Ekrana basma mantığı
            if not detay_modu:
                ozet_placeholder.markdown(ozet_text + "▌")
            else:
                # Özet bitti, sabitle
                ozet_placeholder.markdown(ozet_text)
                # Detayları expander içinde göster (sürekli güncellenir)
                with detay_container.container():
                    with st.expander("📜 Daha Fazla Detay ve Kaynaklar", expanded=True):
                        st.markdown(detay_text + "▌")

        # Akış bitti, imleçleri temizle
        ozet_placeholder.markdown(ozet_text)
        
        final_content_for_history = full_text # Geçmişe kaydedilecek ham metin

        if detay_modu or (kaynaklar and baglam_metni):
            with detay_container.container():
                with st.expander("📜 Daha Fazla Detay ve Kaynaklar", expanded=False):
                    # Detay metni varsa bas
                    if detay_text:
                        st.markdown(detay_text)
                    
                    # Kaynakları SADECE burada ekle
                    if kaynaklar and "tefekkürdeyim" not in full_text:
                        st.markdown("\n\n---\n**📚 Yararlanılan Kaynaklar:**")
                        seen = set()
                        for k in kaynaklar:
                            if k['link'] not in seen:
                                st.markdown(f"- [{k['baslik']}]({k['link']})")
                                seen.add(k['link'])
                                # Geçmişe de kaynakları ekleyelim ki sonra kaybolmasın
                                final_content_for_history += f"\n\n[{k['baslik']}]({k['link']})"
        
        st.session_state.messages.append({"role": "assistant", "content": final_content_for_history})
        scroll_to_bottom()
