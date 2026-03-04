import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime, timedelta

# --- 1. CONFIG & THEME SETUP ---
st.set_page_config(
    page_title="LCDS Impact Tracker", 
    page_icon="🎓", 
    layout="wide", 
    initial_sidebar_state="expanded"
)
pio.templates.default = "plotly_dark"

# --- 2. PROFESSIONAL DARK MODE CSS ---
st.markdown("""
    <style>
        /* MAIN BACKGROUND & TEXT */
        [data-testid="stAppViewContainer"] {
            background-color: #0E1117;
            color: #E0E0E0;
        }
        [data-testid="stSidebar"] {
            background-color: #12141C;
            border-right: 1px solid #2B2F3B;
        }
        
        /* TYPOGRAPHY */
        h1, h2, h3, p, div { font-family: 'Inter', sans-serif; }
        
        /* GRADIENT HEADERS */
        .main-header { 
            font-size: 3rem; 
            font-weight: 800; 
            background: linear-gradient(90deg, #FFD700 0%, #FFFFFF 100%); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent; 
            margin-bottom: 0.5rem;
            text-shadow: 0px 0px 20px rgba(255, 215, 0, 0.2);
        }
        .sub-header { 
            color: #A0AEC0; 
            font-size: 1.1rem;
            font-weight: 400;
            padding-bottom: 1.5rem; 
            border-bottom: 1px solid #2B2F3B;
            margin-bottom: 2rem; 
        }
        
        /* METRIC CARDS (Glassmorphism) */
        div[data-testid="stMetric"] {
            background-color: #1A1C24;
            border: 1px solid #2B2F3B;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            transition: transform 0.2s;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            border-color: #FFD700;
        }
        div[data-testid="stMetricValue"] { 
            color: #FFD700 !important; /* Gold */
            font-size: 2.2rem !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMetricLabel"] {
            color: #A0AEC0 !important;
            font-size: 1rem !important;
        }

        /* TABS STYLING */
        button[data-baseweb="tab"] {
            background-color: transparent !important;
            color: #A0AEC0 !important;
            font-weight: 600;
            border-radius: 5px;
            margin: 0 5px;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background-color: #1A1C24 !important;
            color: #FFD700 !important;
            border: 1px solid #FFD700 !important;
        }

        /* DATAFRAME & UI ELEMENTS */
        [data-testid="stDataFrame"] {
            border: 1px solid #2B2F3B;
            border-radius: 10px;
            background-color: #1A1C24;
        }
        
        /* INPUT FIELDS */
        .stTextInput > div > div > input {
            background-color: #1A1C24;
            color: white;
            border: 1px solid #2B2F3B;
        }
        .stSelectbox > div > div > div {
            background-color: #1A1C24;
            color: white;
        }

        /* FOOTER */
        .footer {
            text-align: center;
            color: #555;
            font-size: 0.85rem;
            margin-top: 80px;
            padding-top: 20px;
            border-top: 1px solid #2B2F3B;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data():
    try:
        df = pd.read_csv("data/lcds_publications.csv")
        cols = ['Date', 'Year', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI', 'Countries']
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
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/University_of_Oxford.svg/1200px-University_of_Oxford.svg.png", width=140)
    st.markdown("## 📊 **Filters**")
    
    if df.empty:
        st.error("Data missing. Please run scraper.")
        st.stop()

    # Styled Radio Button
    period = st.radio(
        "📅 **Time Period**", 
        ["All Time (2019+)", "Last 2 Years", "Last Year", "Last Month", "Last Week"]
    )
    
    st.markdown("---")
    st.info("Tracking publications, preprints, and global citation impact.")

# Logic
now = datetime.now()
if "Week" in period: start = now - timedelta(days=7)
elif "Month" in period: start = now - timedelta(days=30)
elif "Year" in period and "2" not in period: start = now - timedelta(days=365)
elif "2 Years" in period: start = now - timedelta(days=730)
else: start = pd.to_datetime("2019-09-01")

df_filt = df[df['Date'] >= start].copy()

# --- 5. DASHBOARD HEADER ---
st.markdown('<div class="main-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Real-time tracking of research output, citation impact, and global reach.</div>', unsafe_allow_html=True)

# METRICS ROW
c1, c2, c3, c4 = st.columns(4)
c1.metric("📚 Publications", f"{len(df_filt):,}")
c2.metric("💬 Total Citations", f"{int(df_filt['Citations'].sum()):,}")
c3.metric("📝 Preprints", f"{len(df_filt[df_filt['Type'].str.contains('Preprint', case=False, na=False)]):,}")
c4.metric("👥 Active Researchers", f"{df_filt['LCDS Author'].nunique()}")

st.markdown("<br>", unsafe_allow_html=True)

# --- 6. TABS ---
tab1, tab2, tab3 = st.tabs(["📄 **Publications Database**", "📊 **Impact Analytics**", "🌍 **Global Map**"])

# === TAB 1: LIST ===
with tab1:
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1: search = st.text_input("🔍 Search Database", placeholder="Search by Title, Author, or Journal...").lower()
    with col2: sort = st.selectbox("Sort Data", ["Newest First", "Oldest First", "Most Cited", "Author (A-Z)"])
    
    view = df_filt.copy()
    if search:
        view = view[view['Title'].str.lower().str.contains(search, na=False) | view['LCDS Author'].str.lower().str.contains(search, na=False)]
    
    if "Newest" in sort: view = view.sort_values("Date", ascending=False)
    elif "Oldest" in sort: view = view.sort_values("Date", ascending=True)
    elif "Cited" in sort: view = view.sort_values("Citations", ascending=False)
    elif "Author" in sort: view = view.sort_values("LCDS Author")

    with col3:
        st.markdown("<div class='align-bottom'></div>", unsafe_allow_html=True)
        st.download_button("📥 Download CSV", view.to_csv(index=False).encode('utf-8'), "lcds_data.csv", "text/csv", use_container_width=True)

    st.dataframe(
        view[['Date', 'Citations', 'LCDS Author', 'Title', 'Journal', 'DOI']],
        hide_index=True,
        use_container_width=True,
        height=600,
        column_config={
            "DOI": st.column_config.LinkColumn("Link", display_text="Open Paper"),
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "Citations": st.column_config.NumberColumn("Cites", format="%d"),
            "Title": st.column_config.TextColumn("Title", width="large"),
        }
    )

# === TAB 2: ANALYTICS ===
with tab2:
    if not df_filt.empty:
        c1, c2 = st.columns(2)
        
        # CHART 1: TOP AUTHORS
        with c1:
            st.markdown("### 🏆 Top Researchers (by Citations)")
            auth = df_filt.groupby('LCDS Author')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
            
            # Plasma Gradient for Bars (Purple -> Orange -> Yellow)
            fig = px.bar(
                auth, x='Citations', y='LCDS Author', orientation='h', 
                color='Citations', 
                color_continuous_scale='Plasma', 
                text_auto=True
            )
            fig.update_layout(
                yaxis={'categoryorder':'total ascending', 'title': None}, 
                xaxis={'title': None},
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#E0E0E0"),
                coloraxis_showscale=False
            )
            st.plotly_chart(fig, use_container_width=True)
            
        # CHART 2: TOP JOURNALS
        with c2:
            st.markdown("### 📰 High-Impact Journals")
            jour = df_filt[~df_filt['Journal'].isin(['Preprint','Unknown'])].groupby('Journal')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
            
            # Viridis Gradient for Journals
            fig = px.bar(
                jour, x='Citations', y='Journal', orientation='h', 
                color='Citations', 
                color_continuous_scale='Viridis',
                text_auto=True
            )
            fig.update_layout(
                yaxis={'categoryorder':'total ascending', 'title': None}, 
                xaxis={'title': None},
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#E0E0E0"),
                coloraxis_showscale=False
            )
            st.plotly_chart(fig, use_container_width=True)

        # CHART 3: CITATION TIMELINE
        st.markdown("### 📈 Citation Velocity")
        time_stats = df_filt.groupby('Year')['Citations'].sum().reset_index()
        fig_time = px.area(
            time_stats, x='Year', y='Citations', 
            markers=True,
            color_discrete_sequence=['#FFD700'] # Pure Gold Line
        )
        fig_time.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#E0E0E0"),
            xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="#333")
        )
        st.plotly_chart(fig_time, use_container_width=True)

# === TAB 3: MAP ===
with tab3:
    st.markdown("### 🌍 Global Impact Map")
    st.caption("Locations of institutions collaborating with or citing LCDS research.")
    
    if not df_filt.empty and 'Countries' in df_filt.columns:
        if df_filt['Countries'].astype(str).str.len().sum() > 5:
            df_ex = df_filt.assign(Country=df_filt['Countries'].astype(str).str.split(',')).explode('Country')
            df_ex['Country'] = df_ex['Country'].str.strip()
            df_ex = df_ex[df_ex['Country'].str.len() == 2]
            
            if not df_ex.empty:
                stats = df_ex.groupby('Country').agg({'Citations': 'sum', 'DOI': 'count'}).reset_index()
                
                # Manual Coords for Stability
                coords = {'US': [37, -95], 'GB': [55, -3], 'CN': [35, 104], 'DE': [51, 10], 'FR': [46, 2], 'IT': [41, 12], 'CA': [56, -106], 'AU': [-25, 133], 'NL': [52, 5], 'ES': [40, -3], 'SE': [60, 18], 'CH': [46, 8], 'IN': [20, 78], 'BR': [-14, -51], 'ZA': [-30, 22], 'SG': [1.3, 103.8], 'JP': [36, 138], 'KR': [35, 127], 'RU': [61, 105], 'BE': [50, 4], 'DK': [56, 9], 'IE': [53, -7], 'AT': [47, 14], 'PL': [51, 19], 'CZ': [49, 15], 'PT': [39, -8], 'GR': [39, 21], 'TR': [39, 35], 'IL': [31, 34], 'NZ': [-40, 174], 'MX': [23, -102], 'AR': [-38, -63], 'CL': [-35, -71], 'CO': [4, -74], 'EG': [26, 30], 'NG': [9, 8], 'KE': [0, 37], 'SA': [23, 45], 'AE': [23, 53], 'IR': [32, 53], 'PK': [30, 69], 'BD': [23, 90], 'TH': [15, 100], 'VN': [14, 108], 'ID': [-0, 113], 'MY': [4, 101]}
                
                stats['lat'] = stats['Country'].map(lambda x: coords.get(x, [0,0])[0])
                stats['lon'] = stats['Country'].map(lambda x: coords.get(x, [0,0])[1])
                stats = stats[stats['lat'] != 0]
                
                # Dark Matter Map Style
                fig = px.scatter_geo(
                    stats, lat="lat", lon="lon", size="Citations", hover_name="Country", 
                    size_max=50, projection="natural earth", 
                    color="Citations", 
                    color_continuous_scale="Plasma" # Pops against dark map
                )
                fig.update_geos(
                    showcountries=True, countrycolor="#444", 
                    showcoastlines=True, coastlinecolor="#444", 
                    landcolor="#1E1E1E", showocean=False, 
                    bgcolor="rgba(0,0,0,0)"
                )
                fig.update_layout(
                    margin={"r":0,"t":10,"l":0,"b":10}, 
                    paper_bgcolor="rgba(0,0,0,0)", geo_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white")
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No valid country data found in selection.")
        else:
            st.warning("⚠️ Country data is populating in background. Check back later.")

# --- FOOTER ---
st.markdown("<div class='footer'>© Leverhulme Centre for Demographic Science - University of Oxford</div>", unsafe_allow_html=True)
