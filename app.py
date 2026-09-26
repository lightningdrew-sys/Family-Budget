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

if os.path.exists('.env'):
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))
else:
    load_dotenv()

st.set_page_config(page_title="Family Budget Dashboard", page_icon="🏡", layout="centered")

if 'envelopes' not in st.session_state:
    st.session_state.envelopes = {
        "Groceries": 400.00,
        "Dining out": 150,
        "Auto": 100,
        "Unassigned": 0.00
    }

    if 'transaction_mappings' not in st.session_state:
        st.session_state.transaction_mappings = {}

@st.cache_data(ttl=600)
def fetch_sandbox_data():
    client_id = st.secrets.get("PLAID_CLIENT_ID") or os.getenv("PLAID_CLIENT_ID")
    secret_key = st.secrets.get("PLAID_SECRET") or os.getenv("PLAID_SECRET")

    configuration = plaid.Configuration(
        host=plaid.Environment.Sandbox,
        api_key={
            'clientId': client_id,
            'secret': secret_key,
        }
    )
    api_client = plaid.ApiClient(configuration)
    client = plaid_api.PlaidApi(api_client)

    try:
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

def auto_categorize(t_id, name, amount):
    if t_id in st.session_state.transaction_mappings:
        return st.session_state.transaction_mappings[t_id]

    name_lower = name.lower()
    if "walmart" in name_lower or "braums" in name_lower:
        return "Groceries"
    elif "esurance" in name_lower:
        return "auto"
    elif "mcdonalds" in name_lower:
        return "Dining out"
    return "Unassigned"


st.title("🏡 Our Family Budget")
st.markdown("Your Envelopes")

for env_name, budget_total in st.session_state.envelopes.items():
    if env_name == "Unassigned":
        continue
    spent = envelope_spending.get(env_name, 0.0)
    remaining = budget_total - spent

    # Render a progress bar for each active budget bucket
    progress_ratio = min(max(spent / budget_total, 0.0), 1.0) if budget_total > 0 else 0.0

    col_label, col_bar = st.columns([1, 2])
    with col_label:
        st.markdown(f"**{env_name}**  \n`${remaining:,.2f}` left of \${budget_total:,.2f}")
    with col_bar:
        st.write("")  # Tiny spacer vertical alignment
        st.progress(progress_ratio)

st.divider()

# --- SECTION 2: ADD / REMOVE ENVELOPES MANAGER ---
st.subheader("🛠️ Manage Envelopes")
with st.expander("Click here to add or delete custom envelopes"):
    # Form layout to add a new option
    st.markdown("### Add New Envelope")
    new_name = st.text_input("Envelope Name (e.g., Rent, Subscriptions)")
    new_budget = st.number_input("Monthly Budget Target (\$)", min_value=0.0, step=10.0)

    if st.button("Add Envelope", use_container_width=True):
        if new_name and new_name not in st.session_state.envelopes:
            st.session_state.envelopes[new_name] = new_budget
            st.success(f"Created envelope: {new_name}!")
            st.rerun()

    st.divider()

    # Dropdown option to remove an existing envelope
    st.markdown("### Remove Existing Envelope")
    removable_options = [e for e in st.session_state.envelopes.keys() if e != "Unassigned"]
    env_to_remove = st.selectbox("Select envelope to destroy", removable_options)

    if st.button("Delete Selected Envelope", type="primary", use_container_width=True):
        del st.session_state.envelopes[env_to_remove]
        st.warning(f"Removed envelope: {env_to_remove}")
        st.rerun()

st.divider()

# --- SECTION 3: TRANSACTION INTERACTIVE LEDGER ---
st.subheader("💳 Transaction Breakdown")

if raw_transactions:
    for t in raw_transactions:
        t_id = t['transaction_id']
        current_env = auto_categorize(t_id, t['name'], t['amount'])

        # Display each individual purchase row along with a responsive dropdown menu
        col_tx, col_select = st.columns([2, 1])
        with col_tx:
            st.markdown(f"**{t['name']}**  \n*{t['date']}* | `${t['amount']:,.2f}`")
        with col_select:
            # Let you or your spouse manually fix categorization dynamically
            all_envs = list(st.session_state.envelopes.keys())
            default_index = all_envs.index(current_env) if current_env in all_envs else 0

            chosen_env = st.selectbox(
                "Assign to:",
                all_envs,
                index=default_index,
                key=f"select_{t_id}"
            )

            # Save reassignment directly to browser memory state
            if chosen_env != current_env:
                st.session_state.transaction_mappings[t_id] = chosen_env
                st.rerun()
else:
    st.info("No transaction inputs processed.")

