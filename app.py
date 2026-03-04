import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
import os
from datetime import datetime, timedelta

# --- 1. CONFIG ---
st.set_page_config(
    page_title="LCDS Impact Tracker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)
pio.templates.default = "plotly_dark"

# --- 2. CLASSY DARK CSS ---
st.markdown("""
    <style>
        /* General App */
        .stApp { background-color: #0b0c10; color: #c5c6c7; }
        [data-testid="stSidebar"] { background-color: #1f2833; border-right: 1px solid #45a29e; }
        
        /* Headers */
        .gold-header {
            background: linear-gradient(90deg, #D4AF37, #F2F2F2);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            font-size: 3rem; font-weight: 800; margin-bottom: 0px;
        }
        .sub-text { color: #66fcf1; font-size: 1.1rem; margin-bottom: 2rem; border-bottom: 1px solid #45a29e; padding-bottom: 1rem; }

        /* Metric Cards */
        div[data-testid="stMetric"] {
            background-color: #1a1d26; border: 1px solid #45a29e; border-radius: 10px; padding: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: 0.3s;
        }
        div[data-testid="stMetric"]:hover { border-color: #D4AF37; transform: translateY(-2px); }
        div[data-testid="stMetricValue"] { color: #D4AF37 !important; font-size: 2.2rem !important; font-weight: 700; }
        div[data-testid="stMetricLabel"] { color: #c5c6c7 !important; }

        /* UI Elements */
        [data-testid="stDataFrame"] { border: 1px solid #333; background-color: #1a1d26; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [data-baseweb="tab"] { height: 50px; background-color: #1f2833; border-radius: 5px; color: #c5c6c7; }
        .stTabs [aria-selected="true"] { background-color: #D4AF37 !important; color: #0b0c10 !important; font-weight: bold; }
        .stButton button { width: 100%; border-radius: 8px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 3. ROBUST DATA LOADING ---
@st.cache_data(ttl=3600)
def load_data():
    file_path = "data/lcds_publications.csv"
    if not os.path.exists(file_path): return pd.DataFrame()
    
    try:
        # Load with error skipping
        try:
            df = pd.read_csv(file_path, on_bad_lines='skip', engine='python')
        except:
            df = pd.read_csv(file_path, error_bad_lines=False, engine='python')

        # Auto-Rename Columns
        rename_map = {
            'author': 'LCDS Author', 'doi': 'DOI', 'citations': 'Citations',
            'year': 'Year', 'date': 'Date', 'title': 'Title',
            'journal': 'Journal', 'type': 'Type', 'countries': 'Countries'
        }
        df.rename(columns=lambda x: rename_map.get(x.lower(), x), inplace=True)
        
        # Ensure Critical Columns
        req_cols = ['Date', 'Year', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI', 'Countries']
        for c in req_cols:
            if c not in df.columns:
                if c == 'Citations': df[c] = 0
                elif c == 'Year': df[c] = datetime.now().year
                else: df[c] = "Unknown" if c != 'Countries' else ""
        
        # Clean Types
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(0).astype(int)
        df['Citations'] = pd.to_numeric(df['Citations'], errors='coerce').fillna(0)
        
        return df.dropna(subset=['Date'])
    except: return pd.DataFrame()

# Sidebar Refresh
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/University_of_Oxford.svg/1200px-University_of_Oxford.svg.png", width=140)
    if st.button("🔄 Force Reload Data", type="primary"):
        st.cache_data.clear()
        st.rerun()

df = load_data()

# --- 4. FILTERS ---
with st.sidebar:
    st.markdown("### 🔍 Filters")
    if df.empty:
        st.error("📉 CSV is empty. Please run scraper.")
        st.stop()
        
    # Time Filter
    period = st.radio(
        "Time Period", 
        ["All Time (2019+)", "Last 2 Years", "Last Year", "Last Month", "Last Week"], 
        index=0
    )
    
    # Date Logic
    now = datetime.now()
    if "Week" in period: start = now - timedelta(days=7)
    elif "Month" in period: start = now - timedelta(days=30)
    elif "Year" in period and "2" not in period: start = now - timedelta(days=365)
    elif "2 Years" in period: start = now - timedelta(days=730)
    else: start = pd.to_datetime("2019-09-01")
    
    df_filt = df[df['Date'] >= start].copy()
    
    st.markdown("---")
    st.caption(f"Loaded **{len(df)}** records.")

# --- 5. DASHBOARD ---
st.markdown('<div class="gold-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">Tracking research output, citation impact, and global collaborations.</div>', unsafe_allow_html=True)

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Publications", f"{len(df_filt):,}")
c2.metric("Total Citations", f"{int(df_filt['Citations'].sum()):,}")
c3.metric("Preprints", f"{len(df_filt[df_filt['Type'].str.contains('Preprint', case=False, na=False)]):,}")
c4.metric("Active Researchers", f"{df_filt['LCDS Author'].nunique()}")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📄 **Database**", "📊 **Impact Analytics**", "🌍 **Global Map**"])

# === TAB 1: DATABASE ===
with tab1:
    c_search, c_sort, c_dl = st.columns([3, 1, 1])
    
    # Inputs
    search = c_search.text_input("Search", placeholder="Title, Author, or Journal...").lower()
    sort = c_sort.selectbox("Sort", ["Newest First", "Most Cited", "Author A-Z"])
    
    # Filter Logic
    view = df_filt.copy()
    if search:
        view = view[view['Title'].str.lower().str.contains(search, na=False) | view['LCDS Author'].str.lower().str.contains(search, na=False)]
    
    if "Newest" in sort: view = view.sort_values("Date", ascending=False)
    elif "Cited" in sort: view = view.sort_values("Citations", ascending=False)
    elif "Author" in sort: view = view.sort_values("LCDS Author")
    
    # Download Button (Restored & Prominent)
    with c_dl:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True) # Spacer align
        if not view.empty:
            st.download_button(
                label="📥 Download View (CSV)",
                data=view.to_csv(index=False).encode('utf-8'),
                file_name=f"lcds_data_{period.replace(' ', '_').lower()}.csv",
                mime="text/csv",
                use_container_width=True
            )

    # Data Display
    if view.empty:
        st.info(f"📅 No publications found for **{period}** matching your search.")
    else:
        st.dataframe(
            view[['Date', 'Citations', 'LCDS Author', 'Title', 'Journal', 'DOI']], 
            hide_index=True, 
            use_container_width=True, 
            height=600, 
            column_config={"DOI": st.column_config.LinkColumn("Link"), "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD")}
        )

# === TAB 2: ANALYTICS ===
with tab2:
    if df_filt.empty:
        st.info("📊 No data available for analytics in this period.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🏆 Top Researchers (Impact)")
            if df_filt['Citations'].sum() > 0:
                top_auth = df_filt.groupby('LCDS Author')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
                fig = px.bar(top_auth, x='Citations', y='LCDS Author', orientation='h', text_auto=True, color='Citations', color_continuous_scale='Plasma')
                fig.update_layout(yaxis={'categoryorder':'total ascending', 'title': None}, xaxis={'title': None}, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#c5c6c7'), coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No citations recorded yet.")

        with c2:
            st.markdown("### 📰 Top Journals")
            valid_journals = df_filt[~df_filt['Journal'].isin(['Preprint','Unknown', ''])]
            if not valid_journals.empty:
                top_jour = valid_journals.groupby('Journal')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
                fig = px.bar(top_jour, x='Citations', y='Journal', orientation='h', text_auto=True, color='Citations', color_continuous_scale='Viridis')
                fig.update_layout(yaxis={'categoryorder':'total ascending', 'title': None}, xaxis={'title': None}, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#c5c6c7'), coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No journal data available.")
        
        st.markdown("### 📈 Citation Growth")
        timeline = df_filt.groupby('Year')['Citations'].sum().reset_index()
        if not timeline.empty:
            fig = px.area(timeline, x='Year', y='Citations', markers=True)
            fig.update_traces(line_color='#D4AF37', fill_color='rgba(212, 175, 55, 0.3)')
            fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#c5c6c7'), xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#333'))
            st.plotly_chart(fig, use_container_width=True)

# === TAB 3: MAP ===
with tab3:
    st.markdown("### 🌍 Global Impact Map")
    if df_filt.empty:
        st.info("No data to map.")
    elif 'Countries' in df_filt.columns:
        valid_map_data = df_filt[df_filt['Countries'].astype(str).str.len() > 1].copy()
        
        if not valid_map_data.empty:
            map_df = valid_map_data.assign(Country=valid_map_data['Countries'].astype(str).str.split(',')).explode('Country')
            map_df = map_df[map_df['Country'].str.strip().str.len() == 2]
            
            if not map_df.empty:
                map_stats = map_df.groupby('Country').agg({'Citations': 'sum'}).reset_index()
                coords = {'US': [37, -95], 'GB': [55, -3], 'CN': [35, 104], 'DE': [51, 10], 'FR': [46, 2], 'IT': [41, 12], 'CA': [56, -106], 'AU': [-25, 133], 'NL': [52, 5], 'ES': [40, -3], 'SE': [60, 18], 'CH': [46, 8], 'IN': [20, 78], 'BR': [-14, -51], 'ZA': [-30, 22], 'SG': [1.3, 103.8], 'JP': [36, 138], 'KR': [35, 127], 'RU': [61, 105], 'BE': [50, 4], 'DK': [56, 9], 'IE': [53, -7], 'AT': [47, 14], 'PL': [51, 19], 'CZ': [49, 15], 'PT': [39, -8], 'GR': [39, 21], 'TR': [39, 35], 'IL': [31, 34], 'NZ': [-40, 174], 'MX': [23, -102], 'AR': [-38, -63], 'CL': [-35, -71], 'CO': [4, -74], 'EG': [26, 30], 'NG': [9, 8], 'KE': [0, 37], 'SA': [23, 45], 'AE': [23, 53], 'IR': [32, 53], 'PK': [30, 69], 'BD': [23, 90], 'TH': [15, 100], 'VN': [14, 108], 'ID': [-0, 113], 'MY': [4, 101]}
                map_stats['lat'] = map_stats['Country'].map(lambda x: coords.get(x, [0,0])[0])
                map_stats['lon'] = map_stats['Country'].map(lambda x: coords.get(x, [0,0])[1])
                map_stats = map_stats[map_stats['lat'] != 0]
                
                fig = px.scatter_geo(map_stats, lat="lat", lon="lon", size="Citations", hover_name="Country", size_max=50, projection="natural earth", color="Citations", color_continuous_scale="Plasma")
                fig.update_geos(showcountries=True, countrycolor="#444", landcolor="#1A1C24", showocean=False, bgcolor="rgba(0,0,0,0)")
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", geo_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No valid country data found.")
        else: st.warning("⚠️ Country data is populating. Check back later.")
    else: st.info("Country data missing.")
