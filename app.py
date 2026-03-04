import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🎓", layout="wide")

# --- CUSTOM BRANDING CSS ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
        
        h1, h2, h3 { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-weight: 700; }
        
        /* Gradient Subheading */
        .trendy-sub {
            background: linear-gradient(90deg, #002147 0%, #C49102 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            font-size: 1.5rem; font-weight: 600; margin-bottom: 30px;
        }
        @media (prefers-color-scheme: dark) {
            .trendy-sub { background: linear-gradient(90deg, #81D4FA 0%, #FFD700 100%); }
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

# --- LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data():
    url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    try:
        df = pd.read_csv(url)
        # Defaults for missing columns
        if 'Publication Type' not in df.columns: df['Publication Type'] = 'Journal Article'
        if 'Journal Name' not in df.columns: df['Journal Name'] = 'Unknown'
        if 'Citation Count' not in df.columns: df['Citation Count'] = 0
        if 'Year of Publication' not in df.columns: df['Year of Publication'] = datetime.now().year
        
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        return df
    except: return pd.DataFrame()

df = load_data()

# --- SIDEBAR ---
st.sidebar.title("🔍 Filters")
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

# Download
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Export")
csv_data = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("Download CSV", csv_data, f"lcds_data_{datetime.now().date()}.csv", "text/csv")

# --- DASHBOARD ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact over the years.</div>', unsafe_allow_html=True)
st.markdown(f"**Viewing:** {time_filter} | **Records Found:** {len(df_filtered)}")
st.divider()

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Output", len(df_filtered))
c2.metric("Total Citations", int(df_filtered['Citation Count'].sum()))
c3.metric("Preprints", len(df_filtered[df_filtered['Publication Type'] == 'Preprint']))
c4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# --- PLOTS ---
col1, col2 = st.columns([2, 1])  # Make the citation chart wider (2/3rds)

with col1:
    st.subheader("📈 Citation Momentum")
    if 'Year of Publication' in df_filtered.columns:
        # Group citations by Year
        df_cite = df_filtered.groupby('Year of Publication')['Citation Count'].sum().reset_index()
        df_cite = df_cite.sort_values('Year of Publication')
        
        if not df_cite.empty:
            # Create a smooth Area Chart
            fig = px.area(df_cite, x='Year of Publication', y='Citation Count', 
                          title="Citations Accumulated by Publication Year",
                          markers=True,
                          color_discrete_sequence=['#002147']) # Oxford Blue
            
            fig.update_layout(xaxis_type='category', plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No citation data available for this period.")

with col2:
    st.subheader("📑 Output Type")
    df_type = df_filtered['Publication Type'].value_counts().reset_index()
    if not df_type.empty:
        df_type.columns = ['Publication Type', 'Count']
        # Donut chart
        fig2 = px.pie(df_type, values='Count', names='Publication Type', hole=0.5, 
                      color_discrete_sequence=['#C49102', '#002147']) # Gold & Blue
        fig2.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No data available.")

# --- TABLE ---
st.subheader("📄 Recent Publications")

# Configure Columns for display
if 'Date Available Online' in df_filtered.columns:
    df_filtered['Date Display'] = df_filtered['Date Available Online'].dt.strftime('%Y-%m-%d')
else:
    df_filtered['Date Display'] = ""

# Select columns to show
cols_to_show = ['Date Display', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']
df_display = df_filtered[[c for c in cols_to_show if c in df_filtered.columns]].copy()

# Rename for UI
df_display = df_display.rename(columns={'Date Display': 'Date', 'Publication Type': 'Type', 'Citation Count': 'Cites'})

# Render native DataFrame
st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "DOI": st.column_config.LinkColumn(
            "Link",
            help="Click to view paper",
            display_text="View Paper"
        ),
        "Cites": st.column_config.NumberColumn(
            "Cites",
            format="%d"
        )
    }
)

# Footer
st.markdown("""<div class="footer">© University of Oxford 2026 - All Rights Reserved. | <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a></div>""", unsafe_allow_html=True)
