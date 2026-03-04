import streamlit as st
import pandas as pd
import time
from datetime import datetime

# --- LOAD DATA (THE CACHE-BUSTER FIX) ---
def load_data():
    # This timestamp changes every second, forcing GitHub to ignore its own cache
    cache_buster = int(time.time())
    
    # Use the 'data' branch specifically where the scraper pushes
    url = f"https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv?v={cache_buster}"
    
    try:
        # We tell pandas not to use a local cache either
        df = pd.read_csv(url, storage_options={'Cache-Control': 'no-cache'})
        
        # Clean up dates and types
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Year of Publication'] = df['Date Available Online'].dt.year
        return df, "Freshly Pulled from GitHub"
    except Exception as e:
        st.sidebar.error(f"Error: {e}")
        return pd.DataFrame(), "Failed to Load"

# --- EXECUTION ---
df, status = load_data()
st.sidebar.info(f"Source Status: {status}")
