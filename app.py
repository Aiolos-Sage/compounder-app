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
    
    .block-container {{ max-width: 1200px; padding-top: 2rem; }}
    
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

# --- CUSTOM CARD RENDERER ---
def render_custom_card(title, value, target, description):
    return f"""
    <div style="
        background-color: {colors['surface']};
        border: 1px solid {colors['border']};
        border-radius: 12px;
        padding: 20px;
        height: 100%;
        display: flex;
        flex-direction: column;
        box-shadow: {colors['shadow']};
    ">
        <div style="margin-bottom: auto;">
            <div style="
                text-transform: uppercase;
                font-size: 0.75rem;
                font-weight: 700;
                color: {colors['on_surface_variant']};
                margin-bottom: 8px;
                letter-spacing: 0.5px;
            ">
                {title}
            </div>
            <div style="
                font-size: 2.2rem;
                font-weight: 700;
                color: {colors['primary']};
                margin-bottom: 12px;
            ">
                {value}
            </div>
            <div style="margin-bottom: 15px;">
                <span style="
                    background-color: {colors['success_bg']};
                    color: {colors['success_text']};
                    padding: 6px 12px;
                    border-radius: 16px;
                    font-size: 0.85rem;
                    font-weight: 600;
                ">
                    → Target: {target}
                </span>
            </div>
        </div>
        <div style="
            font-size: 0.85rem;
            color: {colors['on_surface_variant']};
            line-height: 1.4;
            padding-top: 12px;
            border-top: 1px solid {colors['border']};
        ">
            {description}
        </div>
    </div>
    """

# --- INFOGRAPHIC HTML ---
html_guide = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root{
      /* --- Material 3 Expressive-inspired tokens --- */
      --primary:#1a73e8; --on-primary:#ffffff; --primary-container:#e8f0fe;
      --secondary:#34a853; --secondary-container:rgba(52,168,83,.14);
      --tertiary:#fbbc04; --tertiary-container:rgba(251,188,4,.18);
      --error:#ea4335; --outline:rgba(31,31,31,.14);
      --surface:#ffffff; --surface-1:#fbfbfb;
      --surface-container-low:#f5f7fb; --surface-container:#f1f3f4;
      --surface-container-high:#e9eef6;
      --on-surface:#1f1f1f; --on-surface-variant:#5f6368;
      --shadow-1: 0 1px 2px rgba(0,0,0,.06), 0 2px 10px rgba(0,0,0,.06);
      --shadow-2: 0 6px 18px rgba(0,0,0,.10), 0 2px 6px rgba(0,0,0,.08);
      --r-xl: 28px; --r-lg: 22px; --r-md: 18px; --r-sm: 14px;
      font-size: 16px;
    }
    *{ box-sizing:border-box; }
    body{
      margin:0;
      background: #ffffff; /* FORCE WHITE BACKGROUND */
      color: var(--on-surface);
      font-family: Roboto, "Google Sans", sans-serif;
      font-size: 1rem; line-height: 1.45;
    }
    .page{ max-width: 1140px; margin: 0 auto; padding: 1.25rem 1.1rem 3rem; }
    
    .hero{
      position: relative; overflow: hidden; border-radius: var(--r-xl);
      border: 1px solid var(--outline);
      background: linear-gradient(135deg, rgba(26,115,232,.10), rgba(52,168,83,.08) 48%, rgba(251,188,4,.10));
      box-shadow: var(--shadow-2); padding: 1.35rem 1.35rem 1.2rem;
    }
    .title{ display:flex; gap: 1rem; align-items:flex-start; min-width: 0; }
    .mark{
      width: 54px; height: 54px; border-radius: 18px; background: var(--surface);
      border: 1px solid rgba(26,115,232,.18); box-shadow: var(--shadow-1);
      display:grid; place-items:center; flex: 0 0 auto;
    }
    h1{ margin:0; font-size: 2.25rem; font-weight: 800; letter-spacing: .2px; }
    .subtitle{ margin:.35rem 0 0; font-size: 1.05rem; color: rgba(31,31,31,.74); }
    .grid{ display:grid; gap: 1rem; margin-top: 1rem; }
    .card{
      border-radius: var(--r-xl); border: 1px solid var(--outline);
      background: rgba(255,255,255,.86); box-shadow: var(--shadow-1);
      padding: 1.15rem 1.15rem 1.05rem; position: relative; overflow:hidden;
    }
    .card:before{
      content:""; position:absolute; inset:-2px auto auto -2px; width: 10px; height: 100%;
      background: linear-gradient(180deg, rgba(26,115,232,.95), rgba(52,168,83,.75), rgba(251,188,4,.75));
      border-top-left-radius: var(--r-xl); border-bottom-left-radius: var(--r-xl); opacity: .85;
    }
    .card-header{ display:flex; gap: .85rem; align-items:flex-start; margin-bottom: .8rem; }
    .step{
      width: 40px; height: 40px; border-radius: 14px; background: var(--primary-container);
      border: 1px solid rgba(26,115,232,.18); display:grid; place-items:center;
      font-weight: 900; color: #174ea6; font-size: 1rem; flex: 0 0 auto;
    }
    h2{ margin: .1rem 0 0; font-size: 1.35rem; font-weight: 800; letter-spacing: .2px; }
    ul{ margin: .2rem 0 0 1.1rem; padding:0; font-size: 1rem; color: var(--on-surface); }
    li{ margin:.35rem 0; }
    .muted{ margin:.2rem 0 0; color: var(--on-surface-variant); font-size: 1rem; }
    .two-col{ display:grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .tile{
      border-radius: var(--r-lg); border: 1px solid rgba(31,31,31,.10);
      background: var(--surface-container); padding: 1rem; position: relative; overflow:hidden;
    }
    .tile h3{ margin:0 0 .5rem; font-size: 1.15rem; font-weight: 800; position: relative; z-index: 1; }
    .formula{
      font-family: ui-monospace, monospace; font-size: 1rem; padding: .65rem .75rem;
      border-radius: var(--r-md); border: 1px solid rgba(31,31,31,.14);
      background: rgba(255,255,255,.9); position: relative; z-index: 1;
      overflow-x:auto; white-space: nowrap;
    }
    .ratio-grid, .score-grid{ display:grid; gap: 1rem; align-items: stretch; }
    .ratio-grid { grid-template-columns: 1fr 1fr; }
    .score-grid { grid-template-columns: 1.1fr .9fr; }
    @media (max-width: 980px){ .ratio-grid, .score-grid, .two-col{ grid-template-columns: 1fr; } }
    .panel{
      border-radius: var(--r-lg); border: 1px solid rgba(31,31,31,.12);
      background: var(--surface-container-low); padding: 1rem; position: relative; overflow:hidden;
    }
    .panel h3{ margin:0; font-size: 1.15rem; font-weight: 900; }
    .panel p{ margin: .5rem 0 0; font-size: 1rem; color: rgba(31,31,31,.82); }
    .footer{
      border-radius: var(--r-xl); border: 1px solid var(--outline);
      background: rgba(255,255,255,.86); box-shadow: var(--shadow-1);
      padding: 1rem 1.15rem; color: rgba(31,31,31,.72); font-size: 1rem;
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="top">
        <div class="title">
          <div class="mark">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
              <path d="M4 18V6" stroke="#1a73e8" stroke-width="1.5" stroke-linecap="round"/>
              <path d="M4 18H20" stroke="#1a73e8" stroke-width="1.5" stroke-linecap="round"/>
              <path d="M7 15l4-5 3 3 4-6" stroke="#34a853" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div>
            <h1>The Compounder Formula</h1>
            <p class="subtitle">A framework to identify businesses that grow cash and reinvest it at high returns.</p>
          </div>
        </div>
      </div>
    </section>

    <div class="grid">
      <section class="card">
        <div class="card-header">
          <div class="step">1</div>
          <div><h2>What Is a Compounder?</h2></div>
        </div>
        <ul>
          <li>Generates significant free cash flow.</li>
          <li>Reinvests that cash at high rates of return.</li>
          <li><strong>Outcome:</strong> Rising intrinsic value over long periods.</li>
        </ul>
      </section>

      <section class="card">
        <div class="card-header">
          <div class="step">2</div>
          <div><h2>Key Inputs (Definitions)</h2></div>
        </div>
        <div class="two-col">
          <div class="tile">
            <h3>Free Cash Flow (FCF)</h3>
            <div class="formula">FCF = Operating Cash Flow − CapEx</div>
            <p class="muted"><strong>Meaning:</strong> Cash left after maintaining and growing assets.</p>
          </div>
          <div class="tile">
            <h3>Invested Capital (IC)</h3>
            <div class="formula">IC = Total Assets − Total Current Liabilities</div>
            <p class="muted"><strong>Meaning:</strong> Capital truly tied up in operations.</p>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-header">
          <div class="step">3</div>
          <div><h2>Two Core Ratios</h2></div>
        </div>
        <div class="ratio-grid">
          <div class="panel">
            <h3>ROIIC (Efficiency)</h3>
            <div class="formula">ROIIC = Δ FCF ÷ Δ IC</div>
            <p><strong>Target: >15-20%</strong> (Strong Moat)</p>
            <p class="muted">"For each $1 of new capital, how much new cash flow?"</p>
          </div>
          <div class="panel">
            <h3>Reinvestment Rate (Opportunity)</h3>
            <div class="formula">Reinvestment Rate = Δ IC ÷ Total FCF</div>
            <p><strong>Target: >80%</strong> (Aggressive Compounder)</p>
            <p class="muted">"How much of the cash generated is plowed back into growth?"</p>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-header">
          <div class="step">4</div>
          <div><h2>Final Compounder Score</h2></div>
        </div>
        <div class="panel" style="background: var(--surface-container);">
          <div class="formula">Score = ROIIC × Reinvestment Rate</div>
          <p><strong>Interpretation:</strong> This score approximates the sustainable growth rate of the company's intrinsic value.</p>
        </div>
      </section>
      
      <section class="footer">
        Tip: Use 5-10 year averages to smooth cycles and reduce one-off noise.
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
        
        # --- METRICS SECTION (CUSTOM HTML CARDS) ---
        m1, m2, m3 = st.columns(3)
        
        with m1:
            st.markdown(render_custom_card(
                "COMPOUNDER SCORE",
                f"{score:.1%}",
                ">20%",
                "High ROIIC (moat) plus high reinvestment rate (runway) identify the best long-term compounders."
            ), unsafe_allow_html=True)
            
        with m2:
            st.markdown(render_custom_card(
                "RETURN ON INCREMENTAL INVESTED CAPITAL (ROIIC)",
                f"{roiic:.1%}",
                ">15%",
                "Shows how efficiently the business allocates capital and how strong the moat is."
            ), unsafe_allow_html=True)
            
        with m3:
            st.markdown(render_custom_card(
                "REINVESTMENT RATE",
                f"{reinvest:.1%}",
                ">80%",
                "Shows how much reinvestment opportunity the business has and how long its growth runway might be."
            ), unsafe_allow_html=True)
        
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
            components.html(html_guide, height=2000, scrolling=True)
            
    else:
        st.warning("Select a range with at least 2 periods.")
