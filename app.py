import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="Model Dedektifi")
st.title("🕵️‍♂️ Model Dedektifi")

# 1. API Anahtarını Al
api_key = st.secrets.get("API_KEY", "")
if not api_key:
    st.error("❌ API Anahtarı 'Secrets' içinde bulunamadı!")
    st.stop()

# 2. Bağlan
try:
    genai.configure(api_key=api_key)
    st.info("Google Sunucularına Bağlanıldı. Modeller listeleniyor...")
    
    # 3. Modelleri Listele
    bulunanlar = []
    for m in genai.list_models():
        # Sadece metin üretebilen modelleri bul
        if 'generateContent' in m.supported_generation_methods:
            bulunanlar.append(m.name)
            st.success(f"✅ ERIŞİLEBİLİR MODEL: **{m.name}**")
            
    if not bulunanlar:
        st.error("🚨 HİÇBİR MODEL BULUNAMADI! (API Anahtarında veya Bölgede kısıtlama olabilir)")
    else:
        st.balloons()
        st.write("---")
        st.write("### Ne Yapmalısın?")
        st.write("Yukarıdaki yeşil kutularda yazan isimlerden birini (Örn: `models/gemini-pro`) kopyalayıp bana gönder.")

except Exception as e:
    st.error(f"🔥 BAĞLANTI HATASI: {str(e)}")
