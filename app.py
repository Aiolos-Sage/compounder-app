import streamlit as st
import requests
import pandas as pd

# --- PAGE CONFIG ---
st.set_page_config(page_title="Compounder Formula", page_icon="📈")

st.title("📈 Compounder Dashboard")
st.markdown("""
Identify high-quality compounders using **ROIIC** and **Reinvestment Rates**.
""")

# --- SECURE CONFIGURATION ---
try:
    API_KEY = st.secrets["FISCAL_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("⚠️ API Key missing. Please add 'FISCAL_API_KEY' to your Streamlit Secrets.")
    st.stop()

BASE_URL = "https://api.fiscal.ai/v1/company/financials"

# --- INPUT SECTION ---
ticker_input = st.text_input(
    "Enter Company Key (Format: EXCHANGE_TICKER)", 
    value="NASDAQ_AMZN",
    help="Examples: NASDAQ_AMZN, NYSE_APG"
).strip().upper()

# --- HELPER FUNCTIONS ---
def find_col(df, candidates):
    """
    Finds a column from a list of potential names (case-insensitive).
    """
    if df is None or df.empty: return None
    col_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in col_map:
            return df[col_map[cand.lower()]]
    return None

def fetch_standardized_data(endpoint_type, company_key):
    """
    Fetches data from the STANDARDIZED endpoint.
    Automatically unpacks 'metricsValues' if present.
    """
    # URL Structure based on your reference
    url = f"{BASE_URL}/{endpoint_type}/standardized"
    
    headers = {
        "X-API-KEY": API_KEY,
        "User-Agent": "StreamlitCompounder/1.0"
    }
    
    params = {
        "companyKey": company_key,
        "periodType": "annual",
        "currency": "USD",
        "apiKey": API_KEY 
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            st.error(f"API Error ({endpoint_type}): {response.status_code}")
            return pd.DataFrame()

        data = response.json()
        
        # Standardize Data List
        rows = data.get('data', data) if isinstance(data, dict) else data
        if not rows: return pd.DataFrame()
            
        # --- ROBUST UNPACKING ---
        # Checks if data is flat or nested in 'metricsValues'
        clean_rows = []
        for row in rows:
            # If 'metricsValues' exists, extract it. Otherwise, use the row as is.
            base_data = {k: v for k, v in row.items() if k != 'metricsValues'}
            metrics = row.get('metricsValues', {})
            if isinstance(metrics, dict):
                base_data.update(metrics)
            clean_rows.append(base_data)
            
        df = pd.DataFrame(clean_rows)
        
        # Handle Dates (fiscalDate is standard, but we check both)
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
        st.warning("⚠️ Format required: EXCHANGE_TICKER (e.g., NASDAQ_AMZN)")
    else:
        with st.spinner(f"Fetching standardized data for {ticker_input}..."):
            
            # 1. Fetch Standardized Reports
            cf_df = fetch_standardized_data("cash-flow-statement", ticker_input)
            bs_df = fetch_standardized_data("balance-sheet", ticker_input)

            if cf_df.empty or bs_df.empty:
                st.error("No data returned. Check the ticker format.")
            else:
                # 2. Extract Columns (Using Standardized Keys)
                # Fiscal.ai standardized keys are typically camelCase or snake_case
                
                ocf = find_col(cf_df, ['operatingCashFlow', 'operating_cash_flow'])
                capex = find_col(cf_df, ['capitalExpenditure', 'capital_expenditure'])
                assets = find_col(bs_df, ['totalAssets', 'total_assets'])
                curr_liab = find_col(bs_df, ['totalCurrentLiabilities', 'total_current_liabilities'])

                # 3. Validation & Calculation
                if ocf is not None and assets is not None:
                    capex = capex if capex is not None else 0
                    curr_liab = curr_liab if curr_liab is not None else 0
                    
                    # Logic: FCF = OCF + CapEx (Standardized usually has negative CapEx)
                    fcf_series = ocf + capex
                    
                    # Logic: Invested Capital = Total Assets - Current Liabilities
                    ic_series = assets - curr_liab
                    
                    # Merge & Clean
                    df_calc = pd.DataFrame({
                        'FCF': fcf_series, 
                        'Invested_Capital': ic_series
                    }).dropna()

                    if len(df_calc) >= 2:
                        # 4. Compute Metrics
                        start, end = df_calc.index[0], df_calc.index[-1]
                        
                        A1 = df_calc['FCF'].sum()
                        B1 = df_calc.loc[end, 'FCF'] - df_calc.loc[start, 'FCF']
                        A2 = df_calc.loc[end, 'Invested_Capital'] - df_calc.loc[start, 'Invested_Capital']
                        
                        roiic = B1 / A2 if A2 != 0 else 0
                        reinvest = A2 / A1 if A1 != 0 else 0
                        score = roiic * reinvest
                        
                        # --- OUTPUT ---
                        st.divider()
                        st.subheader(f"Analysis: {ticker_input}")
                        st.caption(f"Period: {start.year} - {end.year}")
                        
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Compounder Score", f"{score:.1%}")
                        col2.metric("ROIIC", f"{roiic:.1%}")
                        col3.metric("Reinvestment Rate", f"{reinvest:.1%}")
                        
                        if score > 0.15: st.success("✅ **High Probability Compounder**")
                        elif score > 0.10: st.warning("⚠️ **Moderate Compounder**")
                        else: st.error("❌ **Low Efficiency**")
                        
                        with st.expander("View Underlying Data"):
                            st.dataframe(df_calc.style.format("${:,.0f}"))
                    else:
                        st.warning("Not enough historical data points (Need 2+ years).")
                else:
                    st.error("Could not find required columns in standardized data.")
                    st.write("Available CF Keys:", cf_df.columns.tolist())
                    st.write("Available BS Keys:", bs_df.columns.tolist())
