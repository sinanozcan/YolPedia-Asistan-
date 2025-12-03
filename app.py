# -*- coding: utf-8 -*-
import streamlit as st
import streamlit.components.v1 as components 
import requests
import google.generativeai as genai
import time
import json
import random

# ================= GÜVENLİ BAŞLANGIÇ & AYARLAR =================
# --- OPTİMİZASYON AYARLARI ---
MAX_MESSAGE_LIMIT = 15     # Bir kullanıcının oturum başına sorabileceği maksimum soru
MIN_TIME_DELAY = 3         # İki soru arasında geçmesi gereken minimum süre (saniye)
# ----------------------------

GOOGLE_API_KEY = None
try:
    GOOGLE_API_KEY = st.secrets.get("API_KEY", "")
except Exception:
    GOOGLE_API_KEY = ""

DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildiğimin âlimiyim, bilmediğimin tâlibiyim!"'
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/Yolpedia-favicon.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
USER_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/group.png"

# --- SAYFA AYARLARI ---
st.set_page_config(page_title=ASISTAN_ISMI, page_icon=YOLPEDIA_ICON, layout="wide")

# --- API KEY KONTROLÜ ---
if not GOOGLE_API_KEY or len(GOOGLE_API_KEY) < 10:
    st.error("❌ API Anahtarı bulunamadı! Lütfen Streamlit panelinde 'Secrets' kısmına 'API_KEY' adıyla geçerli anahtarınızı ekleyin.")
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
    
    /* Spinner Rengi */
    .stSpinner > div {
        border-top-color: #ff4b4b !important;
    }
</style>
""", unsafe_allow_html=True)

# --- VERİ YÜKLEME ---
@st.cache_data(persist="disk", show_spinner=False)
def veri_yukle():
    try:
        # Dosyayı binary modda oku ve decode et (daha toleranslı)
        with open(DATA_FILE, "rb") as f: 
            content = f.read().decode("utf-8", errors="ignore")
        
        # Tüm kontrol karakterlerini temizle (tab, newline, return hariç)
        import re
        content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', content)
        
        # Satır sonlarını normalize et
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            # Eğer hala hata varsa, daha agresif temizlik yap
            st.warning(f"İlk deneme başarısız, agresif temizlik yapılıyor...")
            
            # Tüm non-ASCII ve kontrol karakterlerini kaldır
            content = ''.join(char for char in content if ord(char) >= 32 or char in '\n\r\t')
            data = json.loads(content)
        
        processed_data = []
        for d in data:
            if not isinstance(d, dict): 
                continue
            
            ham_baslik = str(d.get('baslik', '')).strip()
            ham_icerik = str(d.get('icerik', '')).strip()
            
            # İçerikteki kontrol karakterlerini de temizle
            ham_baslik = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', ham_baslik)
            ham_icerik = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', ham_icerik)
            
            d['baslik'] = ham_baslik
            d['icerik'] = ham_icerik
            d['norm_baslik'] = tr_normalize(ham_baslik)
            d['norm_icerik'] = tr_normalize(ham_icerik)
            processed_data.append(d)
        
        st.success(f"✅ {len(processed_data)} kayıt başarıyla yüklendi!")
        return processed_data
        
    except json.JSONDecodeError as e:
        st.error(f"❌ JSON formatı hatalı: Satır {e.lineno}, Sütun {e.colno}")
        st.info("💡 JSON dosyasını https://jsonlint.com/ sitesinde kontrol edin.")
        st.code(f"Hata detayı: {str(e)}", language="text")
        return []
    except FileNotFoundError:
        st.error(f"❌ Dosya bulunamadı: {DATA_FILE}")
        return []
    except Exception as e:
        st.error(f"❌ Beklenmeyen hata: {e}")
        import traceback
        st.code(traceback.format_exc(), language="text")
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
        "content": "Merhaba, Can Dost! Ben Can Dede. Sol menüden istediğin modu seç:\n\n• **Sohbet Modu:** Birlikte yol üzerine konuşuruz, gönül muhabbeti ederiz.\n\n• **Araştırma Modu:** YolPedia arşivinden sana kaynak sunarım.\n\nBuyur Erenler, hangi modda buluşalım?"
    }]

if 'expanded_sources' not in st.session_state: 
    st.session_state.expanded_sources = {}
if 'request_count' not in st.session_state: 
    st.session_state.request_count = 0
if 'last_reset_time' not in st.session_state: 
    st.session_state.last_reset_time = time.time()
if 'last_request_time' not in st.session_state: 
    st.session_state.last_request_time = 0

# Bir saat geçtiyse sayacı sıfırla
if time.time() - st.session_state.last_reset_time > 3600:
    st.session_state.request_count = 0
    st.session_state.last_reset_time = time.time()

# --- SIDEBAR ---
with st.sidebar:
    st.title("Mod Seçimi")
    
    # JSON TEMİZLEME BUTONU
    if st.button("🧹 JSON Dosyasını Temizle", help="Geçersiz karakterleri temizler"):
        with st.spinner("Dosya temizleniyor..."):
            try:
                import re
                import shutil
                
                # Orijinali yedekle
                backup_file = f"{DATA_FILE}.backup"
                shutil.copy(DATA_FILE, backup_file)
                st.info(f"📦 Yedek oluşturuldu: {backup_file}")
                
                # Dosyayı satır satır oku ve temizle (daha güvenli)
                with open(DATA_FILE, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                
                st.info(f"📖 {len(lines)} satır okundu")
                
                # Her satırı temizle
                cleaned_lines = []
                for i, line in enumerate(lines, 1):
                    # Tüm kontrol karakterlerini temizle
                    clean_line = re.sub(r'[\x00-\x1f\x7f]', '', line)
                    # Tab ve newline'ı geri ekle
                    if i < len(lines):  # Son satır hariç
                        clean_line = clean_line.rstrip() + '\n'
                    cleaned_lines.append(clean_line)
                
                full_content = ''.join(cleaned_lines)
                
                # JSON parse et
                try:
                    data = json.loads(full_content)
                    st.success(f"✅ JSON parse başarılı: {len(data)} kayıt")
                except json.JSONDecodeError as e:
                    st.error(f"❌ Hala hata var. Satır {e.lineno}, Kolon {e.colno}")
                    st.code(f"Hatalı bölüm: {full_content[max(0, e.pos-50):e.pos+50]}")
                    
                    # Daha agresif temizlik: sadece yazdırılabilir karakterleri tut
                    st.warning("🔧 Agresif temizlik uygulanıyor...")
                    full_content = ''.join(char for char in full_content 
                                          if char.isprintable() or char in '\n\r\t ')
                    data = json.loads(full_content)
                
                # Temiz dosyayı kaydet
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                st.success(f"✅ Dosya temizlendi ve kaydedildi!")
                
                # Cache'i temizle ve yeniden yükle
                st.cache_data.clear()
                st.session_state.db = veri_yukle()
                time.sleep(1)
                st.rerun()
                
            except FileNotFoundError:
                st.error(f"❌ Dosya bulunamadı: {DATA_FILE}")
            except Exception as e:
                st.error(f"❌ Beklenmeyen hata: {type(e).__name__}")
                st.code(str(e))
                import traceback
                with st.expander("Detaylı Hata"):
                    st.code(traceback.format_exc())
    
    st.markdown("---")
    
    if st.session_state.db: 
        st.success(f"📊 **{len(st.session_state.db)} kayıt** hazır")
    else: 
        st.error("⚠️ Veritabanı yüklenemedi!")
    
    secilen_mod = st.radio("Can Dede nasıl yardımcı olsun?", ["Sohbet Modu", "Araştırma Modu"])
    
    # --- OPTİMİZASYON: Kota Göstergesi ---
    kalan_hak = MAX_MESSAGE_LIMIT - st.session_state.request_count
    if kalan_hak > 0:
        st.info(f"⏳ Kalan Soru Hakkı: **{kalan_hak}**")
    else:
        st.error("🛑 Günlük limit doldu can.")
    # -------------------------------------

    if st.button("🗑️ Sohbeti Sıfırla"):
        st.session_state.messages = [{"role": "assistant", "content": "Sohbet sıfırlandı. Buyur can."}]
        st.session_state.expanded_sources = {}
        st.rerun()

# --- HEADER ---
st.markdown(f"""
    <div class="top-logo-container"><img src="{YOLPEDIA_ICON}" class="top-logo"></div>
    <div class="main-header"><img src="{CAN_DEDE_ICON}" class="dede-img"><h1 class="title-text">{ASISTAN_ISMI}</h1></div>
    <div class="motto-text">{MOTTO}</div>
    """, unsafe_allow_html=True)

# --- ARAMA ---
def alakali_icerik_bul(kelime, db):
    if not db or not kelime or len(kelime) < 3: 
        return [], ""
    
    norm_sorgu = tr_normalize(kelime)
    anahtarlar = [k for k in norm_sorgu.split() if len(k) > 2]
    sonuclar = []
    
    for d in db:
        puan = 0
        d_baslik = d.get('norm_baslik', '')
        d_icerik = d.get('norm_icerik', '')
        
        if norm_sorgu in d_baslik: 
            # Eğer başlıkta önemli kelimeler geçiyorsa ekstra puan
            if any(x in d_baslik for x in ["gulbank", "tercuman", "dua", "siir"]):
                puan += 500  
            else:
                puan += 200        
        elif norm_sorgu in d_icerik: 
            puan += 100
            
        for k in anahtarlar:
            if k in d_baslik: 
                puan += 40
            elif k in d_icerik: 
                puan += 10
                
        if puan > 50:
            sonuclar.append({
                "baslik": d.get('baslik', 'Başlıksız'),
                "link": d.get('link', '#'),
                "icerik": d.get('icerik', '')[:1500],
                "puan": puan
            })
            
    sonuclar.sort(key=lambda x: x['puan'], reverse=True)
    
    if sonuclar:
        esik = sonuclar[0]['puan'] * 0.4
        return [s for s in sonuclar if s['puan'] >= esik], norm_sorgu
    return [], norm_sorgu

# --- AKILLI MODEL BULUCU ---
def get_best_available_model():
    try:
        model_list = genai.list_models()
        available_models = []
        for m in model_list:
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if not available_models: 
            return None

        preferences = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro", "gemini-pro"]
        for p in preferences:
            for m in available_models:
                if p in m: 
                    return m
        return available_models[0]
    except Exception:
        return "gemini-1.5-flash"

# --- OPTİMİZASYON: YEREL CEVAP KONTROLÜ (API KULLANMAZ) ---
def yerel_cevap_kontrol(text):
    text_norm = tr_normalize(text)
    
    # Basit selamlaşmalar için kotayı harcama
    selamlar = ["merhaba", "selam", "selamun aleykum", "iyi gunler", "gunaydin", "iyi aksamlar"]
    hal_hatir = ["nasilsin", "naber", "ne var ne yok", "nasil gidiyor"]
    kimlik = ["sen kimsin", "adin ne", "necisin", "kimsin"]
    
    if any(s == text_norm for s in selamlar):
        return random.choice([
            "Aşk ile merhaba can.", 
            "Selam olsun gönlü güzel olana.", 
            "Merhaba erenler, hoş geldin."
        ])
        
    if any(h in text_norm for h in hal_hatir):
        return random.choice([
            "Şükür Hak'ka, hizmetteyiz.", 
            "Gönüller bir olsun, biz iyiyiz can.", 
            "Erenlerin himmetiyle yoldayız."
        ])
        
    if any(k in text_norm for k in kimlik):
        return "Ben Can Dede. YolPedia'nın hizmetkârıyım. Gönül kırmaz, yol sorana yoldaş olurum."
        
    return None

# --- CEVAP FONKSİYONU ---
def can_dede_cevapla(user_prompt, kaynaklar, mod):
    if not GOOGLE_API_KEY:
        yield "❌ HATA: API Anahtarı eksik."
        return

    # --- OPTİMİZASYON: Önce yerel veriye bak (Bedava) ---
    yerel_cevap = yerel_cevap_kontrol(user_prompt)
    if yerel_cevap:
        time.sleep(0.5) 
        yield yerel_cevap
        return
    # ----------------------------------------------------

    # --- SİSTEM YÖNERGESİ (DİL ve ÜSLUP AYARLARI) ---
    if "Sohbet" in mod:
        system_prompt = """Sen 'Can Dede'sin. Alevi-Bektaşi felsefesini benimsemiş, gönül gözü açık bir rehbersin.

        KESİN KURALLAR:
        1. DİL: Kullanıcı seninle hangi dilde konuşursa mutlaka O DİLDE cevap ver.
        2. ÜSLUP: 'Selamünaleyküm' yerine 'Aşk ile', 'Merhaba Can', 'Erenler' kullan.
        3. ADAPTASYON: Soru basitse masalsı, derinse tasavvufi cevap ver.
        4. TAVIR: Yargılama, sevgi dolu ol.
        """
        full_content = system_prompt + "\n\nKullanıcı: " + user_prompt
    else:
        if not kaynaklar:
            yield "📚 Aradığın konuyla ilgili YolPedia'da kaynak bulamadım can."
            return
        
        # --- OPTİMİZASYON: Kaynakları Kısalt (Token Tasarrufu) ---
        kaynak_metni = "\n".join([f"- {k['baslik']}: {k['icerik'][:400]}" for k in kaynaklar[:3]])
        
        system_prompt = f"""Sen YolPedia asistanısın.
        GÖREV: Aşağıdaki kaynaklara dayanarak net bilgi ver.
        DİL KURALI: Kullanıcı hangi dilde sorduysa o dilde cevapla.
        KAYNAKLAR:\n{kaynak_metni}"""
        
        full_content = system_prompt + "\n\nSoru: " + user_prompt

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model_name = get_best_available_model()
        if not model_name:
            yield "❌ Google API modellerine erişilemiyor."
            return

        model = genai.GenerativeModel(model_name)
        response = model.generate_content(full_content, stream=True)
        
        for chunk in response:
            if chunk.text: 
                yield chunk.text
            
    except Exception as e:
        yield f"⚠️ Bağlantı hatası: {str(e)}"

# --- SCROLL FONKSİYONU ---
def scroll_to_bottom():
    js = """
    <script>
        var body = window.parent.document.querySelector(".main");
        if (body) {
            body.scrollTop = body.scrollHeight;
        }
    </script>
    """
    components.html(js, height=0)

# --- UI AKIŞI ---
for msg in st.session_state.messages:
    icon = CAN_DEDE_ICON if msg["role"] == "assistant" else USER_ICON
    with st.chat_message(msg["role"], avatar=icon):
        st.markdown(msg["content"])

prompt = st.chat_input("Can Dede'ye sor...")

if prompt:
    # --- OPTİMİZASYON: KOTA VE HIZ KONTROLÜ ---
    if st.session_state.request_count >= MAX_MESSAGE_LIMIT:
        st.error(f"🛑 Erenler, bugünlük muhabbet kotamız doldu ({MAX_MESSAGE_LIMIT} soru). Yarın yine bekleriz.")
        st.stop()
        
    current_time = time.time()
    if current_time - st.session_state.last_request_time < MIN_TIME_DELAY:
        st.warning("⏳ Biraz nefeslen can, çok hızlı soruyorsun...")
        st.stop()
    
    st.session_state.last_request_time = current_time
    st.session_state.request_count += 1
    # ------------------------------------------

    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=USER_ICON).markdown(prompt)
    
    # Mesaj gönderildiğinde scroll
    scroll_to_bottom()
    
    kaynaklar = []
    if "Araştırma" in secilen_mod:
        kaynaklar, _ = alakali_icerik_bul(prompt, st.session_state.db)
    
    with st.chat_message("assistant", avatar=CAN_DEDE_ICON):
        placeholder = st.empty()
        full_text = ""
        
        # --- DÜŞÜNÜYOR ANİMASYONU ---
        with st.spinner("Can Dede tefekkürde daldı, cevap hazırlıyor..."):
            response_generator = can_dede_cevapla(prompt, kaynaklar, secilen_mod)
            
            try:
                first_chunk = next(response_generator)
                full_text += first_chunk
                placeholder.markdown(full_text + "▌")
            except StopIteration:
                pass
            except Exception as e:
                full_text = f"Hata: {e}"

        # --- STREAMING ---
        for chunk in response_generator:
            full_text += chunk
            placeholder.markdown(full_text + "▌")
        
        placeholder.markdown(full_text)
        
        if "Araştırma" in secilen_mod and kaynaklar:
            st.markdown("---")
            st.markdown("**📚 Kaynaklar:**")
            for k in kaynaklar[:5]:
                st.markdown(f"• [{k['baslik']}]({k['link']})")
        
        st.session_state.messages.append({"role": "assistant", "content": full_text})
        
        # Cevap bittiğinde scroll
        scroll_to_bottom()
