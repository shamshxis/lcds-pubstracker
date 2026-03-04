import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime, timedelta

# --- 1. PAGE CONFIG & DARK MODE FORCE ---
st.set_page_config(
    page_title="LCDS Impact Tracker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Set Plotly to Dark Theme by default
pio.templates.default = "plotly_dark"

# --- 2. CLASSY DARK CSS ---
st.markdown("""
    <style>
        /* Force Dark Backgrounds */
        [data-testid="stAppViewContainer"] {
            background-color: #0E1117;
            color: #FAFAFA;
        }
        [data-testid="stSidebar"] {
            background-color: #161b24;
            border-right: 1px solid #333;
        }
        
        /* Headers - Gold Accent */
        h1, h2, h3 {
            color: #e0e0e0 !important;
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-weight: 600;
        }
        .main-header {
            font-size: 2.8rem;
            font-weight: 700;
            background: linear-gradient(90deg, #D4AF37 0%, #FAFAFA 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0px;
        }
        .sub-header {
            color: #a0a0a0;
            font-size: 1.1rem;
            border-bottom: 1px solid #444;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }

        /* Metric Cards styling */
        div[data-testid="stMetricValue"] {
            color: #D4AF37 !important; /* Gold Text */
            font-size: 2rem !important;
        }
        div[data-testid="stMetricLabel"] {
            color: #a0a0a0 !important;
        }
        [data-testid="stMetric"] {
            background-color: #1f242e;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #333;
        }

        /* Tables */
        [data-testid="stDataFrame"] {
            border: 1px solid #444;
        }
        
        /* Footer */
        .footer {
            margin-top: 60px;
            padding-top: 20px;
            border-top: 1px solid #333;
            text-align: center;
            color: #666;
            font-size: 0.8rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. LOAD DATA (Robust) ---
@st.cache_data(ttl=3600)
def load_data():
    try:
        df = pd.read_csv("data/lcds_publications.csv")
        # Ensure all columns exist
        cols = ['Date', 'Year', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI', 'Field', 'Countries']
        for c in cols:
            if c not in df.columns:
                if c == 'Citations': df[c] = 0
                elif c == 'Year': df[c] = datetime.now().year
                else: df[c] = "Unknown" if c != 'Countries' else ""
        
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(0).astype(int)
        df['Citations'] = pd.to_numeric(df['Citations'], errors='coerce').fillna(0)
        return df
    except: return pd.DataFrame()

df = load_data()

# --- 4. SIDEBAR ---
st.sidebar.markdown("### 🎓 Filters")

if df.empty:
    st.warning("Data loading... please wait.")
    st.stop()

# Filter Controls
period = st.sidebar.radio("Time Range", ["All Time (2019+)", "Last 2 Years", "Last Year", "Last Month", "Last Week"])
now = datetime.now()
if "Week" in period: start = now - timedelta(days=7)
elif "Month" in period: start = now - timedelta(days=30)
elif "Year" in period and "2" not in period: start = now - timedelta(days=365)
elif "2 Years" in period: start = now - timedelta(days=730)
else: start = pd.to_datetime("2019-09-01")

df_filt = df[df['Date'] >= start].copy()

# --- 5. MAIN DASHBOARD ---
st.markdown('<div class="main-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Tracking research impact, preprints, and global collaborations.</div>', unsafe_allow_html=True)

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Publications", len(df_filt))
c2.metric("Total Citations", int(df_filt['Citations'].sum()))
c3.metric("Preprints", len(df_filt[df_filt['Type']=="Preprint"]))
c4.metric("Active Researchers", df_filt['LCDS Author'].nunique())

st.divider()

# --- 6. TABS ---
tab1, tab2, tab3 = st.tabs(["📄 Publications List", "📊 Analytics", "🌍 Global Reach"])

# TAB 1: LIST
with tab1:
    col1, col2 = st.columns([3, 1])
    with col1: search = st.text_input("🔍 Search Database", placeholder="Title, Author, or Journal...").lower()
    with col2: sort = st.selectbox("Sort By", ["Newest First", "Oldest First", "Most Cited", "Title A-Z"])

    # Search Logic
    if search:
        df_view = df_filt[
            df_filt['Title'].str.lower().str.contains(search, na=False) |
            df_filt['LCDS Author'].str.lower().str.contains(search, na=False)
        ].copy()
    else: df_view = df_filt.copy()

    # Sort Logic
    if "Newest" in sort: df_view = df_view.sort_values("Date", ascending=False)
    elif "Oldest" in sort: df_view = df_view.sort_values("Date", ascending=True)
    elif "Cited" in sort: df_view = df_view.sort_values("Citations", ascending=False)
    elif "Title" in sort: df_view = df_view.sort_values("Title", ascending=True)

    # Clean Download
    st.caption(f"Showing {len(df_view)} publications.")
    st.download_button("📥 Download This View (CSV)", df_view.to_csv(index=False).encode('utf-8'), "lcds_data.csv", "text/csv")

    st.dataframe(
        df_view,
        column_order=("Date", "Citations", "LCDS Author", "Title", "Journal", "Type", "DOI"),
        column_config={
            "DOI": st.column_config.LinkColumn("Link", display_text="Open"),
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "Title": st.column_config.TextColumn("Title", width="large"),
        },
        hide_index=True, use_container_width=True, height=600
    )

# TAB 2: ANALYTICS (Plotly Dark Theme)
with tab2:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Citations per Year")
        if not df_filt.empty:
            stats = df_filt.groupby('Year')['Citations'].sum().reset_index()
            # Gold color for bars
            fig = px.bar(stats, x='Year', y='Citations', color_discrete_sequence=['#D4AF37'])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
            
    with c2:
        st.subheader("Research Distribution")
        if not df_filt.empty:
            # Smart Fallback
            f_col = 'Journal' if "Pending" in df_filt['Field'].unique() else 'Field'
            counts = df_filt[f_col].value_counts().head(10).reset_index()
            counts.columns = ['Label', 'Count']
            
            fig = px.pie(counts, values='Count', names='Label', hole=0.4, 
                         color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)

# TAB 3: GLOBAL MAP
with tab3:
    st.subheader("Global Citation Impact")
    st.markdown("Pins represent locations of citing/collaborating institutions.")
    
    if not df_filt.empty and 'Countries' in df_filt.columns:
        try:
            df_ex = df_filt.assign(Country=df_filt['Countries'].astype(str).str.split(',')).explode('Country')
            df_ex['Country'] = df_ex['Country'].str.strip()
            df_ex = df_ex[df_ex['Country'].str.len() == 2]

            if not df_ex.empty:
                stats = df_ex.groupby('Country').agg({'Citations': 'sum', 'DOI': 'count'}).reset_index()
                
                # Extended Coordinates
                coords = {'US': [37.09, -95.71], 'GB': [55.37, -3.43], 'CN': [35.86, 104.19], 'DE': [51.16, 10.45], 'FR': [46.22, 2.21], 'IT': [41.87, 12.56], 'CA': [56.13, -106.34], 'AU': [-25.27, 133.77], 'JP': [36.20, 138.25], 'NL': [52.13, 5.29], 'ES': [40.46, -3.74], 'SE': [60.12, 18.64], 'CH': [46.81, 8.22], 'BR': [-14.23, -51.92], 'IN': [20.59, 78.96], 'ZA': [-30.55, 22.93], 'RU': [61.52, 105.31], 'KR': [35.90, 127.76], 'SG': [1.35, 103.81], 'BE': [50.50, 4.46], 'DK': [56.26, 9.50], 'NO': [60.47, 8.46], 'FI': [61.92, 25.74], 'IE': [53.14, -7.69], 'AT': [47.51, 14.55], 'PL': [51.91, 19.14], 'CZ': [49.81, 15.47], 'PT': [39.39, -8.22], 'GR': [39.07, 21.82], 'TR': [38.96, 35.24], 'IL': [31.04, 34.85], 'NZ': [-40.90, 174.88], 'MX': [23.63, -102.55], 'AR': [-38.41, -63.61], 'CL': [-35.67, -71.54], 'CO': [4.57, -74.29], 'EG': [26.82, 30.80], 'NG': [9.08, 8.67], 'KE': [-0.02, 37.90], 'SA': [23.88, 45.07], 'AE': [23.42, 53.84], 'IR': [32.42, 53.68], 'PK': [30.37, 69.34], 'BD': [23.68, 90.35], 'TH': [15.87, 100.99], 'VN': [14.05, 108.27], 'ID': [-0.78, 113.92], 'MY': [4.21, 101.97], 'UA': [48.37, 31.16], 'HU': [47.16, 19.50], 'RO': [45.94, 24.96], 'RS': [44.01, 21.00]}
                
                stats['lat'] = stats['Country'].map(lambda x: coords.get(x, [None, None])[0])
                stats['lon'] = stats['Country'].map(lambda x: coords.get(x, [None, None])[1])
                plot_data = stats.dropna(subset=['lat'])
                
                if not plot_data.empty:
                    fig = px.scatter_geo(plot_data, lat="lat", lon="lon", size="Citations", color="DOI", hover_name="Country", size_max=45, projection="natural earth", color_continuous_scale="Viridis")
                    fig.update_geos(showcountries=True, countrycolor="#555", showcoastlines=True, landcolor="#262730", showocean=False)
                    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", geo_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)
                else: st.info("Mapping incomplete.")
            else: st.info("No country data.")
        except: st.error("Map error.")

st.markdown("""<div class="footer">© Leverhulme Centre for Demographic Science - University of Oxford</div>""", unsafe_allow_html=True)
