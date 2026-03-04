import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", layout="wide")

# --- CUSTOM CSS (Clean White Text for Dark Mode) ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
        
        h1, h2, h3 { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-weight: 700; color: white; }
        
        /* Subheading: Clean White for Dark Mode */
        .trendy-sub {
            color: white; 
            font-size: 1.5rem; 
            font-weight: 600; 
            margin-bottom: 25px;
        }
        
        /* Sticky Footer */
        .footer {
            position: fixed; left: 0; bottom: 0; width: 100%;
            background-color: #1E1E1E; color: #888; text-align: center;
            padding: 12px; font-size: 0.85rem; z-index: 999;
            border-top: 1px solid #333;
        }
        .footer a { color: #FFD700; text-decoration: none; font-weight: bold; }
        
        .block-container { padding-bottom: 80px; }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA WITH CACHE BUSTER ---
def load_data():
    # Cache buster ensures fresh data pull from the data branch
    timestamp = int(time.time())
    url = f"https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv?v={timestamp}"
    
    try:
        df = pd.read_csv(url)
        
        if df.empty:
            return pd.DataFrame()

        # Data Cleaning based on Colab logic
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        
        # Ensure 'Year' is available for the impact graph
        if 'Year' in df.columns:
            df['Year_Num'] = pd.to_numeric(df['Year'], errors='coerce')
            
        return df
    except Exception as e:
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR DIAGNOSTICS ---
st.sidebar.title("🔍 Controls")
if st.sidebar.button("🔄 Force Data Refresh"):
    st.cache_data.clear()
    st.rerun()

# --- HEADER ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact over the years.</div>', unsafe_allow_html=True)

# Safety check for empty data
if df.empty:
    st.info("📊 **System Update in Progress**")
    st.write("The scraper is currently verifying LCDS affiliations and fetching new preprints. Please refresh in 60 seconds.")
    st.stop()

# --- METRIC CARDS ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Output", len(df))
c2.metric("Total Citations", int(df['Citation Count'].sum()))
c3.metric("Preprints", len(df[df['Publication Type'] == 'Preprint']))
c4.metric("Verified Authors", df['LCDS Author'].nunique())

st.divider()

# --- YEAR-BY-YEAR IMPACT CHART ---
st.subheader("📈 Impact Over the Years (Citations)")

if 'Year_Num' in df.columns:
    # Filter for valid years and group citations to show the trend
    df_plot = df[df['Year_Num'].between(2018, 2027)].copy()
    df_plot = df_plot.groupby('Year_Num')['Citation Count'].sum().reset_index().sort_values('Year_Num')
    
    if not df_plot.empty:
        # Oxford Blue line on a dark background
        fig = px.area(
            df_plot, 
            x='Year_Num', 
            y='Citation Count', 
            markers=True,
            color_discrete_sequence=['#81D4FA'], # Lighter blue for dark mode
            labels={'Year_Num': 'Year', 'Citation Count': 'Citations'}
        )
        fig.update_layout(
            xaxis_type='category', 
            plot_bgcolor="rgba(0,0,0,0)", 
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No yearly citation data available.")

# --- PUBLICATIONS TABLE (Restored Original Dark Table) ---
st.subheader("📄 Recent Publications")

# Reformatting dates for the UI table
df['Date'] = df['Date Available Online'].dt.strftime('%Y-%m-%d')

# Selecting columns exactly as per your screenshots
cols_to_show = ['Date', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']
df_display = df[[c for c in cols_to_show if c in df.columns]].copy()

# Final rename for table headers
df_display = df_display.rename(columns={'Publication Type': 'Type', 'Citation Count': 'Cites'})

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
st.markdown(f"""
    <div class="footer">
        © University of Oxford {datetime.now().year} - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">Visit our Website or Follow us on Social Media</a>
    </div>
""", unsafe_allow_html=True)
