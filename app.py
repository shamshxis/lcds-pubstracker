import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🎓", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
        h1, h2, h3 { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-weight: 700; }
        
        .trendy-sub {
            background: linear-gradient(90deg, #002147 0%, #C49102 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            font-size: 1.5rem; font-weight: 600; margin-bottom: 20px;
        }
        
        .footer {
            position: fixed; left: 0; bottom: 0; width: 100%;
            background-color: #002147; color: white; text-align: center;
            padding: 10px; font-size: 0.8rem; z-index: 1000;
        }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        .block-container { padding-bottom: 60px; }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA FUNCTION ---
# Using cache to prevent constant reloading, but allowing manual clear
@st.cache_data(ttl=3600) 
def load_data():
    url = "data/lcds_publications.csv" # Local path in repo
    # Fallback to GitHub raw if local not found (for testing/deployment variations)
    if not pd.io.common.file_exists(url):
        url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
        
    try:
        df = pd.read_csv(url)
        # Type Conversion
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(datetime.now().year)
        if 'Country' not in df.columns: df['Country'] = "Global"
        return df
    except Exception as e:
        return pd.DataFrame()

# --- SIDEBAR & REFRESH LOGIC ---
st.sidebar.title("🔍 Controls")

# Force Refresh Button
if st.sidebar.button("🔄 Force Refresh Data"):
    st.cache_data.clear()
    st.toast("Cache cleared! Reloading data...", icon="✅")
    time.sleep(1) # Visual pause
    st.rerun()

df = load_data()

if df.empty:
    st.warning("⚠️ Data is currently being updated or is empty. Please wait a moment and click Refresh.")
    st.stop()

# Time Filter
time_opt = st.sidebar.radio("Time Period", ["Since Sep 2019", "Last Year", "Last Month", "Last Week"], index=0)
now = datetime.now()

if time_opt == "Last Week": start = now - timedelta(days=7)
elif time_opt == "Last Month": start = now - timedelta(days=30)
elif time_opt == "Last Year": start = now - timedelta(days=365)
else: start = pd.to_datetime("2019-09-01")

df_filtered = df[df['Date Available Online'] >= start].copy()

# CSV Download
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Export")
csv_data = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("Download Current View CSV", csv_data, f"lcds_data_{time_opt.replace(' ', '_')}.csv", "text/csv")

# --- DASHBOARD ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact across the years.</div>', unsafe_allow_html=True)

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Publications", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c4.metric("Global Reach", df_filtered['Country'].nunique())

st.divider()

# Charts Row 1
col1, col2 = st.columns(2)
with col1:
    st.subheader("📈 Citations Trend")
    df_yearly = df_filtered.groupby('Year')['Citation Count'].sum().reset_index()
    if not df_yearly.empty:
        fig = px.bar(df_yearly, x='Year', y='Citation Count', title="Citations per Year", color_discrete_sequence=['#002147'])
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No citation data for this period.")

with col2:
    st.subheader("🌍 Collaboration Map")
    if 'Country' in df_filtered.columns:
        # Simple parsing of multiple countries
        countries = df_filtered['Country'].str.split(', ').explode().value_counts().reset_index()
        countries.columns = ['Country Code', 'Count']
        if not countries.empty:
            fig_map = px.choropleth(countries, locations="Country Code", color="Count",
                                    hover_name="Country Code", title="Author Affiliations",
                                    color_continuous_scale="Plasma")
            st.plotly_chart(fig_map, use_container_width=True)

# Charts Row 2
col3, col4 = st.columns(2)
with col3:
    st.subheader("📊 Research Areas")
    df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
    df_area = df_area[df_area['Journal Area'] != 'Multidisciplinary']
    if not df_area.empty:
        fig_pie = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Prism)
        st.plotly_chart(fig_pie, use_container_width=True)

with col4:
    st.subheader("📑 Output Type")
    df_type = df_filtered['Publication Type'].value_counts().reset_index()
    df_type.columns = ['Type', 'Count']
    fig_type = px.pie(df_type, values='Count', names='Type', hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe)
    st.plotly_chart(fig_type, use_container_width=True)

# Data Table
st.subheader("📄 Publications List")
st.dataframe(
    df_filtered[['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'DOI']],
    use_container_width=True,
    column_config={"DOI": st.column_config.LinkColumn("DOI Link")}
)

# Footer
st.markdown("""
    <div class="footer">
        © Certified University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a>
    </div>
""", unsafe_allow_html=True)
