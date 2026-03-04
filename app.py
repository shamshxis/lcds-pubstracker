import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="LCDS Impact Tracker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS (Branding + "Web 2.0" Layout) ---
st.markdown("""
    <style>
        /* Import Google Font */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');

        /* DYNAMIC HEADERS */
        h1, h2, h3 {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-weight: 700;
        }
        
        /* TRENDY GRADIENT SUBHEADING */
        .trendy-sub {
            background: linear-gradient(90deg, #002147 0%, #C49102 100%); /* Oxford Blue -> Gold */
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 1.5rem;
            font-weight: 600;
            margin-top: -10px;
            margin-bottom: 30px;
        }
        @media (prefers-color-scheme: dark) {
            .trendy-sub { background: linear-gradient(90deg, #81D4FA 0%, #FFD700 100%); }
        }

        /* FOOTER */
        .footer {
            position: fixed; left: 0; bottom: 0; width: 100%;
            background-color: #002147; color: white; text-align: center;
            padding: 12px; font-size: 0.85rem; z-index: 1000;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.2);
        }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        
        /* SCROLLABLE TABLE CONTAINER (Web 2.0 Style) */
        .table-container {
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 8px;
            background-color: var(--background-color);
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }

        /* STYLED HTML TABLE */
        .styled-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Roboto', sans-serif; /* Requested Google Font */
            font-size: 0.9rem;
            color: var(--text-color);
        }
        /* Sticky Header */
        .styled-table thead tr th {
            position: sticky; top: 0;
            background-color: #002147; /* Oxford Blue */
            color: #ffffff;
            text-align: left;
            padding: 12px 15px;
            z-index: 1;
        }
        /* Rows */
        .styled-table tbody tr { border-bottom: 1px solid #eee; }
        .styled-table tbody tr:nth-of-type(even) { background-color: rgba(0,0,0,0.02); } /* Zebra Stripe */
        .styled-table td { padding: 10px 15px; }
        .styled-table a { color: #0066cc; text-decoration: none; font-weight: bold; border-bottom: 1px dotted #0066cc; }
        .styled-table a:hover { color: #003366; border-bottom: 1px solid #003366; }

        /* DARK MODE OVERRIDES */
        @media (prefers-color-scheme: dark) {
            .styled-table thead tr th { background-color: #1E1E1E; color: #FFD700; }
            .styled-table tbody tr { border-bottom: 1px solid #333; }
            .styled-table tbody tr:nth-of-type(even) { background-color: rgba(255,255,255,0.05); }
            .styled-table td { color: #ddd; }
            .styled-table a { color: #4da6ff; border-bottom: 1px dotted #4da6ff; }
            .table-container { border: 1px solid #444; }
        }
        
        .block-container { padding-bottom: 80px; }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data():
    url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    try:
        df = pd.read_csv(url)
        
        # Self-Healing: Ensure all columns exist
        required_cols = [
            'Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 
            'Journal Area', 'Year', 'Citation Count', 'Publication Type', 'DOI'
        ]
        for col in required_cols:
            if col not in df.columns:
                if col == 'Citation Count': df[col] = 0
                elif col == 'Year': df[col] = datetime.now().year
                else: df[col] = "Unknown"

        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(datetime.now().year)
        
        return df
    except: return pd.DataFrame()

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.title("🔍 Filters")

if df.empty:
    st.warning("⚠️ Data loading... please wait.")
    st.stop()

# Time Filter
time_filter = st.sidebar.radio("Select Period", ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"], index=1)
now = datetime.now()

if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

# Apply Filters
mask = (df['Date Available Online'] >= start_date)
df_filtered = df[mask].copy()

# --- DOWNLOAD BUTTON ---
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Export Data")
csv_data = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button(
    label="Download Full CSV",
    data=csv_data,
    file_name=f"lcds_impact_data_{datetime.now().strftime('%Y-%m-%d')}.csv",
    mime="text/csv"
)

# --- MAIN DASHBOARD ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Leverhulme Centre for Demographic Science (LCDS) measuring our impact across the years.</div>', unsafe_allow_html=True)

st.markdown(f"**Viewing:** {time_filter} | **Records Found:** {len(df_filtered)}")
st.divider()

# METRICS
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Publications", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c4.metric("Active Researchers", df_filtered['LCDS Author'].nunique())

st.divider()

# --- PLOTS (2x2 Grid) ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 Citations Over Time")
    # Yearly Bar Chart
    df_yearly = df_filtered.groupby('Year')['Citation Count'].sum().reset_index()
    if not df_yearly.empty:
        fig = px.bar(df_yearly, x='Year', y='Citation Count', title="Total Citations per Year",
                     color_discrete_sequence=['#002147'])
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No citation data available for this period.")

with col2:
    st.subheader("📊 Impact by Field")
    # Pie Chart
    df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
    df_area = df_area[df_area['Journal Area'] != 'Multidisciplinary']
    if not df_area.empty:
        fig = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4, 
                     color_discrete_sequence=px.colors.qualitative.Prism)
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No field data available.")

col3, col4 = st.columns(2)

with col3:
    st.subheader("📑 Citation Distribution")
    # Histogram
    if not df_filtered.empty:
        fig_hist = px.histogram(df_filtered, x="Citation Count", nbins=20, 
                                title="Distribution of Citations",
                                color_discrete_sequence=['#C49102']) # Gold color
        st.plotly_chart(fig_hist, use_container_width=True)
    else: st.info("No data.")

with col4:
    st.subheader("📄 Publication Types")
    # Pie Chart
    df_type = df_filtered['Publication Type'].value_counts().reset_index()
    df_type.columns = ['Type', 'Count']
    if not df_type.empty:
        fig_type = px.pie(df_type, values='Count', names='Type', hole=0.4, 
                          color_discrete_sequence=px.colors.qualitative.Safe)
        st.plotly_chart(fig_type, use_container_width=True)
    else: st.info("No data.")

# --- DATA TABLE (Scrollable HTML) ---
st.subheader("📄 Recent Publications List")

# Display columns
display_cols = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'DOI']
df_display = df_filtered[display_cols].copy()

# Format DOI & Date
df_display['DOI'] = df_display['DOI'].apply(lambda x: f'<a href="{x}" target="_blank">View</a>' if str(x).startswith('http') else x)
df_display['Date Available Online'] = df_display['Date Available Online'].dt.strftime('%Y-%m-%d')

# Render HTML
html_table = df_display.to_html(escape=False, index=False, classes="styled-table")
st.markdown(f'<div class="table-container">{html_table}</div>', unsafe_allow_html=True)

# --- FOOTER ---
st.markdown("""
    <div class="footer">
        © Certified University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a>
    </div>
""", unsafe_allow_html=True)
