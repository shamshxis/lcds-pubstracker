import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="LCDS Impact Tracker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ACADEMIC CSS (Clean, Professional) ---
st.markdown("""
    <style>
        /* Main Font */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');
        html, body, [class*="css"] { font-family: 'Roboto', sans-serif; }
        
        /* Header */
        .main-header {
            font-family: 'Georgia', serif;
            color: #002147; /* Oxford Blue */
            font-size: 2.5rem;
            font-weight: bold;
            margin-bottom: 0px;
        }
        .sub-header {
            color: #555;
            font-size: 1.1rem;
            margin-bottom: 25px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 10px;
        }
        
        /* Metrics Cards */
        div[data-testid="stMetricValue"] {
            font-size: 1.8rem;
            color: #002147;
        }
        
        /* Sidebar */
        section[data-testid="stSidebar"] {
            background-color: #f8f9fa;
        }
        
        /* Table Links */
        a { color: #0066cc; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("data/lcds_publications.csv")
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Year'] = df['Date'].dt.year.fillna(0).astype(int)
        df['Citations'] = pd.to_numeric(df['Citations'], errors='coerce').fillna(0)
        
        # Ensure 'Countries' column exists for map
        if 'Countries' not in df.columns: df['Countries'] = ''
        
        return df
    except: return pd.DataFrame()

df = load_data()

# --- SIDEBAR CONTROLS ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/University_of_Oxford.svg/1200px-University_of_Oxford.svg.png", width=100)
st.sidebar.title("Filters")

if df.empty:
    st.warning("Data initializing... Please wait for the nightly scrape.")
    st.stop()

# 1. Time Filter
period = st.sidebar.radio(
    "Time Range", 
    ["All Time (Sep 2019+)", "Last 2 Years", "Last Year", "Last Month", "Last Week"],
    index=0
)

now = datetime.now()
if "Week" in period: start_date = now - timedelta(days=7)
elif "Month" in period: start_date = now - timedelta(days=30)
elif "Year" in period and "2" not in period: start_date = now - timedelta(days=365)
elif "2 Years" in period: start_date = now - timedelta(days=730)
else: start_date = pd.to_datetime("2019-09-01")

# 2. Type Filter
pub_types = st.sidebar.multiselect("Publication Type", df['Type'].unique(), default=df['Type'].unique())

# 3. Apply Filters
df_filtered = df[(df['Date'] >= start_date) & (df['Type'].isin(pub_types))].copy()

# --- HEADER ---
st.markdown('<div class="main-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Tracking research impact, preprints, and global collaborations.</div>', unsafe_allow_html=True)

# --- METRICS ROW ---
m1, m2, m3, m4 = st.columns(4)
m1.metric("📚 Publications", len(df_filtered))
m2.metric("💬 Total Citations", int(df_filtered['Citations'].sum()))
m3.metric("📝 Preprints", len(df_filtered[df_filtered['Type']=="Preprint"]))
m4.metric("🌍 Countries Reached", df_filtered['Countries'].str.split(',').explode().nunique())

st.markdown("---")

# --- TABS INTERFACE ---
tab1, tab2, tab3 = st.tabs(["📄 Publications List", "📊 Analytics & Impact", "🌍 Global Reach"])

# === TAB 1: LIST ===
with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Recent Research")
    with col2:
        # DOWNLOAD BUTTON 1
        csv = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download List (CSV)", csv, "lcds_publications.csv", "text/csv")
    
    # Display Table (Clean)
    show_df = df_filtered[['Date', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI']].copy()
    show_df['Date'] = show_df['Date'].dt.date
    show_df['DOI'] = show_df['DOI'].apply(lambda x: f'<a href="{x}" target="_blank">View Paper</a>')
    
    st.write(show_df.to_html(escape=False, index=False), unsafe_allow_html=True)

# === TAB 2: ANALYTICS ===
with tab2:
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("Citations by Year")
        yr_counts = df_filtered.groupby('Year')['Citations'].sum().reset_index()
        fig_bar = px.bar(yr_counts, x='Year', y='Citations', color_discrete_sequence=['#002147'])
        st.plotly_chart(fig_bar, use_container_width=True)
        
    with c2:
        st.subheader("Research Fields")
        field_counts = df_filtered['Field'].value_counts().head(10).reset_index()
        field_counts.columns = ['Field', 'Count']
        fig_pie = px.pie(field_counts, values='Count', names='Field', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
        st.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("Citation Impact Distribution")
    fig_hist = px.histogram(df_filtered, x="Citations", nbins=30, color_discrete_sequence=['#C49102'], 
                           title="How many citations do our papers typically get?")
    st.plotly_chart(fig_hist, use_container_width=True)

# === TAB 3: WORLD MAP (Creative) ===
with tab3:
    st.subheader("🌍 Global Collaboration Map")
    st.markdown("Mapping the countries of institutions we collaborate with.")
    
    # Process Country Data
    all_countries = df_filtered['Countries'].str.split(',').explode().str.strip()
    all_countries = all_countries[all_countries != ''] # Remove empty
    country_counts = all_countries.value_counts().reset_index()
    country_counts.columns = ['ISO_Alpha_2', 'Papers']
    
    # Plot Choropleth
    if not country_counts.empty:
        fig_map = px.choropleth(
            country_counts,
            locations="ISO_Alpha_2",
            color="Papers",
            hover_name="ISO_Alpha_2",
            color_continuous_scale="Blues",
            projection="natural earth"
        )
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.info("No country data available for current selection.")

# --- FOOTER ---
st.markdown("""
    <br><br>
    <div style="text-align: center; color: #666; font-size: 0.8rem;">
        © 2026 Leverhulme Centre for Demographic Science | Data sourced from Crossref & OpenAlex
    </div>
""", unsafe_allow_html=True)
