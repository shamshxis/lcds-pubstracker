import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="LCDS Impact Tracker",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- LOAD DATA FROM SILENT BRANCH ---
@st.cache_data(ttl=3600)  # Cache clears every 1 hour to keep data fresh
def load_data():
    # URL pointing to the raw CSV on the 'data' branch
    url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    
    try:
        # Load CSV from the raw URL
        df = pd.read_csv(url)
        
        # Convert Date column to datetime objects
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        
        # Fill missing values for cleaner display
        if 'Journal Area' in df.columns:
            df['Journal Area'] = df['Journal Area'].fillna('Multidisciplinary')
        if 'Publication Type' in df.columns:
            df['Publication Type'] = df['Publication Type'].fillna('Journal Article')
            
        return df
    except Exception as e:
        # Return empty dataframe if data isn't ready yet
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.title("🔍 Filters")

if df.empty:
    st.warning("⚠️ Waiting for data...")
    st.info("The scraper runs nightly. Please trigger the 'Daily Publication Scraper' action manually in GitHub Actions to generate the first CSV.")
    st.stop()

# 1. Time Filter
time_options = ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"]
time_filter = st.sidebar.radio("Select Period", time_options, index=1)

now = datetime.now()
if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

# 2. Publication Type Filter
if 'Publication Type' in df.columns:
    pub_types = df['Publication Type'].unique()
    selected_types = st.sidebar.multiselect("Publication Type", pub_types, default=pub_types)
else:
    selected_types = []

# 3. Apply Filters
# Filter by date
mask = (df['Date Available Online'] >= start_date)
# Filter by type if column exists
if 'Publication Type' in df.columns and selected_types:
    mask = mask & (df['Publication Type'].isin(selected_types))

df_filtered = df[mask].copy()

# --- MAIN DASHBOARD ---
st.title("🌍 LCDS Publications Tracker")
st.markdown(f"**Viewing:** {time_filter} | **Records Found:** {len(df_filtered)}")

# --- ROW 1: KEY METRICS ---
col1, col2, col3, col4 = st.columns(4)

total_cites = int(df_filtered['Citation Count'].sum()) if 'Citation Count' in df_filtered.columns else 0
preprints = len(df_filtered[df_filtered['Publication Type'] == 'Preprint']) if 'Publication Type' in df_filtered.columns else 0

col1.metric("Total Output", len(df_filtered))
col2.metric("Total Citations", total_cites)
col3.metric("Preprints / Working Papers", preprints)
col4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# --- ROW 2: VISUALS ---
c_chart1, c_chart2 = st.columns(2)

with c_chart1:
    st.subheader("📊 Impact by Field")
    if 'Journal Area' in df_filtered.columns:
        # Group by Area and sum citations
        df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
        # Filter out "Pending" and zero citations for a cleaner chart
        df_area = df_area[
            (df_area['Journal Area'] != 'Pending (Recent)') & 
            (df_area['Citation Count'] > 0)
        ]
        
        if not df_area.empty:
            fig_impact = px.pie(
                df_area, 
                values='Citation Count', 
                names='Journal Area', 
                hole=0.4,
                title="Citation Share by Field",
                color_discrete_sequence=px.colors.qualitative.Prism
            )
            fig_impact.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_impact, use_container_width=True)
        else:
            st.info("Not enough citation data for this period.")
    else:
        st.error("Column 'Journal Area' missing.")

with c_chart2:
    st.subheader("📑 Journals vs. Preprints")
    if 'Publication Type' in df_filtered.columns:
        fig_type = px.pie(
            df_filtered, 
            names='Publication Type', 
            hole=0.4,
            title="Publication Type Distribution",
            color_discrete_sequence=px.colors.qualitative.Safe
        )
        st.plotly_chart(fig_type, use_container_width=True)
    else:
        st.info("Publication Type data missing.")

# --- ROW 3: RECENT PAPERS TABLE ---
st.subheader(f"📄 Recent Publications ({len(df_filtered)})")

# Define columns to display
desired_cols = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']
display_cols = [c for c in desired_cols if c in df_filtered.columns]

st.dataframe(
    df_filtered[display_cols],
    column_config={
        "DOI": st.column_config.LinkColumn("Link", display_text="Open Paper"),
        "Date Available Online": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
        "Citation Count": st.column_config.NumberColumn("Cites"),
    },
    hide_index=True,
    use_container_width=True
)

# --- DOWNLOAD BUTTON ---
csv_data = df_filtered.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Download Filtered Data (CSV)",
    data=csv_data,
    file_name=f"lcds_publications_{datetime.now().strftime('%Y-%m-%d')}.csv",
    mime="text/csv"
)
