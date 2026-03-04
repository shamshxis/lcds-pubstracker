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
        
        /* Subheading: Dark Oxford Blue for Readability */
        .trendy-sub {
            color: #002147; 
            font-size: 1.5rem; 
            font-weight: 600; 
            margin-bottom: 30px;
        }
        
        @media (prefers-color-scheme: dark) {
            .trendy-sub { color: #FFD700; } 
        }
        
        /* Sticky Footer */
        .footer {
            position: fixed; left: 0; bottom: 0; width: 100%;
            background-color: #002147; color: white; text-align: center;
            padding: 12px; font-size: 0.85rem; z-index: 999;
        }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        
        .block-container { padding-bottom: 80px; }
    </style>
""", unsafe_allow_html=True)

# --- APP-SIDE FIREWALL SETTINGS ---
# These terms will be hidden from the UI even if they exist in the CSV
FORBIDDEN_WORDS = [
    'photocatalyst', 's-scheme', 'baryon', 'graphene', 'lattice', 
    'oxide', 'splitting', 'quantum', 'spectroscopy', 'perovskite'
]

# --- LOAD DATA WITH CACHE BUSTER ---
def load_data():
    # Adding a timestamp forces GitHub to bypass its 5-minute cache
    timestamp = int(time.time())
    url = f"https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv?v={timestamp}"
    
    try:
        df = pd.read_csv(url)
        
        if df.empty:
            return pd.DataFrame(), "File is Empty"

        # 1. APPLY FIREWALL: Filter out any non-demography titles
        if 'Paper Title' in df.columns:
            mask = df['Paper Title'].str.lower().apply(
                lambda x: not any(word in str(x) for word in FORBIDDEN_WORDS)
            )
            df = df[mask]

        # 2. DATA CLEANING
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Year of Publication'] = df['Date Available Online'].dt.year
        
        return df, "Freshly Pulled"
    except Exception as e:
        return pd.DataFrame(), f"Waiting for Data... ({e})"

# --- SIDEBAR & DIAGNOSTICS ---
st.sidebar.title("🔍 Diagnostics")
df, status = load_data()
st.sidebar.info(f"Source Status: {status}")

if st.sidebar.button("🔄 Force Clear Cache"):
    st.cache_data.clear()
    st.rerun()

# --- MAIN DASHBOARD HEADER ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact over the years.</div>', unsafe_allow_html=True)

# Safety check if data is missing or being wiped by the scraper
if df.empty:
    st.warning("📊 **Data Update in Progress**")
    st.info("The scraper is currently verifying LCDS affiliations. Please wait 1-2 minutes and click 'Force Clear Cache' in the sidebar.")
    st.stop()

# --- FILTERS ---
time_filter = st.sidebar.radio("Select Period", ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"], index=1)
now = datetime.now()

if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

df_filtered = df[df['Date Available Online'] >= start_date].copy()

# --- METRICS ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Output", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint'] if 'Publication Type' in df_filtered.columns else []))
c4.metric("Active Authors", df_filtered['LCDS Author'].nunique() if 'LCDS Author' in df_filtered.columns else 0)

st.divider()

# --- CUMULATIVE IMPACT GRAPH ---
st.subheader("📈 Cumulative Impact (Citations)")

if 'Year of Publication' in df_filtered.columns and not df_filtered.empty:
    # Prepare cumulative data
    df_cite = df_filtered.groupby('Year of Publication')['Citation Count'].sum().reset_index()
    df_cite = df_cite.sort_values('Year of Publication')
    df_cite['Cumulative Citations'] = df_cite['Citation Count'].cumsum()
    
    # Create Oxford Blue Area Chart
    fig = px.area(
        df_cite, 
        x='Year of Publication', 
        y='Cumulative Citations', 
        markers=True,
        color_discrete_sequence=['#002147']
    )
    fig.update_layout(
        xaxis_type='category', 
        plot_bgcolor="rgba(0,0,0,0)", 
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=30, b=0)
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No citation data available for this selected period.")

# --- PUBLICATIONS TABLE ---
st.subheader("📄 Recent Publications")

# Column formatting
if 'Date Available Online' in df_filtered.columns:
    df_filtered['Date'] = df_filtered['Date Available Online'].dt.strftime('%Y-%m-%d')
else:
    df_filtered['Date'] = ""

cols_to_show = ['Date', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'DOI']
df_display = df_filtered[[c for c in cols_to_show if c in df_filtered.columns]].copy()
df_display = df_display.rename(columns={'Citation Count': 'Cites'})

st.dataframe(
    df_display, 
    use_container_width=True, 
    hide_index=True, 
    column_config={
        "DOI": st.column_config.LinkColumn("Link", display_text="View Paper"),
        "Cites": st.column_config.NumberColumn("Cites", format="%d")
    }
)

# --- EXPORT ---
st.sidebar.markdown("---")
csv_data = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("📥 Download Filtered CSV", csv_data, f"lcds_export_{datetime.now().date()}.csv", "text/csv")

# --- FOOTER ---
st.markdown(f"""
    <div class="footer">
        © University of Oxford {datetime.now().year} - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">Visit our Website or Follow us on Social Media</a>
    </div>
""", unsafe_allow_html=True)
