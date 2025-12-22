import streamlit as st
import requests
import pandas as pd
import numpy as np

# --- 1. PAGE CONFIG & GOOGLE MATERIAL CSS ---
st.set_page_config(page_title="Compounder Formula", page_icon="📊", layout="wide")

# Custom CSS for Material Design Look
st.markdown("""
<style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Roboto', sans-serif;
    }

    /* Primary Container Styling (Card-like look) */
    .block-container {
        padding-top: 3rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }

    /* Header Styling */
    h1 {
        font-weight: 700;
        color: #202124; /* Google Black */
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        color: #5f6368; /* Google Gray */
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }

    /* Material Cards for Metrics */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
        transition: all 0.3s cubic-bezier(.25,.8,.25,1);
    }
    div[data-testid="stMetric"]:hover {
        box-shadow: 0 14px 28px rgba(0,0,0,0.25), 0 10px 10px rgba(0,0,0,0.22);
    }
    label[data-testid="stMetricLabel"] {
        font-size: 0.9rem;
        color: #5f6368;
        font-weight: 500;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a73e8; /* Google Blue */
    }

    /* Custom Button Styling (Material Pill) */
    .stButton > button {
        background-color: #1a73e8;
        color: white;
        border-radius: 24px;
        padding: 0.5rem 2rem;
        font-weight: 500;
        border: none;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        transition: background-color 0.2s, box-shadow 0.2s;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .stButton > button:hover {
        background-color: #174ea6;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }

    /* Report Card Styling */
    .report-card {
        background-color: #ffffff;
        border-radius: 16px;
        padding: 25px;
        margin-top: 20px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 1px 2px 0 rgba(60,64,67,0.3), 0 1px 3px 1px rgba(60,64,67,0.15);
    }
    
    /* Table Styling inside Markdown */
    table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'Roboto', sans-serif;
    }
    th {
        text-align: left;
        color: #5f6368;
        font-weight: 500;
        border-bottom: 2px solid #e0e0e0;
        padding: 10px;
    }
    td {
        padding: 12px 10px;
        border-bottom: 1px solid #f1f3f4;
        color: #202124;
    }
    tr:last-child td {
        border-bottom: none;
        font-weight: bold;
        background-color: #f8f9fa;
    }

    /* Dark Mode Overrides (Optional compatibility) */
    @media (prefers-color-scheme: dark) {
        h1, .subtitle, td { color: #e8eaed !important; }
        .report-card, div[data-testid="stMetric"] { background-color: #303134 !important; border-color: #5f6368 !important; }
        label[data-testid="stMetricLabel"] { color: #9aa0a6 !important; }
        div[data-testid="stMetricValue"] { color: #8ab4f8 !important; }
    }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown("<h1>Compounder Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Analyze capital allocation efficiency using the Compounder Formula.</div>", unsafe_allow_html=True)

# --- SECURE CONFIGURATION ---
try:
    API_KEY = st.secrets["FISCAL_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("⚠️ API Key missing. Please add 'FISCAL_API_KEY' to your Streamlit Secrets.")
    st.stop()

BASE_URL = "https://api.fiscal.ai/v1/company/financials"
LIST_URL = "https://api.fiscal.ai/v2/companies-list"

# --- LOGIC & HELPERS ---
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

def clean_value(val):
    if isinstance(val, dict):
        return val.get('value', val.get('raw', val.get('amount', 0)))
    return val

def format_currency(val):
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
    headers = {"X-API-KEY": API_KEY, "User-Agent": "StreamlitCompounder/7.0"}
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

# --- INPUT SECTION (Styled Container) ---
with st.container():
    with st.spinner("Connecting to database..."):
        company_map = get_company_map()

    col_search, col_time = st.columns([2, 1])
    
    with col_search:
        if company_map:
            selected_label = st.selectbox(
                "Select Company", 
                options=list(company_map.keys()),
                index=None,
                placeholder="Search by Ticker or Name (e.g. NVDA)...",
                label_visibility="visible"
            )
            target_company_key = company_map[selected_label] if selected_label else None
        else:
            st.error("Database Connection Failed.")
            target_company_key = None

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

st.write("") # Whitespace

# --- ANALYSIS EXECUTION ---
if target_company_key:
    company_name = selected_label.split('(')[0] if selected_label else target_company_key
    
    with st.spinner(f"Analyzing {company_name}..."):
        cf_annual = fetch_data("cash-flow-statement", target_company_key, "annual")
        bs_annual = fetch_data("balance-sheet", target_company_key, "annual")
        cf_q = fetch_data("cash-flow-statement", target_company_key, "quarterly", limit=8)
        bs_q = fetch_data("balance-sheet", target_company_key, "quarterly", limit=4)

        if cf_annual.empty or bs_annual.empty:
            st.warning(f"No annual data found for {company_name}.")
        else:
            try:
                # --- DATA PROCESSING ---
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
                
                # --- TTM LOGIC ---
                if include_ttm and not cf_q.empty and not bs_q.empty:
                    last_annual = df_calc.index[-1]
                    last_q = cf_q.index[-1]
                    if last_q > last_annual:
                        last_4 = cf_q.tail(4)
                        if len(last_4) == 4:
                            ocf_t = pd.to_numeric(last_4.get('cash_flow_statement_cash_from_operating_activities'), errors='coerce').fillna(0).sum()
                            cpx_col = last_4.get('cash_flow_statement_capital_expenditure')
                            if cpx_col is None: cpx_col = last_4.get('cash_flow_statement_purchases_of_property_plant_and_equipment')
                            cpx_t = pd.to_numeric(cpx_col, errors='coerce').fillna(0).sum()
                            fcf_t = ocf_t - abs(cpx_t)
                            
                            lbs = bs_q.iloc[-1]
                            ast_t = float(clean_value(lbs.get('balance_sheet_total_assets', 0)))
                            liab_t = float(clean_value(lbs.get('balance_sheet_total_current_liabilities', 0)))
                            ic_t = ast_t - liab_t
                            
                            ttm_row = pd.DataFrame({'FCF': [fcf_t], 'Invested_Capital': [ic_t]}, index=[last_q])
                            df_calc = pd.concat([df_calc, ttm_row])

                # --- SLICING ---
                if len(df_calc) > selected_limit:
                    df_final = df_calc.tail(selected_limit)
                else:
                    df_final = df_calc

                if len(df_final) >= 2:
                    start_idx, end_idx = df_final.index[0], df_final.index[-1]
                    
                    # Labels
                    try: s_yr = str(start_idx.year)
                    except: s_yr = str(start_idx)[:4]
                    try:
                        if include_ttm and end_idx > cf_annual.index[-1]: e_yr = "TTM"
                        else: e_yr = str(end_idx.year)
                    except: e_yr = str(end_idx)[:4]

                    # Values
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
                    
                    # --- RENDER RESULTS ---
                    
                    # 1. Header Card
                    st.markdown(f"<h3>{company_name} Analysis ({s_yr} - {e_yr})</h3>", unsafe_allow_html=True)
                    
                    # 2. Key Metrics Row
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Compounder Score", f"{score:.1%}")
                    m2.metric("ROIIC", f"{roiic:.1%}")
                    m3.metric
