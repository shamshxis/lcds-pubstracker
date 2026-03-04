import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime, timedelta

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="LCDS Impact Tracker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Force Plotly to use a dark theme that matches our CSS
pio.templates.default = "plotly_dark"

# --- 2. SAFE DARK MODE CSS ---
# This CSS purely recolors existing elements. It does not inject new HTML structures.
st.markdown("""
    <style>
        /* 1. Main Backgrounds */
        .stApp {
            background-color: #0E1117;
            color: #FAFAFA;
        }
        [data-testid="stSidebar"] {
            background-color: #161B22;
            border-right: 1px solid #30363D;
        }

        /* 2. Typography - Gold & Silver */
        h1, h2, h3 {
            font-family: 'Helvetica Neue', sans-serif;
            color: #E6EDF3 !important;
        }
        h1 {
            background: linear-gradient(90deg, #D4AF37, #E6EDF3);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
        }
        
        /* 3. Metrics Cards - Clean Dark Look */
        [data-testid="stMetric"] {
            background-color: #21262D;
            border: 1px solid #30363D;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        [data-testid="stMetricLabel"] {
            color: #8B949E !important;
        }
        [data-testid="stMetricValue"] {
            color: #D4AF37 !important; /* Oxford Gold */
            font-size: 24px !important;
        }

        /* 4. Tables & Dataframes */
        [data-testid="stDataFrame"] {
            border: 1px solid #30363D;
        }
        
        /* 5. Sidebar Elements */
        .stRadio > label { color: #E6EDF3 !important; }
        
        /* 6. Footer Styling (Simple Text) */
        .footer-text {
            text-align: center;
            color: #484F58;
            font-size: 12px;
            margin-top: 50px;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. LOAD DATA (Robust) ---
@st.cache_data(ttl=3600)
def load_data():
    try:
        df = pd.read_csv("data/lcds_publications.csv")
        # Ensure all columns exist to prevent crashes
        required_cols = ['Date', 'Year', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI', 'Countries']
        for c in required_cols:
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

# --- 4. SIDEBAR FILTERS ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/University_of_Oxford.svg/1200px-University_of_Oxford.svg.png", width=120)
    st.markdown("### 🔍 **Filters**")
    
    if df.empty:
        st.error("Data is initializing... Please run the scraper.")
        st.stop()

    period = st.radio(
        "Time Period", 
        ["All Time (2019+)", "Last 2 Years", "Last Year", "Last Month", "Last Week"]
    )
    
    st.divider()
    st.info("Tracking publications, preprints, and global reach.")

# Filter Logic
now = datetime.now()
if "Week" in period: start = now - timedelta(days=7)
elif "Month" in period: start = now - timedelta(days=30)
elif "Year" in period and "2" not in period: start = now - timedelta(days=365)
elif "2 Years" in period: start = now - timedelta(days=730)
else: start = pd.to_datetime("2019-09-01")

df_filt = df[df['Date'] >= start].copy()

# --- 5. MAIN DASHBOARD ---
st.title("Leverhulme Centre for Demographic Science")
st.markdown("##### Real-time tracking of research output, citation impact, and global collaborations.")
st.markdown("---")

# METRICS
c1, c2, c3, c4 = st.columns(4)
c1.metric("Publications", f"{len(df_filt):,}")
c2.metric("Total Citations", f"{int(df_filt['Citations'].sum()):,}")
c3.metric("Preprints", f"{len(df_filt[df_filt['Type'].str.contains('Preprint', case=False, na=False)]):,}")
c4.metric("Active Researchers", f"{df_filt['LCDS Author'].nunique()}")

st.markdown("<br>", unsafe_allow_html=True)

# --- 6. TABS ---
tab1, tab2, tab3 = st.tabs(["📄 Publications Database", "📊 Impact Analytics", "🌍 Global Map"])

# === TAB 1: DATA TABLE ===
with tab1:
    c_search, c_sort, c_down = st.columns([3, 1, 1])
    
    with c_search:
        search = st.text_input("Search", placeholder="Title, Author, or Journal...").lower()
    with c_sort:
        sort = st.selectbox("Sort", ["Newest First", "Most Cited", "Author (A-Z)"])
    
    # Filter & Sort
    view = df_filt.copy()
    if search:
        view = view[view['Title'].str.lower().str.contains(search, na=False) | view['LCDS Author'].str.lower().str.contains(search, na=False)]
    
    if "Newest" in sort: view = view.sort_values("Date", ascending=False)
    elif "Cited" in sort: view = view.sort_values("Citations", ascending=False)
    elif "Author" in sort: view = view.sort_values("LCDS Author")

    with c_down:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True) # Spacer
        st.download_button("📥 Download CSV", view.to_csv(index=False).encode('utf-8'), "lcds_data.csv", "text/csv", use_container_width=True)

    st.dataframe(
        view[['Date', 'Citations', 'LCDS Author', 'Title', 'Journal', 'DOI']],
        hide_index=True,
        use_container_width=True,
        height=600,
        column_config={
            "DOI": st.column_config.LinkColumn("Link", display_text="Open"),
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "Title": st.column_config.TextColumn("Title", width="large")
        }
    )

# === TAB 2: ANALYTICS ===
with tab2:
    if not df_filt.empty:
        col1, col2 = st.columns(2)
        
        # CHART 1: TOP AUTHORS
        with col1:
            st.subheader("🏆 Top Researchers (Impact)")
            auth_stats = df_filt.groupby('LCDS Author')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
            
            fig_auth = px.bar(
                auth_stats, x='Citations', y='LCDS Author', orientation='h', 
                color='Citations', color_continuous_scale='Plasma', text_auto=True
            )
            fig_auth.update_layout(yaxis={'categoryorder':'total ascending', 'title': None}, xaxis={'title': None}, coloraxis_showscale=False)
            st.plotly_chart(fig_auth, use_container_width=True)

        # CHART 2: TOP JOURNALS
        with col2:
            st.subheader("📰 Top Journals (Impact)")
            jour_stats = df_filt[~df_filt['Journal'].isin(['Preprint','Unknown'])].groupby('Journal')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
            
            fig_jour = px.bar(
                jour_stats, x='Citations', y='Journal', orientation='h', 
                color='Citations', color_continuous_scale='Viridis', text_auto=True
            )
            fig_jour.update_layout(yaxis={'categoryorder':'total ascending', 'title': None}, xaxis={'title': None}, coloraxis_showscale=False)
            st.plotly_chart(fig_jour, use_container_width=True)

        # CHART 3: TIMELINE
        st.subheader("📈 Citation Growth")
        time_stats = df_filt.groupby('Year')['Citations'].sum().reset_index()
        fig_time = px.area(
            time_stats, x='Year', y='Citations', 
            markers=True, color_discrete_sequence=['#D4AF37']
        )
        fig_time.update_layout(xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#30363D'))
        st.plotly_chart(fig_time, use_container_width=True)

# === TAB 3: MAP ===
with tab3:
    st.subheader("🌍 Global Collaboration & Impact")
    
    if not df_filt.empty and 'Countries' in df_filt.columns:
        # Check for valid country data
        if df_filt['Countries'].astype(str).str.len().sum() > 5:
            df_ex = df_filt.assign(Country=df_filt['Countries'].astype(str).str.split(',')).explode('Country')
            df_ex['Country'] = df_ex['Country'].str.strip()
            # Valid ISO code check
            df_ex = df_ex[df_ex['Country'].str.len() == 2]
            
            if not df_ex.empty:
                stats = df_ex.groupby('Country').agg({'Citations': 'sum', 'DOI': 'count'}).reset_index()
                
                # Manual Coords for Stability
                coords = {'US': [37, -95], 'GB': [55, -3], 'CN': [35, 104], 'DE': [51, 10], 'FR': [46, 2], 'IT': [41, 12], 'CA': [56, -106], 'AU': [-25, 133], 'NL': [52, 5], 'ES': [40, -3], 'SE': [60, 18], 'CH': [46, 8], 'IN': [20, 78], 'BR': [-14, -51], 'ZA': [-30, 22], 'SG': [1.3, 103.8], 'JP': [36, 138], 'KR': [35, 127], 'RU': [61, 105], 'BE': [50, 4], 'DK': [56, 9], 'IE': [53, -7], 'AT': [47, 14], 'PL': [51, 19], 'CZ': [49, 15], 'PT': [39, -8], 'GR': [39, 21], 'TR': [39, 35], 'IL': [31, 34], 'NZ': [-40, 174], 'MX': [23, -102], 'AR': [-38, -63], 'CL': [-35, -71], 'CO': [4, -74], 'EG': [26, 30], 'NG': [9, 8], 'KE': [0, 37], 'SA': [23, 45], 'AE': [23, 53], 'IR': [32, 53], 'PK': [30, 69], 'BD': [23, 90], 'TH': [15, 100], 'VN': [14, 108], 'ID': [-0, 113], 'MY': [4, 101]}
                
                stats['lat'] = stats['Country'].map(lambda x: coords.get(x, [0,0])[0])
                stats['lon'] = stats['Country'].map(lambda x: coords.get(x, [0,0])[1])
                stats = stats[stats['lat'] != 0]
                
                # Dark Map Styling
                fig = px.scatter_geo(
                    stats, lat="lat", lon="lon", size="Citations", hover_name="Country", 
                    size_max=50, projection="natural earth", 
                    color="Citations", color_continuous_scale="Plasma"
                )
                fig.update_geos(
                    showcountries=True, countrycolor="#444", 
                    showcoastlines=True, coastlinecolor="#444", 
                    landcolor="#0D1117", showocean=False, 
                    bgcolor="rgba(0,0,0,0)"
                )
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", geo_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No valid country data found in current selection.")
        else:
            st.warning("⚠️ Country data is populating. Check back later.")

# --- FOOTER ---
st.markdown("<p class='footer-text'>© Leverhulme Centre for Demographic Science - University of Oxford</p>", unsafe_allow_html=True)
