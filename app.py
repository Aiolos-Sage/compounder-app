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
def fetch_and_process(endpoint_type, company_key):
    """
    Fetches data, unpacks 'metricsValues', and standardizes dates.
    """
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
        
        # 1. Unpack Data
        rows = data.get('data', data) if isinstance(data, dict) else data
        if not rows: return pd.DataFrame()
            
        # 2. Flatten 'metricsValues' if present
        clean_rows = []
        for row in rows:
            base_data = {k: v for k, v in row.items() if k != 'metricsValues'}
            metrics = row.get('metricsValues', {})
            if isinstance(metrics, dict):
                base_data.update(metrics)
            clean_rows.append(base_data)
            
        df = pd.DataFrame(clean_rows)
        
        # 3. Handle Dates
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
        with st.spinner(f"Fetching data for {ticker_input}..."):
            
            # 1. Fetch Data
            cf_df = fetch_and_process("cash-flow-statement", ticker_input)
            bs_df = fetch_and_process("balance-sheet", ticker_input)

            if cf_df.empty or bs_df.empty:
                st.error("No data returned. Check the ticker format.")
            else:
                # 2. Extract Columns using EXACT keys from your error log
                try:
                    # CASH FLOW KEYS
                    ocf = cf_df.get('cash_flow_statement_cash_from_operating_activities')
                    
                    # Try primary CapEx key, then fallback to Purchases of PPE
                    capex = cf_df.get('cash_flow_statement_capital_expenditure')
                    if capex is None:
                        capex = cf_df.get('cash_flow_statement_purchases_of_property_plant_and_equipment')

                    # BALANCE SHEET KEYS
                    assets = bs_df.get('balance_sheet_total_assets')
                    curr_liab = bs_df.get('balance_sheet_total_current_liabilities')

                    # 3. Calculation
                    if ocf is not None and assets is not None:
                        # Handle missing CapEx/Liabilities safely
                        capex = capex if capex is not None else 0
                        curr_liab = curr_liab if curr_liab is not None else 0
                        
                        # CALCULATION LOGIC:
                        # FCF = OCF - CapEx (We subtract the absolute value to be safe, ensuring it's an outflow)
                        # "Purchases of PPE" is usually a positive number in these reports representing cost.
                        fcf_series = ocf - capex.abs()
                        
                        # IC = Total Assets - Current Liabilities
                        ic_series = assets - curr_liab
                        
                        # Merge
                        df_calc = pd.DataFrame({
                            'FCF': fcf_series, 
                            'Invested_Capital': ic_series
                        }).dropna()

                        if len(df_calc) >= 2:
                            # 4. Metrics
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
                            st.warning("Not enough historical data points.")
                    else:
                        st.error("Could not find required columns.")
                        st.write("Debug: OCF Found?", ocf is not None)
                        st.write("Debug: Assets Found?", assets is not None)
                except Exception as e:
                    st.error(f"Calculation Error: {e}")
