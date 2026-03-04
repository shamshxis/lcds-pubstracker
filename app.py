import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="LCDS Research Impact",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. ACADEMIC CSS STYLING ---
st.markdown("""
    <style>
        /* Import Google Font 'Roboto' for a clean, modern academic look */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Roboto', sans-serif;
        }
        
        /* Main Headers - Oxford Blue */
        .main-header {
            font-family: 'Georgia', serif;
            color: #002147; 
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0px;
        }
        
        /* Subheader - Grey & Professional */
        .sub-header {
            color: #555;
            font-size: 1.1rem;
            border-bottom: 1px solid #ddd;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }
        
        /* Metric Cards Styling */
        div[data-testid="stMetricValue"] {
            font-size: 1.8rem;
            color: #002147;
            font-weight: 500;
        }
        
        /* Footer Styling */
        .footer {
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #666;
            font-size: 0.85rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data():
    csv_url = "data/lcds_publications.csv"
    try:
        df = pd.read_csv(csv_url)
        
        # Self-Healing Columns
        required_cols = ['Date', 'Year', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI', 'Field', 'Countries']
        for col in required_cols:
            if col not in df.columns:
                if col == 'Citations': df[col] = 0
                elif col == 'Year': df[col] = datetime.now().year
                else: df[col] = "Unknown" if col != 'Countries' else ""
        
        # Conversions
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(0).astype(int)
        df['Citations'] = pd.to_numeric(df['Citations'], errors='coerce').fillna(0)
        
        return df
    except Exception:
        return pd.DataFrame()

df = load_data()

# --- 4. SIDEBAR ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/University_of_Oxford.svg/1200px-University_of_Oxford.svg.png", width=120)
st.sidebar.title("Filters")

if df.empty:
    st.warning("⚠️ Data loading... check back shortly.")
    st.stop()

# Time Filter
time_options = ["All Time (2019+)", "Last 2 Years", "Last Year", "Last Month", "Last Week"]
period = st.sidebar.radio("Time Range", time_options, index=0)

now = datetime.now()
if "Week" in period: start_date = now - timedelta(days=7)
elif "Month" in period: start_date = now - timedelta(days=30)
elif "Year" in period and "2" not in period: start_date = now - timedelta(days=365)
elif "2 Years" in period: start_date = now - timedelta(days=730)
else: start_date = pd.to_datetime("2019-09-01")

# Apply Time Filter
df_filtered = df[df['Date'] >= start_date].copy()

# --- 5. MAIN DASHBOARD ---
st.markdown('<div class="main-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Tracking research impact, preprints, and global collaborations.</div>', unsafe_allow_html=True)

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("📚 Publications", len(df_filtered))
c2.metric("💬 Total Citations", int(df_filtered['Citations'].sum()))
c3.metric("📝 Preprints", len(df_filtered[df_filtered['Type']=="Preprint"]))
c4.metric("👥 Active Researchers", df_filtered['LCDS Author'].nunique())

st.divider()

# --- 6. TABS INTERFACE ---
tab1, tab2, tab3 = st.tabs(["📄 Publications List", "📊 Analytics", "🌍 Global Reach"])

# === TAB 1: INTERACTIVE TABLE ===
with tab1:
    col1, col2 = st.columns([3, 1])
    
    with col1:
        search_query = st.text_input("🔍 Search", placeholder="Title, Author, or Journal...").lower()
    
    with col2:
        # Sort option using native selectbox
        sort_option = st.selectbox("Sort By", ["Newest First", "Oldest First", "Most Cited", "Title A-Z"])

    # --- APPLY LOCAL FILTERS ---
    # 1. Search
    if search_query:
        df_view = df_filtered[
            df_filtered['Title'].str.lower().str.contains(search_query) |
            df_filtered['LCDS Author'].str.lower().str.contains(search_query) |
            df_filtered['Journal'].str.lower().str.contains(search_query)
        ].copy()
    else:
        df_view = df_filtered.copy()

    # 2. Sort
    if "Newest" in sort_option:
        df_view = df_view.sort_values(by="Date", ascending=False)
    elif "Oldest" in sort_option:
        df_view = df_view.sort_values(by="Date", ascending=True)
    elif "Cited" in sort_option:
        df_view = df_view.sort_values(by="Citations", ascending=False)
    elif "Title" in sort_option:
        df_view = df_view.sort_values(by="Title", ascending=True)

    # --- DOWNLOAD BUTTON (Current View) ---
    st.caption(f"Showing {len(df_view)} publications based on current filters.")
    
    csv_data = df_view.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download This List (CSV)",
        data=csv_data,
        file_name=f"lcds_data_export_{datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv"
    )

    # --- INTERACTIVE DATAFRAME ---
    st.dataframe(
        df_view,
        column_order=("Date", "Citations", "LCDS Author", "Title", "Journal", "Type", "DOI"),
        column_config={
            "DOI": st.column_config.LinkColumn("Link", display_text="Open Paper"),
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "Citations": st.column_config.NumberColumn("Cites"),
            "Title": st.column_config.TextColumn("Paper Title", width="large"),
        },
        hide_index=True,
        use_container_width=True,
        height=600
    )

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
        # Fallback logic for pie chart
        if not df_filtered.empty:
            unique_fields = df_filtered['Field'].unique()
            # If fields are missing/generic, switch to Journal
            if len(unique_fields) < 3 and "Pending" in unique_fields:
                plot_col, title = 'Journal', "By Journal"
            else:
                plot_col, title = 'Field', "By Research Field"

            st.subheader(title)
            counts = df_filtered[plot_col].value_counts().head(10).reset_index()
            counts.columns = ['Label', 'Count']
            fig_pie = px.pie(counts, values='Count', names='Label', hole=0.4, 
                             color_discrete_sequence=px.colors.qualitative.Prism)
            st.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("Citation Impact Distribution")
    if not df_filtered.empty:
        fig_hist = px.histogram(df_filtered, x="Citations", nbins=20, 
                               title="Distribution of Citations", color_discrete_sequence=['#C49102'])
        st.plotly_chart(fig_hist, use_container_width=True)

# === TAB 3: GLOBAL MAP (BUBBLE PINS) ===
with tab3:
    st.subheader("Global Citation Impact")
    st.markdown("Pins represent countries where our co-authored papers have been cited or published. **Size = Total Citations**.")

    if not df_filtered.empty and 'Countries' in df_filtered.columns:
        # Explode country list
        df_exploded = df_filtered.assign(Country=df_filtered['Countries'].str.split(',')).explode('Country')
        df_exploded['Country'] = df_exploded['Country'].str.strip()
        df_exploded = df_exploded[df_exploded['Country'] != '']
        df_exploded = df_exploded.dropna(subset=['Country'])

        if not df_exploded.empty:
            # Aggregate Data
            country_stats = df_exploded.groupby('Country').agg({
                'Citations': 'sum',
                'DOI': 'count'
            }).reset_index().rename(columns={'DOI': 'Paper_Count'})

            # Coordinate Map (Major Research Hubs)
            country_coords = {
                'US': [37.09, -95.71], 'GB': [55.37, -3.43], 'CN': [35.86, 104.19],
                'DE': [51.16, 10.45], 'FR': [46.22, 2.21], 'IT': [41.87, 12.56],
                'CA': [56.13, -106.34], 'AU': [-25.27, 133.77], 'JP': [36.20, 138.25],
                'NL': [52.13, 5.29], 'ES': [40.46, -3.74], 'SE': [60.12, 18.64],
                'CH': [46.81, 8.22], 'BR': [-14.23, -51.92], 'IN': [20.59, 78.96],
                'ZA': [-30.55, 22.93], 'RU': [61.52, 105.31], 'KR': [35.90, 127.76],
                'SG': [1.35, 103.81], 'BE': [50.50, 4.46], 'DK': [56.26, 9.50],
                'NO': [60.47, 8.46], 'FI': [61.92, 25.74], 'IE': [53.14, -7.69],
                'AT': [47.51, 14.55], 'PL': [51.91, 19.14], 'CZ': [49.81, 15.47]
            }

            # Map Lat/Lon
            country_stats['lat'] = country_stats['Country'].map(lambda x: country_coords.get(x, [None, None])[0])
            country_stats['lon'] = country_stats['Country'].map(lambda x: country_coords.get(x, [None, None])[1])
            plot_data = country_stats.dropna(subset=['lat', 'lon'])

            if not plot_data.empty:
                # Plot Bubble Map
                fig_map = px.scatter_geo(
                    plot_data,
                    lat="lat",
                    lon="lon",
                    size="Citations",
                    color="Paper_Count",
                    hover_name="Country",
                    size_max=40,
                    projection="natural earth",
                    color_continuous_scale="Viridis",
                )
                fig_map.update_geos(showcountries=True, countrycolor="#d1d1d1", showcoastlines=True)
                fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
                st.plotly_chart(fig_map, use_container_width=True)
            else:
                st.warning("Coordinate mapping incomplete for current country list.")
        else:
            st.info("No country data available for current selection.")
    else:
        st.info("Country data missing.")

# --- 7. FOOTER ---
st.markdown("""
    <div class="footer">
        © Leverhulme Centre for Demographic Science - University of Oxford
    </div>
""", unsafe_allow_html=True)
