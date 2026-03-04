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

# --- 2. MINIMAL CSS (Safe Mode) ---
st.markdown("""
    <style>
        /* Only styling the footer to keep it subtle */
        .footer {
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #eee;
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
        
        # Ensure all columns exist
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
st.title("Leverhulme Centre for Demographic Science")
st.markdown("Tracking research impact, preprints, and global collaborations.")

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
        sort_option = st.selectbox("Sort By", ["Newest First", "Oldest First", "Most Cited", "Title A-Z"])

    # --- APPLY LOCAL FILTERS ---
    if search_query:
        df_view = df_filtered[
            df_filtered['Title'].str.lower().str.contains(search_query, na=False) |
            df_filtered['LCDS Author'].str.lower().str.contains(search_query, na=False) |
            df_filtered['Journal'].str.lower().str.contains(search_query, na=False)
        ].copy()
    else:
        df_view = df_filtered.copy()

    # Sort
    if "Newest" in sort_option: df_view = df_view.sort_values(by="Date", ascending=False)
    elif "Oldest" in sort_option: df_view = df_view.sort_values(by="Date", ascending=True)
    elif "Cited" in sort_option: df_view = df_view.sort_values(by="Citations", ascending=False)
    elif "Title" in sort_option: df_view = df_view.sort_values(by="Title", ascending=True)

    # Download
    st.caption(f"Showing {len(df_view)} publications.")
    csv_data = df_view.to_csv(index=False).encode('utf-8')
    st.download_button(label="📥 Download This List (CSV)", data=csv_data, file_name=f"lcds_export.csv", mime="text/csv")

    # Interactive Table
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
        # Pie Chart Logic
        if not df_filtered.empty:
            unique_fields = df_filtered['Field'].unique()
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

# === TAB 3: GLOBAL MAP (SAFE MODE) ===
with tab3:
    st.subheader("Global Citation Impact")
    st.markdown("Pins represent countries where our co-authored papers have been cited or published.")

    if not df_filtered.empty and 'Countries' in df_filtered.columns:
        # Explode & Clean
        try:
            df_exploded = df_filtered.assign(Country=df_filtered['Countries'].astype(str).str.split(',')).explode('Country')
            df_exploded['Country'] = df_exploded['Country'].str.strip()
            df_exploded = df_exploded[df_exploded['Country'].str.len() == 2] # Keep only valid ISO codes
            
            if not df_exploded.empty:
                country_stats = df_exploded.groupby('Country').agg({'Citations': 'sum', 'DOI': 'count'}).reset_index()
                
                # EXTENSIVE COORDINATE MAP (Covering most of the world)
                coords = {
                    'US': [37.09, -95.71], 'GB': [55.37, -3.43], 'CN': [35.86, 104.19], 'DE': [51.16, 10.45],
                    'FR': [46.22, 2.21], 'IT': [41.87, 12.56], 'CA': [56.13, -106.34], 'AU': [-25.27, 133.77],
                    'JP': [36.20, 138.25], 'NL': [52.13, 5.29], 'ES': [40.46, -3.74], 'SE': [60.12, 18.64],
                    'CH': [46.81, 8.22], 'BR': [-14.23, -51.92], 'IN': [20.59, 78.96], 'ZA': [-30.55, 22.93],
                    'RU': [61.52, 105.31], 'KR': [35.90, 127.76], 'SG': [1.35, 103.81], 'BE': [50.50, 4.46],
                    'DK': [56.26, 9.50], 'NO': [60.47, 8.46], 'FI': [61.92, 25.74], 'IE': [53.14, -7.69],
                    'AT': [47.51, 14.55], 'PL': [51.91, 19.14], 'CZ': [49.81, 15.47], 'PT': [39.39, -8.22],
                    'GR': [39.07, 21.82], 'TR': [38.96, 35.24], 'IL': [31.04, 34.85], 'NZ': [-40.90, 174.88],
                    'MX': [23.63, -102.55], 'AR': [-38.41, -63.61], 'CL': [-35.67, -71.54], 'CO': [4.57, -74.29],
                    'EG': [26.82, 30.80], 'NG': [9.08, 8.67], 'KE': [-0.02, 37.90], 'SA': [23.88, 45.07],
                    'AE': [23.42, 53.84], 'IR': [32.42, 53.68], 'PK': [30.37, 69.34], 'BD': [23.68, 90.35],
                    'TH': [15.87, 100.99], 'VN': [14.05, 108.27], 'ID': [-0.78, 113.92], 'MY': [4.21, 101.97]
                }

                country_stats['lat'] = country_stats['Country'].map(lambda x: coords.get(x, [None, None])[0])
                country_stats['lon'] = country_stats['Country'].map(lambda x: coords.get(x, [None, None])[1])
                plot_data = country_stats.dropna(subset=['lat', 'lon'])

                if not plot_data.empty:
                    fig_map = px.scatter_geo(
                        plot_data, lat="lat", lon="lon", size="Citations",
                        color="DOI", hover_name="Country", size_max=40,
                        projection="natural earth", color_continuous_scale="Viridis"
                    )
                    fig_map.update_geos(showcountries=True, countrycolor="#d1d1d1", showcoastlines=True)
                    fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
                    st.plotly_chart(fig_map, use_container_width=True)
                else:
                    st.info("Mapping incomplete for current country list.")
        except Exception as e:
            st.error(f"Map error: {e}")
    else:
        st.info("Country data missing.")

# --- 7. FOOTER ---
st.markdown("""
    <div class="footer">
        © Leverhulme Centre for Demographic Science - University of Oxford
    </div>
""", unsafe_allow_html=True)
