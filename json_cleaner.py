#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON Temizleyici - Geçersiz kontrol karakterlerini temizler
"""
import json
import re

INPUT_FILE = "yolpedia_data.json"
OUTPUT_FILE = "yolpedia_data_clean.json"

def clean_json_file():
    print(f"📖 Dosya okunuyor: {INPUT_FILE}")
    
    try:
        # Dosyayı oku (errors='ignore' ile geçersiz karakterleri atla)
        with open(INPUT_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        print(f"✅ Dosya okundu: {len(content)} karakter")
        
        # Kontrol karakterlerini temizle (tab, newline, return hariç)
        print("🧹 Kontrol karakterleri temizleniyor...")
        clean_content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', content)
        
        # JSON'u parse et ve yeniden yaz (formatlanmış)
        print("🔍 JSON parse ediliyor...")
        data = json.loads(clean_content)
        
        print(f"✅ {len(data)} kayıt bulundu")
        
        # Temiz JSON'u yaz
        print(f"💾 Temiz dosya yazılıyor: {OUTPUT_FILE}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n🎉 Başarılı! Temiz dosya: {OUTPUT_FILE}")
        print(f"📝 Orijinal dosya yedeklendi: {INPUT_FILE}.backup")
        
        # Orijinali yedekle
        import shutil
        shutil.copy(INPUT_FILE, f"{INPUT_FILE}.backup")
        
        # Temiz dosyayı orijinal isimle kaydet
        shutil.copy(OUTPUT_FILE, INPUT_FILE)
        print(f"✅ {INPUT_FILE} güncellendi!")
        
    except FileNotFoundError:
        print(f"❌ HATA: {INPUT_FILE} bulunamadı!")
    except json.JSONDecodeError as e:
        print(f"❌ JSON HATASI: {e}")
        print("\n🔍 Hatalı satırı bulalım:")
        
        # Hatalı bölümü göster
        lines = clean_content.split('\n')
        if e.lineno <= len(lines):
            start = max(0, e.lineno - 3)
            end = min(len(lines), e.lineno + 2)
            
            print(f"\n--- Satır {start+1} - {end+1} ---")
            for i in range(start, end):
                marker = ">>> " if i == e.lineno - 1 else "    "
                print(f"{marker}{i+1}: {lines[i][:100]}")
    except Exception as e:
        print(f"❌ BEKLENMEYEN HATA: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("🧹 JSON TEMİZLEYİCİ")
    print("=" * 60)
    clean_json_file()
