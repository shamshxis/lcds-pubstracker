import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", layout="wide")

# --- CSS (Clean White Text for Dark Mode) ---
st.markdown("""
    <style>
        h1, h2, h3 { color: white !important; font-family: 'Helvetica Neue', sans-serif; }
        .trendy-sub { color: white; font-size: 1.4rem; font-weight: 600; margin-bottom: 20px; }
        .footer { position: fixed; left: 0; bottom: 0; width: 100%; background-color: #0E1117; color: #777; text-align: center; padding: 10px; font-size: 0.8rem; border-top: 1px solid #333; z-index: 999; }
        .footer a { color: #FFD700; text-decoration: none; }
        .block-container { padding-bottom: 80px; }
    </style>
""", unsafe_allow_html=True)

def load_data():
    timestamp = int(time.time())
    url = f"https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv?v={timestamp}"
    try:
        df = pd.read_csv(url)
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        return df
    except: return pd.DataFrame()

df = load_data()

# --- HEADER ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact over the years.</div>', unsafe_allow_html=True)

if df.empty:
    st.info("📊 The data file is being refreshed. Please click 'Force Refresh' in the sidebar in a moment.")
    if st.sidebar.button("🔄 Force Refresh"): st.rerun()
    st.stop()

# --- METRIC CARDS ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Verified Output", len(df))
c2.metric("Total Citations", int(df['Citation Count'].sum()) if 'Citation Count' in df.columns else 0)
c3.metric("Preprints Found", len(df[df['Publication Type'] == 'Preprint']) if 'Publication Type' in df.columns else 0)
c4.metric("Verified Authors", df['LCDS Author'].nunique() if 'LCDS Author' in df.columns else 0)

st.divider()

# --- CUMULATIVE IMPACT CHART ---
if 'Year' in df.columns:
    st.subheader("📈 Accumulated Citation Impact")
    df_chart = df[pd.to_numeric(df['Year'], errors='coerce').notnull()].copy()
    df_chart['Year'] = df_chart['Year'].astype(int)
    df_plot = df_chart.groupby('Year')['Citation Count'].sum().reset_index().sort_values('Year')
    df_plot['Cumulative'] = df_plot['Citation Count'].cumsum()
    fig = px.area(df_plot, x='Year', y='Cumulative', markers=True, color_discrete_sequence=['#81D4FA'])
    fig.update_layout(xaxis_type='category', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
    st.plotly_chart(fig, use_container_width=True)

# --- PUBLICATIONS TABLE ---
st.subheader("📄 Recent Publications")
if 'Year' in df.columns:
    df = df.sort_values(by=['Year', 'Date Available Online'], ascending=[False, False])

st.sidebar.download_button("📥 Download Verified CSV", df.to_csv(index=False).encode('utf-8'), "lcds_verified_impact.csv", "text/csv")

cols = ['Year', 'Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'DOI']
df_disp = df[[c for c in cols if c in df.columns]].copy()
if 'Date Available Online' in df_disp.columns:
    df_disp['Date'] = df_disp['Date Available Online'].dt.strftime('%Y-%m-%d')
    df_disp = df_disp.drop(columns=['Date Available Online'])

st.dataframe(df_disp, use_container_width=True, hide_index=True, column_config={"DOI": st.column_config.LinkColumn("Link", display_text="View Paper")})

st.markdown(f'<div class="footer">© University of Oxford {datetime.now().year} | <a href="https://www.demography.ox.ac.uk" target="_blank">Visit Website</a></div>', unsafe_allow_html=True)
