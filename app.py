import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🎓", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
        h1, h2, h3 { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-weight: 700; }
        .trendy-sub { color: #002147; font-size: 1.5rem; font-weight: 600; margin-bottom: 30px; }
        @media (prefers-color-scheme: dark) { .trendy-sub { color: #FFD700; } }
        .footer { position: fixed; left: 0; bottom: 0; width: 100%; background-color: #002147; color: white; text-align: center; padding: 12px; font-size: 0.85rem; z-index: 999; }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        .block-container { padding-bottom: 80px; }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data():
    # Adding a random query param to URL to trick cache if needed, but st.cache_data handling is better
    url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    try:
        df = pd.read_csv(url)
        # Defaults
        if 'Publication Type' not in df.columns: df['Publication Type'] = 'Journal Article'
        if 'Journal Name' not in df.columns: df['Journal Name'] = 'Unknown'
        if 'Citation Count' not in df.columns: df['Citation Count'] = 0
        
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Year of Publication'] = df['Date Available Online'].dt.year
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        return df
    except: return pd.DataFrame()

# --- SIDEBAR & REFRESH ---
st.sidebar.title("🔍 Filters")

# MANUAL REFRESH BUTTON
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

df = load_data()

if df.empty:
    st.warning("⚠️ Data loading or empty. Click Refresh if this persists.")
    st.stop()

# Time Filter
time_filter = st.sidebar.radio("Period", ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"], index=1)
now = datetime.now()
if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

df_filtered = df[df['Date Available Online'] >= start_date].copy()

# Download
st.sidebar.markdown("---")
csv = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("Download CSV", csv, "lcds_data.csv", "text/csv")

# --- DASHBOARD ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact over the years.</div>', unsafe_allow_html=True)
st.markdown(f"**Viewing:** {time_filter} | **Records:** {len(df_filtered)}")
st.divider()

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Output", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# Chart (Cumulative)
st.subheader("📈 Cumulative Impact (Citations)")
if 'Year of Publication' in df_filtered.columns and not df_filtered.empty:
    df_cite = df_filtered.groupby('Year of Publication')['Citation Count'].sum().reset_index().sort_values('Year of Publication')
    df_cite['Cumulative Citations'] = df_cite['Citation Count'].cumsum()
    fig = px.area(df_cite, x='Year of Publication', y='Cumulative Citations', markers=True, color_discrete_sequence=['#002147'])
    fig.update_layout(xaxis_type='category', plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)
else: st.info("No data for chart.")

# Table
st.subheader("📄 Recent Publications")
cols = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']
df_disp = df_filtered[[c for c in cols if c in df_filtered.columns]].copy()
df_disp['Date Available Online'] = df_disp['Date Available Online'].dt.strftime('%Y-%m-%d')
df_disp = df_disp.rename(columns={'Date Available Online': 'Date', 'Publication Type': 'Type', 'Citation Count': 'Cites'})

st.dataframe(
    df_disp, use_container_width=True, hide_index=True,
    column_config={"DOI": st.column_config.LinkColumn("Link", display_text="View Paper"), "Cites": st.column_config.NumberColumn("Cites", format="%d")}
)

# Footer
st.markdown("""<div class="footer">© University of Oxford 2026 - All Rights Reserved. | <a href="https://www.demography.ox.ac.uk" target="_blank">Visit our Website or Follow us on Social Media</a></div>""", unsafe_allow_html=True)
