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
        
        /* Table Links Styling */
        a {
            color: #0066cc;
            text-decoration: none;
            font-weight: 500;
        }
        a:hover {
            text-decoration: underline;
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
        
        # --- SELF-HEALING: Ensure all columns exist ---
        required_cols = ['Date', 'Year', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI', 'Field', 'Countries']
        for col in required_cols:
            if col not in df.columns:
                if col == 'Citations': df[col] = 0
                elif col == 'Year': df[col] = datetime.now().year
                else: df[col] = "Unknown" if col != 'Countries' else ""
        
        # Data Type Conversions
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(0).astype(int)
        df['Citations'] = pd.to_numeric(df['Citations'], errors='coerce').fillna(0)
        
        return df
    except Exception as e:
        return pd.DataFrame()

df = load_data()

# --- 4. SIDEBAR CONTROLS ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/University_of_Oxford.svg/1200px-University_of_Oxford.svg.png", width=120)
st.sidebar.title("Research Filters")

if df.empty:
    st.warning("⚠️ Data is loading or empty.")
    st.info("The scraper runs daily. Please check back shortly.")
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

# Publication Type Filter
all_types = list(df['Type'].unique())
selected_types = st.sidebar.multiselect("Publication Type", all_types, default=all_types)

# Apply Filters
df_filtered = df[(df['Date'] >= start_date) & (df['Type'].isin(selected_types))].copy()

# --- 5. MAIN DASHBOARD ---

# Header Section
st.markdown('<div class="main-header">Leverhulme Centre for Demographic Science</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Tracking research impact, preprints, and global collaborations.</div>', unsafe_allow_html=True)

# Metrics Row
m1, m2, m3, m4 = st.columns(4)
m1.metric("📚 Publications", len(df_filtered))
m2.metric("💬 Total Citations", int(df_filtered['Citations'].sum()))
m3.metric("📝 Preprints", len(df_filtered[df_filtered['Type']=="Preprint"]))
# Count unique active researchers in filtered set
active_researchers = df_filtered['LCDS Author'].nunique()
m4.metric("👥 Active Researchers", active_researchers)

st.divider()

# --- 6. TABS INTERFACE ---
tab1, tab2, tab3 = st.tabs(["📄 Publications List", "📊 Analytics & Impact", "🌍 Global Reach"])

# === TAB 1: LIST & DOWNLOAD ===
with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Recent Publications")
    with col2:
        # CSV Download Button
        csv_data = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"lcds_data_{datetime.now().strftime('%Y-%m-%d')}.csv",
            mime="text/csv"
        )
    
    # Display Clean Table
    if not df_filtered.empty:
        # Prepare display dataframe
        show_df = df_filtered[['Date', 'LCDS Author', 'Title', 'Journal', 'Type', 'Citations', 'DOI']].copy()
        
        # Format Date to YYYY-MM-DD
        show_df['Date'] = show_df['Date'].dt.strftime('%Y-%m-%d')
        
        # Format DOI as clickable link
        show_df['DOI'] = show_df['DOI'].apply(lambda x: f'<a href="{x}" target="_blank">View Paper</a>' if str(x).startswith('http') else x)
        
        # Render as HTML
        st.write(show_df.to_html(escape=False, index=False, border=0, classes="dataframe table table-hover"), unsafe_allow_html=True)
    else:
        st.info("No publications found for this period.")

# === TAB 2: ANALYTICS ===
with tab2:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Citations per Year")
        if not df_filtered.empty:
            yearly_counts = df_filtered.groupby('Year')['Citations'].sum().reset_index()
            fig_bar = px.bar(yearly_counts, x='Year', y='Citations', 
                             color_discrete_sequence=['#002147'])
            fig_bar.update_layout(xaxis_type='category')
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No citation data available.")
            
    with col2:
        st.subheader("Research Fields")
        if not df_filtered.empty and 'Field' in df_filtered.columns:
            # Filter out "Multidisciplinary" to show specific fields if possible
            field_df = df_filtered[df_filtered['Field'] != 'Multidisciplinary']
            if field_df.empty: field_df = df_filtered # Fallback
            
            field_counts = field_df['Field'].value_counts().head(10).reset_index()
            field_counts.columns = ['Field', 'Count']
            
            fig_pie = px.pie(field_counts, values='Count', names='Field', hole=0.4, 
                             color_discrete_sequence=px.colors.qualitative.Prism)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Field data not available.")

    # Histogram of Citations
    st.subheader("Citation Impact Distribution")
    if not df_filtered.empty:
        fig_hist = px.histogram(df_filtered, x="Citations", nbins=20, 
                               title="Distribution of Citations (How many papers get X citations?)",
                               color_discrete_sequence=['#C49102'])
        st.plotly_chart(fig_hist, use_container_width=True)

# === TAB 3: GLOBAL MAP ===
with tab3:
    st.subheader("🌍 Global Collaboration Map")
    st.markdown("Mapping the institutional countries of our co-authors.")
    
    if not df_filtered.empty and 'Countries' in df_filtered.columns:
        # 1. Extract and Flatten Countries
        # Data format is "US,GB,FR" string in column
        all_countries = df_filtered['Countries'].str.split(',').explode().str.strip()
        
        # 2. Filter empty strings
        all_countries = all_countries[all_countries != '']
        all_countries = all_countries.dropna()
        
        if not all_countries.empty:
            country_counts = all_countries.value_counts().reset_index()
            country_counts.columns = ['ISO_Alpha_2', 'Papers']
            
            # 3. Plot Choropleth Map
            fig_map = px.choropleth(
                country_counts,
                locations="ISO_Alpha_2",
                color="Papers",
                hover_name="ISO_Alpha_2",
                color_continuous_scale="Blues",
                projection="natural earth",
                title="Publications by Collaborating Country"
            )
            fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.info("Global collaboration data is currently being enriched. Please check back later.")
    else:
        st.info("No country data available for the selected period.")

# --- 7. FOOTER ---
st.markdown("""
    <div class="footer">
        © 2026 Leverhulme Centre for Demographic Science | University of Oxford <br>
        Data sourced from Crossref & OpenAlex
    </div>
""", unsafe_allow_html=True)
