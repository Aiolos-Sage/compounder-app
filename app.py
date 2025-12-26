import streamlit as st
import requests
import pandas as pd
import numpy as np
import streamlit.components.v1 as components

# --- SAFE IMPORT FOR GEMINI ---
try:
    import google.generativeai as genai
    has_gemini_lib = True
except ImportError:
    has_gemini_lib = False

# --- PAGE CONFIG ---
st.set_page_config(page_title="Compounder Formula (Pro)", page_icon="📊", layout="wide")

# --- THEME MANAGEMENT ---
if 'theme' not in st.session_state:
    st.session_state.theme = 'light'

def toggle_theme():
    st.session_state.theme = 'dark' if st.session_state.theme == 'light' else 'light'

# Sidebar Toggle
with st.sidebar:
    st.header("Settings")
    is_dark = st.toggle("Dark Mode", value=(st.session_state.theme == 'dark'), on_change=toggle_theme)

# --- DEFINE COLOR PALETTES (Material 3) ---
if st.session_state.theme == 'dark':
    # Google Dark Mode Tokens
    colors = {
        "bg": "#121212",
        "surface": "#1E1E1E",
        "surface_high": "#2C2C2C",
        "on_surface": "#E3E3E3",
        "on_surface_variant": "#C4C7C5",
        "primary": "#8AB4F8", 
        "border": "#444746",
        "shadow": "0 4px 8px rgba(0,0,0,0.5)",
        "success_bg": "rgba(129, 201, 149, 0.12)",
        "success_text": "#81C995",
        "warning_bg": "rgba(253, 214, 99, 0.12)",
        "warning_text": "#FDD663",
        "error_bg": "rgba(242, 139, 130, 0.12)",
        "error_text": "#F28B82",
        "blue_bg": "rgba(138, 180, 248, 0.12)",
        "blue_text": "#8AB4F8"
    }
else:
    # Google Light Mode Tokens
    colors = {
        "bg": "#FFFFFF",
        "surface": "#FFFFFF",
        "surface_high": "#F8F9FA",
        "on_surface": "#1F1F1F",
        "on_surface_variant": "#5F6368",
        "primary": "#1A73E8",
        "border": "#E0E0E0",
        "shadow": "0 1px 2px rgba(0,0,0,0.06)",
        "success_bg": "#E6F4EA",
        "success_text": "#137333",
        "warning_bg": "#FEF7E0",
        "warning_text": "#B06000",
        "error_bg": "#FCE8E6",
        "error_text": "#C5221F",
        "blue_bg": "#E8F0FE",
        "blue_text": "#1967d2"
    }

# --- INJECT DYNAMIC CSS ---
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {{
        font-family: 'Roboto', sans-serif;
        background-color: {colors['bg']};
        color: {colors['on_surface']};
    }}
    
    /* Main Container */
    .block-container {{ 
        max-width: 1200px; 
        padding-top: 2rem; 
    }}
    
    /* Streamlit Metric Cards */
    div[data-testid="stMetric"] {{
        background-color: {colors['surface']};
        padding: 15px;
        border-radius: 12px;
        border: 1px solid {colors['border']};
        box-shadow: {colors['shadow']};
    }}
    div[data-testid="stMetricValue"] {{
        color: {colors['primary']} !important;
        font-weight: 700;
        font-size: 1.6rem;
    }}
    label[data-testid="stMetricLabel"] {{
        color: {colors['on_surface_variant']};
    }}
    
    /* Tables */
    table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 15px;
        background-color: {colors['surface']};
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid {colors['border']};
    }}
    th {{
        text-align: left;
        color: {colors['on_surface_variant']};
        background-color: {colors['surface_high']};
        padding: 12px;
        font-weight: 600;
        border-bottom: 1px solid {colors['border']};
    }}
    td {{
        padding: 12px;
        border-bottom: 1px solid {colors['border']};
        color: {colors['on_surface']};
    }}
    tr:last-child td {{
        font-weight: bold;
        background-color: {colors['surface_high']};
        border-bottom: none;
    }}
    
    /* Inputs */
    input[type="text"] {{
        background-color: {colors['surface']} !important;
        color: {colors['on_surface']} !important;
        border: 1px solid {colors['border']} !important;
    }}
    div[data-baseweb="select"] > div {{
        background-color: {colors['surface']} !important;
        color: {colors['on_surface']} !important;
        border-color: {colors['border']} !important;
    }}
    
    /* Headers */
    h1, h2, h3 {{ color: {colors['on_surface']} !important; }}
    
    /* Verdict Banner Styles */
    .verdict-box {{
        padding: 12px;
        border-radius: 8px;
        margin-top: 15px;
        display: flex;
        align-items: center;
        gap: 10px;
        border: 1px solid transparent;
    }}
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
    for k in keys_to_try:
        if k in data_dict: return data_dict[k]
    return None

@st.cache_data(show_spinner=False)
def fetch_quickfs_data(ticker):
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
    try:
        annual = raw_data.get("financials", {}).get("annual", {})
        quarterly = raw_data.get("financials", {}).get("quarterly", {})
        
        cfo_a = smart_get(annual, ["cf_cfo", "cfo", "cash_flow_operating"])
        capex_a = smart_get(annual, ["capex", "capital_expenditures"])
        assets_a = smart_get(annual, ["total_assets", "assets"])
        liab_a = smart_get(annual, ["total_current_liabilities", "liabilities_current"])
        dates_a = annual.get("period_end_date", annual.get("fiscal_year", []))
        
        if not cfo_a or not dates_a: return None, "Required annual metrics missing."

        min_len = min(len(cfo_a), len(dates_a))
        df_annual = pd.DataFrame({
            "OCF": cfo_a[-min_len:],
            "CapEx": capex_a[-min_len:] if capex_a else [0]*min_len,
            "Assets": assets_a[-min_len:] if assets_a else [0]*min_len,
            "Liabilities": liab_a[-min_len:] if liab_a else [0]*min_len
        })
        df_annual.index = [str(d).split('-')[0] for d in dates_a[-min_len:]]
        
        df_ttm = None
        cfo_q = smart_get(quarterly, ["cf_cfo", "cfo", "cash_flow_operating"])
        capex_q = smart_get(quarterly, ["capex", "capital_expenditures"])
        assets_q = smart_get(quarterly, ["total_assets", "assets"])
        liab_q = smart_get(quarterly, ["total_current_liabilities", "liabilities_current"])
        
        if cfo_q and len(cfo_q) >= 4:
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

# --- STATIC HTML GUIDE (Original White Background Version) ---
html_guide = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>The Compounder Formula</title>
  <style>
    :root{
      --primary:#1a73e8; 
      --surface:#ffffff; 
      --on-surface:#1f1f1f;
      --r-xl: 28px; 
      --r-lg: 22px; 
      --shadow-1: 0 1px 2px rgba(0,0,0,.06);
      font-family: Roboto, sans-serif;
    }
    body{ 
        margin:0; 
        background: #ffffff; /* FORCE WHITE BACKGROUND */
        color: #1f1f1f;      /* FORCE DARK TEXT */
    }
    .page{ 
        max-width: 1140px; 
        margin: 0 auto; 
        padding: 1.25rem 1.1rem 3rem; 
    }
    .card{
      border-radius: var(--r-xl); 
      border: 1px solid rgba(31,31,31,.14);
      background: #f8f9fa; 
      box-shadow: var(--shadow-1);
      padding: 1.5rem; 
      margin-bottom: 1rem;
    }
    h1{ margin:0; font-size: 2rem; color: #1a73e8; }
    h2{ margin-top:0; font-size: 1.3rem; }
    .formula{
      font-family: monospace; 
      background: #ffffff; 
      padding: 10px;
      border-radius: 8px; 
      display: inline-block; 
      margin: 5px 0;
      border: 1px solid #e0e0e0;
    }
    .grid{ display:grid; gap: 1rem; }
  </style>
</head>
<body>
  <div class="page">
    <section class="card" style="background:#ffffff; border:none; box-shadow:none; padding-left:0;">
      <h1>The Compounder Formula Guide</h1>
      <p style="color:#5f6368;">A framework to identify businesses that grow cash and reinvest it at high returns.</p>
    </section>
    
    <div class="grid">
      <section class="card">
        <h2>1. Definitions</h2>
        <p><strong>Free Cash Flow (FCF):</strong> <span class="formula">Operating Cash Flow - CapEx</span></p>
        <p><strong>Invested Capital (IC):</strong> <span class="formula">Total Assets - Total Current Liabilities</span></p>
      </section>

      <section class="card">
        <h2>2. Core Ratios</h2>
        <p><strong>ROIIC (Efficiency):</strong> Measures the return on <em>new</em> capital invested.</p>
        <p>Target: <strong style="color:#1a73e8;">>15-20%</strong> indicates a strong moat.</p>
        <br>
        <p><strong>Reinvestment Rate (Opportunity):</strong> Measures how much FCF is plowed back into growth.</p>
        <p>Target: <strong style="color:#1a73e8;">>80%</strong> indicates an aggressive compounder.</p>
      </section>

      <section class="card">
        <h2>3. Final Score</h2>
        <p><span class="formula">Score = ROIIC × Reinvestment Rate</span></p>
        <p>This approximates the sustainable growth rate of the company's intrinsic value.</p>
      </section>
    </div>
  </div>
</body>
</html>
"""

# --- APP LOGIC ---

col_input, col_btn = st.columns([3, 1])
with col_input:
    ticker = st.text_input("Ticker", "APG:US", label_visibility="collapsed", placeholder="Enter Ticker (e.g. APG:US)").strip().upper()
with col_btn:
    load_btn = st.button("Load Financials", type="primary", use_container_width=True)

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

if st.session_state.data_loaded:
    df_main = st.session_state.raw_df
    df_ttm = st.session_state.ttm_df
    meta = st.session_state.meta
    
    st.divider()
    
    # TIMEFRAME SELECTOR
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
    
    # FILTERING
    if end_period == "TTM" and df_ttm is not None:
        df_combined = pd.concat([df_main, df_ttm])
        df_slice = df_combined.loc[start_period:].copy() 
    else:
        df_slice = df_main.loc[start_period : end_period].copy()

    # CALCULATIONS
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
        
        # Verdict Styling
        if reinvest < 0.20: 
            v_txt, v_bg, v_col = "Cash Cow", colors['warning_bg'], colors['warning_text']
        elif 0.80 <= reinvest <= 1.00: 
            v_txt, v_bg, v_col = "Aggressive Compounder", colors['success_bg'], colors['success_text']
        elif reinvest > 1.00: 
            v_txt, v_bg, v_col = "External Funding (>100%)", colors['error_bg'], colors['error_text']
        else: 
            v_txt, v_bg, v_col = "Moderate Reinvestment", colors['blue_bg'], colors['blue_text']

        st.subheader(f"{meta.get('name', ticker)} Analysis ({start_idx} - {end_idx})")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Compounder Score", f"{score:.1%}", "Target: >20%")
        m2.metric("ROIIC", f"{roiic:.1%}", "Target: >15%")
        m3.metric("Reinvestment Rate", f"{reinvest:.1%}", "Target: >80%")
        
        # HTML Table with Dynamic Colors
        table_html = f"""
        <table>
            <thead><tr><th>Metric</th><th>Value</th><th>Formula</th><th>Label</th></tr></thead>
            <tbody>
                <tr><td><b>Accumulated FCF</b></td><td>{format_currency(A1)}</td><td>∑ FCF</td><td><b>A1</b></td></tr>
                <tr><td><b>Increase in FCF</b></td><td>{format_currency(B1)}</td><td>FCF<sub>end</sub> - FCF<sub>start</sub></td><td><b>B1</b></td></tr>
                <tr><td><b>Increase in IC</b></td><td>{format_currency(A2)}</td><td>IC<sub>end</sub> - IC<sub>start</sub></td><td><b>A2</b></td></tr>
                <tr><td><b>ROIIC</b></td><td>{roiic:.1%}</td><td>B1 / A2</td><td><b>C1</b></td></tr>
                <tr><td><b>Reinvestment Rate</b></td><td>{reinvest:.1%}</td><td>A2 / A1</td><td><b>C2</b></td></tr>
                <tr style="background-color:{colors['surface_high']}"><td><b>Final Score</b></td><td>{score:.1%}</td><td>C1 × C2</td><td><b>Result</b></td></tr>
            </tbody>
        </table>
        """
        st.markdown(table_html, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="verdict-box" style="background-color:{v_bg}; border-color:{v_bg};">
            <span style="font-size:1.2rem;">🧬</span>
            <span style="color:{v_col}; font-weight:700;">Phase: {v_txt}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        st.write("")
        
        with st.expander("View Data"):
            st.markdown(f"""
            <small style="color: {colors['on_surface_variant']};">
            <b>QuickFS Data Mapping:</b><br>
            • Operating Cash Flow is named <b>Cash From Operations</b> on QuickFS Cash Flow Statement.<br>
            • CapEx is found under <b>Property, Plant, & Equipment</b> on QuickFS Cash Flow Statement.<br>
            • Total Assets and Total Current Liabilities are part of the <b>Balance Sheet</b>.
            </small>
            <br><br>
            """, unsafe_allow_html=True)
            
            df_display = df_slice.rename(columns={
                "OCF": "Operating Cash Flow",
                "Assets": "Total Assets",
                "Liabilities": "Total Current Liabilities"
            })
            st.dataframe(df_display.style.format("{:,.0f}"))
        
        with st.expander("The Compounder Formula Guide"):
            # Render the static white-themed HTML in a safe iframe
            components.html(html_guide, height=800, scrolling=True)
            
    else:
        st.warning("Select a range with at least 2 periods.")
