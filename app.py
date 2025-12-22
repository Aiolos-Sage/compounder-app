import streamlit as st
import requests
import pandas as pd
import numpy as np

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
def clean_value(val):
    """
    Extracts the numeric value if the API returns a dictionary (e.g. {'value': 100}).
    Otherwise returns the value as is.
    """
    if isinstance(val, dict):
        # Try common keys for values
        return val.get('value', val.get('raw', val.get('amount', 0)))
    return val

def fetch_and_process(endpoint_type, company_key):
    """
    Fetches data, unpacks 'metricsValues', and cleans nested dictionary values.
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
            
        # 2. Flatten 'metricsValues' and CLEAN data
        clean_rows = []
        for row in rows:
            base_data = {k: v for k, v in row.items() if k != 'metricsValues'}
            metrics = row.get('metricsValues', {})
            
            if isinstance(metrics, dict):
                # Clean every metric value in case it is nested
                cleaned_metrics = {k: clean_value(v) for k, v in metrics.items()}
                base_data.update(cleaned_metrics)
            
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
                try:
                    # 2. Extract Columns
                    # Note: We enforce float conversion to prevent type errors
                    
                    # Cash Flow
                    ocf_raw = cf_df.get('cash_flow_statement_cash_from_operating_activities')
                    capex_raw = cf_df.get('cash_flow_statement_capital_expenditure')
                    if capex_raw is None:
                        capex_raw = cf_df.get('cash_flow_statement_purchases_of_property_plant_and_equipment')

                    # Balance Sheet
                    assets_raw = bs_df.get('balance_sheet_total_assets')
                    curr_liab_raw = bs_df.get('balance_sheet_total_current_liabilities')

                    # 3. Safe Calculation
                    if ocf_raw is not None and assets_raw is not None:
                        # Ensure numeric (coerce errors to NaN, then fill 0)
                        ocf = pd.to_numeric(ocf_raw, errors='coerce').fillna(0)
                        capex = pd.to_numeric(capex_raw, errors='coerce').fillna(0) if capex_raw is not None else 0
                        
                        assets = pd.to_numeric(assets_raw, errors='coerce').fillna(0)
                        curr_liab = pd.to_numeric(curr_liab_raw, errors='coerce').fillna(0) if curr_liab_raw is not None else 0

                        # CALCULATION:
                        # If CapEx is negative (outflow), abs() makes it positive so we can subtract it (standardizing logic)
                        # FCF = OCF - |CapEx|
                        if isinstance(capex, (int, float)):
                            fcf_series = ocf - abs(capex)
                        else:
                            fcf_series = ocf - capex.abs()

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
                except Exception as e:
                    st.error(f"Calculation Error: {e}")
