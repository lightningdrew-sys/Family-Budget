import os
import time
from datetime import date, timedelta
import pandas as pd
from dotenv import load_dotenv
import streamlit as st
import plaid
from plaid.api import plaid_api
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

st.set_page_config(page_title="Family Budget Dashboard", page_icon="🏡", layout="centered")


@st.cache_data(ttl=600)
def fetch_sandbox_data():
    configuration = plaid.Configuration(
        host=plaid.Environment.Sandbox,
        api_key={
            'clientId': os.getenv('PLAID_CLIENT_ID'),
            'secret': os.getenv('PLAID_SECRET'),
        }
    )
    api_client = plaid.ApiClient(configuration)
    client = plaid_api.PlaidApi(api_client)

    try:
        # 🛠️ UPDATE THIS BLOCK TO WRAP 'transactions' IN THE Products TYPE:
        pt_request = SandboxPublicTokenCreateRequest(
            institution_id="ins_109508",
            initial_products=[Products('transactions')]  # <-- Changed from ["transactions"]
        )
        pt_response = client.sandbox_public_token_create(pt_request)
        public_token = pt_response['public_token']

        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = client.item_public_token_exchange(exchange_request)
        access_token = exchange_response['access_token']

        time.sleep(5)

        start_date = date.today() - timedelta(days=30)
        end_date = date.today()

        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options=TransactionsGetRequestOptions()
        )
        response = client.transactions_get(request)
        return response['transactions']

    except Exception as e:
        st.error(f"Failed to connect to Plaid Sandbox: {e}")
        return []


raw_transactions = fetch_sandbox_data()

st.title("🏡 Our Family Budget")
st.markdown("⚡ *Live Sandbox Data Stream*")

# 1. Row of Visual Metric Cards
st.subheader("Monthly Overview")
col1, col2, col3 = st.columns(3)

# Process some basic totals from the data for our cards
total_spent = sum(t['amount'] for t in raw_transactions if t['amount'] > 0)
grocery_spent = sum(t['amount'] for t in raw_transactions if 'Food and Drink' in t['category'])

col1.metric("Total Spent (30d)", f"${total_spent:,.2f}")
col2.metric("Groceries & Dining", f"${grocery_spent:,.2f}", "On Track")
col3.metric("Accounts Linked", "1 (Sandbox)")

st.divider()

# 2. Main Transaction Table
st.subheader("Recent Transactions")

if raw_transactions:
    # Convert Plaid's data structure into a clean Pandas dataframe for display
    data_list = []
    for t in raw_transactions:
        data_list.append({
            "Date": t['date'],
            "Description": t['name'],
            "Category": t['category'][0] if t['category'] else "Uncategorized",
            "Amount": f"${t['amount']:,.2f}"
        })

    df = pd.DataFrame(data_list)

    # Render a beautiful interactive table that handles search and sorting natively
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.warning("No transactions found or Plaid configuration missing.")

