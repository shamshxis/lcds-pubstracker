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
            div[data-testid="stDataFrame"] th {
                color: #FFD54F !important;
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
    url = "data/lcds_publications.csv"
    if not pd.io.common.file_exists(url):
        url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    try:
        df = pd.read_csv(url)
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(datetime.now().year)
        return df
    except: return pd.DataFrame()

# --- HIGHLIGHT LOGIC ---
def highlight_conversions(row):
    """Glows Gold if article converted from Preprint -> Journal recently."""
    current_year = datetime.now().year
    if "(Journal Publication Now Available)" in str(row['Paper Title']):
        if row['Year'] >= current_year:
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
c4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# --- CHARTS ROW ---
col1, col2 = st.columns(2)

# Chart 1: Bar Chart (Citations per Year)
with col1:
    st.subheader("📈 Citations Trend")
    df_yearly = df_filtered.groupby('Year')['Citation Count'].sum().reset_index()
    if not df_yearly.empty:
        fig = px.bar(df_yearly, x='Year', y='Citation Count', 
                     title="Total Citations per Year", 
                     color_discrete_sequence=['#64B5F6'])
        fig.update_layout(xaxis_title=None, yaxis_title=None, height=350)
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No citation data available.")

# Chart 2: Doughnut Chart (Citations by Journal)
with col2:
    st.subheader("🍩 Top Journals by Impact")
    # Group by Journal and sum citations
    df_journal = df_filtered.groupby('Journal Name')['Citation Count'].sum().reset_index()
    # Filter out 0 citations to keep chart clean and sort
    df_journal = df_journal[df_journal['Citation Count'] > 0].sort_values('Citation Count', ascending=False)
    
    # Optional: Take top 15 to prevent clutter, group rest as "Other" could be done but usually top 10-15 is enough
    if not df_journal.empty:
        # Use Pastel color sequence which pops against dark mode
        fig_donut = px.pie(df_journal.head(15), values='Citation Count', names='Journal Name', 
                           title="Citations per Journal (Top 15)",
                           hole=0.6, 
                           color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_donut.update_layout(height=350, showlegend=False) # Hide legend to save space, rely on hover
        fig_donut.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_donut, use_container_width=True)
    else: st.info("No citation data available by journal.")

st.divider()

# --- DATA TABLE ---
st.subheader("📄 Publications List")

# Apply Gold Glow
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
        © Leverhulme Centre for Demographic Science - University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a>
    </div>
""", unsafe_allow_html=True)
