import streamlit as st
import pandas as pd
import numpy as np
from quickfs import QuickFS  # Using the library from the GitHub repo

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

    /* Verdict Tags */
    .verdict-tag { padding: 4px 12px; border-radius: 16px; font-size: 0.85rem; font-weight: 500; margin-top: 5px; display: inline-block; }
    .v-green { background-color: #e6f4ea; color: #137333; }
    .v-blue { background-color: #e8f0fe; color: #1967d2; }
    .v-yellow { background-color: #fef7e0; color: #b06000; }
    .v-red { background-color: #fce8e6; color: #c5221f; }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown("<h1>Compounder Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Powered by <strong>QuickFS SDK</strong>. Analyze capital allocation efficiency.</div>", unsafe_allow_html=True)

# --- SECURE CONFIGURATION ---
try:
    # Use the same key variable name for consistency
    API_KEY = st.secrets["QUICKFS_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("⚠️ API Key missing. Please add `QUICKFS_API_KEY` to your Streamlit Secrets.")
    st.stop()

# --- HELPER FUNCTIONS ---
def format_currency(val):
    if val is None or pd.isna(val): return "N/A"
    abs_val = abs(val)
    if abs_val >= 1e9: return f"${val/1e9:,.2f} B"
    if abs_val >= 1e6: return f"${val/1e6:,.2f} M"
    return f"${val:,.0f}"

def get_data_from_sdk(ticker):
    """
    Uses the QuickFS library to fetch full data.
    """
    try:
        # Initialize Client as per LautaroParada/quickfs documentation
        client = QuickFS(API_KEY)
        
        # 'get_data_full' pulls metadata + all financial statements in one go
        response = client.get_data_full(symbol=ticker)
        
        return response
    except Exception as e:
        return None

# --- INPUT SECTION ---
with st.container():
    c1, c2 = st.columns([3, 1])
    
    with c1:
        ticker_input = st.text_input(
            "Enter Ticker (Format: EXCHANGE:SYMBOL)", 
            value="US:MSFT",
            help="Examples: US:AAPL, LSE:SHELL, TSX:SHOP"
        ).strip().upper()
        
    with c2:
        timeframe = st.selectbox(
            "Timeframe",
            ["5 Years", "10 Years", "20 Years"],
            index=1
        )
        limit_map = {"5 Years": 5, "10 Years": 10, "20 Years": 20}
        selected_limit = limit_map[timeframe]

st.divider()

# --- MAIN ANALYSIS ---
if st.button("🚀 Run Analysis", type="primary"):
    with st.spinner(f"Fetching data for {ticker_input} using QuickFS SDK..."):
        
        # 1. Fetch Data using SDK
        data = get_data_from_sdk(ticker_input)
        
        if not data:
            st.error("Connection Error: Could not retrieve data. Check your API Key and Ticker format.")
        elif "error" in data:
             # QuickFS sometimes returns {'error': '...'}
             st.error(f"API Error: {data['error']}")
        else:
            try:
                # 2. Extract Data
                # The SDK returns the raw JSON structure from QuickFS
                metadata = data.get("metadata", {})
                financials = data.get("financials", {})
                annual = financials.get("annual", {})
                
                company_name = metadata.get("name", ticker_input)
                currency = metadata.get("currency", "USD")

                # 3. Create DataFrame
                # QuickFS arrays are typically [Oldest .... Newest]
                # We extract the specific metrics for the Compounder Formula
                
                # Check if data exists
                if not annual:
                    st.error("No annual data found for this ticker.")
                else:
                    # Metrics mapping (QuickFS keys)
                    # cfo = Operating Cash Flow
                    # capex = Capital Expenditures
                    # assets = Total Assets
                    # liabilities_current = Total Current Liabilities
                    
                    cfo = annual.get("cfo", [])
                    capex = annual.get("capex", [])
                    assets = annual.get("assets", [])
                    liab = annual.get("liabilities_current", [])
                    
                    # Handle Dates (fiscal_year is usually provided)
                    years = annual.get("fiscal_year", [])
                    
                    # Ensure all arrays align to the shortest length
                    min_len = min(len(cfo), len(capex), len(assets), len(liab), len(years))
                    
                    if min_len < 2:
                        st.warning("Not enough historical data to calculate compounder score (Need 2+ years).")
                    else:
                        # Slice to valid length
                        df = pd.DataFrame({
                            "Year": years[-min_len:],
                            "OCF": cfo[-min_len:],
                            "CapEx": capex[-min_len:],
                            "Assets": assets[-min_len:],
                            "Liabilities": liab[-min_len:]
                        })
                        
                        df.set_index("Year", inplace=True)
                        
                        # 4. Calculate Variables
                        # FCF = OCF - |CapEx|
                        df['FCF'] = df['OCF'] - df['CapEx'].abs()
                        
                        # Invested Capital (Operating Approach)
                        df['IC'] = df['Assets'] - df['Liabilities']
                        
                        # 5. Filter by Timeframe
                        if len(df) > selected_limit:
                            df_slice = df.tail(selected_limit)
                        else:
                            df_slice = df
                            
                        # 6. Final Formulas
                        start_year = df_slice.index[0]
                        end_year = df_slice.index[-1]
                        
                        A1 = df_slice['FCF'].sum() # Accumulated FCF
                        
                        FCF_start = df_slice.loc[start_year, 'FCF']
                        FCF_end = df_slice.loc[end_year, 'FCF']
                        B1 = FCF_end - FCF_start # Growth in FCF
                        
                        IC_start = df_slice.loc[start_year, 'IC']
                        IC_end = df_slice.loc[end_year, 'IC']
                        A2 = IC_end - IC_start # Growth in IC
                        
                        # Ratios
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
                        st.caption(f"Analysis Period: {start_year} - {end_year}")

                        # Metrics
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

                        # Verdict Banner
                        st.markdown(f"""
                        <div style="background-color:{v_bg}; padding:15px; border-radius:8px; margin-top:15px; border:1px solid {v_bg}; display:flex; align-items:center; gap:10px;">
                            <span style="font-size:1.2rem;">🧬</span>
                            <span style="color:{v_col}; font-weight:600;">Corporate Phase: {v_txt}</span>
                        </div>
                        """, unsafe_allow_html=True)

                        # Data Expander
                        st.write("")
                        with st.expander("View Underlying Data"):
                            st.dataframe(df_slice.style.format("{:,.0f}"))

            except Exception as e:
                st.error(f"Calculation Error: {e}")
