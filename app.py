import streamlit as st
import requests
import pandas as pd
import numpy as np

# --- PAGE CONFIG ---
st.set_page_config(page_title="Compounder Formula", page_icon="📈", layout="wide")

st.title("📈 Compounder Dashboard")
st.markdown("Identify high-quality compounders using **ROIIC** and **Reinvestment Rates**.")

# --- SECURE CONFIGURATION ---
try:
    API_KEY = st.secrets["FISCAL_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("⚠️ API Key missing. Please add 'FISCAL_API_KEY' to your Streamlit Secrets.")
    st.stop()

BASE_URL = "https://api.fiscal.ai/v1/company/financials"
LIST_URL = "https://api.fiscal.ai/v2/companies-list"

# --- SMART EXCHANGE MAPPING ---
def normalize_exchange(exchange_name):
    """
    Converts raw exchange names (e.g., 'Nasdaq Global Select') 
    into the prefixes required by Fiscal.ai (e.g., 'NASDAQ').
    """
    if not exchange_name: return "UNKNOWN"
    name = str(exchange_name).upper()
    
    if "NASDAQ" in name: return "NASDAQ"
    if "NEW YORK" in name or "NYSE" in name: return "NYSE"
    if "LONDON" in name or "LSE" in name: return "LSE"
    if "TORONTO" in name or "TSX" in name: return "TSX"
    if "AMEX" in name: return "AMEX"
    if "OTC" in name: return "OTC"
    
    return name.split(' ')[0]

# --- CACHED DATA LOADING ---
@st.cache_data(ttl=3600)
def get_company_map():
    """
    Fetches company list and builds a smart map: 
    'NVIDIA (NVDA)' -> 'NASDAQ_NVDA'
    """
    headers = {"X-API-KEY": API_KEY}
    params = {"pageNumber": 1, "pageSize": 6000, "apiKey": API_KEY}
    
    try:
        response = requests.get(LIST_URL, headers=headers, params=params)
        if response.status_code != 200:
            return {}
            
        data = response.json()
        rows = data.get('data', data) if isinstance(data, dict) else data
        
        company_map = {}
        for row in rows:
            ticker = row.get('ticker')
            name = row.get('companyName', row.get('name', ticker))
            raw_exchange = row.get('exchangeName', row.get('exchange', 'UNKNOWN'))
            exchange_prefix = normalize_exchange(raw_exchange)
            
            if ticker and exchange_prefix != "UNKNOWN":
                full_key = f"{exchange_prefix}_{ticker}"
                label = f"{name} ({ticker})"
                company_map[label] = full_key
                
        return company_map
    except Exception:
        return {}

# --- HELPER FUNCTIONS ---
def clean_value(val):
    if isinstance(val, dict):
        return val.get('value', val.get('raw', val.get('amount', 0)))
    return val

def fetch_and_process(endpoint_type, company_key):
    url = f"{BASE_URL}/{endpoint_type}/standardized"
    headers = {"X-API-KEY": API_KEY, "User-Agent": "StreamlitCompounder/3.0"}
    params = {"companyKey": company_key, "periodType": "annual", "currency": "USD", "apiKey": API_KEY}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
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
    except Exception:
        return pd.DataFrame()

# --- MAIN LAYOUT ---

# 1. Load Data
with st.spinner("Syncing company database..."):
    company_map = get_company_map()

# 2. Search Bar
st.write("") 
if company_map:
    selected_label = st.selectbox(
        "🔎 **Search Company** (Type Ticker or Name)", 
        options=list(company_map.keys()),
        index=None,
        placeholder="e.g. NVDA, MSFT, Apple..."
    )
    target_company_key = company_map[selected_label] if selected_label else None
else:
    st.error("Could not connect to company database.")
    target_company_key = None

# 3. Auto-Run Analysis
st.divider()

if target_company_key:
    st.info(f"⚡ Analyzing **{target_company_key}** ...")
    
    with st.spinner("Fetching financial reports..."):
        cf_df = fetch_and_process("cash-flow-statement", target_company_key)
        bs_df = fetch_and_process("balance-sheet", target_company_key)

        if cf_df.empty or bs_df.empty:
            st.error(f"No financial data returned for {target_company_key}. The company might not have reported annual data yet.")
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
                    # Clean
                    ocf = pd.to_numeric(ocf_raw, errors='coerce').fillna(0)
                    capex = pd.to_numeric(capex_raw, errors='coerce').fillna(0) if capex_raw is not None else 0
                    assets = pd.to_numeric(assets_raw, errors='coerce').fillna(0)
                    curr_liab = pd.to_numeric(curr_liab_raw, errors='coerce').fillna(0) if curr_liab_raw is not None else 0

                    # Calc
                    if isinstance(capex, (int, float)): fcf_series = ocf - abs(capex)
                    else: fcf_series = ocf - capex.abs()
                    ic_series = assets - curr_liab
                    
                    df_calc = pd.DataFrame({'FCF': fcf_series, 'Invested_Capital': ic_series}).dropna()

                    if len(df_calc) >= 2:
                        # Metrics
                        start_idx, end_idx = df_calc.index[0], df_calc.index[-1]
                        try: s_year, e_year = start_idx.year, end_idx.year
                        except AttributeError: s_year, e_year = start_idx, end_idx

                        A1 = df_calc['FCF'].sum()
                        B1 = df_calc.loc[end_idx, 'FCF'] - df_calc.loc[start_idx, 'FCF']
                        A2 = df_calc.loc[end_idx, 'Invested_Capital'] - df_calc.loc[start_idx, 'Invested_Capital']
                        
                        roiic = B1 / A2 if A2 != 0 else 0
                        reinvest = A2 / A1 if A1 != 0 else 0
                        score = roiic * reinvest
                        
                        # Display
                        st.success(f"**Analysis Complete ({s_year} - {e_year})**")
                        
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Compounder Score", f"{score:.1%}", help="ROIIC x Reinvestment Rate")
                        c2.metric("ROIIC", f"{roiic:.1%}", help="Return on Incremental Invested Capital")
                        c3.metric("Reinvestment Rate", f"{reinvest:.1%}", help="% of Cash Flow reinvested")
                        
                        if score > 0.15: st.success("✅ **High Probability Compounder**")
                        elif score > 0.10: st.warning("⚠️ **Moderate Compounder**")
                        else: st.error("❌ **Low Efficiency**")
                        
                        # RAW DATA EXPANDER
                        with st.expander("View Calculation Data"):
                            st.dataframe(df_calc.style.format("${:,.0f}"))
                            
                        # --- NEW GUIDE EXPANDER ---
                        with st.expander("📘 Reference: The Compounder Formula Guide"):
                            st.markdown("""
                            ### 1. The Objective
                            The goal is to identify **"Compounders"**: companies that generate cash and reinvest it at high rates of return.
                            This combination is the most powerful engine for creating long-term shareholder value.

                            ### 2. Core Definitions
                            **A. Free Cash Flow (FCF)**
                            Actual cash remaining after maintenance and development of assets.
                            $$FCF = \\text{Operating Cash Flow} - \\text{Capital Expenditures}$$

                            **B. Invested Capital (Operating Approach)**
                            Total assets actually used in business operations.
                            $$Invested Capital = \\text{Total Assets} - \\text{Total Current Liabilities}$$

                            ### 3. The Calculation Process
                            We analyze a long period (typically 10 years) to smooth out volatility.
                            * **A1 (Accumulated FCF):** Sum of all FCF generated. (Total "fuel" produced).
                            * **B1 (Delta FCF):** $FCF_{end} - FCF_{start}$ (Growth in cash flow stream).
                            * **A2 (Delta IC):** $IC_{end} - IC_{start}$ (New capital added to balance sheet).

                            ### 4. The Efficiency Ratios
                            **Metric C1: Return on Incremental Invested Capital (ROIIC)**
                            $$ROIIC = \\frac{B1 \\ (\\Delta FCF)}{A2 \\ (\\Delta IC)}$$
                            *Target: >15-20% indicates a strong competitive advantage (Moat).*

                            **Metric C2: Reinvestment Rate**
                            $$\\text{Reinvestment Rate} = \\frac{A2 \\ (\\Delta IC)}{A1 \\ (\\text{Accumulated FCF})}$$
                            *Target: 80-100% indicates an aggressive compounder.*
                            *Interpretation: <20% is a Cash Cow; >100% is funding growth via debt/equity.*

                            ### 5. The Final Compounder Score
                            $$\\text{Score} = C1 \\times C2$$
                            This score approximates the sustainable growth rate of the company's intrinsic value.
                            """)

                    else:
                        st.warning("Insufficient historical data (Need 2+ years).")
                else:
                    st.error("Required data columns missing.")
            except Exception as e:
                st.error(f"Calculation Error: {e}")
