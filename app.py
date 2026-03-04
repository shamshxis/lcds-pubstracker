import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", layout="wide")

# --- CUSTOM BRANDING ---
st.markdown("""
    <style>
        .trendy-sub { color: #002147; font-size: 1.5rem; font-weight: 600; margin-bottom: 30px; }
        .footer { position: fixed; left: 0; bottom: 0; width: 100%; background-color: #002147; color: white; text-align: center; padding: 12px; font-size: 0.85rem; z-index: 999; }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        .block-container { padding-bottom: 80px; }
    </style>
""", unsafe_allow_html=True)

def load_data():
    # Cache Buster to ensure fresh data pull
    url = f"https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv?v={int(time.time())}"
    try:
        df = pd.read_csv(url)
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Year'] = df['Date Available Online'].dt.year
        return df
    except: return pd.DataFrame()

df = load_data()

# --- HEADER ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact over the years.</div>', unsafe_allow_html=True)

if st.sidebar.button("🔄 Force Refresh"):
    st.cache_data.clear()
    st.rerun()

if df.empty:
    st.warning("⚠️ Data is updating. If this is a demo, please wait 30 seconds and refresh.")
    st.stop()

# --- METRICS ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Output", len(df))
c2.metric("Total Citations", int(df['Citation Count'].sum()))
c3.metric("Recent Papers (2025)", len(df[df['Year'] >= 2025]))
c4.metric("Active Authors", df['LCDS Author'].nunique())

st.divider()

# --- CUMULATIVE IMPACT CHART ---
st.subheader("📈 Cumulative Citation Growth")
if not df.empty and 'Year' in df.columns:
    df_cite = df.groupby('Year')['Citation Count'].sum().reset_index().sort_values('Year')
    df_cite['Cumulative'] = df_cite['Citation Count'].cumsum()
    fig = px.area(df_cite, x='Year', y='Cumulative', markers=True, color_discrete_sequence=['#002147'])
    fig.update_layout(xaxis_type='category', plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

# --- RECENT PUBLICATIONS TABLE ---
st.subheader("📄 Recent Publications")
# Formatting for table
df_disp = df[['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'DOI']].copy()
df_disp['Date'] = df_disp['Date Available Online'].dt.strftime('%Y-%m-%d')
df_disp = df_disp.drop(columns=['Date Available Online'])

st.dataframe(
    df_disp[['Date', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'DOI']], 
    use_container_width=True, 
    hide_index=True,
    column_config={"DOI": st.column_config.LinkColumn("Link", display_text="View Paper")}
)

# --- FOOTER ---
st.markdown(f'<div class="footer">© University of Oxford {datetime.now().year} | <a href="https://www.demography.ox.ac.uk">Visit Website</a></div>', unsafe_allow_html=True)
