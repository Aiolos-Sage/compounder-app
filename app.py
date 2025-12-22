import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- 1. PAGE CONFIG & GOOGLE MATERIAL CSS ---
st.set_page_config(page_title="Compounder Formula", page_icon="📊", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Roboto', sans-serif;
    }

    .block-container {
        padding-top: 3rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }

    h1 {
        font-weight: 700;
        color: #202124;
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        color: #5f6368;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }

    /* Metric Cards */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    }
    label[data-testid="stMetricLabel"] {
        font-size: 0.95rem;
        color: #5f6368;
        font-weight: 500;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a73e8;
    }
    div[data-testid="stMetricDelta"] {
        font-size: 0.85rem;
        color: #3c4043;
    }

    /* Table Styling */
    table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'Roboto', sans-serif;
        margin-top: 20px;
        background-color: #ffffff;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    }
    th {
        text-align: left;
        color: #5f6368;
        font-weight: 600;
        border-bottom: 2px solid #e0e0e0;
        padding: 12px 15px;
        background-color: #f8f9fa;
    }
    td {
        padding: 12px 15px;
        border-bottom: 1px solid #f1f3f4;
        color: #202124;
    }
    tr:last-child td {
        border-bottom: none;
        font-weight: bold;
        background-color: #f8f9fa;
    }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown("<h1>Compounder Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Analyze capital allocation efficiency using the Compounder Formula. (Source: Yahoo Finance)</div>", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def format_currency(val):
    if val is None or pd.isna(val): return "N/A"
    abs_val = abs(val)
    if abs_val >= 1e9:
        return f"${val/1e9:,.2f} B"
    elif abs_val >= 1e6:
        return f"${val/1e6:,.2f} M"
    else:
        return f"${val:,.0f}"

def get_yfinance_data(ticker_symbol):
    """
    Fetches data using yfinance (Free, No API Key).
    Returns Annual and Quarterly DataFrames for Cash Flow and Balance Sheet.
    """
    stock = yf.Ticker(ticker_symbol)
    
    # Fetch Data
    # yfinance returns data with Dates as Columns. We transpose to make Dates the Index.
    try:
        cf_annual = stock.cashflow.T
        bs_annual = stock.balance_sheet.T
        cf_q = stock.quarterly_cashflow.T
        bs_q = stock.quarterly_balance_sheet.T
        
        # Get Company Name
        try:
            info = stock.info
            name = info.get('longName', ticker_symbol)
        except:
            name = ticker_symbol
            
        return name, cf_annual, bs_annual, cf_q, bs_q
        
    except Exception as e:
        return None, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def process_financials(cf_df, bs_df):
    """
    Extracts FCF and Invested Capital from yfinance DataFrames.
    """
    if cf_df.empty or bs_df.empty: return None

    # yfinance Key Mapping
    # Note: Keys can vary slightly, so we use .get() with defaults
    try:
        # 1. Operating Cash Flow
        # yfinance usually calls it 'Operating Cash Flow' or 'Total Cash From Operating Activities'
        ocf = cf_df.get('Operating Cash Flow')
        if ocf is None: ocf = cf_df.get('Total Cash From Operating Activities')
        
        # 2. CapEx
        # yfinance CapEx is usually negative. We need the absolute value for subtraction.
        capex = cf_df.get('Capital Expenditure')
        if capex is None: capex = cf_df.get('Capital Expenditures')
        
        # 3. Invested Capital Components
        assets = bs_df.get('Total Assets')
        curr_liab = bs_df.get('Current Liabilities')
        if curr_liab is None: curr_liab = bs_df.get('Total Current Liabilities')

        # Validation
        if ocf is None or assets is None:
            return None

        # Clean NaNs
        ocf = ocf.fillna(0)
        capex = capex.fillna(0) if capex is not None else 0
        assets = assets.fillna(0)
        curr_liab = curr_liab.fillna(0) if curr_liab is not None else 0

        # Calculate Variables
        # FCF = OCF - |CapEx|  (Using abs ensures we subtract the cost)
        fcf_series = ocf - abs(capex)
        
        # IC = Total Assets - Current Liabilities
        ic_series = assets - curr_liab

        # Create DataFrame
        df = pd.DataFrame({
            'FCF': fcf_series,
            'Invested_Capital': ic_series
        })
        
        # Ensure Index is Datetime and Sorted
        df.index = pd.to_datetime(df.index)
        df = df.sort_index(ascending=True)
        
        return df.dropna()

    except Exception:
        return None

# --- INPUT SECTION ---
col_input, col_time = st.columns([2, 1])

with col_input:
    # yfinance doesn't support easy "search by name", so we use a text input for Ticker.
    ticker_input = st.text_input("Enter Ticker Symbol", value="GOOG", placeholder="e.g. AAPL, MSFT, NVDA").upper()

with col_time:
    timeframe_label = st.selectbox(
        "Timeframe",
        options=[
            "5 Years (Inc. YTD/TTM)", "Last 5 Fiscal Years",
            "10 Years (Inc. YTD/TTM)", "Last 10 Fiscal Years",
            "20 Years (Inc. YTD/TTM)", "Last 20 Fiscal Years"
        ],
        index=2
    )

limit_map = {
    "5 Years (Inc. YTD/TTM)": 5, "Last 5 Fiscal Years": 5,
    "10 Years (Inc. YTD/TTM)": 10, "Last 10 Fiscal Years": 10,
    "20 Years (Inc. YTD/TTM)": 20, "Last 20 Fiscal Years": 20
}
selected_limit = limit_map[timeframe_label]
include_ttm = "Inc." in timeframe_label

st.divider()

# --- MAIN LOGIC ---
if st.button("Run Analysis", type="primary"):
    with st.spinner(f"Fetching data for {ticker_input} from Yahoo Finance..."):
        
        # 1. Fetch Raw Data
        name, cf_annual, bs_annual, cf_q, bs_q = get_yfinance_data(ticker_input)
        
        if cf_annual.empty:
            st.error(f"Could not find financial data for **{ticker_input}**. Please check the ticker symbol.")
        else:
            # 2. Process Annual Data
            df_calc = process_financials(cf_annual, bs_annual)
            
            if df_calc is None or df_calc.empty:
                 st.error("Data incomplete (Missing OCF or Assets fields in Yahoo Finance data).")
            else:
                # 3. TTM Calculation (The "Pro" Logic)
                if include_ttm and not cf_q.empty and not bs_q.empty:
                    try:
                        last_annual_date = df_calc.index[-1]
                        
                        # Process Quarterly Data
                        df_q_calc = process_financials(cf_q, bs_q)
                        
                        if df_q_calc is not None:
                            last_quarter_date = df_q_calc.index[-1]
                            
                            # If we have newer quarterly data than annual
                            if last_quarter_date > last_annual_date:
                                # Get last 4 quarters
                                last_4_q = df_q_calc.tail(4)
                                if len(last_4_q) == 4:
                                    # Sum FCF for TTM
                                    fcf_ttm = last_4_q['FCF'].sum()
                                    
                                    # Take Latest Invested Capital (Snapshot)
                                    ic_ttm = last_4_q['Invested_Capital'].iloc[-1]
                                    
                                    # Append TTM Row
                                    ttm_row = pd.DataFrame({
                                        'FCF': [fcf_ttm],
                                        'Invested_Capital': [ic_ttm]
                                    }, index=[last_quarter_date])
                                    
                                    df_calc = pd.concat([df_calc, ttm_row])
                    except Exception as e:
                        st.warning(f"Could not calculate TTM: {e}")

                # 4. Slice Data (Timeframe)
                if len(df_calc) > selected_limit:
                    df_final = df_calc.tail(selected_limit)
                else:
                    df_final = df_calc

                if len(df_final) >= 2:
                    # 5. Calculate Formulas
                    start_date = df_final.index[0]
                    end_date = df_final.index[-1]
                    
                    # Labels
                    s_yr = start_date.year
                    e_yr = "TTM" if (include_ttm and end_date > cf_annual.index.max()) else end_date.year
                    
                    A1 = df_final['FCF'].sum()
                    
                    FCF_start = df_final.loc[start_date, 'FCF']
                    FCF_end = df_final.loc[end_date, 'FCF']
                    B1 = FCF_end - FCF_start
                    
                    IC_start = df_final.loc[start_date, 'Invested_Capital']
                    IC_end = df_final.loc[end_date, 'Invested_Capital']
                    A2 = IC_end - IC_start
                    
                    # Ratios
                    roiic = B1 / A2 if A2 != 0 else 0
                    reinvest = A2 / A1 if A1 != 0 else 0
                    score = roiic * reinvest
                    
                    # 6. Verdict Logic
                    verdict_text = ""
                    bg_color = ""
                    text_color = ""
                    
                    if reinvest < 0.20:
                        verdict_text = "Cash Cow (Mature, low growth, distributes dividends)"
                        bg_color = "#fef7e0"
                        text_color = "#b06000"
                    elif 0.80 <= reinvest <= 1.00:
                        verdict_text = "Aggressive Compounder"
                        bg_color = "#e6f4ea"
                        text_color = "#137333"
                    elif reinvest > 1.00:
                        verdict_text = "Company is investing more than it earns (funding via debt or equity)"
                        bg_color = "#fce8e6"
                        text_color = "#c5221f"
                    else:
                        verdict_text = "Moderate Reinvestment (Standard Growth)"
                        bg_color = "#e8f0fe"
                        text_color = "#1967d2"

                    # --- RENDER RESULTS ---
                    st.markdown(f"<h3>{name} ({ticker_input}) Analysis ({s_yr} - {e_yr})</h3>", unsafe_allow_html=True)

                    m1, m2, m3 = st.columns(3)
                    m1.metric("Compounder Score", f"{score:.1%}", "Target: >20%")
                    m2.metric("ROIIC", f"{roiic:.1%}", "Target: >15%")
                    m3.metric("Reinvestment Rate", f"{reinvest:.1%}", "Target: >80%")

                    # Table
                    table_md = "| Notes | Value | Formula | Metric | Label |\n|---|---|---|---|---|\n"
                    rows_data = [
                        {"N": f"Total FCF generated ({len(df_final)} yrs)", "V": format_currency(A1), "F": f"$\\sum FCF$", "M": "Accumulated FCF", "L": "A1"},
                        {"N": f"FCF growth: {format_currency(FCF_start)} → {format_currency(FCF_end)}", "V": format_currency(B1), "F": f"$FCF_{{end}} - FCF_{{start}}$", "M": "Increase in FCF", "L": "B1"},
                        {"N": "Capital invested to achieve growth", "V": format_currency(A2), "F": f"$IC_{{end}} - IC_{{start}}$", "M": "Increase in IC", "L": "A2"},
                        {"N": "Return on New Capital", "V": f"{roiic:.1%}", "F": "$B1 / A2$", "M": "ROIIC (>15% Target)", "L": "C1"},
                        {"N": "% of FCF reinvested", "V": f"{reinvest:.1%}", "F": "$A2 / A1$", "M": "Reinvestment (>80% Target)", "L": "C2"},
                        {"N": "Compounder Efficiency Score", "V": f"**{score:.1%}**", "F": "$C1 \\times C2$", "M": "Score (>20% Target)", "L": "Result"},
                    ]
                    
                    for r in rows_data:
                        table_md += f"| {r['N']} | {r['V']} | {r['F']} | **{r['M']}** | **{r['L']}** |\n"

                    st.markdown(table_md, unsafe_allow_html=True)

                    # Verdict Banner
                    st.markdown(f"""
                    <div style="
                        background-color: {bg_color}; 
                        padding: 16px; 
                        border-radius: 8px; 
                        margin-top: 15px; 
                        border: 1px solid {bg_color};
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    ">
                        <span style="font-size: 1.2rem;">🧬</span>
                        <span style="color: {text_color}; font-weight: 600; font-size: 1rem;">
                            Corporate Phase: {verdict_text}
                        </span>
                    </div>
                    """, unsafe_allow_html=True)

                    # Footer
                    st.write("")
                    with st.expander(f"View Underlying Data ({s_yr}-{e_yr})"):
                        st.dataframe(df_final.style.format("${:,.0f}"), use_container_width=True)
                    
                    with st.expander("📘 Reference: Formula Guide"):
                        st.markdown("""
                        **FCF (Free Cash Flow)** = Operating Cash Flow - CapEx  
                        **IC (Invested Capital)** = Total Assets - Current Liabilities  
                        **ROIIC** = $\Delta$ FCF / $\Delta$ IC (Target > 15%)  
                        **Reinvestment Rate** = $\Delta$ IC / Accumulated FCF (Target > 80%)  
                        """)
                
                else:
                    st.warning("Insufficient historical data found.")
