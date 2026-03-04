import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🎓", layout="wide")

# --- TRENDY DARK-MODE CSS ---
st.markdown("""
    <style>
        .trendy-sub {
            background: linear-gradient(90deg, #002147 0%, #C49102 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 1.5rem; font-weight: 600; margin-bottom: 30px;
        }
        @media (prefers-color-scheme: dark) {
            .trendy-sub { background: linear-gradient(90deg, #81D4FA 0%, #FFD700 100%); -webkit-background-clip: text; }
        }
        .footer {
            position: fixed; left: 0; bottom: 0; width: 100%;
            background-color: #002147; color: white; text-align: center;
            padding: 12px; font-size: 0.85rem; z-index: 999;
        }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        .table-container { max-height: 500px; overflow-y: auto; border-radius: 8px; border: 1px solid #ddd; }
        .styled-table { width: 100%; border-collapse: collapse; font-family: 'Roboto', sans-serif; font-size: 0.9rem; }
        .styled-table thead tr th { position: sticky; top: 0; background-color: #002147; color: white; padding: 12px; z-index: 1; }
        .styled-table td { padding: 10px; border-bottom: 1px solid #eee; }
        @media (prefers-color-scheme: dark) {
            .styled-table thead tr th { background-color: #1E1E1E; color: #FFD700; }
            .styled-table td { border-bottom: 1px solid #333; color: #ddd; }
        }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data():
    url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    try:
        df = pd.read_csv(url)
        # FORCE COLUMNS TO EXIST
        if 'Publication Type' not in df.columns: df['Publication Type'] = 'Journal Article'
        if 'Journal Area' not in df.columns: df['Journal Area'] = 'Multidisciplinary'
        if 'Citation Count' not in df.columns: df['Citation Count'] = 0
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        return df
    except: return pd.DataFrame()

df = load_data()

# --- SIDEBAR ---
st.sidebar.title("🔍 Filters")
if df.empty:
    st.warning("⚠️ Data loading... Check back in 2 mins.")
    st.stop()

time_filter = st.sidebar.radio("Select Period", ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"], index=1)
now = datetime.now()
if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

df_filtered = df[(df['Date Available Online'] >= start_date)].copy()

# --- HEADER ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact across the years.</div>', unsafe_allow_html=True)

# --- METRICS ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Output", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# --- PLOTS (RESTORED!) ---
c1, c2 = st.columns(2)
with c1:
    st.subheader("📊 Impact by Field")
    # Group by Area
    df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
    # Fill N/A so chart doesn't break
    df_area['Journal Area'] = df_area['Journal Area'].fillna('Unknown')
    if not df_area.empty:
        fig = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4, 
                     color_discrete_sequence=px.colors.qualitative.Prism)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No citation data available.")

with c2:
    st.subheader("📑 Type Distribution")
    # Simple count by type
    df_type = df_filtered['Publication Type'].value_counts().reset_index()
    df_type.columns = ['Publication Type', 'Count']
    if not df_type.empty:
        fig2 = px.pie(df_type, values='Count', names='Publication Type', hole=0.4, 
                      color_discrete_sequence=px.colors.qualitative.Safe)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No publication type data available.")

# --- TABLE ---
st.subheader("📄 Recent Publications")
df_display = df_filtered[['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']].copy()
df_display['DOI'] = df_display['DOI'].apply(lambda x: f'<a href="{x}" target="_blank">View</a>' if str(x).startswith('http') else x)
if 'Date Available Online' in df_display.columns:
    df_display['Date Available Online'] = df_display['Date Available Online'].dt.strftime('%Y-%m-%d')

html_table = df_display.to_html(escape=False, index=False, classes="styled-table")
st.markdown(f'<div class="table-container">{html_table}</div>', unsafe_allow_html=True)

# --- FOOTER ---
st.markdown("""
    <div class="footer">
        © University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a>
    </div>
""", unsafe_allow_html=True)
