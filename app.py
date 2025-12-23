import streamlit as st
import requests
import pandas as pd
import numpy as np

# --- SAFE IMPORT FOR GEMINI ---
try:
    import google.generativeai as genai
    has_gemini_lib = True
except ImportError:
    has_gemini_lib = False

# --- PAGE CONFIG ---
st.set_page_config(page_title="Compounder Formula (Pro)", page_icon="📊", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
    html, body, [class*="css"] { font-family: 'Roboto', sans-serif; }
    .block-container { max-width: 1200px; padding-top: 2rem; }
    
    /* Metrics */
    div[data-testid="stMetric"] {
        background-color: #ffffff; padding: 15px; border-radius: 10px;
        border: 1px solid #e0e0e0; box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    div[data-testid="stMetricValue"] { color: #1a73e8; font-weight: 700; font-size: 1.6rem; }
    
    /* Tables */
    table { width: 100%; border-collapse: collapse; margin-top: 15px; }
    th { text-align: left; color: #5f6368; background-color: #f8f9fa; padding: 10px; }
    td { padding: 10px; border-bottom: 1px solid #eee; color: #202124; }
    tr:last-child td { font-weight: bold; background-color: #f8f9fa; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Compounder Dashboard")
st.markdown("Analyze capital allocation efficiency with flexible timeframes.")

# --- CONFIG ---
try:
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("⚠️ API Key missing. Please add `QUICKFS_API_KEY` to secrets.")
    st.stop()

# --- HELPER FUNCTIONS ---
def format_currency(val):
    if val is None or pd.isna(val): return "N/A"
    abs_val = abs(val)
    if abs_val >= 1e9: return f"${val/1e9:,.2f} B"
    if abs_val >= 1e6: return f"${val/1e6:,.2f} M"
    return f"${val:,.0f}"

def smart_get(data_dict, keys_to_try):
    """Finds the first matching key in a dictionary."""
    for k in keys_to_try:
        if k in data_dict: return data_dict[k]
    return None

@st.cache_data(show_spinner=False)
def fetch_quickfs_data(ticker):
    """
    Fetches FULL data from QuickFS. Cached to allow changing years without re-fetching.
    """
    url = f"https://public-api.quickfs.net/v1/data/all-data/{ticker}"
    params = {"api_key": API_KEY}
    try:
        r = requests.get(url, params=params)
        if r.status_code != 200: return None, f"API Error: {r.status_code}"
        data = r.json()
        if "data" not in data: return None, "Invalid data received."
        return data["data"], None
    except Exception as e:
        return None, str(e)

def process_financials(raw_data):
    """
    Extracts Annual and Quarterly data, aligns them, and builds the TTM row.
    """
    try:
        annual = raw_data.get("financials", {}).get("annual", {})
        quarterly = raw_data.get("financials", {}).get("quarterly", {})
        
        # --- 1. PROCESS ANNUAL ---
        # Identify Keys
        cfo_a = smart_get(annual, ["cf_cfo", "cfo", "cash_flow_operating"])
        capex_a = smart_get(annual, ["capex", "capital_expenditures"])
        assets_a = smart_get(annual, ["total_assets", "assets"])
        liab_a = smart_get(annual, ["total_current_liabilities", "liabilities_current"])
        
        # Dates
        dates_a = annual.get("period_end_date", annual.get("fiscal_year", []))
        
        if not cfo_a or not dates_a:
            return None, "Required annual metrics missing."

        # Align lengths
        min_len = min(len(cfo_a), len(dates_a))
        df_annual = pd.DataFrame({
            "OCF": cfo_a[-min_len:],
            "CapEx": capex_a[-min_len:] if capex_a else [0]*min_len,
            "Assets": assets_a[-min_len:] if assets_a else [0]*min_len,
            "Liabilities": liab_a[-min_len:] if liab_a else [0]*min_len
        })
        # Extract Year (e.g. "2023" from "2023-12")
        df_annual.index = [str(d).split('-')[0] for d in dates_a[-min_len:]]
        
        # --- 2. PROCESS TTM (If Quarterly Exists) ---
        df_ttm = None
        cfo_q = smart_get(quarterly, ["cf_cfo", "cfo", "cash_flow_operating"])
        capex_q = smart_get(quarterly, ["capex", "capital_expenditures"])
        assets_q = smart_get(quarterly, ["total_assets", "assets"])
        liab_q = smart_get(quarterly, ["total_current_liabilities", "liabilities_current"])
        
        if cfo_q and len(cfo_q) >= 4:
            # TTM Logic: Sum last 4 quarters for Flow, take Last quarter for Stock
            ttm_ocf = sum(cfo_q[-4:])
            ttm_capex = sum(capex_q[-4:]) if capex_q else 0
            ttm_assets = assets_q[-1] if assets_q else 0
            ttm_liab = liab_q[-1] if liab_q else 0
            
            df_ttm = pd.DataFrame({
                "OCF": [ttm_ocf], "CapEx": [ttm_capex], 
                "Assets": [ttm_assets], "Liabilities": [ttm_liab]
            }, index=["TTM"])

        return df_annual, df_ttm

    except Exception as e:
        return None, str(e)

# --- APP LOGIC ---

# 1. Ticker Input
col_input, col_btn = st.columns([3, 1])
with col_input:
    ticker = st.text_input("Ticker", "APG:US", label_visibility="collapsed", placeholder="Enter Ticker (e.g. APG:US)").strip().upper()
with col_btn:
    load_btn = st.button("Load Financials", type="primary", use_container_width=True)

# 2. State Management
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.raw_df = None
    st.session_state.ttm_df = None
    st.session_state.meta = {}

if load_btn and ticker:
    with st.spinner("Fetching data..."):
        raw, error = fetch_quickfs_data(ticker)
        if error:
            st.error(error)
            st.session_state.data_loaded = False
        else:
            df_annual, df_ttm = process_financials(raw)
            if isinstance(df_annual, pd.DataFrame):
                st.session_state.raw_df = df_annual
                st.session_state.ttm_df = df_ttm
                st.session_state.meta = raw.get("metadata", {})
                st.session_state.data_loaded = True
            else:
                st.error(df_ttm)

# 3. Main Dashboard
if st.session_state.data_loaded:
    df_main = st.session_state.raw_df
    df_ttm = st.session_state.ttm_df
    meta = st.session_state.meta
    
    st.divider()
    
    # --- TIMEFRAME SELECTOR ---
    available_years = list(df_main.index)
    available_options = available_years.copy()
    if df_ttm is not None:
        available_options.append("TTM")
    
    default_end_idx = len(available_options) - 1
    default_start_idx = max(0, default_end_idx - 10)
    
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        start_period = st.selectbox("Start Year", available_years, index=default_start_idx)
    with c2:
        valid_end_options = [opt for opt in available_options if opt == "TTM" or opt >= start_period]
        end_idx = len(valid_end_options)-1 
        end_period = st.selectbox("End Year", valid_end_options, index=end_idx)
    
    # --- FILTERING LOGIC ---
    if end_period == "TTM" and df_ttm is not None:
        df_combined = pd.concat([df_main, df_ttm])
        df_slice = df_combined.loc[start_period:] 
    else:
        df_slice = df_main.loc[start_period : end_period]

    # --- CALCULATIONS ---
    if len(df_slice) >= 2:
        df_slice['FCF'] = df_slice['OCF'] - df_slice['CapEx'].abs()
        df_slice['IC'] = df_slice['Assets'] - df_slice['Liabilities']
        
        start_idx = df_slice.index[0]
        end_idx = df_slice.index[-1]
        
        A1 = df_slice['FCF'].sum()
        B1 = df_slice.loc[end_idx, 'FCF'] - df_slice.loc[start_idx, 'FCF']
        A2 = df_slice.loc[end_idx, 'IC'] - df_slice.loc[start_idx, 'IC']
        
        roiic = B1 / A2 if A2 != 0 else 0
        reinvest = A2 / A1 if A1 != 0 else 0
        score = roiic * reinvest
        
        # Verdict
        if reinvest < 0.20: v_txt, v_bg, v_col = "Cash Cow", "#fef7e0", "#b06000"
        elif 0.80 <= reinvest <= 1.00: v_txt, v_bg, v_col = "Aggressive Compounder", "#e6f4ea", "#137333"
        elif reinvest > 1.00: v_txt, v_bg, v_col = "External Funding (>100%)", "#fce8e6", "#c5221f"
        else: v_txt, v_bg, v_col = "Moderate Reinvestment", "#e8f0fe", "#1967d2"

        # --- DISPLAY ---
        st.subheader(f"{meta.get('name', ticker)} Analysis ({start_idx} - {end_idx})")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Compounder Score", f"{score:.1%}", "Target: >20%")
        m2.metric("ROIIC", f"{roiic:.1%}", "Target: >15%")
        m3.metric("Reinvestment Rate", f"{reinvest:.1%}", "Target: >80%")
        
        # HTML Table
        table_html = f"""
        <table>
            <thead><tr><th>Metric</th><th>Value</th><th>Formula</th><th>Label</th></tr></thead>
            <tbody>
                <tr><td><b>Accumulated FCF</b></td><td>{format_currency(A1)}</td><td>∑ FCF</td><td><b>A1</b></td></tr>
                <tr><td><b>Increase in FCF</b></td><td>{format_currency(B1)}</td><td>FCF<sub>end</sub> - FCF<sub>start</sub></td><td><b>B1</b></td></tr>
                <tr><td><b>Increase in IC</b></td><td>{format_currency(A2)}</td><td>IC<sub>end</sub> - IC<sub>start</sub></td><td><b>A2</b></td></tr>
                <tr><td><b>ROIIC</b></td><td>{roiic:.1%}</td><td>B1 / A2</td><td><b>C1</b></td></tr>
                <tr><td><b>Reinvestment Rate</b></td><td>{reinvest:.1%}</td><td>A2 / A1</td><td><b>C2</b></td></tr>
                <tr style="background-color:#f8f9fa"><td><b>Final Score</b></td><td>{score:.1%}</td><td>C1 × C2</td><td><b>Result</b></td></tr>
            </tbody>
        </table>
        """
        st.markdown(table_html, unsafe_allow_html=True)
        
        # Verdict Banner
        st.markdown(f"""
        <div style="background-color:{v_bg}; padding:12px; border-radius:8px; margin-top:15px; border:1px solid {v_bg}; display:flex; align-items:center; gap:10px;">
            <span style="font-size:1.2rem;">🧬</span>
            <span style="color:{v_col}; font-weight:600;">Phase: {v_txt}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # ADDED SPACE HERE
        st.write("")
        st.write("")
        
        with st.expander("View Data"):
            st.dataframe(df_slice.style.format("{:,.0f}"))
            
    else:
        st.warning("Select a range with at least 2 periods.")
