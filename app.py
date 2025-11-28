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
MOTTO = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"

# --- SAYFA AYARLARI ---
st.set_page_config(page_title=ASISTAN_ISMI, page_icon=YOLPEDIA_ICON, layout="wide")

# --- API KEY KONTROLÜ ---
if not API_KEYS:
    st.error("❌ Geçerli API anahtarı bulunamadı. Lütfen secrets.toml dosyasını kontrol edin.")
    st.stop()

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

# --- VERİ YÜKLEME (İYİLEŞTİRİLMİŞ) ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f: 
            data = json.load(f)
            if not isinstance(data, list):
                st.error(f"❌ {DATA_FILE} geçersiz format (liste olmalı).")
                return []
            
            processed_data = []
            for d in data:
                if not isinstance(d, dict):
                    continue
                    
                ham_baslik = d.get('baslik', '')
                ham_icerik = d.get('icerik', '')
                
                d['norm_baslik'] = tr_normalize(ham_baslik)
                d['norm_icerik'] = tr_normalize(ham_icerik)
                processed_data.append(d)
            
            if processed_data:
                st.sidebar.success(f"✅ {len(processed_data)} kayıt yüklendi")
            else:
                st.sidebar.warning("⚠️ Veri yüklendi ama hiçbir kayıt işlenemedi!")
            return processed_data
            
    except FileNotFoundError:
        st.sidebar.warning(f"⚠️ {DATA_FILE} bulunamadı. Araştırma modu çalışmayacak.")
        return []
    except json.JSONDecodeError:
        st.sidebar.error(f"❌ {DATA_FILE} geçersiz JSON formatında.")
        return []
    except Exception as e:
        st.sidebar.error(f"❌ Veri yükleme hatası: {str(e)}")
        return []

def tr_normalize(text):
    if not isinstance(text, str): 
        return ""
    return text.translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC")).lower()

# Session state başlatma
if 'db' not in st.session_state: 
    st.session_state.db = veri_yukle()

if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant", 
        "content": "Merhaba Can Dost! Ben Can Dede. Sol menüden modunu seç, gönlünden geçeni sor."
    }]

# --- MOD SEÇİMİ (SIDEBAR) ---
with st.sidebar:
    st.image(CAN_DEDE_ICON, width=100)
    st.title("Mod Seçimi")
    
    # Veritabanı durumu göster
    if st.session_state.db:
        st.success(f"📊 **{len(st.session_state.db)} kayıt** hazır")
    else:
        st.error("⚠️ Veritabanı yüklenemedi!")
    
    secilen_mod = st.radio(
        "Can Dede nasıl yardımcı olsun?",
        ["☕ Sohbet Modu", "🔍 Araştırma Modu"],
        captions=["Sadece muhabbet eder, kaynak taramaz.", "YolPedia kütüphanesini tarar ve kaynak sunar."]
    )
    st.markdown("---")
    st.info(f"Aktif Mod: **{secilen_mod}**")
    
    if st.button("🗑️ Sohbeti Sıfırla"):
        st.session_state.messages = [{
            "role": "assistant", 
            "content": "Sohbet sıfırlandı. Yeni bir konuşma başlayalım Can Dost!"
        }]
        st.rerun()

# --- HEADER ---
st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header"><img src="{CAN_DEDE_ICON}" class="dede-img"><h1 class="title-text">Can Dede</h1></div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)

# --- ARAMA MOTORU (HIZLANDIRILMIŞ VE DÜZELTİLMİŞ) ---
def alakali_icerik_bul(kelime, db, mod):
    if "Sohbet" in mod:
        return "", []

    if not db or not kelime or not isinstance(kelime, str): 
        return "", []
    
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    
    if len(norm_sorgu) < 3: 
        return "", []

    sonuclar = []
    
    # TÜM VERİTABANINI TARA (erken çıkış kaldırıldı)
    for d in db:
        if not isinstance(d, dict):
            continue
            
        puan = 0
        d_baslik = d.get('norm_baslik', '')
        d_icerik = d.get('norm_icerik', '')
        
        # Tam eşleşme varsa direkt yüksek puan ver
        if norm_sorgu in d_baslik: 
            puan += 100
        elif norm_sorgu in d_icerik: 
            puan += 50
        
        # Kısmi eşleşme kontrolü
        for k in anahtarlar:
            if k in d_baslik: 
                puan += 20
            elif k in d_icerik: 
                puan += 5
        
        # Eşik değeri düşürüldü: 15 -> 10 (daha fazla sonuç)
        if puan > 10:
            sonuclar.append({"veri": d, "puan": puan})
    
    # En iyi sonuçları sırala ve al
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    en_iyiler = sonuclar[:8]  # 6 -> 8'e çıkarıldı
    
    context_text = ""
    kaynaklar = []
    
    # İçerik limiti optimum seviyede
    for item in en_iyiler:
        v = item['veri']
        v_baslik = v.get('baslik', 'Başlıksız')
        v_icerik = v.get('icerik', '')
        v_link = v.get('link', '#')
        
        context_text += f"\n--- KAYNAK: {v_baslik} ---\n{v_icerik[:3000]}\n"
        kaynaklar.append({"baslik": v_baslik, "link": v_link, "puan": item['puan']})
        
    return context_text, kaynaklar

# --- MODEL SEÇİCİ (İYİLEŞTİRİLMİŞ) ---
def uygun_modeli_bul_ve_getir():
    try:
        mevcut_modeller = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if not mevcut_modeller: 
            return None, "Hiçbir model bulunamadı"
            
        tercihler = ["gemini-1.5-flash", "models/gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
        for t in tercihler:
            for m in mevcut_modeller:
                if t in m: 
                    return m, None
        return mevcut_modeller[0], None
    except Exception as e:
        return None, str(e)

# --- CAN DEDE CEVAP FONKSİYONU (İYİLEŞTİRİLMİŞ) ---
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

    # --- SİSTEM PROMPT ---
    system_prompt = f"""
    Sen 'Can Dede'sin. Anadolu'nun kadim bilgeliğini modern, seküler ve felsefi bir dille harmanlayan bir rehbersin.
    
    ÜSLUP VE KURALLARIN:
    1. DİL DESTEĞİ: Kullanıcı hangi dilde sorarsa MUTLAKA O DİLDE cevap ver.
    2. Türkçe konuşuluyorsa: "Erenler", "Can dost", "Can", "Sevgili dost" gibi hitaplar kullan.
    3. FELSEFE: Dogmatik değil; akılcı, hümanist ve felsefi bir derinlikle konuş.
    4. TAVIR: Kaba veya cahilce sorulara tartışmaya girmeden, hikmetle kısa cevap verip geç.
    
    {gorev_tanimi}
    
    BİLGİ KAYNAKLARI:
    {kaynak_metni}
    """

    contents = []
    contents.append({"role": "user", "parts": [system_prompt]})
    contents.append({"role": "model", "parts": ["Anlaşıldı."]}) 
    
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
    
    for idx, key in enumerate(API_KEYS):
        try:
            genai.configure(api_key=key)
            model_adi, hata = uygun_modeli_bul_ve_getir()
            
            if not model_adi: 
                continue

            model = genai.GenerativeModel(model_adi)
            response = model.generate_content(contents, stream=True, safety_settings=guvenlik)
            
            for chunk in response:
                try:
                    if hasattr(chunk, 'text') and chunk.text: 
                        yield chunk.text
                except AttributeError:
                    continue
                except Exception:
                    continue
            return
            
        except Exception as e:
            error_msg = str(e).lower()
            if "quota" in error_msg or "429" in error_msg:
                continue
            elif "invalid" in error_msg or "api key" in error_msg:
                continue
            else:
                time.sleep(0.5)
                continue

    yield "Şu anda tefekkürderim (Bağlantı Sorunu - Tüm API anahtarları denendi)."

# --- OTOMATİK KAYDIRMA (İYİLEŞTİRİLMİŞ) ---
def scroll_to_bottom():
    js = """
    <script>
    function forceScroll() {
        const main = window.parent.document.querySelector(".main");
        if (main) {
            main.scrollTop = main.scrollHeight;
        }
    }
    setTimeout(forceScroll, 100);
    setTimeout(forceScroll, 300);
    setTimeout(forceScroll, 600);
    setTimeout(forceScroll, 1000);
    </script>
    """
    components.html(js, height=0)

# --- MESAJ GEÇMİŞİ ---
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

# --- KULLANICI GİRİŞİ ---
prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    # ARAMA (Mod'a göre) - GÖRÜNÜR STATUS MESAJI
    if "Araştırma" in secilen_mod:
        # Görünür status container oluştur
        status_container = st.empty()
        status_container.markdown("""
            <div style="
                background: linear-gradient(90deg, #1e3a8a, #3b82f6);
                color: white;
                padding: 15px 20px;
                border-radius: 10px;
                text-align: center;
                font-size: 16px;
                font-weight: 500;
                margin: 20px 0;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                animation: pulse 2s infinite;
            ">
                🔍 <strong>Lütfen bekleyin...</strong><br>
                <span style="font-size: 14px; opacity: 0.9;">
                YolPedia arşivinde ilgili kaynaklar taranıyor (2236 kayıt)
                </span>
            </div>
            <style>
                @keyframes pulse {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.85; transform: scale(0.98); }
                }
            </style>
        """, unsafe_allow_html=True)
        
        # Arama yap
        baglam_metni, kaynaklar = alakali_icerik_bul(prompt, st.session_state.db, secilen_mod)
        
        # Status mesajını temizle
        status_container.empty()
        
        # DEBUG: Kaç kaynak bulundu?
        if kaynaklar:
            st.sidebar.info(f"🎯 **{len(kaynaklar)} kaynak** bulundu")
        else:
            st.sidebar.warning("⚠️ İlgili kaynak bulunamadı")
    else:
        baglam_metni, kaynaklar = "", []
    
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
            
            # Sadece Araştırma Modunda Detay
            if "Araştırma" in secilen_mod and ("###DETAY###" in chunk or "###DETAY###" in full_text):
                if not detay_modu_aktif:
                    parts = full_text.split("###DETAY###")
                    ozet_text = parts[0]
                    if len(parts) > 1: 
                        detay_text = parts[1]
                    detay_modu_aktif = True
                else:
                    if "###DETAY###" in chunk: 
                        chunk = chunk.replace("###DETAY###", "")
                    detay_text += chunk
            else:
                ozet_text += chunk
            
            if not detay_modu_aktif:
                placeholder.markdown(ozet_text + "▌")
            else:
                placeholder.markdown(ozet_text)
        
        placeholder.markdown(ozet_text)
        
        final_history = full_text

        # --- ARAŞTIRMA MODUNDA KAYNAK LİSTELE ---
        if "Araştırma" in secilen_mod and kaynaklar and detay_modu_aktif:
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
