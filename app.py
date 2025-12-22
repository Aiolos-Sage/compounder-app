import streamlit as st
import requests
import pandas as pd

# --- PAGE CONFIG ---
st.set_page_config(page_title="Compounder Formula", page_icon="📈")

st.title("📈 Compounder Dashboard (Fiscal.ai)")
st.markdown("""
Identify high-quality compounders using **ROIIC** and **Reinvestment Rates**.
""")

# --- SECURE CONFIGURATION ---
# We retrieve the key from Streamlit Secrets to keep it safe.
try:
    API_KEY = st.secrets["FISCAL_API_KEY"]
except FileNotFoundError:
    st.error("Secrets file not found. Please set up your secrets.toml file.")
    st.stop()
except KeyError:
    st.error("API Key not found in secrets. Please add 'FISCAL_API_KEY' to your secrets.")
    st.stop()

BASE_URL = "https://api.fiscal.ai/v1/company/financials"

# --- INPUT SECTION ---
ticker_input = st.text_input(
    "Enter Company Key (Format: EXCHANGE_TICKER)", 
    value="NYSE_APG",
    help="Examples: NASDAQ_MSFT, NYSE_APG"
).strip().upper()

# --- HELPER FUNCTIONS ---
def find_col(df, candidates):
    """
    Helper to find the correct column name regardless of capitalization.
    """
    if df is None or df.empty: return None
    col_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in col_map:
            return df[col_map[cand.lower()]]
    return None

def fetch_fiscal_data(endpoint_type, company_key):
    """
    Fetches data using the 'As Reported' endpoints provided.
    Includes Headers and User-Agent to prevent 403 Blocking.
    """
    url = f"{BASE_URL}/{endpoint_type}/as-reported"
    
    # We send the key in the Header (Standard Practice) AND Query Param (User URL)
    # Adding a User-Agent is critical to not look like a bot.
    headers = {
        "X-API-KEY": API_KEY,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    params = {
        "companyKey": company_key,
        "periodType": "annual",
        "currency": "USD", # Standardize currency
        "apiKey": API_KEY  # Sending in both places ensures maximum compatibility
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            st.error(f"API Error ({endpoint_type}): {response.status_code}")
            try:
                # Print the exact error message from Fiscal.ai for debugging
                st.json(response.json())
            except:
                st.write(response.text)
            return pd.DataFrame()

        data = response.json()
        
        # Standardize Data (Fiscal.ai often wraps data in a 'data' key)
        rows = data.get('data', data) if isinstance(data, dict) else data
        
        if not rows: 
            return pd.DataFrame()
            
        df = pd.DataFrame(rows)
        
        # Handle Dates (fiscalDate or date)
        if 'fiscalDate' in df.columns:
            df['date'] = pd.to_datetime(df['fiscalDate'])
        elif 'date' in df.columns:
             df['date'] = pd.to_datetime(df['date'])
        
        if 'date' in df.columns:
            df = df.sort_values(by='date', ascending=True).set_index('date')
            
        return df

    except Exception as e:
        st.error(f"Connection Error: {e}")
        return pd.DataFrame()

# --- MAIN LOGIC ---
if st.button("Run Analysis"):
    if "_" not in ticker_input:
        st.warning("⚠️ Format required: EXCHANGE_TICKER (e.g., NYSE_APG)")
    else:
        with st.spinner(f"Fetching reports for {ticker_input}..."):
            
            # 1. Fetch Reports (Cash Flow & Balance Sheet)
            cf_df = fetch_fiscal_data("cash-flow-statement", ticker_input)
            bs_df = fetch_fiscal_data("balance-sheet", ticker_input)

            if cf_df.empty or bs_df.empty:
                st.error("No data returned. Check the ticker format or API limits.")
            else:
                # 2. Extract Columns (Smart Search for column variations)
                ocf = find_col(cf_df, ['operatingCashFlow', 'netCashProvidedByOperatingActivities', 'NetCashFromOperatingActivities'])
                capex = find_col(cf_df, ['capitalExpenditure', 'paymentsForCapitalExpenditure', 'capex'])
                assets = find_col(bs_df, ['totalAssets', 'assets'])
                curr_liab = find_col(bs_df, ['totalCurrentLiabilities', 'currentLiabilities'])

                # 3. Calculate Formula
                if ocf is not None and assets is not None:
                    # Clean optional columns
                    capex = capex if capex is not None else 0
                    curr_liab = curr_liab if curr_liab is not None else 0
                    
                    # Logic: FCF = OCF + CapEx (If CapEx is negative outflow, we add it. If positive, subtract.)
                    # We assume standard API return where outflows are negative.
                    fcf_series = ocf + capex
                    
                    # Logic: Invested Capital = Total Assets - Current Liabilities
                    ic_series = assets - curr_liab
                    
                    # Create Calculation DataFrame
                    df_calc = pd.DataFrame({
                        'FCF': fcf_series, 
                        'Invested_Capital': ic_series
                    }).dropna()

                    if len(df_calc) >= 2:
                        # 4. Compute Growth Metrics
                        start, end = df_calc.index[0], df_calc.index[-1]
                        
                        # Values
                        A1_accum_fcf = df_calc['FCF'].sum()
                        B1_delta_fcf = df_calc.loc[end, 'FCF'] - df_calc.loc[start, 'FCF']
                        A2_delta_ic = df_calc.loc[end, 'Invested_Capital'] - df_calc.loc[start, 'Invested_Capital']
                        
                        # Ratios
                        roiic = B1_delta_fcf / A2_delta_ic if A2_delta_ic != 0 else 0
                        reinvest = A2_delta_ic / A1_accum_fcf if A1_accum_fcf != 0 else 0
                        score = roiic * reinvest
                        
                        # --- DASHBOARD OUTPUT ---
                        st.divider()
                        st.subheader(f"Analysis: {ticker_input}")
                        st.caption(f"Period: {start.year} - {end.year}")
                        
                        # Top Metrics
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Compounder Score", f"{score:.1%}")
                        col2.metric("ROIIC", f"{roiic:.1%}")
                        col3.metric("Reinvestment Rate", f"{reinvest:.1%}")
                        
                        # Verdict Logic
                        if score > 0.15: 
                            st.success("✅ **High Probability Compounder** (>15%)")
                        elif score > 0.10: 
                            st.warning("⚠️ **Moderate Compounder** (10-15%)")
                        else: 
                            st.error("❌ **Low Efficiency** (<10%)")
                        
                        # Detailed Data View
                        with st.expander("View Underlying Data"):
                            st.write("Calculated Data (USD):")
                            st.dataframe(df_calc.style.format("${:,.0f}"))
                    else:
                        st.warning("Not enough historical data points to calculate growth (Need 2+ years).")
                else:
                    st.error("Could not identify required columns (OCF or Total Assets) in the API response.")
                    st.write("Columns found in Cash Flow:", cf_df.columns.tolist())
                    st.write("Columns found in Balance Sheet:", bs_df.columns.tolist())
