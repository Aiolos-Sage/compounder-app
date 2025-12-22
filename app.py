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
    headers = {"X-API-KEY": API_KEY}
    params = {"pageNumber": 1, "pageSize": 6000, "apiKey": API_KEY}
    try:
        response = requests.get(LIST_URL, headers=headers, params=params)
        if response.status_code != 200: return {}
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

def fetch_data(endpoint_type, company_key, period="annual", limit=30):
    """
    Fetches Standardized Financials for a specific period (Annual or Quarterly).
    """
    url = f"{BASE_URL}/{endpoint_type}/standardized"
    headers = {"X-API-KEY": API_KEY, "User-Agent": "StreamlitCompounder/5.0"}
    params = {"companyKey": company_key, "periodType": period, "currency": "USD", "limit": limit, "apiKey": API_KEY}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200: return pd.DataFrame()
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
        
        # Standardize Date Index
        date_col = None
        if 'reportDate' in df.columns: date_col = 'reportDate'
        elif 'fiscalDate' in df.columns: date_col = 'fiscalDate'
        elif 'date' in df.columns: date_col = 'date'
        
        if date_col:
            df['date_index'] = pd.to_datetime(df[date_col])
            df = df.sort_values(by='date_index', ascending=True).set_index('date_index')
            
        return df
    except Exception:
        return pd.DataFrame()

# --- MAIN LAYOUT ---
with st.spinner("Syncing company database..."):
    company_map = get_company_map()

st.write("") 
col_search, col_time = st.columns([3, 1])

with col_search:
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

with col_time:
    timeframe_label = st.selectbox(
        "⏱️ **Select Timeframe**",
        options=[
            "5 Years (Inc. YTD/TTM)",
            "Last 5 Fiscal Years",
            "10 Years (Inc. YTD/TTM)",
            "Last 10 Fiscal Years",
            "20 Years (Inc. YTD/TTM)",
            "Last 20 Fiscal Years"
        ],
        index=2
    )

# Logic Map
limit_map = {
    "5 Years (Inc. YTD/TTM)": 5, "Last 5 Fiscal Years": 5,
    "10 Years (Inc. YTD/TTM)": 10, "Last 10 Fiscal Years": 10,
    "20 Years (Inc. YTD/TTM)": 20, "Last 20 Fiscal Years": 20
}
selected_limit = limit_map[timeframe_label]
include_ttm = "Inc." in timeframe_label

st.divider()

if target_company_key:
    st.info(f"⚡ Analyzing **{target_company_key}** ...")
    
    with st.spinner("Fetching Annual & Quarterly reports..."):
        # 1. Fetch ANNUAL Data
        cf_annual = fetch_data("cash-flow-statement", target_company_key, "annual")
        bs_annual = fetch_data("balance-sheet", target_company_key, "annual")
        
        # 2. Fetch QUARTERLY Data (For TTM Calculation)
        cf_q = fetch_data("cash-flow-statement", target_company_key, "quarterly", limit=8)
        bs_q = fetch_data("balance-sheet", target_company_key, "quarterly", limit=4)

        if cf_annual.empty or bs_annual.empty:
            st.error(f"No annual data found for {target_company_key}.")
        else:
            try:
                # --- PROCESS ANNUAL DATA ---
                def extract_series(cf, bs):
                    ocf_raw = cf.get('cash_flow_statement_cash_from_operating_activities')
                    capex_raw = cf.get('cash_flow_statement_capital_expenditure')
                    if capex_raw is None: capex_raw = cf.get('cash_flow_statement_purchases_of_property_plant_and_equipment')
                    assets_raw = bs.get('balance_sheet_total_assets')
                    curr_liab_raw = bs.get('balance_sheet_total_current_liabilities')
                    
                    if ocf_raw is None or assets_raw is None: return None
                    
                    ocf = pd.to_numeric(ocf_raw, errors='coerce').fillna(0)
                    capex = pd.to_numeric(capex_raw, errors='coerce').fillna(0)
                    assets = pd.to_numeric(assets_raw, errors='coerce').fillna(0)
                    curr_liab = pd.to_numeric(curr_liab_raw, errors='coerce').fillna(0)
                    
                    # FCF = OCF - |CapEx|
                    fcf = ocf - capex.abs()
                    ic = assets - curr_liab
                    return pd.DataFrame({'FCF': fcf, 'Invested_Capital': ic}).dropna()

                df_calc = extract_series(cf_annual, bs_annual)
                
                # --- PROCESS TTM (The Upgrade) ---
                # Only if "Inc. YTD" is selected AND we have recent quarterly data
                if include_ttm and not cf_q.empty and not bs_q.empty:
                    last_annual_date = df_calc.index[-1]
                    last_quarter_date = cf_q.index[-1]
                    
                    # Check if we have new data since the last annual report
                    if last_quarter_date > last_annual_date:
                        # Get last 4 quarters for TTM Cash Flow
                        last_4_q = cf_q.tail(4)
                        if len(last_4_q) == 4:
                            # Summing quarters gives TTM
                            ocf_ttm = pd.to_numeric(last_4_q.get('cash_flow_statement_cash_from_operating_activities'), errors='coerce').fillna(0).sum()
                            
                            capex_col = last_4_q.get('cash_flow_statement_capital_expenditure')
                            if capex_col is None: capex_col = last_4_q.get('cash_flow_statement_purchases_of_property_plant_and_equipment')
                            capex_ttm = pd.to_numeric(capex_col, errors='coerce').fillna(0).sum()
                            
                            fcf_ttm = ocf_ttm - abs(capex_ttm)
                            
                            # Balance Sheet is a SNAPSHOT (Use latest quarter, do not sum)
                            latest_bs = bs_q.iloc[-1]
                            assets_ttm = float(clean_value(latest_bs.get('balance_sheet_total_assets', 0)))
                            liab_ttm = float(clean_value(latest_bs.get('balance_sheet_total_current_liabilities', 0)))
                            ic_ttm = assets_ttm - liab_ttm
                            
                            # Create TTM Row
                            ttm_row = pd.DataFrame({
                                'FCF': [fcf_ttm],
                                'Invested_Capital': [ic_ttm]
                            }, index=[last_quarter_date]) # Use latest Q date
                            
                            # Append to main dataframe
                            df_calc = pd.concat([df_calc, ttm_row])

                # --- SLICE DATA ---
                # Take the last N periods
                if len(df_calc) > selected_limit:
                    df_final = df_calc.tail(selected_limit)
                else:
                    df_final = df_calc

                if len(df_final) >= 2:
                    start_idx, end_idx = df_final.index[0], df_final.index[-1]
                    
                    # Labels
                    s_label = start_idx.year
                    # Check if end is TTM (if date > last fiscal year end)
                    if include_ttm and end_idx > cf_annual.index[-1]:
                        e_label = "TTM (Current)"
                    else:
                        e_label = end_idx.year

                    A1 = df_final['FCF'].sum()
                    B1 = df_final.loc[end_idx, 'FCF'] - df_final.loc[start_idx, 'FCF']
                    A2 = df_final.loc[end_idx, 'Invested_Capital'] - df_final.loc[start_idx, 'Invested_Capital']
                    
                    roiic = B1 / A2 if A2 != 0 else 0
                    reinvest = A2 / A1 if A1 != 0 else 0
                    score = roiic * reinvest
                    
                    # Display
                    st.success(f"**Analysis Complete ({s_label} - {e_label})**")
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Compounder Score", f"{score:.1%}", help="ROIIC x Reinvestment Rate")
                    c2.metric("ROIIC", f"{roiic:.1%}", help="Return on Incremental Invested Capital")
                    c3.metric("Reinvestment Rate", f"{reinvest:.1%}", help="% of Cash Flow reinvested")
                    
                    if score > 0.15: st.success("✅ **High Probability Compounder**")
                    elif score > 0.10: st.warning("⚠️ **Moderate Compounder**")
                    else: st.error("❌ **Low Efficiency**")
                    
                    with st.expander(f"View Underlying Data ({timeframe_label})"):
                        st.dataframe(df_final.style.format("${:,.0f}"))
                        
                    with st.expander("📘 Reference: The Compounder Formula Guide"):
                        st.markdown("""
                        ### 1. The Objective
                        Identify companies that generate cash and reinvest it at high rates of return.

                        ### 2. Core Definitions
                        * **FCF (Free Cash Flow):** Operating Cash Flow - CapEx
                        * **IC (Invested Capital):** Total Assets - Current Liabilities
                        * **TTM (Trailing Twelve Months):** Sum of the last 4 quarters. Used for "Current" data to ensure valid comparison with annual figures.

                        ### 3. The Ratios
                        * **ROIIC:** $\\Delta FCF / \\Delta IC$ (Target: >15-20%)
                        * **Reinvestment Rate:** $\\Delta IC / \\text{Accumulated FCF}$ (Target: 80-100%)
                        * **Score:** $ROIIC \\times Reinvestment$
                        """)
                else:
                    st.warning("Insufficient data.")
            except Exception as e:
                st.error(f"Calculation Error: {e}")
