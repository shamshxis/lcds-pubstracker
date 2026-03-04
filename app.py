import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
import os
from datetime import datetime, timedelta

# 1. CONFIG
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🎓", layout="wide")
pio.templates.default = "plotly_dark"

# 2. CSS STYLING
st.markdown("""
    <style>
        .stApp { background-color: #0b0c10; color: #E0E0E0; }
        [data-testid="stSidebar"] { background-color: #1f2833; border-right: 1px solid #45a29e; }
        
        .gold-header {
            background: linear-gradient(90deg, #D4AF37 0%, #F5F5F5 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            font-size: 3rem; font-weight: 800;
        }
        
        div[data-testid="stMetric"] {
            background-color: #1a1d26; border: 1px solid #45a29e; border-radius: 10px;
            padding: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        div[data-testid="stMetricValue"] { color: #D4AF37 !important; }
        
        [data-testid="stDataFrame"] { border: 1px solid #333; background-color: #1a1d26; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [aria-selected="true"] { background-color: #D4AF37 !important; color: #000 !important; }
    </style>
""", unsafe_allow_html=True)

# 3. DATA LOADING
@st.cache_data(ttl=3600)
def load_data():
    file = "data/lcds_publications.csv"
    if not os.path.exists(file): return pd.DataFrame()
    
    try:
        # Load safely
        df = pd.read_csv(file, on_bad_lines='skip', engine='python')
        
        # Normalize columns
        rename = {'author':'LCDS Author', 'citations':'Citations', 'year':'Year', 'date':'Date', 'title':'Title', 'journal':'Journal', 'countries':'Countries'}
        df.rename(columns=lambda x: rename.get(x.lower(), x), inplace=True)
        
        # Fill missing
        for c in ['Date','Year','Citations','LCDS Author','Title','Journal','Countries']:
            if c not in df.columns: df[c] = 0 if c in ['Citations','Year'] else ""
            
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Citations'] = pd.to_numeric(df['Citations'], errors='coerce').fillna(0)
        return df.dropna(subset=['Date'])
    except: return pd.DataFrame()

df = load_data()

# 4. SIDEBAR
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/University_of_Oxford.svg/1200px-University_of_Oxford.svg.png", width=140)
    if st.button("🔄 Force Reload Data"): st.cache_data.clear(); st.rerun()
    
    if df.empty:
        st.warning("No data found. Please run the scraper.")
        st.stop()
        
    period = st.radio("Time Period", ["All Time (2019+)", "Last 2 Years", "Last Year", "Last Month", "Last Week"], index=0)
    
    now = datetime.now()
    if "Week" in period: start = now - timedelta(days=7)
    elif "Month" in period: start = now - timedelta(days=30)
    elif "Year" in period and "2" not in period: start = now - timedelta(days=365)
    elif "2 Years" in period: start = now - timedelta(days=730)
    else: start = pd.to_datetime("2019-09-01")
    
    df_filt = df[df['Date'] >= start].copy()
    st.markdown("---")
    st.caption(f"Showing **{len(df_filt)}** records")

# 5. DASHBOARD
st.markdown('<div class="gold-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown("Tracking research output, citation impact, and global collaborations.")
st.markdown("---")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Publications", f"{len(df_filt):,}")
c2.metric("Citations", f"{int(df_filt['Citations'].sum()):,}")
c3.metric("Journals", f"{df_filt['Journal'].nunique()}")
c4.metric("Researchers", f"{df_filt['LCDS Author'].nunique()}")

tab1, tab2, tab3 = st.tabs(["📄 Database", "📊 Analytics", "🌍 Global Map"])

# TAB 1
with tab1:
    col1, col2, col3 = st.columns([3, 1, 1])
    search = col1.text_input("Search", placeholder="Title, Author...").lower()
    sort = col2.selectbox("Sort", ["Newest", "Most Cited", "Author"])
    
    view = df_filt.copy()
    if search: view = view[view['Title'].str.lower().str.contains(search, na=False) | view['LCDS Author'].str.lower().str.contains(search, na=False)]
    
    if "Newest" in sort: view = view.sort_values("Date", ascending=False)
    elif "Cited" in sort: view = view.sort_values("Citations", ascending=False)
    else: view = view.sort_values("LCDS Author")
    
    col3.markdown("<br>", unsafe_allow_html=True)
    col3.download_button("📥 Download CSV", view.to_csv(index=False).encode('utf-8'), f"lcds_{period.replace(' ','_')}.csv", "text/csv")
    
    if view.empty: st.info("No publications found for this period.")
    else: st.dataframe(view[['Date','Citations','LCDS Author','Title','Journal']], use_container_width=True, hide_index=True)

# TAB 2
with tab2:
    if df_filt.empty: st.info("No data available.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Top Researchers")
            if df_filt['Citations'].sum() > 0:
                auth = df_filt.groupby('LCDS Author')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
                st.plotly_chart(px.bar(auth, x='Citations', y='LCDS Author', orientation='h', color='Citations', color_continuous_scale='Plasma'), use_container_width=True)
            else: st.info("No citations recorded.")
        with c2:
            st.subheader("Top Journals")
            valid = df_filt[~df_filt['Journal'].isin(['Preprint','Unknown',''])]
            if not valid.empty:
                jour = valid.groupby('Journal')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
                st.plotly_chart(px.bar(jour, x='Citations', y='Journal', orientation='h', color='Citations', color_continuous_scale='Viridis'), use_container_width=True)
            else: st.info("No journal data.")

# TAB 3
with tab3:
    st.subheader("Global Impact")
    if not df_filt.empty and 'Countries' in df_filt.columns:
        valid = df_filt[df_filt['Countries'].str.len() > 1].copy()
        if not valid.empty:
            map_df = valid.assign(Country=valid['Countries'].str.split(',')).explode('Country')
            map_df = map_df[map_df['Country'].str.len() == 2]
            stats = map_df.groupby('Country')['Citations'].sum().reset_index()
            
            st.plotly_chart(px.scatter_geo(stats, locations='Country', size='Citations', color='Citations', projection='natural earth', color_continuous_scale='Plasma'), use_container_width=True)
        else: st.info("No country data available.")
    else: st.info("Country data missing.")
