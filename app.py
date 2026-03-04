import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="LCDS Impact Tracker",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TRENDY & DARK-MODE FRIENDLY CSS ---
st.markdown("""
    <style>
        /* 1. Dynamic Headers (Auto-adapts to Dark/Light Mode) */
        h1, h2, h3 {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        
        /* 2. Trendy Gradient Subheading */
        .trendy-sub {
            background: linear-gradient(90deg, #002147 0%, #C49102 100%); /* Oxford Blue -> Gold */
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 1.5rem;
            font-weight: 600;
            margin-top: -10px;
            margin-bottom: 30px;
        }

        /* Dark Mode Adjustment for Subheading */
        @media (prefers-color-scheme: dark) {
            .trendy-sub {
                background: linear-gradient(90deg, #81D4FA 0%, #FFD700 100%); /* Light Blue -> Gold */
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
        }

        /* 3. Footer Styling */
        .footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: #002147; /* Always Oxford Blue background */
            color: white;
            text-align: center;
            padding: 12px;
            font-size: 0.85rem;
            z-index: 999;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.2);
        }
        .footer a {
            color: #FFD700; /* Gold links */
            text-decoration: none;
            font-weight: bold;
        }
        
        /* Padding to prevent content being hidden behind footer */
        .block-container {
            padding-bottom: 80px;
        }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA (FROM SILENT BRANCH) ---
@st.cache_data(ttl=3600)
def load_data():
    # URL to your raw CSV on the data branch
    # REPLACE 'shamshxis' and 'lcds-pubstracker' if needed!
    url = "https://raw.githubusercontent.com/shamshxis/lcds-pubstracker/data/data/lcds_publications.csv"
    
    try:
        df = pd.read_csv(url)
        
        # 1. Define EXPECTED columns
        expected_cols = [
            'Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 
            'Paper Title', 'Journal Name', 'Journal Area', 
            'Year of Publication', 'Citation Count', 'Publication Type'
        ]
        
        # 2. FORCE columns to exist
        for col in expected_cols:
            if col not in df.columns:
                df[col] = "Unknown" if col != 'Citation Count' else 0

        # 3. Clean Data Types
        df['Date Available Online'] = pd.to_datetime(df['Date Available Online'], errors='coerce')
        df['Citation Count'] = pd.to_numeric(df['Citation Count'], errors='coerce').fillna(0)
        df['Journal Area'] = df['Journal Area'].fillna('Pending (Recent)')
        df['Publication Type'] = df['Publication Type'].fillna('Journal Article')

        return df
    except Exception as e:
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.title("🔍 Filters")

if df.empty:
    st.warning("⚠️ No data available yet.")
    st.info("The scraper is running. Please check back in a few minutes.")
    st.stop()

# Time Filter
time_options = ["All Time", "Last 5 Years", "Last Year", "Last Month", "Last Week"]
time_filter = st.sidebar.radio("Select Period", time_options, index=1)

now = datetime.now()
if time_filter == "Last Week": start_date = now - timedelta(days=7)
elif time_filter == "Last Month": start_date = now - timedelta(days=30)
elif time_filter == "Last Year": start_date = now - timedelta(days=365)
elif time_filter == "Last 5 Years": start_date = now - timedelta(days=5*365)
else: start_date = pd.to_datetime("2000-01-01")

# Publication Type Filter
pub_types = df['Publication Type'].unique()
selected_types = st.sidebar.multiselect("Publication Type", pub_types, default=pub_types)

# Apply Filters
mask = (df['Date Available Online'] >= start_date) & (df['Publication Type'].isin(selected_types))
df_filtered = df[mask].copy()

# --- MAIN DASHBOARD ---

# 1. HEADER
st.title("Leverhulme Centre for Demographic Science")
st.markdown('<div class="trendy-sub">Measuring our impact across the years.</div>', unsafe_allow_html=True)

st.markdown(f"**Viewing:** {time_filter} | **Records Found:** {len(df_filtered)}")
st.divider()

# 2. METRICS
col1, col2, col3, col4 = st.columns(4)
total_cites = int(df_filtered['Citation Count'].sum())
preprint_count = len(df_filtered[df_filtered['Publication Type'] == 'Preprint'])

col1.metric("Total Output", len(df_filtered))
col2.metric("Total Citations", total_cites)
col3.metric("Preprints", preprint_count)
col4.metric("Active Authors", df_filtered['LCDS Author'].nunique())

st.divider()

# 3. VISUALS
c1, c2 = st.columns(2)
with c1:
    st.subheader("📊 Impact by Field")
    df_area = df_filtered.groupby('Journal Area')['Citation Count'].sum().reset_index()
    # Filter for cleaner chart
    df_area = df_area[(df_area['Journal Area'] != 'Pending (Recent)') & (df_area['Citation Count'] > 0)]
    
    if not df_area.empty:
        fig = px.pie(df_area, values='Citation Count', names='Journal Area', hole=0.4, 
                     title="Citations per Field", color_discrete_sequence=px.colors.qualitative.Prism)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No citation data available for this period.")

with c2:
    st.subheader("📑 Type Distribution")
    fig2 = px.pie(df_filtered, names='Publication Type', hole=0.4, 
                  title="Journals vs. Preprints", color_discrete_sequence=px.colors.qualitative.Safe)
    st.plotly_chart(fig2, use_container_width=True)

# 4. DATA TABLE
st.subheader(f"📄 Recent Publications")

# Select columns
cols_to_show = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Publication Type', 'Citation Count', 'DOI']
final_cols = [c for c in cols_to_show if c in df_filtered.columns]

# Create display copy
df_display = df_filtered[final_cols].copy()

# 1. Turn DOI links into clickable HTML anchors
if 'DOI' in df_display.columns:
    df_display['DOI'] = df_display['DOI'].apply(lambda x: f'<a href="{x}" target="_blank">View</a>' if str(x).startswith('http') else x)

# 2. Convert to HTML (escape=False allows tags to render)
html_table = df_display.to_html(escape=False, index=False, border=0, classes="styled-table")

# 3. Render with Custom CSS wrapper for Scrollbars & Google Fonts
st.markdown(f"""
    <style>
        /* Import Google Font */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500&display=swap');

        /* Scrollable Container */
        .table-container {{
            max-height: 500px;       /* Fixed height */
            overflow-y: auto;        /* Vertical scrollbar */
            overflow-x: hidden;      /* Hide horizontal scroll */
            border: 1px solid #ddd;
            border-radius: 8px;      /* Rounded corners */
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); /* Subtle shadow */
        }}

        /* Table Styling */
        .styled-table {{
            width: 100%;
            border-collapse: collapse;
            font-family: 'Roboto', sans-serif; /* Google Font */
            font-size: 0.85rem;      /* Small, professional size */
        }}

        /* Sticky Header */
        .styled-table thead tr th {{
            position: sticky;
            top: 0;
            background-color: #002147; /* Oxford Blue */
            color: #ffffff;
            text-align: left;
            padding: 12px 15px;
            font-weight: 500;
            z-index: 1; /* Keeps header on top of content */
        }}

        /* Row Styling */
        .styled-table tbody tr {{
            border-bottom: 1px solid #eeeeee;
        }}
        
        .styled-table tbody tr:nth-of-type(even) {{
            background-color: rgba(0,0,0,0.02); /* Zebra striping */
        }}
        
        .styled-table tbody tr:hover {{
            background-color: rgba(0, 33, 71, 0.05); /* Hover effect */
            transition: background-color 0.2s ease-in-out;
        }}

        .styled-table td {{
            padding: 10px 15px;
            color: var(--text-color);
        }}

        /* Link Styling */
        .styled-table a {{
            color: #0066cc;
            text-decoration: none;
            font-weight: 600;
            border-bottom: 1px dotted #0066cc;
        }}
        .styled-table a:hover {{
            color: #003366;
            border-bottom: 1px solid #003366;
        }}

        /* Dark Mode Adjustments */
        @media (prefers-color-scheme: dark) {{
            .styled-table thead tr th {{
                background-color: #1E1E1E;
                color: #FFD700; /* Gold Header Text */
                border-bottom: 2px solid #333;
            }}
            .styled-table tbody tr {{
                border-bottom: 1px solid #333;
            }}
            .styled-table tbody tr:nth-of-type(even) {{
                background-color: rgba(255,255,255,0.05);
            }}
            .styled-table tbody tr:hover {{
                background-color: rgba(255,255,255,0.1);
            }}
            .styled-table a {{
                color: #4da6ff;
                border-bottom: 1px dotted #4da6ff;
            }}
            .table-container {{
                border: 1px solid #444;
            }}
        }}
    </style>

    <div class="table-container">
        {html_table}
    </div>
""", unsafe_allow_html=True)

# 5. FOOTER
st.markdown("""
    <div class="footer">
        Certified University of Oxford 2026 - All Rights Reserved. | 
        <a href="https://www.demography.ox.ac.uk" target="_blank">demography.ox.ac.uk</a>
    </div>
""", unsafe_allow_html=True)
