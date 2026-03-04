import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🎓", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
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
        if 'Country' not in df.columns: df['Country'] = "Global"
        return df
    except: return pd.DataFrame()

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.title("🔍 Filters")
if df.empty:
    st.warning("⚠️ Data loading... check back shortly.")
    st.stop()

# Time Filter
time_opt = st.sidebar.radio("Period", ["Since Sep 2019", "Last Year", "Last Month", "Last Week"], index=0)
now = datetime.now()

if time_opt == "Last Week": start = now - timedelta(days=7)
elif time_opt == "Last Month": start = now - timedelta(days=30)
elif time_opt == "Last Year": start = now - timedelta(days=365)
else: start = pd.to_datetime("2019-09-01")

df_filtered = df[df['Date Available Online'] >= start].copy()

# Download Button
st.sidebar.markdown("---")
csv = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("📥 Download Current View CSV", csv, f"lcds_data_{time_opt.replace(' ', '_')}.csv", "text/csv")

# --- MAIN DASHBOARD ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact across the years.</div>', unsafe_allow_html=True)

# 1. METRICS
c1, c2, c3, c4 = st.columns(4)
c1.metric("Publications", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c4.metric("Countries Reached", df_filtered['Country'].nunique())

st.divider()

# 2. CHARTS ROW 1
col1, col2 = st.columns(2)
with col1:
    st.subheader("📈 Citations Over Time")
    df_yearly = df_filtered.groupby('Year')['Citation Count'].sum().reset_index()
    if not df_yearly.empty:
        fig = px.bar(df_yearly, x='Year', y='Citation Count', title="Citations per Year", color_discrete_sequence=['#002147'])
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No data.")

with col2:
    st.subheader("🌍 Collaboration Map")
    # Simple map based on Country codes
    if 'Country' in df_filtered.columns:
        # Split multiple countries if comma separated
        country_series = df_filtered['Country'].str.split(', ').explode()
        df_map = country_series.value_counts().reset_index()
        df_map.columns = ['Country Code', 'Count']
        if not df_map.empty:
            fig_map = px.choropleth(df_map, locations="Country Code", color="Count", 
                                    hover_name="Country Code", title="Global Reach (Author Affiliations)",
                                    color_continuous_scale=px.colors.sequential.Plasma)
            st.plotly_chart(fig_map, use_container_width=True)
    else: st.info("No country data.")

# 3. CHARTS ROW 2
col3, col4 = st.columns(2)
with col3:
    st.subheader("📊 Impact by Field")
    df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
    df_area = df_area[df_area['Journal Area'] != 'Multidisciplinary']
    if not df_area.empty:
        fig_pie = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Prism)
        st.plotly_chart(fig_pie, use_container_width=True)

with col4:
    st.subheader("📑 Publication Types")
    df_type = df_filtered['Publication Type'].value_counts().reset_index()
    df_type.columns = ['Type', 'Count']
    fig_type = px.pie(df_type, values='Count', names='Type', hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe)
    st.plotly_chart(fig_type, use_container_width=True)

# 4. DATA TABLE
st.subheader("📄 Recent Publications")
st.dataframe(
    df_filtered[['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'DOI']],
    use_container_width=True,
    column_config={"DOI": st.column_config.LinkColumn("DOI Link")}
)

# --- FOOTER ---
st.markdown("""
    <div class="footer">
        © Certified University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a>
    </div>
""", unsafe_allow_html=True)
