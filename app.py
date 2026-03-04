import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🎓", layout="wide")

# --- CUSTOM CSS (Branding + Dark Mode) ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
        
        /* Header Gradient */
        .trendy-sub {
            background: linear-gradient(90deg, #002147 0%, #C49102 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            font-size: 1.5rem; font-weight: 600; margin-bottom: 20px;
        }
        @media (prefers-color-scheme: dark) {
            .trendy-sub { background: linear-gradient(90deg, #81D4FA 0%, #FFD700 100%); }
        }
        
        /* Footer */
        .footer {
            position: fixed; left: 0; bottom: 0; width: 100%;
            background-color: #002147; color: white; text-align: center;
            padding: 10px; font-size: 0.8rem; z-index: 1000;
        }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        
        /* Table Styling */
        .table-container { max-height: 500px; overflow-y: auto; border: 1px solid #ddd; border-radius: 8px; }
        .styled-table { width: 100%; border-collapse: collapse; font-family: 'Roboto', sans-serif; font-size: 0.9rem; }
        .styled-table th { position: sticky; top: 0; background-color: #002147; color: white; padding: 10px; z-index: 1; }
        .styled-table td { padding: 8px; border-bottom: 1px solid #eee; }
        
        @media (prefers-color-scheme: dark) {
            .styled-table th { background-color: #1E1E1E; color: #FFD700; }
            .styled-table td { border-bottom: 1px solid #333; color: #ddd; }
        }
        .block-container { padding-bottom: 60px; }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data():
    url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    try:
        df = pd.read_csv(url)
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(datetime.now().year)
        
        # Defensive: Ensure columns exist
        if 'Publication Type' not in df.columns: df['Publication Type'] = 'Journal Article'
        if 'Journal Area' not in df.columns: df['Journal Area'] = 'Multidisciplinary'
        
        return df
    except: return pd.DataFrame()

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.title("🔍 Filters")
if df.empty:
    st.warning("⚠️ Data loading... check back shortly.")
    st.stop()

# Time Filter
time_filter = st.sidebar.radio("Period", ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"], index=1)
now = datetime.now()

if time_filter == "Last Week": start = now - timedelta(days=7)
elif time_filter == "Last Month": start = now - timedelta(days=30)
elif time_filter == "Last Year": start = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start = now - timedelta(days=5*365)
else: start = pd.to_datetime("2000-01-01")

df_filtered = df[df['Date Available Online'] >= start].copy()

# Download Button
st.sidebar.markdown("---")
csv = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("📥 Download CSV", csv, "lcds_data.csv", "text/csv")

# --- MAIN DASHBOARD ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact across the years.</div>', unsafe_allow_html=True)

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Publications", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c4.metric("Active Researchers", df_filtered['LCDS Author'].nunique())

st.divider()

# --- PLOTS ROW 1 ---
col1, col2 = st.columns(2)
with col1:
    st.subheader("📈 Citations Over Time")
    # Group by Year
    df_yearly = df_filtered.groupby('Year')['Citation Count'].sum().reset_index()
    if not df_yearly.empty:
        fig = px.bar(df_yearly, x='Year', y='Citation Count', title="Total Citations per Year",
                     color_discrete_sequence=['#002147'])
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No citation data for this period.")

with col2:
    st.subheader("📊 Impact by Field")
    df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
    df_area = df_area[df_area['Journal Area'] != 'Multidisciplinary']
    if not df_area.empty:
        fig = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Prism)
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No field data available.")

# --- PLOTS ROW 2 ---
col3, col4 = st.columns(2)
with col3:
    st.subheader("📑 Distribution Histogram")
    # Histogram of Citation Counts
    if not df_filtered.empty:
        fig_hist = px.histogram(df_filtered, x="Citation Count", nbins=20, 
                                title="Citation Distribution",
                                color_discrete_sequence=['#C49102'])
        st.plotly_chart(fig_hist, use_container_width=True)
    else: st.info("No data.")

with col4:
    st.subheader("📄 Publication Types")
    df_type = df_filtered['Publication Type'].value_counts().reset_index()
    df_type.columns = ['Type', 'Count']
    if not df_type.empty:
        fig_type = px.pie(df_type, values='Count', names='Type', hole=0.4,
                          color_discrete_sequence=px.colors.qualitative.Safe)
        st.plotly_chart(fig_type, use_container_width=True)
    else: st.info("No type data.")

# --- TABLE ---
st.subheader("📄 Recent Publications List")
df_disp = df_filtered[['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'DOI']].copy()
df_disp['DOI'] = df_disp['DOI'].apply(lambda x: f'<a href="{x}" target="_blank">View</a>' if str(x).startswith('http') else x)
df_disp['Date Available Online'] = df_disp['Date Available Online'].dt.strftime('%Y-%m-%d')

html = df_disp.to_html(escape=False, index=False, classes="styled-table")
st.markdown(f'<div class="table-container">{html}</div>', unsafe_allow_html=True)

# --- FOOTER ---
st.markdown("""
    <div class="footer">
        © Certified University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a>
    </div>
""", unsafe_allow_html=True)
