import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime, timedelta

# --- CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🎓", layout="wide", initial_sidebar_state="expanded")
pio.templates.default = "plotly_dark"

# --- CUSTOM CSS ---
# We keep only the CSS that enhances elements (gradients, metric colors) without breaking Streamlit's native dark mode.
st.markdown("""
    <style>
        .main-header { 
            font-size: 2.8rem; 
            font-weight: 800; 
            background: linear-gradient(90deg, #D4AF37, #FFFFFF); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent; 
            margin-bottom: 0rem;
        }
        .sub-header { 
            color: #A0AEC0; 
            font-size: 1.1rem;
            padding-bottom: 1.5rem; 
            margin-bottom: 1.5rem; 
        }
        div[data-testid="stMetricValue"] { 
            color: #D4AF37 !important; 
        }
        .align-bottom {
            margin-top: 27px;
        }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data():
    try:
        df = pd.read_csv("data/lcds_publications.csv")
        # Ensure cols
        for c in['Date', 'Year', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI', 'Countries']:
            if c not in df.columns: df[c] = 0 if c in ['Citations','Year'] else ""
            
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(0).astype(int)
        df['Citations'] = pd.to_numeric(df['Citations'], errors='coerce').fillna(0)
        return df
    except: 
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🎓 Filters")
    st.divider()
    
    if df.empty:
        st.warning("Data loading... please wait.")
        st.stop()

    period = st.radio("Time Range",["All Time (2019+)", "Last 2 Years", "Last Year", "Last Month", "Last Week"])
    
    # Simple footer in sidebar
    st.markdown("<br><br><br><br>", unsafe_allow_html=True)
    st.caption("LCDS Impact Tracker v1.0")

now = datetime.now()
if "Week" in period: start = now - timedelta(days=7)
elif "Month" in period: start = now - timedelta(days=30)
elif "Year" in period and "2" not in period: start = now - timedelta(days=365)
elif "2 Years" in period: start = now - timedelta(days=730)
else: start = pd.to_datetime("2019-09-01")

df_filt = df[df['Date'] >= start].copy()

# --- MAIN HEADER ---
st.markdown('<div class="main-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Tracking research impact, preprints, and global collaborations.</div>', unsafe_allow_html=True)

# --- KPI METRICS CARD ---
# Wrapping metrics in a border container makes them look like a modern dashboard panel
with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📚 Publications", len(df_filt))
    c2.metric("🎯 Total Citations", int(df_filt['Citations'].sum()))
    c3.metric("⏳ Preprints", len(df_filt[df_filt['Type'].str.contains("Preprint", case=False, na=False)]))
    c4.metric("👥 Active Researchers", df_filt['LCDS Author'].nunique())

st.write("") # Small spacer

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📄 Publications List", "📊 Impact Analytics", "🌍 Global Map"])

# TAB 1: LIST
with tab1:
    # Top action bar for Tab 1
    action_col1, action_col2, action_col3 = st.columns([4, 2, 2])
    
    with action_col1:
        search = st.text_input("🔍 Search", placeholder="Search by Title, Author...").lower()
    with action_col2:
        sort = st.selectbox("Sort By",["Newest", "Citations", "Author"])
    with action_col3:
        st.markdown('<div class="align-bottom"></div>', unsafe_allow_html=True)
        csv_data = df_filt.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download CSV", csv_data, "lcds_data.csv", "text/csv", use_container_width=True)
    
    # Process view
    view = df_filt.copy()
    if search:
        view = view[view['Title'].str.lower().str.contains(search, na=False) | view['LCDS Author'].str.lower().str.contains(search, na=False)]
    
    if sort == "Newest": view = view.sort_values("Date", ascending=False)
    elif sort == "Citations": view = view.sort_values("Citations", ascending=False)
    elif sort == "Author": view = view.sort_values("LCDS Author")

    st.dataframe(
        view[['Date', 'Citations', 'LCDS Author', 'Title', 'Journal', 'DOI']], 
        hide_index=True, 
        use_container_width=True, 
        height=500,
        column_config={"DOI": st.column_config.LinkColumn("Link")}
    )

# TAB 2: ANALYTICS
with tab2:
    st.write("") # Spacer
    c1, c2 = st.columns(2, gap="large")
    
    # Custom color scale to match the #D4AF37 Gold theme
    gold_scale =["#2b2b2b", "#8b7324", "#D4AF37"] 

    with c1:
        st.subheader("🏆 Top Researchers")
        st.caption("Ranked by total citations in the selected period.")
        if not df_filt.empty:
            auth = df_filt.groupby('LCDS Author')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
            fig = px.bar(auth, x='Citations', y='LCDS Author', orientation='h', color='Citations', color_continuous_scale=gold_scale)
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=20, b=0))
            fig.update_coloraxes(showscale=False) # Hide color bar for cleaner UI
            st.plotly_chart(fig, use_container_width=True)
            
    with c2:
        st.subheader("📰 Top Journals")
        st.caption("Ranked by total citations (excluding Preprints).")
        if not df_filt.empty:
            jour = df_filt[~df_filt['Journal'].isin(['Preprint','Unknown'])].groupby('Journal')['Citations'].sum().sort_values(ascending=False).head(10).reset_index()
            fig = px.bar(jour, x='Citations', y='Journal', orientation='h', color='Citations', color_continuous_scale=gold_scale)
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=20, b=0))
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, use_container_width=True)

# TAB 3: MAP
with tab3:
    st.write("")
    st.subheader("🌍 Global Impact Map")
    st.caption("Geographic distribution of citations based on collaborator locations.")
    
    with st.container(border=True):
        if not df_filt.empty and 'Countries' in df_filt.columns:
            if df_filt['Countries'].astype(str).str.len().sum() > 5:
                df_ex = df_filt.assign(Country=df_filt['Countries'].astype(str).str.split(',')).explode('Country')
                df_ex['Country'] = df_ex['Country'].str.strip()
                df_ex = df_ex[df_ex['Country'].str.len() == 2]
                
                if not df_ex.empty:
                    stats = df_ex.groupby('Country').agg({'Citations': 'sum', 'DOI': 'count'}).reset_index()
                    coords = {'US': [37, -95], 'GB': [55, -3], 'CN': [35, 104], 'DE': [51, 10], 'FR': [46, 2], 'IT':[41, 12], 'CA': [56, -106], 'AU':[-25, 133], 'NL': [52, 5]}
                    
                    stats['lat'] = stats['Country'].map(lambda x: coords.get(x, [0,0])[0])
                    stats['lon'] = stats['Country'].map(lambda x: coords.get(x,[0,0])[1])
                    stats = stats[stats['lat'] != 0] 
                    
                    fig = px.scatter_geo(
                        stats, lat="lat", lon="lon", size="Citations", hover_name="Country", 
                        size_max=45, projection="natural earth", color="Citations", 
                        color_continuous_scale=["#8b7324", "#D4AF37", "#ffffff"]
                    )
                    fig.update_geos(showcountries=True, countrycolor="#333", showcoastlines=True, coastlinecolor="#333", landcolor="#1e1e1e", showocean=False, bgcolor="rgba(0,0,0,0)")
                    fig.update_layout(margin={"r":0,"t":10,"l":0,"b":10}, paper_bgcolor="rgba(0,0,0,0)", geo_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No valid country codes found yet.")
            else:
                st.warning("⚠️ Country data is still populating. The scraper is fetching it row-by-row. Refresh later.")
