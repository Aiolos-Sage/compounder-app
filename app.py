import streamlit as st
import requests
import pandas as pd
import numpy as np

# --- PAGE CONFIG ---
st.set_page_config(page_title="Compounder Formula", page_icon="📈", layout="wide")

st.title("📈 Compounder Dashboard (Fiscal.ai)")
st.markdown("Identify high-quality compounders using **ROIIC** and **Reinvestment Rates**.")

# --- SECURE CONFIGURATION ---
try:
    API_KEY = st.secrets["FISCAL_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("⚠️ API Key missing. Please add 'FISCAL_API_KEY' to your Streamlit Secrets.")
    st.stop()

BASE_URL = "https://api.fiscal.ai/v1/company/financials"
LIST_URL = "https://api.fiscal.ai/v2/companies-list"

# --- CACHED DATA LOADING (SEARCH FUNCTION) ---
@st.cache_data(ttl=3600) # Cache for 1 hour to prevent constant API hits
def get_company_map():
    """
    Fetches the list of companies to populate the search bar.
    """
    headers = {"X-API-KEY": API_KEY}
    # Fetching 3000 should cover most major global stocks. 
    # You can increase pageSize if needed, but it may slow down loading.
    params = {"pageNumber": 1, "pageSize": 3000, "apiKey": API_KEY}
    
    try:
        response = requests.get(LIST_URL, headers=headers, params=params)
        if response.status_code != 200:
            return {}
            
        data = response.json()
        rows = data.get('data', data) if isinstance(data, dict) else data
        
        # Create a dictionary: "Name (Ticker)" -> "EXCHANGE_TICKER"
        # Example: "Amazon.com Inc (AMZN)" -> "NASDAQ_AMZN"
        company_map = {}
        for row in rows:
            # Adjust these keys based on the actual API response for company list
            ticker = row.get('ticker', 'UNKNOWN')
            exchange = row.get('exchange', 'UNKNOWN')
            name = row.get('companyName', row.get('name', ticker))
            
            # Construct the ID needed for the API
            full_key = f"{exchange}_{ticker}"
            
            # Construct the Display Label
            display_label = f"{ticker} | {name} ({exchange})"
            
            company_map[display_label] = full_key
            
        return company_map
    except Exception:
        return {}

# --- SIDEBAR SEARCH ---
with st.sidebar:
    st.header("🔎 Stock Search")
    company_map = get_company_map()
    
    if company_map:
        selected_label = st.selectbox(
            "Search for a company:", 
            options=list(company_map.keys()),
            index=None,
            placeholder="Type Ticker or Name (e.g. Apple)..."
        )
        
        # Get the API Key (e.g. NASDAQ_AAPL) from the selection
        if selected_label:
            target_company_key = company_map[selected_label]
        else:
            target_company_key = None
    else:
        st.warning("Could not load company list. Please check API Key.")
        target_company_key = st.text_input("Enter Company Key manually:", "NASDAQ_AMZN")

# --- HELPER FUNCTIONS (DATA PROCESSING) ---
def clean_value(val):
    if isinstance(val, dict):
        return val.get('value', val.get('raw', val.get('amount', 0)))
    return val

def fetch_and_process(endpoint_type, company_key):
    url = f"{BASE_URL}/{endpoint_type}/standardized"
    headers = {"X-API-KEY": API_KEY, "User-Agent": "StreamlitCompounder/2.0"}
    params = {"companyKey": company_key, "periodType": "annual", "currency": "USD", "apiKey": API_KEY}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            st.error(f"API Error ({endpoint_type}): {response.status_code}")
            return pd.DataFrame()

        data = response.json()
        rows = data.get('data', data) if isinstance(data, dict) else data
        if not rows: return pd.DataFrame()
            
        clean_rows = []
        for row in rows:
            base_data = {k: v for k, v in row.items() if k != 'metricsValues'}
            metrics = row.get('metricsValues', {})
            if isinstance(metrics, dict):
                cleaned_metrics = {k: clean_value(v) for k, v in metrics.items()}
                base_data.update(cleaned_metrics)
            clean_rows.append(base_data)
            
        df = pd.DataFrame(clean_rows)
        
        # Date Handling
        date_col = None
        if 'reportDate' in df.columns: date_col = 'reportDate'
        elif 'fiscalDate' in df.columns: date_col = 'fiscalDate'
        elif 'date' in df.columns: date_col = 'date'
        
        if date_col:
            df['date_index'] = pd.to_datetime(df[date_col])
            df = df.sort_values(by='date_index', ascending=True).set_index('date_index')
        elif 'fiscalYear' in df.columns:
             df = df.sort_values(by='fiscalYear', ascending=True).set_index('fiscalYear')
            
        return df
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return pd.DataFrame()

# --- MAIN DASHBOARD LOGIC ---
if target_company_key:
    st.subheader(f"Analysis: {target_company_key}")
    
    if st.button("Run Analysis", type="primary"):
        with st.spinner(f"Fetching data for {target_company_key}..."):
            
            cf_df = fetch_and_process("cash-flow-statement", target_company_key)
            bs_df = fetch_and_process("balance-sheet", target_company_key)

            if cf_df.empty or bs_df.empty:
                st.error("No financial data found for this company.")
            else:
                try:
                    # Extract Columns
                    ocf_raw = cf_df.get('cash_flow_statement_cash_from_operating_activities')
                    capex_raw = cf_df.get('cash_flow_statement_capital_expenditure')
                    if capex_raw is None:
                        capex_raw = cf_df.get('cash_flow_statement_purchases_of_property_plant_and_equipment')

                    assets_raw = bs_df.get('balance_sheet_total_assets')
                    curr_liab_raw = bs_df.get('balance_sheet_total_current_liabilities')

                    if ocf_raw is not None and assets_raw is not None:
                        # Clean Data
                        ocf = pd.to_numeric(ocf_raw, errors='coerce').fillna(0)
                        capex = pd.to_numeric(capex_raw, errors='coerce').fillna(0) if capex_raw is not None else 0
                        assets = pd.to_numeric(assets_raw, errors='coerce').fillna(0)
                        curr_liab = pd.to_numeric(curr_liab_raw, errors='coerce').fillna(0) if curr_liab_raw is not None else 0

                        # Calculate
                        # FCF = OCF - |CapEx|
                        if isinstance(capex, (int, float)): fcf_series = ocf - abs(capex)
                        else: fcf_series = ocf - capex.abs()

                        ic_series = assets - curr_liab
                        
                        df_calc = pd.DataFrame({'FCF': fcf_series, 'Invested_Capital': ic_series}).dropna()

                        if len(df_calc) >= 2:
                            # Metrics
                            start_idx, end_idx = df_calc.index[0], df_calc.index[-1]
                            
                            try:
                                s_year = start_idx.year
                                e_year = end_idx.year
                            except AttributeError:
                                s_year, e_year = start_idx, end_idx

                            A1 = df_calc['FCF'].sum()
                            B1 = df_calc.loc[end_idx, 'FCF'] - df_calc.loc[start_idx, 'FCF']
                            A2 = df_calc.loc[end_idx, 'Invested_Capital'] - df_calc.loc[start_idx, 'Invested_Capital']
                            
                            roiic = B1 / A2 if A2 != 0 else 0
                            reinvest = A2 / A1 if A1 != 0 else 0
                            score = roiic * reinvest
                            
                            # Display
                            st.divider()
                            st.markdown(f"**Period Analyzed:** {s_year} - {e_year}")
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric("🏆 Compounder Score", f"{score:.1%}")
                            c2.metric("Efficiency (ROIIC)", f"{roiic:.1%}")
                            c3.metric("Reinvestment Rate", f"{reinvest:.1%}")
                            
                            if score > 0.15: st.success("✅ **High Probability Compounder**")
                            elif score > 0.10: st.warning("⚠️ **Moderate Compounder**")
                            else: st.error("❌ **Low Efficiency**")
                            
                            with st.expander("Show Calculation Data"):
                                st.dataframe(df_calc.style.format("${:,.0f}"))
                        else:
                            st.warning("Insufficient historical data (Need at least 2 years).")
                    else:
                        st.error("Required data columns (OCF/Assets) missing from API response.")
                except Exception as e:
                    st.error(f"Calculation Error: {e}")
else:
    st.info("👈 Please select a company from the sidebar to begin.")
