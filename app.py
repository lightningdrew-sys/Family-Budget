import os
import time
from datetime import date, timedelta
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

st.set_page_config(page_title="Our Family Envelopes", page_icon="🏡", layout="centered")

# 🗄️ 1. INITIALIZE PERSISTENT APP MEMORY
if 'envelopes' not in st.session_state:
    st.session_state.envelopes = {
        "Groceries": 400.00,
        "Dining Out": 150.00,
        "Gas / Fuel": 100.00,
        "Unassigned": 0.00
    }

if 'transaction_mappings' not in st.session_state:
    st.session_state.transaction_mappings = {}

# 🛡️ This memory bucket saves your transactions so buttons don't clear them
if 'cached_ledger_data' not in st.session_state:
    st.session_state.cached_ledger_data = None


# 🛠️ 2. PLAID PIPELINE LOGIC (Runs once per refresh session)
def fetch_sandbox_data_once():
    # If we already have the bank data stored in memory, bypass the API completely!
    if st.session_state.cached_ledger_data is not None:
        return st.session_state.cached_ledger_data

    client_id = st.secrets.get("PLAID_CLIENT_ID") or os.getenv("PLAID_CLIENT_ID")
    secret_key = st.secrets.get("PLAID_SECRET") or os.getenv("PLAID_SECRET")

    configuration = plaid.Configuration(
        host=plaid.Environment.Sandbox,
        api_key={'clientId': client_id, 'secret': secret_key}
    )
    api_client = plaid.ApiClient(configuration)
    client = plaid_api.PlaidApi(api_client)

    try:
        # Create Sandbox token
        pt_request = SandboxPublicTokenCreateRequest(
            institution_id="ins_109508",
            initial_products=[Products('transactions')]
        )
        pt_response = client.sandbox_public_token_create(pt_request)
        public_token = pt_response['public_token']

        # Exchange public token
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = client.item_public_token_exchange(exchange_request)
        access_token = exchange_response['access_token']

        # Give sandbox time to bake the history ledger
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

        # Unpack to native Python list of dictionaries
        stable_transactions = []
        for t in response.transactions:
            stable_transactions.append({
                "transaction_id": t.transaction_id,
                "name": t.name,
                "amount": float(t.amount),
                "date": str(t.date)
            })

        # Save into browser state vault before returning
        st.session_state.cached_ledger_data = stable_transactions
        return stable_transactions

    except Exception as e:
        st.error(f"Plaid Connection Error: {e}")
        return []


# Fetch data via our smart network gatekeeper
raw_transactions = fetch_sandbox_data_once()


# 📑 3. HELPER LOGIC: ROUTE TRANSACTIONS TO ENVELOPES
def auto_categorize(t_id, name, amount):
    if t_id in st.session_state.transaction_mappings:
        return st.session_state.transaction_mappings[t_id]

    name_lower = name.lower()
    if "uber" in name_lower or "taxi" in name_lower or "lyft" in name_lower:
        return "Gas / Fuel"
    elif "mcdonald" in name_lower or "starbucks" in name_lower or "place" in name_lower:
        return "Dining Out"
    elif "spark" in name_lower or "market" in name_lower or "grocery" in name_lower:
        return "Groceries"
    return "Unassigned"


# Calculate envelope totals natively
envelope_spending = {name: 0.0 for name in st.session_state.envelopes}
for t in raw_transactions:
    assigned_env = auto_categorize(t['transaction_id'], t['name'], t['amount'])
    if assigned_env in envelope_spending:
        envelope_spending[assigned_env] += t['amount']

# 🎨 4. STREAMLIT USER INTERFACE FRAMEWORK
st.title("🏡 Our Family Envelopes")

# --- SECTION 1: THE ENVELOPE LEDGER ---
st.subheader("📬 Your Envelopes")

for env_name, budget_total in st.session_state.envelopes.items():
    if env_name == "Unassigned":
        continue
    spent = envelope_spending.get(env_name, 0.0)
    remaining = budget_total - spent

    progress_ratio = min(max(spent / budget_total, 0.0), 1.0) if budget_total > 0 else 0.0

    col_label, col_bar = st.columns(2)
    with col_label:
        st.markdown(f"**{env_name}**  \n`${remaining:,.2f}` left of \${budget_total:,.2f}")
    with col_bar:
        st.write("")
        st.progress(progress_ratio)

st.divider()

# --- SECTION 2: ADD / REMOVE ENVELOPES MANAGER ---
st.subheader("🛠️ Manage Envelopes")
with st.expander("Click here to add or delete custom envelopes"):
    st.markdown("### Add New Envelope")
    new_name = st.text_input("Envelope Name (e.g., Rent, Subscriptions)")
    new_budget = st.number_input("Monthly Budget Target (\$)", min_value=0.0, step=10.0)

    if st.button("Add Envelope", use_container_width=True):
        if new_name and new_name not in st.session_state.envelopes:
            st.session_state.envelopes[new_name] = new_budget
            st.success(f"Created envelope: {new_name}!")
            st.those_changes_saved = st.rerun()

    st.divider()

    st.markdown("### Remove Existing Envelope")
    removable_options = [e for e in st.session_state.envelopes.keys() if e != "Unassigned"]
    env_to_remove = st.selectbox("Select envelope to destroy", removable_options)

    if st.button("Delete Selected Envelope", type="primary", use_container_width=True):
        if env_to_remove in st.session_state.envelopes:
            del st.session_state.envelopes[env_to_remove]
            st.warning(f"Removed envelope: {env_to_remove}")
            st.rerun()

st.divider()

# --- SECTION 3: TRANSACTION INTERACTIVE LEDGER ---
st.subheader("💳 Transaction Breakdown")

if raw_transactions:
    for t in raw_transactions:
        t_id = t['transaction_id']
        t_name = t['name']
        t_amount = t['amount']
        t_date = t['date']

        current_env = auto_categorize(t_id, t_name, t_amount)

        col_tx, col_select = st.columns(2)
        with col_tx:
            st.markdown(f"**{t_name}**  \n*{t_date}* | `${t_amount:,.2f}`")
        with col_select:
            all_envs = list(st.session_state.envelopes.keys())
            default_index = all_envs.index(current_env) if current_env in all_envs else 0

            chosen_env = st.selectbox(
                "Assign to:",
                all_envs,
                index=default_index,
                key=f"select_{t_id}"
            )

            if chosen_env != current_env:
                st.session_state.transaction_mappings[t_id] = chosen_env
                st.rerun()
else:
    st.info("No transaction inputs processed.")