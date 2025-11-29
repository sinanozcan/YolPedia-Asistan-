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
MOTTO = '"Bildiğimin âlimiyim, bilmediğinin tâlibiyim!"'
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
    .subtitle-text { font-size: 18px; font-weight: 400; margin-top: 5px; color: #aaaaaa; text-align: center; }
    .top-logo-container { display: flex; justify-content: center; margin-bottom: 20px; padding-top: 10px; }
    .top-logo { width: 80px; opacity: 1.0; }
    .motto-text { text-align: center; font-size: 16px; font-style: italic; color: #cccccc; margin-bottom: 25px; font-family: 'Georgia', serif; }
    @media (prefers-color-scheme: light) { 
        .title-text { color: #000000; } 
        .subtitle-text { color: #555555; }
        .motto-text { color: #555555; } 
    }
    .stChatMessage { margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- VERİ YÜKLEME ---
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
        "content": "Merhaba Can Dost! Ben Can Dede. **Sol menüden** istediğin modu seç:\n\n• **☕ Sohbet Modu:** Birlikte yol üzerine konuşuruz, gönül sohbeti ederiz.\n• **🔍 Araştırma Modu:** YolPedia arşivinden sana kaynak sunarım.\n\nHaydi, hangi modda buluşalım?"
    }]

# RATE LIMITING
if 'request_count' not in st.session_state:
    st.session_state.request_count = 0
if 'last_reset_time' not in st.session_state:
    st.session_state.last_reset_time = time.time()

if time.time() - st.session_state.last_reset_time > 3600:
    st.session_state.request_count = 0
    st.session_state.last_reset_time = time.time()

# --- MOD SEÇİMİ (SIDEBAR) ---
with st.sidebar:
    st.image(CAN_DEDE_ICON, width=100)
    st.title("Mod Seçimi")
    
    if st.session_state.db:
        st.success(f"📊 **{len(st.session_state.db)} kayıt** hazır")
    else:
        st.error("⚠️ Veritabanı yüklenemedi!")
    
    kalan_limit = 50 - st.session_state.request_count
    if kalan_limit > 30:
        st.info(f"💬 Kalan: **{kalan_limit}/50** (saatlik)")
    elif kalan_limit > 10:
        st.warning(f"⚠️ Kalan: **{kalan_limit}/50**")
    else:
        st.error(f"🔴 Kalan: **{kalan_limit}/50**")
    
    secilen_mod = st.radio(
        "Can Dede nasıl yardımcı olsun?",
        ["☕ Sohbet Modu", "🔍 Araştırma Modu"],
        captions=[
            "Samimi sohbet eder, felsefi konuşur.", 
            "Kütüphane memuru gibi kaynak sunar."
        ]
    )
    st.markdown("---")
    st.info(f"Aktif: **{secilen_mod}**")
    
    if st.button("🗑️ Sohbeti Sıfırla"):
        st.session_state.messages = [{
            "role": "assistant", 
            "content": "Sohbet sıfırlandı Can Dost! **Sol menüden** modunu seç, yeniden başlayalım."
        }]
        st.rerun()

# --- HEADER ---
st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header">
        <img src="{CAN_DEDE_ICON}" class="dede-img">
        <h1 class="title-text">{ASISTAN_ISMI}</h1>
    </div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)

# --- ARAMA MOTORU (KALİTE ODAKLI) ---
def alakali_icerik_bul(kelime, db):
    if not db or not kelime or not isinstance(kelime, str): 
        return [], ""
    
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    
    if len(norm_sorgu) < 3: 
        return [], ""

    sonuclar = []
    
    for d in db:
        if not isinstance(d, dict):
            continue
            
        puan = 0
        d_baslik = d.get('norm_baslik', '')
        d_icerik = d.get('norm_icerik', '')
        
        # TAM EŞLEŞME - Çok yüksek puan
        if norm_sorgu in d_baslik: 
            puan += 200
        elif norm_sorgu in d_icerik: 
            puan += 100
        
        # ANAHTAR KELİME EŞLEŞME
        for k in anahtarlar:
            if k in d_baslik: 
                puan += 40
            elif k in d_icerik: 
                puan += 10
        
        # SADECE İLGİLİ SONUÇLAR (eşik yükseltildi)
        if puan > 50:  # 25 -> 50 (daha seçici)
            sonuclar.append({
                "veri": d, 
                "puan": puan,
                "baslik": d.get('baslik', 'Başlıksız'),
                "link": d.get('link', '#'),
                "icerik": d.get('icerik', '')[:1500]
            })
    
    # Puanlamaya göre sırala
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    
    # KALİTE KONTROLÜ: İlk kaynağın puanının %40'ından düşük olanları eleme
    if sonuclar:
        en_yuksek_puan = sonuclar[0]['puan']
        esik_puan = en_yuksek_puan * 0.4  # %40 eşiği
        
        kaliteli_sonuclar = [s for s in sonuclar if s['puan'] >= esik_puan]
        return kaliteli_sonuclar, norm_sorgu
    
    return [], norm_sorgu

# --- MODEL SEÇİCİ ---
def uygun_modeli_bul_ve_getir():
    try:
        mevcut_modeller = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if not mevcut_modeller: 
            return None, "Hiçbir model bulunamadı"
            
        tercihler = ["gemini-1.5-flash", "models/gemini-1.5-flash"]
        for t in tercihler:
            for m in mevcut_modeller:
                if t in m: 
                    return m, None
        return mevcut_modeller[0], None
    except Exception as e:
        return None, str(e)

# --- CAN DEDE CEVAP (OPTIMIZE EDİLMİŞ) ---
def can_dede_cevapla(user_prompt, kaynaklar, mod):
    if not API_KEYS:
        yield "❌ API anahtarı eksik."
        return

    # SOHBET MODU
    if "Sohbet" in mod:
        system_prompt = """Sen 'Can Dede'sin - Gerçek bir Alevi dedesi, insan-ı kâmil.

KİŞİLİĞİN:
- Yüzyılların bilgeliğini taşıyan ama modern dünyayı anlayan bir ulu kişisin
- Hem hikmetli hem sevecen, hem otoriter hem alçakgönüllü
- İnsanlar seninle konuştuktan sonra hem hayran kalır hem de kendilerini daha iyi hisseder
- Yol gösterirken dayatmazsın, soru sorarak insanı kendi hakikatine ulaştırırsın

ÜSLUBUN:
- "Erenler", "Can dost", "Sevgili yoldaş", "Kardeşim" gibi sıcak hitaplar
- Deyişlerden, ozanlardan, Yunus'tan, Pir Sultan'dan alıntılar yaparsın
- Bazen bir hikaye anlatır, bazen bir soru sorarsın
- Sözlerin kısa ama derin, şiirsel ama anlaşılır
- Dogmatik değil, özgür düşünceli ve hümanistsin

ÖRNEKLER:
- "Can dost, 'Dost kara bahtımdan usanmaz mı?' demiş Yunus. Sen de kendinden usanma..."
- "Erenler, yol uzun derler ama asıl olan yürüyendir. Sen ne soruyorsun?"
- "Sevgili kardeşim, hakikat kuyunun dibinde değil, gönül aynasındadır."

İnsanları etkileyecek, dönüştürecek, idol edinilecek bir REHBERsin."""

    # ARAŞTIRMA MODU
    else:
        if not kaynaklar:
            yield "📚 İlgili kaynak bulunamadı. Lütfen sorunuzu farklı kelimelerle tekrar deneyin."
            return
        
        kaynak_bilgi = "\n\n".join([
            f"KAYNAK {i+1}: {k['baslik']}\n{k['icerik'][:800]}"
            for i, k in enumerate(kaynaklar)
        ])
        
        system_prompt = f"""Sen bir YolPedia kütüphane memurusun. GÖREVİN:

1. Aşağıdaki KAYNAKLARA dayanarak KISA bir özet ver (2-3 cümle)
2. Kesinlikle sohbet etme, sadece kaynaklara odaklan
3. Net, profesyonel, bilgilendirici ol

KAYNAKLAR:
{kaynak_bilgi}

Kullanıcı sorusu: {user_prompt}

SADECE kaynaklara dayanarak KISA özet yaz."""

    # API ÇAĞRISI
    random.shuffle(API_KEYS)
    
    for key in API_KEYS:
        try:
            genai.configure(api_key=key)
            model_adi, _ = uygun_modeli_bul_ve_getir()
            
            if not model_adi:
                continue

            model = genai.GenerativeModel(
                model_adi,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 500 if "Araştırma" in mod else 800
                }
            )
            
            response = model.generate_content(
                system_prompt,
                stream=True,
                request_options={"timeout": 30}
            )
            
            for chunk in response:
                try:
                    if hasattr(chunk, 'text') and chunk.text:
                        yield chunk.text
                except:
                    continue
            return
            
        except Exception as e:
            error_msg = str(e).lower()
            if "quota" in error_msg or "429" in error_msg:
                continue
            time.sleep(0.3)
            continue

    yield "❌ Tüm API kotaları doldu. Lütfen yeni API key ekleyin."

# --- OTOMATİK KAYDIRMA ---
def scroll_to_bottom():
    js = """
    <script>
    function forceScroll() {
        const main = window.parent.document.querySelector(".main");
        if (main) { main.scrollTop = main.scrollHeight; }
    }
    setTimeout(forceScroll, 100);
    setTimeout(forceScroll, 500);
    </script>
    """
    components.html(js, height=0)

# --- MESAJ GEÇMİŞİ ---
for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    with st.chat_message(msg["role"], avatar=icon):
        st.markdown(msg["content"])

# --- KULLANICI GİRİŞİ ---
prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    # RATE LIMIT
    if st.session_state.request_count >= 50:
        st.error("⏰ Saatlik limit (50 mesaj). Lütfen 1 saat sonra deneyin.")
        st.stop()
    
    st.session_state.request_count += 1
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    scroll_to_bottom()
    
    # ARAMA (Araştırma Modu)
    kaynaklar = []
    if "Araştırma" in secilen_mod:
        status_container = st.empty()
        status_container.markdown("""
            <div style="
                background: linear-gradient(90deg, #1e3a8a, #3b82f6);
                color: white;
                padding: 15px 20px;
                border-radius: 10px;
                text-align: center;
                font-size: 16px;
                margin: 20px 0;
                animation: pulse 2s infinite;
            ">
                🔍 <strong>Lütfen bekleyin...</strong><br>
                <span style="font-size: 14px;">YolPedia arşivi taranıyor</span>
            </div>
            <style>
                @keyframes pulse {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.85; }
                }
            </style>
        """, unsafe_allow_html=True)
        
        kaynaklar, _ = alakali_icerik_bul(prompt, st.session_state.db)
        status_container.empty()
    
    # CAN DEDE CEVAP
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        placeholder = st.empty()
        
        # Animasyon
        animasyon = f"""
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="width: 12px; height: 12px; border-radius: 50%; background: #aaa; animation: pulse 1s infinite;"></div>
            <span style="font-style: italic; color: #666;">Can Dede düşünüyor...</span>
        </div>
        <style>@keyframes pulse {{ 0%, 100% {{ opacity: 0.3; }} 50% {{ opacity: 1; }} }}</style>
        """
        placeholder.markdown(animasyon, unsafe_allow_html=True)
        
        # Cevap al
        full_text = ""
        for chunk in can_dede_cevapla(prompt, kaynaklar, secilen_mod):
            full_text += chunk
            placeholder.markdown(full_text + "▌")
        
        placeholder.markdown(full_text)
        
        # ARAŞTIRMA MODUNDA KAYNAK LİSTELE
        if "Araştırma" in secilen_mod and kaynaklar:
            st.markdown("\n---\n**📚 İlgili Kaynaklar:**")
            for k in kaynaklar:
                st.markdown(f"• [{k['baslik']}]({k['link']})")
                full_text += f"\n[{k['baslik']}]({k['link']})"
        
        st.session_state.messages.append({"role": "assistant", "content": full_text})
        scroll_to_bottom()
