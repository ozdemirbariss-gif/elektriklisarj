import streamlit as st
import pandas as pd
import json
import math
import requests
from datetime import datetime
from streamlit_js_eval import get_geolocation

# --- 📱 MOBİL VE MİNİMALİST SAYFA AYARLARI ---
st.set_page_config(
    page_title="Elektirikli Şarj Bul", 
    page_icon="⚡", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# 🎨 PREMIUM CSS: "Glow & Glassmorphism" Lüks Tasarım Katmanı
st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        /* Kenar çubuklarını ve Streamlit elementlerini gizleme */
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }
        
        /* Arka Plan: Deep Space Black */
        .stApp { background-color: #060708 !important; }
        .block-container { padding: 1.5rem 1rem !important; max-width: 440px !important; }
        
        /* Modern ve Ortalanmış Başlık */
        .ana-baslik {
            font-family: 'SF Pro Display', '-apple-system', BlinkMacSystemFont, sans-serif;
            font-weight: 800;
            font-size: 26px;
            letter-spacing: -0.5px;
            text-align: center;
            color: #f5f5f7;
            margin-top: 10px;
            margin-bottom: 2px;
        }
        .alt-baslik {
            font-family: '-apple-system', sans-serif;
            font-size: 13px;
            text-align: center;
            color: #6c727a;
            margin-bottom: 25px;
        }
        
        /* ✨ GLASSMORPHISM & NEON GLOW PANEL MİMARİSİ */
        .glass-panel {
            background: rgba(17, 19, 24, 0.75) !important;
            backdrop-filter: blur(20px) !important;
            -webkit-backdrop-filter: blur(20px) !important;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 24px;
            padding: 24px;
            margin-bottom: 20px;
            /* Fütüristik Neon Siber Yeşil Işıma (Glow Effect) */
            box-shadow: 0 0 30px rgba(0, 230, 118, 0.05), 0 10px 30px rgba(0,0,0,0.5);
        }
        
        /* İstasyon Detay Metinleri */
        .istasyon-isim { font-size: 22px; font-weight: 700; color: #f5f5f7; margin: 0 0 6px 0; letter-spacing: -0.3px; }
        .mesafe-text { 
            font-size: 15px; 
            font-weight: 700; 
            color: #00e676; 
            margin: 0 0
