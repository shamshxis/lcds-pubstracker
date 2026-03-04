import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
import os
from datetime import datetime, timedelta

# --- 1. PAGE CONFIG ---
st.set_page_config(
    page_title="LCDS Impact Tracker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Force Plotly Dark Theme
pio.templates.default = "plotly_dark"

# --- 2. PROFESSIONAL CSS STYLING ---
st.markdown("""
    <style>
        /* MAIN BACKGROUND */
        .stApp {
            background-color: #0E1117;
            color: #E0E0E0;
        }
        
        /* SIDEBAR */
        [data-testid="stSidebar"] {
            background-color: #161b24;
            border-right: 1px solid #333;
        }

        /* HEADERS (Gold Gradient) */
        h1, h2, h3 {
            font-family: 'Helvetica Neue', sans-serif;
            font-weight: 700;
        }
        .gold-header {
            background: linear-gradient(90deg, #D4AF37 0%, #F5F5F5 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 0px;
        }
        .sub-text {
            color: #A0AEC0;
            font-size: 1.1rem;
            margin-bottom: 2rem;
            border-bottom: 1px solid #333;
            padding-bottom: 15px;
        }

        /* METRIC CARDS (Glassmorphism) */
        [data-testid="stMetric"] {
            background-color: #1A1C24;
            border: 1px solid #333;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            transition: transform 0.2s;
        }
        [data-testid="stMetric"]:hover {
            transform: translateY(-5px);
            border-color: #D4AF37;
        }
        div[data-testid="stMetricValue"] {
            color: #D4AF37 !important; /* Gold */
            font-size: 2.2rem !important;
            font-weight: 700;
        }
        div[data-testid="stMetricLabel"] {
            color: #A0AEC0 !important;
            font-size: 1rem;
        }

        /* CUSTOM TABS */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            border-bottom: 1px solid #333;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            background-color: transparent;
            border: 1px solid #333;
            border-bottom: none;
            border-radius: 5px 5px 0 0;
            color: #A0AEC0;
            font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
            background-color: #1A1C24 !important;
            color: #D4AF37 !important;
            border-top: 2px solid #D4AF37 !important;
        }

        /* BUTTONS */
        .stButton button {
            background-color: #1A1C24;
            color: #D4AF37;
            border: 1px solid #333;
            border-radius: 8px;
            font-weight: 600;
            transition: 0.3s;
        }
        .stButton button:hover {
            border-color: #D4AF37;
            color: #FFFFFF;
            background-color: #333;
        }

        /* DATAFRAME */
        [data-testid="stDataFrame"] {
            border: 1px solid #333;
            background-color: #1A1C24;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. ROBUST DATA LOADING ---
@st.cache_data(ttl=3600)
def load_data():
    file_path = "data/lcds_publications.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()
    
    try:
        # CRITICAL FIX: Skip bad lines that cause the "Expected 9 fields" error
        df = pd.read_csv(file_path, on_bad_lines='skip', engine='python')
        
        # Normalize Column Names (Fixes mismatches)
        df.columns = [c.strip() for c in df.columns]
        rename_map = {
            'author': 'LCDS Author', 'doi': 'DOI', 'citations': 'Citations',
            'year': 'Year', 'date': 'Date', 'title': 'Title',
            'journal': 'Journal', 'type': 'Type', 'countries': 'Countries',
            'source': 'Journal'
        }
        df.rename(columns=lambda x: rename_map.get(x.lower(), x), inplace=True)
        
        # Ensure Critical Columns Exist
        req_cols = ['Date', 'Year', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI', 'Countries']
        for c in req_cols:
            if c not in df.columns:
                if c == 'Citations': df[c] = 0
                elif c == 'Year': df[c] = datetime.now().year
                else: df[c] = "Unknown" if c != 'Countries' else ""
        
        # Type Conversion
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(0).astype(int)
        df['Citations'] = pd.to_numeric(df['Citations'], errors='coerce').fillna(0)
        
        return df.dropna(subset=['Date']) # Remove rows with bad dates
        
    except Exception as e:
        # Fail gracefully
        return pd.DataFrame()

# Reload Button Logic
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/University_of_Oxford.svg/1200px-University_of_Oxford.svg.png", width=140)
    if st.button("🔄 Force Reload Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

df = load_data()

# --- 4. SIDEBAR FILTERS ---
with st.sidebar:
    st.markdown("### 🔍 **Filters**")
    if df.empty:
        st.error("📉 Data file is empty or corrupted.")
        st.stop()
        
    period = st.radio("Time Period", ["All Time (2019+)", "Last 2 Years", "Last Year", "Last Month"], index=0)
    
    # Date Logic
    now = datetime.now()
    if "Month" in period: start = now - timedelta(days=30)
    elif "Year" in period and "2" not in period: start = now - timedelta(days=365)
    elif "2 Years" in period: start = now - timedelta(days=730)
    else: start = pd.to_datetime("2019-09-01")
    
    df_filt = df[df['Date'] >= start].copy()
    
    st.markdown("---")
    st.caption(f"Showing **{len(df_filt)}** records")

# --- 5. MAIN DASHBOARD ---
st.markdown('<div class="gold-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">Tracking research output, citation impact, and global collaborations.</div>', unsafe_allow_html=True)

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Publications", f"{len(df_filt):,}")
c2.metric("Total Citations", f"{int(df_filt['Citations'].sum()):,}")
c3.metric("Preprints", f"{len(df_filt[df_filt['Type'].str.contains('Preprint', case=False, na=False)]):,}")
c4.metric("Active Researchers", f"{df_filt['LCDS Author'].nunique()}")

st.markdown("<br>", unsafe_allow_html=True)

# Tabs
tab1, tab2, tab3 = st.tabs(["📄 **Database**", "📊 **Analytics**", "🌍 **Global Map**"])

# === TAB 1: DATA ===
with tab1:
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1: search = st.text_input("Search Database", placeholder="Title, Author, or Journal...").lower()
    with col2: sort = st.selectbox("Sort By", ["Newest First", "Most Cited", "Author (A-Z)"])
    
    view = df_filt.copy()
    if search:
        view = view[view['Title'].str.lower().str.contains(search, na=False) | view['LCDS Author'].str.lower().str.contains(search, na=False)]
    
    if "Newest" in sort: view = view.sort_values("Date", ascending=False)
    elif "Cited" in sort: view = view.sort_values("Citations", ascending=False)
    elif "Author" in sort: view = view.sort_values("LCDS Author")
    
    with col3:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        st.download_button("📥 Download CSV", view.to_csv(index=False).encode('utf-8'), "lcds_data.csv", "text/csv", use_container_width=True)
    
    st.dataframe(
        view[['Date', 'Citations', 'LCDS Author', 'Title', 'Journal', 'DOI']],
        hide_index=True, use_container_width=True, height=600,
        column_config={"DOI": st.column_config.LinkColumn("Link"), "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD")}
    )

# === TAB 2: ANALYTICS ===
with tab2:
    if not df_filt.empty:
        c1, c2 = st.columns(2)
        
        # Top Authors
        with c1:
            st.markdown("### 🏆 Top Researchers (Impact)")
            if df_filt['Citations'].sum() > 0:
                auth = df_filt.groupby('LCDS Author')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
                fig = px.bar(auth, x='Citations', y='LCDS Author', orientation='h', text_auto=True, color='Citations', color_continuous_scale='Plasma')
                fig.update_layout(yaxis={'categoryorder':'total ascending', 'title': None}, xaxis={'title': None}, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#E0E0E0'), coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No citations yet.")

        # Top Journals
        with c2:
            st.markdown("### 📰 Top Journals")
            jour = df_filt[~df_filt['Journal'].isin(['Preprint','Unknown',''])].groupby('Journal')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
            if not jour.empty:
                fig = px.bar(jour, x='Citations', y='Journal', orientation='h', text_auto=True, color='Citations', color_continuous_scale='Viridis')
                fig.update_layout(yaxis={'categoryorder':'total ascending', 'title': None}, xaxis={'title': None}, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#E0E0E0'), coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No journal data.")

# === TAB 3: MAP ===
with tab3:
    st.markdown("### 🌍 Global Impact")
    if not df_filt.empty and 'Countries' in df_filt.columns:
        if df_filt['Countries'].str.len().sum() > 5:
            df_ex = df_filt.assign(Country=df_filt['Countries'].astype(str).str.split(',')).explode('Country')
            df_ex = df_ex[df_ex['Country'].str.strip().str.len() == 2]
            
            if not df_ex.empty:
                stats = df_ex.groupby('Country').agg({'Citations': 'sum'}).reset_index()
                coords = {'US': [37, -95], 'GB': [55, -3], 'CN': [35, 104], 'DE': [51, 10], 'FR': [46, 2], 'IT': [41, 12], 'CA': [56, -106], 'AU': [-25, 133], 'NL': [52, 5], 'ES': [40, -3], 'SE': [60, 18], 'CH': [46, 8], 'IN': [20, 78], 'BR': [-14, -51]}
                stats['lat'] = stats['Country'].map(lambda x: coords.get(x, [0,0])[0])
                stats['lon'] = stats['Country'].map(lambda x: coords.get(x, [0,0])[1])
                stats = stats[stats['lat'] != 0]
                
                fig = px.scatter_geo(stats, lat="lat", lon="lon", size="Citations", hover_name="Country", size_max=50, projection="natural earth", color="Citations", color_continuous_scale="Plasma")
                fig.update_geos(showcountries=True, countrycolor="#444", landcolor="#1A1C24", showocean=False, bgcolor="rgba(0,0,0,0)")
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", geo_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No valid country data found.")
        else: st.warning("⚠️ Country data enriching in background.")
    else: st.info("Country data missing.")
