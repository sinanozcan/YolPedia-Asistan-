import streamlit as st
import streamlit.components.v1 as components
import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import google.generativeai as genai
import sys
import time
import json
from PIL import Image
from io import BytesIO

# ================= AYARLAR =================
API_KEY = st.secrets["API_KEY"]
WP_USER = st.secrets["WP_USER"]
WP_PASS = st.secrets["WP_PASS"]
WEBSITE_URL = "https://yolpedia.eu" 
DATA_FILE = "yolpedia_data.json"
ASISTAN_ISMI = "Can Dede | YolPedia Rehberiniz"
MOTTO = '"Bildigimin âlimiyim, bilmedigimin tâlibiyim!"'

# --- RESİMLER ---
YOLPEDIA_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/cropped-Yolpedia-Favicon-e1620391336469.png"
CAN_DEDE_ICON = "https://yolpedia.eu/wp-content/uploads/2025/11/can-dede-logo.png" 
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
    .main-header { 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        margin-top: 5px; 
        margin-bottom: 5px; 
    }
    .dede-img { 
        width: 80px; 
        height: 80px; 
        border-radius: 50%; 
        margin-right: 15px; 
        object-fit: cover;
        border: 2px solid #eee; 
    }
    .title-text { 
        font-size: 36px; 
        font-weight: 700; 
        margin: 0; 
        color: #ffffff; 
    }
    .top-logo-container {
        display: flex;
        justify-content: center;
        margin-bottom: 15px;
        padding-top: 10px;
    }
    .top-logo {
        width: 50px;
        opacity: 0.8; 
    }
    .motto-text { 
        text-align: center; 
        font-size: 16px; 
        font-style: italic; 
        color: #cccccc; 
        margin-bottom: 25px; 
        font-family: 'Georgia', serif; 
    }
    @media (prefers-color-scheme: light) { 
        .title-text { color: #000000; } 
        .motto-text { color: #555555; }
        .dede-img { border: 2px solid #ccc; }
    }
    .stButton button { width: 100%; border-radius: 10px; font-weight: bold; border: 1px solid #ccc; }
    
    /* Gölge sorununu çözen stil */
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

#
