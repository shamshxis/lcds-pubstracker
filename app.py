import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🌍", layout="wide")

# --- LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data():
    # URL to your raw CSV on the data branch
    url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    
    try:
        df = pd.read_csv(url)
        
        # 1. Standardize Dates
        if 'Date Available Online' in df.columns:
            df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        
        # 2. FAILSAFE: Create missing columns if they don't exist yet
        # This prevents the KeyError you were seeing!
        if 'Publication Type' not in df.columns:
            df['Publication Type'] = 'Journal Article' # Default value
            
        if 'Journal Area' not in df.columns:
            df['Journal Area'] = 'Multidisciplinary' # Default value
            
        return df
    except Exception as e:
        # If the file is totally missing or broken
        return pd.DataFrame()

df = load_data()

# --- CHECK IF DATA LOADED ---
if df.empty:
    st.warning("⚠️ Waiting for data...")
    st.info("Please run the 'Daily Publication Scraper' action in GitHub to generate your first dataset.")
    st.stop()

# --- SIDEBAR FILTERS ---
st.sidebar.title("🔍 Filters")

# Time Filter
time_options = ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"]
time_filter = st.sidebar.radio("Select Period", time_options, index=1)

now = datetime.now()
if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

# Publication Type Filter (Now Safe!)
pub_types = df['Publication Type'].unique()
selected_types = st.sidebar.multiselect("Publication Type", pub_types, default=pub_types)

# Apply Filters
mask = (df['Date Available Online'] >= start_date) & (df['Publication Type'].isin(selected_types))
df_filtered = df[mask].copy()

# --- DASHBOARD ---
st.title("🌍 LCDS Publications Tracker")
st.markdown(f"**Viewing:** {time_filter} | **Records Found:** {len(df_filtered)}")

# METRICS
col1, col2, col3, col4 = st.columns(4)
total_cites = int(df_filtered['Citation Count'].sum()) if 'Citation Count' in df_filtered.columns else 0
# Safe check for Preprints
preprint_count = len(df_filtered[df_filtered['Publication Type'] == 'Preprint'])

col1.metric("Total Output", len(df_filtered))
col2.metric("Total Citations", total_cites)
col3.metric("Preprints", preprint_count)
col4.metric("Active Authors", df_filtered['LCDS Author'].nunique() if 'LCDS Author' in df_filtered.columns else 0)

st.divider()

# VISUALS
c1, c2 = st.columns(2)
with c1:
    st.subheader("📊 Impact by Field")
    if 'Journal Area' in df_filtered.columns:
        df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
        # Clean up chart data
        df_area = df_area[(df_area['Journal Area'] != 'Pending (Recent)') & (df_area['Citation Count'] > 0)]
        if not df_area.empty:
            fig = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4, title="Citations per Field")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough data for this chart.")

with c2:
    st.subheader("📑 Type Distribution")
    fig2 = px.pie(df_filtered, names='Publication Type', hole=0.4, title="Journals vs. Preprints")
    st.plotly_chart(fig2, use_container_width=True)

# DATA TABLE
st.subheader(f"📄 Recent Publications")
# Only show columns that actually exist
cols_to_show = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']
final_cols = [c for c in cols_to_show if c in df_filtered.columns]

st.dataframe(
    df_filtered[final_cols],
    column_config={
        "DOI": st.column_config.LinkColumn("Link"),
        "Date Available Online": st.column_config.DateColumn("Date", format="YYYY-MM-DD")
    },
    hide_index=True,
    use_container_width=True
)
