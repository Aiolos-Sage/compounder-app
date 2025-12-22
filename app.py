import streamlit as st
import requests
import pandas as pd

# --- CONFIGURATION ---
API_KEY = "56753137-4528-4f1e-82a7-160461b4f57e"
BASE_URL = "https://api.fiscal.ai/api/v1"

# --- PAGE SETUP ---
st.set_page_config(page_title="Compounder Formula", page_icon="📊")

st.title("📊 Compounder Formula Dashboard")
st.markdown("Calculate **ROIIC** and **Reinvestment Rates** to identify high-quality compounders.")

# --- INPUT ---
ticker_symbol = st.text_input("Enter Ticker Symbol", value="APG").upper()

# --- LOGIC ---
class CompounderCalculator:
    def __init__(self, ticker):
        self.ticker = ticker
        self.headers = {"X-API-KEY": API_KEY}
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_financials(self, statement_type):
        endpoint = f"{BASE_URL}/financials/standardized"
        params = {
            "ticker": self.ticker,
            "statement": statement_type,
            "period": "annual",
            "limit": 10
        }
        try:
            response = self.session.get(endpoint, params=params)
            if response.status_code == 403:
                st.error("API Error: Invalid Key or Access Denied.")
                return pd.DataFrame()
            response.raise_for_status()
            data = response.json()
            df = pd.DataFrame(data['data']) if 'data' in data else pd.DataFrame(data)
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values(by='date', ascending=True).set_index('date')
            return df
        except Exception as e:
            st.error(f"Error fetching {statement_type}: {e}")
            return pd.DataFrame()

    def run(self):
        with st.spinner(f"Fetching data for {self.ticker}..."):
            cf_df = self.get_financials("cash_flow")
            bs_df = self.get_financials("balance_sheet")

        if cf_df.empty or bs_df.empty:
            st.warning("Insufficient data found for this ticker.")
            return

        # Data Processing
        try:
            ocf = cf_df.get('operating_cash_flow')
            capex = cf_df.get('capital_expenditure')
            total_assets = bs_df.get('total_assets')
            current_liabilities = bs_df.get('total_current_liabilities')
            
            common_dates = ocf.index.intersection(total_assets.index)
            
            # Calculations
            fcf_series = ocf.loc[common_dates] + capex.loc[common_dates]
            ic_series = total_assets.loc[common_dates] - current_liabilities.loc[common_dates]
            
            df = pd.DataFrame({'FCF': fcf_series, 'Invested_Capital': ic_series}).dropna()

            if len(df) < 2:
                st.error("Need at least 2 years of data to calculate growth.")
                return
            
            # Formula Variables
            start_date, end_date = df.index[0], df.index[-1]
            fcf_start, fcf_end = df.loc[start_date, 'FCF'], df.loc[end_date, 'FCF']
            ic_start, ic_end = df.loc[start_date, 'Invested_Capital'], df.loc[end_date, 'Invested_Capital']
            
            A1_accumulated_fcf = df['FCF'].sum()
            B1_increase_fcf = fcf_end - fcf_start
            A2_increase_ic = ic_end - ic_start
            
            # Ratios
            C1_roiic = 0 if A2_increase_ic == 0 else B1_increase_fcf / A2_increase_ic
            C2_reinvestment = 0 if A1_accumulated_fcf == 0 else A2_increase_ic / A1_accumulated_fcf
            score = C1_roiic * C2_reinvestment

            # --- DISPLAY RESULTS ---
            st.divider()
            
            # Scorecard
            col1, col2, col3 = st.columns(3)
            col1.metric("Compounder Score", f"{score:.1%}")
            col2.metric("ROIIC (Efficiency)", f"{C1_roiic:.1%}")
            col3.metric("Reinvestment Rate", f"{C2_reinvestment:.1%}")

            # Verdict
            if score > 0.15:
                st.success("✅ VERDICT: High Probability Compounder")
            elif score > 0.10:
                st.warning("⚠️ VERDICT: Moderate Compounder")
            else:
                st.error("❌ VERDICT: Low Efficiency / Capital Heavy")

            # Detailed Data
            st.subheader("Data Breakdown")
            st.write(f"**Period Analyzed:** {start_date.year} - {end_date.year}")
            
            data_col1, data_col2 = st.columns(2)
            with data_col1:
                st.write("#### Growth Engine")
                st.write(f"**[B1] New FCF:** ${B1_increase_fcf/1e6:,.1f}M")
                st.write(f"**[A2] New Capital:** ${A2_increase_ic/1e6:,.1f}M")
            
            with data_col2:
                st.write("#### Base Metrics")
                st.write(f"**Start FCF:** ${fcf_start/1e6:,.1f}M")
                st.write(f"**End FCF:** ${fcf_end/1e6:,.1f}M")

        except Exception as e:
            st.error(f"Calculation Error: {e}")

# --- EXECUTION ---
if st.button("Run Analysis"):
    calc = CompounderCalculator(ticker_symbol)
    calc.run()
