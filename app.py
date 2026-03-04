import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import requests

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🎓", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
        
        h1, h2, h3 { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-weight: 700; }
        
        /* Subheading: Dark and Readable */
        .trendy-sub {
            color: #002147; /* Oxford Blue */
            font-size: 1.5rem; 
            font-weight: 600; 
            margin-bottom: 30px;
        }
        @media (prefers-color-scheme: dark) {
            .trendy-sub { color: #FFD700; } /* Gold in Dark Mode */
        }
        
        /* Footer */
        .footer {
            position: fixed; left: 0; bottom: 0; width: 100%;
            background-color: #002147; color: white; text-align: center;
            padding: 12px; font-size: 0.85rem; z-index: 999;
        }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        
        .block-container { padding-bottom: 80px; }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA (ROBUST PATH CHECK) ---
@st.cache_data(ttl=3600)
def load_data():
    # 1. Primary Target (Nested structure often created by Actions)
    url_nested = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    # 2. Fallback Target (Flat structure)
    url_flat = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/lcds_publications.csv"
    
    df = pd.DataFrame()
    
    # Try Nested first
    try:
        df = pd.read_csv(url_nested)
    except:
        # Try Flat if nested fails
        try:
            df = pd.read_csv(url_flat)
        except:
            return pd.DataFrame() # Give up if both fail

    if not df.empty:
        # Defaults for missing columns
        if 'Publication Type' not in df.columns: df['Publication Type'] = 'Journal Article'
        if 'Journal Name' not in df.columns: df['Journal Name'] = 'Unknown'
        if 'Citation Count' not in df.columns: df['Citation Count'] = 0
        if 'Year of Publication' not in df.columns: df['Year of Publication'] = datetime.now().year
        
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        
    return df

df = load_data()

# --- SIDEBAR & REFRESH ---
st.sidebar.title("🔍 Filters")

# Manual Refresh to see new data immediately
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

if df.empty:
    st.warning("⚠️ Data loading or empty. Check back later.")
    st.stop()

# Time Filter
time_filter = st.sidebar.radio("Select Period", ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"], index=1)
now = datetime.now()

if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

# Apply Filter
mask = (df['Date Available Online'] >= start_date)
df_filtered = df[mask].copy()

# Download Button
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Export")
csv_data = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("Download CSV", csv_data, f"lcds_data_{datetime.now().date()}.csv", "text/csv")

# --- DASHBOARD HEADER ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact over the years.</div>', unsafe_allow_html=True)
st.markdown(f"**Viewing:** {time_filter} | **Records Found:** {len(df_filtered)}")
st.divider()

# --- METRICS ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Output", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# --- CUMULATIVE GRAPH (Full Width) ---
st.subheader("📈 Cumulative Impact (Citations)")

if 'Year of Publication' in df_filtered.columns:
    # 1. Group by Year
    df_cite = df_filtered.groupby('Year of Publication')['Citation Count'].sum().reset_index()
    # 2. Sort Oldest -> Newest
    df_cite = df_cite.sort_values('Year of Publication')
    # 3. Calculate CUMULATIVE Sum (Reversed logic: Line goes UP)
    df_cite['Cumulative Citations'] = df_cite['Citation Count'].cumsum()
    
    if not df_cite.empty:
        fig = px.area(
            df_cite, 
            x='Year of Publication', 
            y='Cumulative Citations', 
            title="Accumulated Citations Over Time",
            markers=True,
            color_discrete_sequence=['#002147'] # Oxford Blue
        )
        fig.update_layout(
            xaxis_type='category', 
            plot_bgcolor="rgba(0,0,0,0)", 
            paper_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No citation data available for this period.")

# --- DATA TABLE ---
st.subheader("📄 Recent Publications")

# Configure Columns
if 'Date Available Online' in df_filtered.columns:
    df_filtered['Date Display'] = df_filtered['Date Available Online'].dt.strftime('%Y-%m-%d')
else:
    df_filtered['Date Display'] = ""

cols_to_show = ['Date Display', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']
df_display = df_filtered[[c for c in cols_to_show if c in df_filtered.columns]].copy()
df_display = df_display.rename(columns={'Date Display': 'Date', 'Publication Type': 'Type', 'Citation Count': 'Cites'})

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "DOI": st.column_config.LinkColumn("Link", display_text="View Paper"),
        "Cites": st.column_config.NumberColumn("Cites", format="%d")
    }
)

# --- FOOTER ---
st.markdown("""
    <div class="footer">
        © University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">Visit our Website or Follow us on Social Media</a>
    </div>
""", unsafe_allow_html=True)
