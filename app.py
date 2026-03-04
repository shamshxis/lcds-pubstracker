import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Tracker", page_icon="🎓", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
        
        /* Gradient Header */
        .trendy-sub {
            background: linear-gradient(90deg, #002147 0%, #C49102 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            font-size: 1.5rem; font-weight: 600; margin-bottom: 20px;
        }
        
        /* Dark Mode Adjustments */
        @media (prefers-color-scheme: dark) {
            .trendy-sub {
                background: linear-gradient(90deg, #64B5F6 0%, #FFD54F 100%); 
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            }
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

# --- LOAD DATA ---
@st.cache_data(ttl=3600) 
def load_data():
    # Priority: Local -> GitHub Raw
    url = "data/lcds_publications.csv"
    if not pd.io.common.file_exists(url):
        url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    try:
        df = pd.read_csv(url)
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(datetime.now().year)
        if 'Country' not in df.columns: df['Country'] = "Global"
        return df
    except: return pd.DataFrame()

# --- STYLING FUNCTION ---
def highlight_conversions(row):
    """
    Highlights rows that are RECENT conversions (Preprint -> Journal).
    Criteria: Contains specific tag AND Year >= Current Year.
    """
    current_year = datetime.now().year
    # Check for the tag added by the scraper
    if "(Journal Publication Now Available)" in str(row['Paper Title']):
        # Only highlight if it's from this year or the future (upcoming)
        if row['Year'] >= current_year:
            # Subtle Gold Background (Works in Light & Dark Mode)
            return ['background-color: rgba(255, 215, 0, 0.15)'] * len(row)
    return [''] * len(row)

# --- SIDEBAR ---
st.sidebar.title("🔍 Controls")

if st.sidebar.button("🔄 Force Refresh"):
    st.cache_data.clear()
    st.toast("Refreshing data...", icon="✅")
    time.sleep(0.5)
    st.rerun()

df = load_data()

if df.empty:
    st.warning("⚠️ Data is currently updating. Please wait.")
    st.stop()

# Time Filter
time_opt = st.sidebar.radio("Time Period", ["Since Sep 2019", "Last Year", "Last Month", "Last Week"], index=0)
now = datetime.now()

if time_opt == "Last Week": start = now - timedelta(days=7)
elif time_opt == "Last Month": start = now - timedelta(days=30)
elif time_opt == "Last Year": start = now - timedelta(days=365)
else: start = pd.to_datetime("2019-09-01")

df_filtered = df[df['Date Available Online'] >= start].copy()

# Export
st.sidebar.markdown("---")
csv_data = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("Download CSV", csv_data, "lcds_data.csv", "text/csv")

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

# Charts
col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 Citations Trend")
    df_yearly = df_filtered.groupby('Year')['Citation Count'].sum().reset_index()
    if not df_yearly.empty:
        fig = px.bar(df_yearly, x='Year', y='Citation Count', 
                     title="Citations per Year", 
                     color_discrete_sequence=['#64B5F6'])
        fig.update_layout(xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No citation data.")

with col2:
    st.subheader("🌍 Collaboration Map")
    if 'Country' in df_filtered.columns:
        # Parse countries (comma separated)
        countries = df_filtered['Country'].str.split(', ').explode().value_counts().reset_index()
        countries.columns = ['Country Code', 'Count']
        if not countries.empty:
            fig_map = px.choropleth(countries, locations="Country Code", color="Count",
                                    hover_name="Country Code", title="Author Affiliations",
                                    color_continuous_scale="Plasma") # High contrast scale
            st.plotly_chart(fig_map, use_container_width=True)

# Table
st.subheader("📄 Publications List")

# Apply Styling
styled_df = df_filtered[['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'DOI', 'Year']].style.apply(highlight_conversions, axis=1)

st.dataframe(
    styled_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "DOI": st.column_config.LinkColumn("DOI"),
        "Citation Count": st.column_config.NumberColumn("Cites", format="%d"),
        "Date Available Online": st.column_config.DateColumn("Date", format="YYYY-MM-DD")
    }
)

# Footer
st.markdown("""
    <div class="footer">
        © Certified University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a>
    </div>
""", unsafe_allow_html=True)
