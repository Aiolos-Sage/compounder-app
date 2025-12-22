import streamlit as st
import requests
import pandas as pd

# --- CONFIGURATION ---
API_KEY = "56753137-4528-4f1e-82a7-160461b4f57e"
BASE_URL = "https://api.fiscal.ai/v1/company/financials"

st.set_page_config(page_title="Compounder Formula", page_icon="📈")

st.title("📈 Compounder Dashboard (Fiscal.ai)")
st.markdown("""
Identify high-quality compounders using **ROIIC** and **Reinvestment Rates**.
""")

# --- INPUT SECTION ---
# Fiscal.ai requires EXCHANGE_TICKER format. We give examples to the user.
ticker_input = st.text_input(
    "Enter Company Key (Format: EXCHANGE_TICKER)", 
    value="NASDAQ_MSFT",
    help="Examples: NASDAQ_MSFT, NYSE_APG, LSE_AHT"
).strip().upper()

# --- HELPER FUNCTIONS ---
def find_col(df, candidates):
    """
    Helper to find the correct column name from 'As Reported' data,
    since API keys might vary slightly (e.g. 'totalAssets' vs 'TotalAssets').
    """
    # Create a lower-case map of existing columns
    col_map = {c.lower(): c for c in df.columns}
    
    for cand in candidates:
        if cand.lower() in col_map:
            return df[col_map[cand.lower()]]
    return None

def fetch_fiscal_data(endpoint_type, company_key):
    """
    Fetches data from the specific Fiscal.ai endpoints provided.
    """
    # Construct URL based on the user's provided endpoints
    url = f"{BASE_URL}/{endpoint_type}/as-reported"
    
    params = {
        "companyKey": company_key,
        "periodType": "annual",
        "apiKey": API_KEY
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Fiscal.ai usually returns a dict or list. We standardize to DataFrame.
        # We look for a 'data' key or assume the list is the root.
        rows = data.get('data', data) if isinstance(data, dict) else data
        
        if not rows:
            return pd.DataFrame()
            
        df = pd.DataFrame(rows)
        
        # Standardize Date Index
        if 'fiscalDate' in df.columns:
            df['date'] = pd.to_datetime(df['fiscalDate'])
        elif 'date' in df.columns:
             df['date'] = pd.to_datetime(df['date'])
        else:
            # Fallback if no date found, create a dummy index (risky but prevents crash)
            return pd.DataFrame()

        df = df.sort_values(by='date', ascending=True).set_index('date')
        return df

    except requests.exceptions.RequestException as e:
        st.error(f"API Error ({endpoint_type}): {e}")
        return pd.DataFrame()

# --- MAIN LOGIC ---
if st.button("Run Analysis"):
    if "_" not in ticker_input:
        st.warning("⚠️ Please use the format **EXCHANGE_TICKER** (e.g., NYSE_APG).")
    else:
        with st.spinner(f"Fetching Fiscal.ai reports for {ticker_input}..."):
            
            # 1. Fetch needed reports
            # We need Cash Flow (for FCF) and Balance Sheet (for Invested Capital)
            cf_df = fetch_fiscal_data("cash-flow-statement", ticker_input)
            bs_df = fetch_fiscal_data("balance-sheet", ticker_input)

            if cf_df.empty or bs_df.empty:
                st.error("No data found. Check the ticker format (e.g. NASDAQ_MSFT) and try again.")
            else:
                # 2. Extract Columns (Smart Search)
                # We search for common variations of the column names to be safe
                
                # Cash Flow Items
                ocf = find_col(cf_df, ['operatingCashFlow', 'netCashProvidedByOperatingActivities', 'NetCashFromOperatingActivities'])
                capex = find_col(cf_df, ['capitalExpenditure', 'capex', 'paymentsForCapitalExpenditure'])
                
                # Balance Sheet Items
                assets = find_col(bs_df, ['totalAssets', 'assets'])
                curr_liab = find_col(bs_df, ['totalCurrentLiabilities', 'currentLiabilities'])

                # Validation
                missing = []
                if ocf is None: missing.append("Operating Cash Flow")
                if assets is None: missing.append("Total Assets")
                
                if missing:
                    st.error(f"Could not find these columns in the API response: {', '.join(missing)}")
                    st.write("Available CF Cols:", cf_df.columns.tolist())
                    st.write("Available BS Cols:", bs_df.columns.tolist())
                else:
                    # Fill missing optional columns with 0 if necessary
                    capex = capex if capex is not None else 0
                    curr_liab = curr_liab if curr_liab is not None else 0

                    # 3. Calculate Formula
                    # FCF = OCF + CapEx (CapEx is usually negative in API, so we ADD. If it's positive, subtract.)
                    # Logic check: If CapEx is positive numbers, subtract. If negative, add. 
                    # We assume standard accounting (negative outflows).
                    fcf_series = ocf + capex
                    
                    # IC = Total Assets - Current Liabilities
                    ic_series = assets - curr_liab
                    
                    # Merge
                    df_calc = pd.DataFrame({
                        'FCF': fcf_series, 
                        'Invested_Capital': ic_series
                    }).dropna()

                    if len(df_calc) < 2:
                        st.error("Insufficient historical data points (need at least 2 years).")
                    else:
                        # 4. Compute Metrics
                        start_date = df_calc.index[0]
                        end_date = df_calc.index[-1]
                        
                        fcf_start = df_calc.loc[start_date, 'FCF']
                        fcf_end = df_calc.loc[end_date, 'FCF']
                        ic_start = df_calc.loc[start_date, 'Invested_Capital']
                        ic_end = df_calc.loc[end_date, 'Invested_Capital']

                        # Variables
                        A1_accumulated_fcf = df_calc['FCF'].sum()
                        B1_increase_fcf = fcf_end - fcf_start
                        A2_increase_ic = ic_end - ic_start

                        # Ratios
                        C1_roiic = B1_increase_fcf / A2_increase_ic if A2_increase_ic != 0 else 0
                        C2_reinvestment = A2_increase_ic / A1_accumulated_fcf if A1_accumulated_fcf != 0 else 0
                        score = C1_roiic * C2_reinvestment

                        # 5. Dashboard Output
                        st.divider()
                        st.subheader(f"Results for {ticker_input}")
                        st.caption(f"Period: {start_date.year} - {end_date.year}")

                        col1, col2, col3 = st.columns(3)
                        col1.metric("Compounder Score", f"{score:.1%}")
                        col2.metric("ROIIC (Efficiency)", f"{C1_roiic:.1%}")
                        col3.metric("Reinvestment Rate", f"{C2_reinvestment:.1%}")

                        if score > 0.15:
                            st.success("✅ **High Probability Compounder**")
                        elif score > 0.10:
                            st.warning("⚠️ **Moderate Compounder**")
                        else:
                            st.error("❌ **Low Efficiency / Capital Heavy**")

                        # Show Raw Data for verification
                        with st.expander("View Underlying Data"):
                            st.dataframe(df_calc.style.format("{:,.0f}"))
