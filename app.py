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

def format_currency(val):
    """Auto-formats to Billions (B) or Millions (M)"""
    if val is None: return "N/A"
    abs_val = abs(val)
    if abs_val >= 1e9:
        return f"${val/1e9:,.2f} B"
    elif abs_val >= 1e6:
        return f"${val/1e6:,.2f} M"
    else:
        return f"${val:,.0f}"

def fetch_data(endpoint_type, company_key, period="annual", limit=30):
    url = f"{BASE_URL}/{endpoint_type}/standardized"
    headers = {"X-API-KEY": API_KEY, "User-Agent": "StreamlitCompounder/6.0"}
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

limit_map = {
    "5 Years (Inc. YTD/TTM)": 5, "Last 5 Fiscal Years": 5,
    "10 Years (Inc. YTD/TTM)": 10, "Last 10 Fiscal Years": 10,
    "20 Years (Inc. YTD/TTM)": 20, "Last 20 Fiscal Years": 20
}
selected_limit = limit_map[timeframe_label]
include_ttm = "Inc." in timeframe_label

st.divider()

if target_company_key:
    # Title showing selected company
    company_name = selected_label.split('(')[0] if selected_label else target_company_key
    
    with st.spinner("Fetching Annual & Quarterly reports..."):
        cf_annual = fetch_data("cash-flow-statement", target_company_key, "annual")
        bs_annual = fetch_data("balance-sheet", target_company_key, "annual")
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
                    
                    fcf = ocf - capex.abs()
                    ic = assets - curr_liab
                    return pd.DataFrame({'FCF': fcf, 'Invested_Capital': ic}).dropna()

                df_calc = extract_series(cf_annual, bs_annual)
                
                # --- PROCESS TTM ---
                if include_ttm and not cf_q.empty and not bs_q.empty:
                    last_annual_date = df_calc.index[-1]
                    last_quarter_date = cf_q.index[-1]
                    
                    if last_quarter_date > last_annual_date:
                        last_4_q = cf_q.tail(4)
                        if len(last_4_q) == 4:
                            ocf_ttm = pd.to_numeric(last_4_q.get('cash_flow_statement_cash_from_operating_activities'), errors='coerce').fillna(0).sum()
                            capex_col = last_4_q.get('cash_flow_statement_capital_expenditure')
                            if capex_col is None: capex_col = last_4_q.get('cash_flow_statement_purchases_of_property_plant_and_equipment')
                            capex_ttm = pd.to_numeric(capex_col, errors='coerce').fillna(0).sum()
                            
                            fcf_ttm = ocf_ttm - abs(capex_ttm)
                            
                            latest_bs = bs_q.iloc[-1]
                            assets_ttm = float(clean_value(latest_bs.get('balance_sheet_total_assets', 0)))
                            liab_ttm = float(clean_value(latest_bs.get('balance_sheet_total_current_liabilities', 0)))
                            ic_ttm = assets_ttm - liab_ttm
                            
                            ttm_row = pd.DataFrame({'FCF': [fcf_ttm], 'Invested_Capital': [ic_ttm]}, index=[last_quarter_date])
                            df_calc = pd.concat([df_calc, ttm_row])

                # --- SLICE DATA ---
                if len(df_calc) > selected_limit:
                    df_final = df_calc.tail(selected_limit)
                else:
                    df_final = df_calc

                if len(df_final) >= 2:
                    start_idx, end_idx = df_final.index[0], df_final.index[-1]
                    
                    # Year Labels
                    try: s_yr = str(start_idx.year)
                    except: s_yr = str(start_idx)[:4]
                    
                    try:
                        # Determine if end is TTM
                        if include_ttm and end_idx > cf_annual.index[-1]:
                            e_yr = "TTM"
                            e_yr_sub = "TTM" # For formula subscript
                        else:
                            e_yr = str(end_idx.year)
                            e_yr_sub = str(end_idx.year)[-2:] # '24'
                            s_yr_sub = s_yr[-2:] # '15'
                    except:
                        e_yr = str(end_idx)[:4]
                        e_yr_sub = "End"

                    # --- CALCULATIONS ---
                    FCF_start = df_final.loc[start_idx, 'FCF']
                    FCF_end = df_final.loc[end_idx, 'FCF']
                    IC_start = df_final.loc[start_idx, 'Invested_Capital']
                    IC_end = df_final.loc[end_idx, 'Invested_Capital']

                    A1 = df_final['FCF'].sum()
                    B1 = FCF_end - FCF_start
                    A2 = IC_end - IC_start
                    
                    roiic = B1 / A2 if A2 != 0 else 0
                    reinvest = A2 / A1 if A1 != 0 else 0
                    score = roiic * reinvest
                    
                    st.header(f"{company_name} Compounder Analysis")
                    st.caption("(Values in Billions USD)")

                    # --- BUILD THE RESULT TABLE ---
                    # Columns: Notes | Value | Formula | Metric | Label
                    
                    # Row 1: A1
                    row_A1 = {
                        "Metric": "Accumulated Free Cash Flow",
                        "Label": "A1",
                        "Value": format_currency(A1),
                        "Formula": f"$\\sum FCF_{{{s_yr}-{e_yr}}}$",
                        "Notes": f"Total FCF generated over the last {len(df_final)} years"
                    }
                    
                    # Row 2: B1
                    row_B1 = {
                        "Metric": "Increase in Free Cash Flow",
                        "Label": "B1",
                        "Value": format_currency(B1),
                        "Formula": f"$FCF_{{{e_yr}}} - FCF_{{{s_yr}}}$",
                        "Notes": f"FCF grew from {format_currency(FCF_start)} ({s_yr}) to {format_currency(FCF_end)} ({e_yr})"
                    }
                    
                    # Row 3: A2
                    row_A2 = {
                        "Metric": "Increase in Invested Capital",
                        "Label": "A2",
                        "Value": format_currency(A2),
                        "Formula": f"$IC_{{{e_yr}}} - IC_{{{s_yr}}}$",
                        "Notes": "Capital invested to achieve this growth"
                    }
                    
                    # Row 4: C1
                    row_C1 = {
                        "Metric": "ROIIC",
                        "Label": "C1",
                        "Value": f"{roiic:.1%}",
                        "Formula": "$B1 / A2$",
                        "Notes": "Return on Incremental Invested Capital"
                    }
                    
                    # Row 5: C2
                    row_C2 = {
                        "Metric": "Reinvestment Rate",
                        "Label": "C2",
                        "Value": f"{reinvest:.1%}",
                        "Formula": "$A2 / A1$",
                        "Notes": "% of total FCF reinvested into the business"
                    }
                    
                    # Row 6: Result
                    row_Res = {
                        "Metric": "Compounder Score",
                        "Label": "Result",
                        "Value": f"**{score:.1%}**",
                        "Formula": "$C1 \\times C2$",
                        "Notes": "Measures overall compounding efficiency"
                    }

                    results_data = [row_A1, row_B1, row_A2, row_C1, row_C2, row_Res]
                    results_df = pd.DataFrame(results_data)

                    # --- RENDER TABLE WITH MARKDOWN (For Math) ---
                    # Streamlit dataframe doesn't render latex in cells easily, so we build a clean Markdown table.
                    
                    md_table = "| Notes | Value | Formula | Metric | Label |\n|---|---|---|---|---|\n"
                    for row in results_data:
                        md_table += f"| {row['Notes']} | {row['Value']} | {row['Formula']} | **{row['Metric']}** | **{row['Label']}** |\n"
                    
                    st.markdown(md_table)
                    
                    # --- EXPORT BUTTON ---
                    csv = results_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="⤓ Export to Sheets (CSV)",
                        data=csv,
                        file_name=f"{target_company_key}_compounder_analysis.csv",
                        mime="text/csv",
                    )
                    
                    # --- RAW DATA ---
                    with st.expander(f"View Underlying Data ({s_yr}-{e_yr})"):
                        st.dataframe(df_final.style.format("${:,.0f}"))

                else:
                    st.warning("Insufficient data.")
            except Exception as e:
                st.error(f"Calculation Error: {e}")
