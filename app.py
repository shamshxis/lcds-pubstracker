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

# --- CUSTOM OXFORD BRANDING CSS ---
st.markdown("""
    <style>
        /* Oxford Blue Headers */
        h1, h2, h3 {
            color: #002147 !important;
            font-family: 'Georgia', serif;
        }
        
        /* Subheading Styling */
        .sub-header {
            font-size: 1.2rem;
            color: #555;
            margin-top: -15px;
            margin-bottom: 25px;
            font-style: italic;
        }

        /* Footer Styling */
        .footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: #002147;
            color: white;
            text-align: center;
            padding: 10px;
            font-size: 0.9rem;
            z-index: 1000;
        }
        .footer a {
            color: #FFD700; /* Gold color for links */
            text-decoration: none;
            font-weight: bold;
        }
        .footer a:hover {
            text-decoration: underline;
        }
        
        /* Adjust main content padding so footer doesn't hide it */
        .block-container {
            padding-bottom: 70px;
        }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA (FROM SILENT BRANCH) ---
@st.cache_data(ttl=3600)
def load_data():
    # URL to your raw CSV on the data branch
    # REPLACE 'shamshxis' and 'lcds-pubstracker' if they change!
    url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    
    try:
        df = pd.read_csv(url)
        
        # 1. Define EXPECTED columns
        expected_cols = [
            'Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 
            'Paper Title', 'Journal Name', 'Journal Area', 
            'Year of Publication', 'Citation Count', 'Publication Type'
        ]
        
        # 2. FORCE columns to exist (fill missing with defaults)
        for col in expected_cols:
            if col not in df.columns:
                df[col] = "Unknown" if col != 'Citation Count' else 0

        # 3. Clean Data Types
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Journal Area'] = df['Journal Area'].fillna('Pending (Recent)')
        df['Publication Type'] = df['Publication Type'].fillna('Journal Article')

        return df
    except Exception as e:
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.title("🔍 Filters")

if df.empty:
    st.warning("⚠️ No data available yet.")
    st.info("The scraper is running. Please check back in a few minutes.")
    st.stop()

# Time Filter
time_options = ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"]
time_filter = st.sidebar.radio("Select Period", time_options, index=1)

now = datetime.now()
if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

# Publication Type Filter
pub_types = df['Publication Type'].unique()
selected_types = st.sidebar.multiselect("Publication Type", pub_types, default=pub_types)

# Apply Filters
mask = (df['Date Available Online'] >= start_date) & (df['Publication Type'].isin(selected_types))
df_filtered = df[mask].copy()

# --- MAIN DASHBOARD ---

# 1. HEADER & BRANDING
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<p class="sub-header">Measuring our impact across the years.</p>', unsafe_allow_html=True)

st.markdown(f"**Viewing:** {time_filter} | **Records Found:** {len(df_filtered)}")
st.divider()

# 2. METRICS
col1, col2, col3, col4 = st.columns(4)
total_cites = int(df_filtered['Citation Count'].sum())
preprint_count = len(df_filtered[df_filtered['Publication Type'] == 'Preprint'])

col1.metric("Total Output", len(df_filtered))
col2.metric("Total Citations", total_cites)
col3.metric("Preprints", preprint_count)
col4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# 3. VISUALS
c1, c2 = st.columns(2)
with c1:
    st.subheader("📊 Impact by Field")
    df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
    # Filter for cleaner chart
    df_area = df_area[(df_area['Journal Area'] != 'Pending (Recent)') & (df_area['Citation Count'] > 0)]
    
    if not df_area.empty:
        fig = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4, 
                     title="Citations per Field", color_discrete_sequence=px.colors.qualitative.Prism)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No citation data available for this period.")

with c2:
    st.subheader("📑 Type Distribution")
    fig2 = px.pie(df_filtered, names='Publication Type', hole=0.4, 
                  title="Journals vs. Preprints", color_discrete_sequence=px.colors.qualitative.Safe)
    st.plotly_chart(fig2, use_container_width=True)

# 4. DATA TABLE
st.subheader(f"📄 Recent Publications")
cols_to_show = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']
st.dataframe(
    df_filtered[cols_to_show],
    column_config={
        "DOI": st.column_config.LinkColumn("Link", display_text="Open Paper"),
        "Date Available Online": st.column_config.DateColumn("Date", format="YYYY-MM-DD")
    },
    hide_index=True,
    use_container_width=True
)

# 5. FOOTER
st.markdown("""
    <div class="footer">
        © University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">Visit our Website</a>
    </div>
""", unsafe_allow_html=True)
