import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="LCDS Impact Tracker", layout="wide")

# --- APP FIREWALL ---
FORBIDDEN_WORDS = ['photocatalyst', 's-scheme', 'baryon', 'graphene', 'lattice', 'oxide', 'quantum']

def load_data():
    # Cache Buster
    url = f"https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv?v={int(time.time())}"
    try:
        df = pd.read_csv(url)
        # Internal Filter
        if not df.empty and 'Paper Title' in df.columns:
            df = df[~df['Paper Title'].str.lower().str.contains('|'.join(FORBIDDEN_WORDS), na=False)]
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        return df
    except: return pd.DataFrame()

df = load_data()

st.title("Leverhulme Centre for Demographic Science")
st.sidebar.info(f"Loaded {len(df)} verified records.")

if st.sidebar.button("🔄 Force Refresh"):
    st.cache_data.clear()
    st.rerun()

if df.empty:
    st.warning("📊 Data is currently being refreshed. Please wait 1 minute.")
    st.stop()

# --- DASHBOARD LOGIC ---
# (Keep your existing Metrics, Cumulative Graph, and Table code here)
# The key is that 'df' is now clean before it reaches the visuals.
