# Geliştirilmiş veri yükleme fonksiyonu

import streamlit as st
import json
from pathlib import Path
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

@st.cache_data(persist="disk", show_spinner=False)
def load_kb() -> List[Dict]:
    """Geliştirilmiş veri yükleme - hata kontrolü ile"""
    data_file = Path("yolpedia_data.json")
    
    # 1. Dosya var mı kontrol et
    if not data_file.exists():
        logger.error(f"❌ Veri dosyası bulunamadı: {data_file}")
        st.error(f"⚠️ Veri dosyası bulunamadı: {data_file}")
        return []
    
    # 2. Dosyayı yükle
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # 3. Veri formatını kontrol et
        if not isinstance(data, list):
            logger.error("❌ Veri formatı hatalı: Liste olmalı")
            st.error("⚠️ Veri formatı hatalı")
            return []
        
        # 4. En az bir kayıt olmalı
        if len(data) == 0:
            logger.warning("⚠️ Veri dosyası boş")
            st.warning("⚠️ Veri tabanında kayıt yok")
            return []
        
        # 5. Kayıt formatını kontrol et
        required_fields = ['baslik', 'link', 'icerik']
        sample = data[0]
        missing = [f for f in required_fields if f not in sample]
        if missing:
            logger.error(f"❌ Eksik alanlar: {missing}")
            st.error(f"⚠️ Veri formatı eksik: {missing}")
            return []
        
        # Başarılı - log
        logger.info(f"✅ {len(data)} kayıt yüklendi")
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON parse hatası: {e}")
        st.error(f"⚠️ JSON formatı hatalı: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Beklenmeyen hata: {e}")
        st.error(f"⚠️ Veri yükleme hatası: {e}")
        return []


# Arama fonksiyonunda debug ekleme
def search_kb(query: str, db: List[Dict]) -> tuple[List[Dict], str]:
    """Geliştirilmiş arama - debug ile"""
    
    # Debug: Veri tabanı kontrolü
    if not db:
        logger.warning("⚠️ Veri tabanı boş!")
        return [], ""
    
    if len(query) < 3:
        logger.info(f"Sorgu çok kısa: '{query}'")
        return [], ""
    
    norm_q = normalize(query)
    logger.info(f"🔍 Arama yapılıyor: '{query}' -> '{norm_q}'")
    
    # Arama skorlarını hesapla
    results = []
    for e in db:
        sc = calc_score(e, norm_q, norm_q.split())
        if sc > 15:  # Eşik
            results.append({
                "baslik": e.get('baslik'),
                "link": e.get('link'),
                "icerik": e.get('icerik', '')[:1500],
                "puan": sc
            })
    
    results.sort(key=lambda x: x['puan'], reverse=True)
    
    # Debug: Sonuçları logla
    logger.info(f"📊 {len(results)} sonuç bulundu (toplam {len(db)} kayıt)")
    if results:
        logger.info(f"En yüksek skor: {results[0]['puan']} - {results[0]['baslik'][:50]}")
    
    return results[:5], norm_q


# Sidebar'a debug bilgisi ekleme
def render_sidebar():
    with st.sidebar:
        st.title("Mod Seçimi")
        mode = st.radio("Seçim", ["Sohbet Modu", "Araştırma Modu"])
        
        # VERİ TABANI DURUMU - YENİ!
        st.divider()
        db_count = len(st.session_state.db)
        if db_count > 0:
            st.success(f"✅ Veri tabanı: {db_count} kayıt")
        else:
            st.error("❌ Veri tabanı boş!")
        
        if st.button("🗑️ Sıfırla"):
            st.session_state.messages = [{"role": "assistant", "content": "Sıfırlandı."}]
            st.session_state.request_count = 0
            st.rerun()
        
        st.divider()
        st.caption(f"📊 {30 - st.session_state.request_count}/30")
        st.caption(f"🔑 Keys: {len(API_KEYS)}")
    
    return mode
