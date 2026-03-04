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

# --- CUSTOM CSS (Branding, Dark Mode, Scrollable Table) ---
st.markdown("""
    <style>
        /* Import Google Font */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');

        /* Dynamic Headers */
        h1, h2, h3 {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        
        /* Oxford Blue & Gold Gradient Subheading */
        .trendy-sub {
            background: linear-gradient(90deg, #002147 0%, #C49102 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 1.5rem;
            font-weight: 600;
            margin-top: -10px;
            margin-bottom: 30px;
        }

        /* Dark Mode Adjustment */
        @media (prefers-color-scheme: dark) {
            .trendy-sub {
                background: linear-gradient(90deg, #81D4FA 0%, #FFD700 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
        }

        /* Footer */
        .footer {
            position: fixed; left: 0; bottom: 0; width: 100%;
            background-color: #002147; color: white; text-align: center;
            padding: 12px; font-size: 0.85rem; z-index: 999;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.2);
        }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        
        /* Table Container */
        .table-container {
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 8px;
            background-color: var(--background-color);
        }

        /* Styled Table */
        .styled-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Roboto', sans-serif;
            font-size: 0.9rem;
            color: var(--text-color);
        }
        .styled-table thead tr th {
            position: sticky; top: 0;
            background-color: #002147;
            color: #ffffff;
            text-align: left;
            padding: 12px 15px;
            z-index: 1;
        }
        .styled-table tbody tr { border-bottom: 1px solid #eee; }
        .styled-table td { padding: 10px 15px; }
        .styled-table a { color: #0066cc; text-decoration: none; font-weight: bold; }
        
        /* Dark Mode Table Override */
        @media (prefers-color-scheme: dark) {
            .styled-table thead tr th { background-color: #1E1E1E; color: #FFD700; }
            .styled-table tbody tr { border-bottom: 1px solid #333; }
            .styled-table td { color: #ddd; }
            .styled-table a { color: #4da6ff; }
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
        
        # Define ALL requested columns to ensure they exist
        required_cols = [
            'Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 
            'Paper Title', 'Journal Name', 'Journal Area', 
            'Year of Publication', 'Citation Count', 'Publication Type'
        ]
        
        # Self-Healing: Create missing columns with defaults
        for col in required_cols:
            if col not in df.columns:
                if col == 'Citation Count': df[col] = 0
                elif col == 'Year of Publication': df[col] = datetime.now().year
                else: df[col] = "Unknown"

        # Type Conversion
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        
        return df
    except Exception as e:
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.title("🔍 Filters")

if df.empty:
    st.warning("⚠️ Data is loading or empty.")
    st.info("Check back in a few minutes after the scraper runs.")
    st.stop()

# Time Filter
time_filter = st.sidebar.radio("Select Period", ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"], index=1)
now = datetime.now()

if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

# Pub Type Filter
all_types = list(df['Publication Type'].unique())
selected_types = st.sidebar.multiselect("Publication Type", all_types, default=all_types)

# Apply Filters
mask = (df['Date Available Online'] >= start_date) & (df['Publication Type'].isin(selected_types))
df_filtered = df[mask].copy()

# --- DOWNLOAD BUTTON (IN SIDEBAR) ---
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Export Data")

# Prepare CSV for download (Ensure all columns are present)
csv_cols = [
    'Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 
    'Paper Title', 'Journal Name', 'Journal Area', 
    'Year of Publication', 'Citation Count', 'Publication Type'
]
# Only export columns that actually exist in the filtered dataframe
final_export_cols = [c for c in csv_cols if c in df_filtered.columns]
csv_data = df_filtered[final_export_cols].to_csv(index=False).encode('utf-8')

st.sidebar.download_button(
    label="Download Filtered CSV",
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
c1.metric("Total Output", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# PLOTS
col_p1, col_p2 = st.columns(2)

with col_p1:
    st.subheader("📊 Impact by Field")
    # Group by Area
    if 'Journal Area' in df_filtered.columns:
        df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
        # Clean up for chart
        df_area = df_area[df_area['Journal Area'] != 'Unknown']
        
        if not df_area.empty and df_area['Citation Count'].sum() > 0:
            fig = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4, 
                         color_discrete_sequence=px.colors.qualitative.Prism)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No citation data available for this selection.")

with col_p2:
    st.subheader("📑 Type Distribution")
    if 'Publication Type' in df_filtered.columns:
        df_type = df_filtered['Publication Type'].value_counts().reset_index()
        df_type.columns = ['Publication Type', 'Count']
        
        if not df_type.empty:
            fig2 = px.pie(df_type, values='Count', names='Publication Type', hole=0.4, 
                          color_discrete_sequence=px.colors.qualitative.Safe)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No publication type data available.")

# DATA TABLE
st.subheader("📄 Recent Publications")

# Display columns (Formatted for screen)
display_cols = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']
# Intersection with available columns
final_display_cols = [c for c in display_cols if c in df_filtered.columns]

df_display = df_filtered[final_display_cols].copy()

# Format DOI as Link
if 'DOI' in df_display.columns:
    df_display['DOI'] = df_display['DOI'].apply(lambda x: f'<a href="{x}" target="_blank">View</a>' if str(x).startswith('http') else x)

# Format Date
if 'Date Available Online' in df_display.columns:
    df_display['Date Available Online'] = df_display['Date Available Online'].dt.strftime('%Y-%m-%d')

# Render HTML Table
html_table = df_display.to_html(escape=False, index=False, classes="styled-table")
st.markdown(f'<div class="table-container">{html_table}</div>', unsafe_allow_html=True)

# --- FOOTER ---
st.markdown("""
    <div class="footer">
        © Certified University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a>
    </div>
""", unsafe_allow_html=True)
