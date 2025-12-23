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

# --- 1. PAGE CONFIG & STYLING ---
st.set_page_config(page_title="Compounder Formula (QuickFS)", page_icon="📊", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Roboto', sans-serif;
    }
    .block-container { max-width: 1200px; padding-top: 2rem; padding-bottom: 3rem; }
    
    h1 { font-weight: 700; color: #202124; margin-bottom: 0.5rem; }
    .subtitle { color: #5f6368; margin-bottom: 2rem; }

    /* Cards */
    div[data-testid="stMetric"] {
        background-color: #ffffff; padding: 20px; border-radius: 12px;
        border: 1px solid #e0e0e0; box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    }
    div[data-testid="stMetricValue"] { color: #1a73e8; font-weight: 700; font-size: 1.6rem; }
    
    /* Table */
    table {
        width: 100%; border-collapse: collapse; font-family: 'Roboto', sans-serif;
        margin-top: 20px; background-color: #ffffff; border-radius: 8px;
        overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    }
    th { text-align: left; color: #5f6368; font-weight: 600; background-color: #f8f9fa; padding: 12px 15px; }
    td { padding: 12px 15px; border-bottom: 1px solid #f1f3f4; color: #202124; }
    tr:last-child td { border-bottom: none; font-weight: bold; background-color: #f8f9fa; }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown("<h1>Compounder Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Powered by <strong>QuickFS</strong>. Analyze capital allocation efficiency.</div>", unsafe_allow_html=True)

# --- SECURE CONFIGURATION ---
try:
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("⚠️ API Key missing. Please add `QUICKFS_API_KEY` to your Streamlit Secrets.")
    st.stop()

# Optional: Gemini Configuration
has_gemini_key = False
if has_gemini_lib:
    try:
        GEMINI_KEY = st.secrets["GOOGLE_API_KEY"]
        genai.configure(api_key=GEMINI_KEY)
        has_gemini_key = True
    except (FileNotFoundError, KeyError):
        has_gemini_key = False

# --- HELPER FUNCTIONS ---
def format_currency(val):
    if val is None or pd.isna(val): return "N/A"
    abs_val = abs(val)
    if abs_val >= 1e9: return f"${val/1e9:,.2f} B"
    if abs_val >= 1e6: return f"${val/1e6:,.2f} M"
    return f"${val:,.0f}"

def fetch_quickfs_direct(ticker):
    """
    Directly hits the endpoint provided by the user.
    """
    base_url = "https://public-api.quickfs.net/v1/data/all-data"
    url = f"{base_url}/{ticker}"
    params = {"api_key": API_KEY}
    
    try:
        response = requests.get(url, params=params)
        
        if response.status_code == 404:
            return None, "Ticker not found. Check format (e.g., use 'IBM:US' not 'US:IBM')."
        if response.status_code == 403:
             return None, "API Key Invalid or Quota Exceeded."
        if response.status_code != 200:
            return None, f"API Error: {response.status_code}"
            
        data = response.json()
        if "data" not in data:
            return None, "Invalid data structure received from QuickFS."
            
        return data["data"], None
    except Exception as e:
        return None, f"Connection Error: {e}"

def smart_get(data_dict, keys_to_try):
    """
    Tries multiple potential key names for a metric.
    Returns the first list found, or None.
    """
    for k in keys_to_try:
        if k in data_dict:
            return data_dict[k], k 
    return None, None

# --- INPUT SECTION ---
with st.container():
    c1, c2 = st.columns([3, 1])
    
    with c1:
        ticker_input = st.text_input(
            "Enter Ticker (Format: SYMBOL:COUNTRY)", 
            value="APG:US",
            help="Examples: APG:US, MSFT:US, SHELL:LSE"
        ).strip().upper()
        
    with c2:
        timeframe = st.selectbox("Timeframe", ["5 Years", "10 Years", "20 Years"], index=1)
        limit_map = {"5 Years": 5, "10 Years": 10, "20 Years": 20}
        selected_limit = limit_map[timeframe]

st.divider()

# --- MAIN ANALYSIS ---
if st.button("🚀 Run Analysis", type="primary"):
    with st.spinner(f"Fetching data for {ticker_input} ..."):
        
        # 1. Fetch Data
        raw_data, error_msg = fetch_quickfs_direct(ticker_input)
        
        if error_msg:
            st.error(error_msg)
        else:
            try:
                # 2. Extract Annual Financials
                meta = raw_data.get("metadata", {})
                company_name = meta.get("name", ticker_input)
                currency = meta.get("currency", "USD")
                
                financials = raw_data.get("financials", {})
                annual = financials.get("annual", {})
                
                # --- 3. SMART KEY MAPPING (FIXED FOR YOUR DATA) ---
                
                # Operating Cash Flow (QuickFS usually uses 'cf_cfo' or 'cfo')
                cfo, cfo_key = smart_get(annual, ["cf_cfo", "cfo", "cash_flow_operating"])
                
                # CapEx
                capex, capex_key = smart_get(annual, ["capex", "capital_expenditures"])
                
                # Total Assets
                assets, assets_key = smart_get(annual, ["total_assets", "assets"])
                
                # Current Liabilities
                liab, liab_key = smart_get(annual, ["total_current_liabilities", "liabilities_current"])
                
                # Identify missing
                missing = []
                if cfo is None: missing.append("Operating Cash Flow (cf_cfo)")
                if capex is None: missing.append("CapEx")
                if assets is None: missing.append("Total Assets")
                if liab is None: missing.append("Total Current Liabilities")
                
                if missing:
                    st.error(f"Could not find the following metrics in QuickFS data: {', '.join(missing)}")
                    with st.expander("🛠️ Debug: See Available Data Keys"):
                        st.write(list(annual.keys()))
                else:
                    # 4. Create DataFrame
                    # Align lengths (QuickFS arrays are typically Oldest -> Newest)
                    min_len = min(len(cfo), len(capex), len(assets), len(liab))
                    
                    if min_len < 2:
                        st.warning("Insufficient historical data (Need 2+ years).")
                    else:
                        # Slice to shortest length (taking the most recent 'min_len' items)
                        df = pd.DataFrame({
                            "OCF": cfo[-min_len:],
                            "CapEx": capex[-min_len:],
                            "Assets": assets[-min_len:],
                            "Liabilities": liab[-min_len:]
                        })
                        
                        # Generate Years
                        if "period_end_date" in annual:
                             # Taking just the year "2024" from "2024-12"
                             raw_dates = annual["period_end_date"][-min_len:]
                             df.index = [d.split('-')[0] for d in raw_dates]
                        elif "fiscal_year" in annual:
                            df.index = annual["fiscal_year"][-min_len:]
                        else:
                            df.index = range(1, min_len + 1)

                        # 5. Formulas
                        # FCF = OCF - |CapEx|
                        df['FCF'] = df['OCF'] - df['CapEx'].abs()
                        df['IC'] = df['Assets'] - df['Liabilities']
                        
                        # 6. Timeframe Slice
                        if len(df) > selected_limit:
                            df_slice = df.tail(selected_limit)
                        else:
                            df_slice = df
                            
                        # 7. Final Calculations
                        start_idx, end_idx = df_slice.index[0], df_slice.index[-1]
                        
                        A1 = df_slice['FCF'].sum()
                        B1 = df_slice.loc[end_idx, 'FCF'] - df_slice.loc[start_idx, 'FCF']
                        A2 = df_slice.loc[end_idx, 'IC'] - df_slice.loc[start_idx, 'IC']
                        
                        roiic = B1 / A2 if A2 != 0 else 0
                        reinvest = A2 / A1 if A1 != 0 else 0
                        score = roiic * reinvest
                        
                        # Verdict Logic
                        if reinvest < 0.20:
                            v_txt, v_bg, v_col = "Cash Cow (Mature/Dividends)", "#fef7e0", "#b06000"
                        elif 0.80 <= reinvest <= 1.00:
                            v_txt, v_bg, v_col = "Aggressive Compounder", "#e6f4ea", "#137333"
                        elif reinvest > 1.00:
                            v_txt, v_bg, v_col = "External Funding (Investing > Earnings)", "#fce8e6", "#c5221f"
                        else:
                            v_txt, v_bg, v_col = "Moderate Reinvestment", "#e8f0fe", "#1967d2"

                        # --- RENDER RESULTS ---
                        st.markdown(f"<h3>{company_name} ({currency})</h3>", unsafe_allow_html=True)
                        st.caption(f"Analysis Period: {start_idx} - {end_idx}")

                        m1, m2, m3 = st.columns(3)
                        m1.metric("Compounder Score", f"{score:.1%}", "Target: >20%")
                        m2.metric("ROIIC", f"{roiic:.1%}", "Target: >15%")
                        m3.metric("Reinvestment Rate", f"{reinvest:.1%}", "Target: >80%")

                        # Table
                        table_html = f"""
                        <table>
                            <thead>
                                <tr><th>Notes</th><th>Value</th><th>Formula</th><th>Metric</th><th>Label</th></tr>
                            </thead>
                            <tbody>
                                <tr><td>Total FCF ({len(df_slice)} yrs)</td><td>{format_currency(A1)}</td><td>∑ FCF</td><td><b>Accumulated FCF</b></td><td><b>A1</b></td></tr>
                                <tr><td>FCF Growth</td><td>{format_currency(B1)}</td><td>FCF<sub>end</sub> - FCF<sub>start</sub></td><td><b>Increase in FCF</b></td><td><b>B1</b></td></tr>
                                <tr><td>Capital Invested</td><td>{format_currency(A2)}</td><td>IC<sub>end</sub> - IC<sub>start</sub></td><td><b>Increase in IC</b></td><td><b>A2</b></td></tr>
                                <tr><td>Return on New Capital</td><td>{roiic:.1%}</td><td>B1 / A2</td><td><b>ROIIC (>15%)</b></td><td><b>C1</b></td></tr>
                                <tr><td>% Reinvested</td><td>{reinvest:.1%}</td><td>A2 / A1</td><td><b>Reinvestment (>80%)</b></td><td><b>C2</b></td></tr>
                                <tr style="background-color:#f8f9fa"><td>Efficiency Score</td><td>{score:.1%}</td><td>C1 × C2</td><td><b>Final Score (>20%)</b></td><td><b>Result</b></td></tr>
                            </tbody>
                        </table>
                        """
                        st.markdown(table_html, unsafe_allow_html=True)

                        # Verdict
                        st.markdown(f"""
                        <div style="background-color:{v_bg}; padding:15px; border-radius:8px; margin-top:15px; border:1px solid {v_bg}; display:flex; align-items:center; gap:10px;">
                            <span style="font-size:1.2rem;">🧬</span>
                            <span style="color:{v_col}; font-weight:600;">Corporate Phase: {v_txt}</span>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # --- GEMINI AI INTEGRATION ---
                        st.write("")
                        st.subheader("🤖 AI Analyst")
                        
                        if has_gemini_lib and has_gemini_key:
                            if st.button("Generate AI Assessment"):
                                with st.spinner("Gemini is analyzing the financials..."):
                                    prompt = f"""
                                    Act as a senior financial analyst. Analyze the following "Compounder Score" data for {company_name}.
                                    
                                    DATA:
                                    - Period: {start_idx} to {end_idx}
                                    - ROIIC: {roiic:.1%}
                                    - Reinvestment Rate: {reinvest:.1%}
                                    - Final Compounder Score: {score:.1%}
                                    - Total FCF Generated: {format_currency(A1)}
                                    - FCF Growth: {format_currency(B1)}
                                    
                                    DEFINITIONS:
                                    - ROIIC > 15% is good.
                                    - Reinvestment Rate > 80% is aggressive. < 20% is a cash cow.
                                    
                                    TASK:
                                    Write a concise assessment. Is this a high-quality compounder? Comment on efficiency and allocation.
                                    """
                                    model = genai.GenerativeModel("gemini-1.5-flash")
                                    response = model.generate_content(prompt)
                                    st.markdown(response.text)
                        elif not has_gemini_lib:
                            st.warning("⚠️ Google AI library not found. Add `google-generativeai` to `requirements.txt`.")
                        elif not has_gemini_key:
                            st.info("To enable AI analysis, add `GOOGLE_API_KEY` to your secrets.")

                        # Data Expander
                        st.write("")
                        with st.expander("View Underlying Data"):
                            st.dataframe(df_slice.style.format("{:,.0f}"))

            except Exception as e:
                st.error(f"Calculation Error: {e}")
