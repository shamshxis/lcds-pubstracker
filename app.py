import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="LCDS Impact Tracker", page_icon="🌍", layout="wide")

# --- LOAD DATA ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("data/lcds_publications.csv")
        df['Date'] = pd.to_datetime(df['Date'])
        return df
    except FileNotFoundError:
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.header("🔍 Filters")

if df.empty:
    st.error("No data found. Please run the scraper first.")
    st.stop()

# Time Filter
time_filter = st.sidebar.radio(
    "Select Time Period",
    ["All Time (Since 2019)", "Last 5 Years", "Last Year", "Last Month", "Last Week"]
)

now = datetime.now()
if time_filter == "Last 5 Years":
    start_date = now - timedelta(days=5*365)
elif time_filter == "Last Year":
    start_date = now - timedelta(days=365)
elif time_filter == "Last Month":
    start_date = now - timedelta(days=30)
elif time_filter == "Last Week":
    start_date = now - timedelta(days=7)
else:
    start_date = pd.to_datetime("2019-01-01")

df_filtered = df[df['Date'] >= start_date]

# Affiliation Filter
aff_types = st.sidebar.multiselect(
    "Affiliation Context",
    options=df['Affiliation_Scope'].unique(),
    default=df['Affiliation_Scope'].unique()
)
df_filtered = df_filtered[df_filtered['Affiliation_Scope'].isin(aff_types)]

# --- MAIN DASHBOARD ---
st.title("🌍 LCDS Publications & Impact Tracker")
st.markdown(f"**Data live as of:** {datetime.now().strftime('%Y-%m-%d')}")

# Top Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Publications", len(df_filtered))
c2.metric("Preprints / Working Papers", len(df_filtered[df_filtered['Type'].isin(['preprint', 'posted-content'])]))
c3.metric("LCDS Core Affiliation", len(df_filtered[df_filtered['Affiliation_Scope'] == "LCDS (Core)"]))
c4.metric("Total Citations", int(df_filtered['Citation_Count'].sum()))

st.divider()

# --- ROW 1: IMPACT VISUALS ---
col_charts_1, col_charts_2 = st.columns([2, 1])

with col_charts_1:
    st.subheader("📈 Output Over Time")
    # Group by Month-Year for cleaner bars
    df_counts = df_filtered.groupby([pd.Grouper(key='Date', freq='M'), 'Type']).size().reset_index(name='Count')
    fig_time = px.bar(df_counts, x='Date', y='Count', color='Type', 
                      title="Publications by Type (Monthly)",
                      color_discrete_sequence=px.colors.qualitative.Bold)
    st.plotly_chart(fig_time, use_container_width=True)

with col_charts_2:
    st.subheader("🧬 Impact by Field")
    # Sunburst chart for Fields
    if 'Field' in df_filtered.columns:
        fig_sun = px.pie(df_filtered, names='Field', title="Distribution by Research Field",
                         hole=0.4, color_discrete_sequence=px.colors.qualitative.Prism)
        fig_sun.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_sun, use_container_width=True)

# --- ROW 2: DETAILED DATA ---
st.subheader(f"📄 Recent Publications ({len(df_filtered)})")

# Search bar
search_query = st.text_input("Search title or author...")
if search_query:
    df_filtered = df_filtered[
        df_filtered['Title'].str.contains(search_query, case=False, na=False) |
        df_filtered['Author'].str.contains(search_query, case=False, na=False)
    ]

# Styled Data Table
st.dataframe(
    df_filtered[['Date', 'Author', 'Title', 'Journal', 'Affiliation_Scope', 'Citation_Count', 'DOI']],
    column_config={
        "DOI": st.column_config.LinkColumn("DOI Link"),
        "Date": st.column_config.DateColumn("Pub. Date"),
    },
    hide_index=True,
    use_container_width=True
)

# Download Button
csv = df_filtered.to_csv(index=False).encode('utf-8')
st.download_button(
    "📥 Download Filtered Data as CSV",
    data=csv,
    file_name="lcds_filtered_publications.csv",
    mime="text/csv"
)
