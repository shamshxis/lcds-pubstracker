import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="LCDS Impact Tracker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. DARK MODE & SCROLLABLE CSS ---
st.markdown("""
    <style>
        /* Import Google Font */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Roboto', sans-serif;
        }
        
        /* Headers - Adaptive Color */
        .main-header {
            font-family: 'Georgia', serif;
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--text-color); /* Adapts to Dark/Light */
            margin-bottom: 0px;
        }
        
        .sub-header {
            font-size: 1.1rem;
            color: #888;
            border-bottom: 1px solid #444;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }
        
        /* Metric Cards */
        div[data-testid="stMetricValue"] {
            font-size: 1.8rem;
            font-weight: 500;
        }
        
        /* SCROLLABLE TABLE CONTAINER */
        .table-container {
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        /* Table Styling */
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th {
            position: sticky;
            top: 0;
            background-color: #002147; /* Oxford Blue Header */
            color: white;
            padding: 10px;
            text-align: left;
            z-index: 1;
        }
        td {
            padding: 8px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        /* Links */
        a { color: #4da6ff; text-decoration: none; }
        a:hover { text-decoration: underline; }

        /* Footer */
        .footer {
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #444;
            text-align: center;
            color: #888;
            font-size: 0.85rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. LOAD DATA (Resilient) ---
@st.cache_data(ttl=3600)
def load_data():
    csv_url = "data/lcds_publications.csv"
    try:
        df = pd.read_csv(csv_url)
        
        # --- SELF-HEALING: Missing Column Fix ---
        # If columns are missing (because enrichment failed), create defaults
        required_cols = ['Date', 'Year', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI', 'Field', 'Countries']
        for col in required_cols:
            if col not in df.columns:
                if col == 'Citations': df[col] = 0
                elif col == 'Year': df[col] = datetime.now().year
                else: df[col] = "Pending" if col == 'Field' else ""

        # Conversions
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(0).astype(int)
        df['Citations'] = pd.to_numeric(df['Citations'], errors='coerce').fillna(0)
        
        return df
    except Exception:
        return pd.DataFrame()

df = load_data()

# --- 4. SIDEBAR ---
st.sidebar.title("Research Filters")

if df.empty:
    st.warning("⚠️ Data loading... check back shortly.")
    st.stop()

# Time Filter
time_options = ["All Time (2019+)", "Last 2 Years", "Last Year", "Last Month", "Last Week"]
period = st.sidebar.radio("Select Time Range", time_options, index=0)

now = datetime.now()
if "Week" in period: start_date = now - timedelta(days=7)
elif "Month" in period: start_date = now - timedelta(days=30)
elif "Year" in period and "2" not in period: start_date = now - timedelta(days=365)
elif "2 Years" in period: start_date = now - timedelta(days=730)
else: start_date = pd.to_datetime("2019-09-01")

# Apply
df_filtered = df[df['Date'] >= start_date].copy()

# --- 5. MAIN LAYOUT ---
st.markdown('<div class="main-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Tracking research impact, preprints, and global collaborations.</div>', unsafe_allow_html=True)

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("📚 Publications", len(df_filtered))
c2.metric("💬 Total Citations", int(df_filtered['Citations'].sum()))
c3.metric("📝 Preprints", len(df_filtered[df_filtered['Type']=="Preprint"]))
c4.metric("👥 Active Researchers", df_filtered['LCDS Author'].nunique())

st.divider()

# --- 6. TABS ---
tab1, tab2, tab3 = st.tabs(["📄 Publications List", "📊 Analytics & Impact", "🌍 Global Reach"])

# === TAB 1: LIST & DOWNLOAD ===
with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Recent Publications")
    with col2:
        # DOWNLOAD BUTTON
        csv_data = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"lcds_data_{datetime.now().strftime('%Y-%m-%d')}.csv",
            mime="text/csv"
        )
    
    # SCROLLABLE TABLE
    if not df_filtered.empty:
        show_df = df_filtered[['Date', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI']].copy()
        show_df['Date'] = show_df['Date'].dt.strftime('%Y-%m-%d')
        show_df['DOI'] = show_df['DOI'].apply(lambda x: f'<a href="{x}" target="_blank">View</a>')
        
        # Render inside the scrollable container div
        html_table = show_df.to_html(escape=False, index=False, classes="dataframe")
        st.markdown(f'<div class="table-container">{html_table}</div>', unsafe_allow_html=True)
    else:
        st.info("No publications found for this period.")

# === TAB 2: ANALYTICS ===
with tab2:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Citations per Year")
        if not df_filtered.empty:
            yearly_counts = df_filtered.groupby('Year')['Citations'].sum().reset_index()
            fig_bar = px.bar(yearly_counts, x='Year', y='Citations', color_discrete_sequence=['#002147'])
            st.plotly_chart(fig_bar, use_container_width=True)
            
    with col2:
        st.subheader("Research Themes")
        # SMART LOGIC: If 'Field' is generic or missing, use 'Journal' instead
        if not df_filtered.empty:
            # Check if fields are mostly "Pending" or "Multidisciplinary"
            unique_fields = df_filtered['Field'].unique()
            if len(unique_fields) < 3 and "Pending" in unique_fields:
                # Fallback to Journal Name
                plot_col = 'Journal'
                title = "By Journal (Field data pending)"
            else:
                plot_col = 'Field'
                title = "By Research Field"

            counts = df_filtered[plot_col].value_counts().head(10).reset_index()
            counts.columns = ['Label', 'Count']
            
            fig_pie = px.pie(counts, values='Count', names='Label', hole=0.4, 
                             color_discrete_sequence=px.colors.qualitative.Prism, title=title)
            st.plotly_chart(fig_pie, use_container_width=True)

# === TAB 3: MAP ===
with tab3:
    st.subheader("Global Collaboration Map")
    if not df_filtered.empty and 'Countries' in df_filtered.columns:
        # Clean country data
        all_c = df_filtered['Countries'].astype(str).str.split(',').explode().str.strip()
        all_c = all_c[all_c != ''].dropna()
        
        if not all_c.empty:
            cnt_counts = all_c.value_counts().reset_index()
            cnt_counts.columns = ['ISO', 'Papers']
            fig_map = px.choropleth(cnt_counts, locations="ISO", color="Papers", hover_name="ISO", 
                                    color_continuous_scale="Blues")
            fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", geo_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.info("Global data is currently being enriched. Check back after the next daily update.")
    else:
        st.info("No country data available.")

# --- 7. FOOTER ---
st.markdown("""
    <div class="footer">
        © Leverhulme Centre for Demographic Science - University of Oxford
    </div>
""", unsafe_allow_html=True)
