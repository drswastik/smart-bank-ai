"""
app.py
The Streamlit frontend for Smart Bank. Integrates standard manual operations
with the AI Action Engine and the restricted Admin Mode console.
"""

import streamlit as st
import pandas as pd
from database import get_db_connection, initialize_database
import banking_ops
import ai_router as router
import os
import time

# --- BULLETPROOF BOOT SEQUENCE ---
def system_boot():
    """Ensures database exists and forcefully provisions the Master Admin on startup."""
    if not os.path.exists("iit_smart_bank.db"):
        initialize_database()
        
    conn = get_db_connection()
    admin_exists = conn.execute("SELECT 1 FROM Users WHERE national_id = 'ADMIN-001'").fetchone()
    conn.close()
    
    if not admin_exists:
        banking_ops.create_user_and_account("System Admin", "admin123", "ADMIN-001", "admin", 100)

system_boot()

st.set_page_config(page_title="Smart Bank", page_icon="🏦", layout="wide")

# Initialize Session State
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.chat_history = []

# --- AUTHENTICATION & KYC SCREEN ---
if not st.session_state.logged_in:
    st.title("🏦 Smart Bank Portal")
    tab1, tab2 = st.tabs(["Login", "NLP Account Creation"])
    
    with tab1:
        with st.form("login_form"):
            login_id = st.text_input("National ID (e.g., PAN-...)").strip()
            login_pass = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                res = banking_ops.verify_login(login_id, login_pass)
                if res['status'] == 'success':
                    st.session_state.update(logged_in=True, user_id=res['user_id'], account_id=res['account_id'], role=res['role'], chat_history=[])
                    st.rerun()
                else:
                    st.error(res['message'])
                    
    with tab2:
        st.info("Write a short bio. Our NLP engine will extract your details and calculate a KYC Confidence Score.")
        bio = st.text_area("Tell us who you are (Include Name and National ID):", "Hi, my name is Dr. Swastik and my PAN card is PAN-ABC12345.")
        new_pass = st.text_input("Create Password", type="password")
        if st.button("Process KYC & Create Account"):
            with st.spinner("NLP Engine parsing bio..."):
                name, nid, conf = router.nlp_kyc_extraction(bio)
                st.write(f"**Extracted Name:** {name} | **Extracted ID:** {nid} | **AI Confidence:** {conf}%")
                
                res = banking_ops.create_user_and_account(name, new_pass, nid, "user", conf)
                if res['status'] == 'success':
                    if conf < 70:
                        st.warning(f"Account registered! Because your KYC score is {conf}%, it was routed to the Admin Queue for manual approval before you can log in.")
                    else:
                        st.success(f"KYC Confidence is {conf}%. Account auto-approved! You may log in.")
                else:
                    st.error(res['message'])
                    
# --- MAIN DASHBOARD ---
else:
    with st.sidebar:
        st.title("🏦 Smart Bank")
        st.caption(f"Account ID: {st.session_state.account_id}")
        st.caption(f"Role: {st.session_state.role.upper()}")
        
        # Live Sidebar Balance
        conn = get_db_connection()
        balance = conn.execute("SELECT balance FROM Accounts WHERE account_id = ?", (st.session_state.account_id,)).fetchone()['balance']
        conn.close()
        st.metric("Live Balance", f"₹ {balance:,.2f}")
        st.markdown("---")
        
        # RBAC Navigation
        pages = ["💳 UI Terminal", "🤖 AI Copilot"]
        if st.session_state.role == "admin":
            pages.append("🛡️ Admin Mode")
            
        page = st.radio("Navigation", pages)
        st.markdown("---")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

    # VIEW 1: Standard Manual UI
    if page == "💳 UI Terminal":
        st.header("Standard UI Interface")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Cash Operations")
            action = st.selectbox("Action", ["DEPOSIT", "WITHDRAWAL"])
            amount = st.number_input("Amount (₹)", min_value=1.0, step=100.0)
            if st.button("Execute"):
                res = banking_ops.process_transaction(st.session_state.account_id, amount, action)
                st.success("Success!") if res['status'] == 'success' else st.error(res['message'])
                time.sleep(1)
                st.rerun()
                
        with col2:
            st.subheader("Fund Transfer (IMPS)")
            receiver = st.text_input("Receiver Account ID")
            transfer_amount = st.number_input("Transfer Amount (₹)", min_value=1.0, step=100.0)
            if st.button("Send Funds"):
                res = banking_ops.process_transfer(st.session_state.account_id, receiver, transfer_amount)
                if res['status'] == 'success':
                    st.success(f"Transferred! TXN ID: {res['txn_id']}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(res['message'])

    # VIEW 2: Dynamic Action Engine
    elif page == "🤖 AI Copilot":
        st.header("AI Action Engine")
        
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
                
        if prompt := st.chat_input("Command the AI (e.g. 'Send ₹500 to ACC-1234' or 'Show my ledger')"):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
                
            with st.chat_message("assistant"):
                with st.spinner("Executing mathematical constraints..."):
                    res = router.route_query(prompt, st.session_state.account_id, st.session_state.chat_history)
                    st.caption(f"🚀 *{res['routed_to']}*")
                    st.markdown(res['response'])
            
            st.session_state.chat_history.append({"role": "assistant", "content": res['response']})
            if res.get("requires_rerun", False):
                time.sleep(1.5)
                st.rerun()

    # VIEW 3: Restricted Admin Desk
    elif page == "🛡️ Admin Mode":
        st.header("System Integrity & Underwriting Console")
        conn = get_db_connection()
        
        # 1. KYC Reviews
        st.subheader("🪪 Pending KYC Approvals")
        kyc_df = pd.read_sql_query("SELECT user_id, name, national_id, kyc_confidence FROM Users WHERE kyc_status = 'PENDING'", conn)
        if not kyc_df.empty:
            for _, row in kyc_df.iterrows():
                with st.expander(f"KYC Alert: {row['name']} | Confidence: {row['kyc_confidence']}%"):
                    st.write(f"**ID Submitted:** {row['national_id']}")
                    c1, c2 = st.columns(2)
                    if c1.button("Approve Account", key=f"kyc_app_{row['user_id']}"):
                        banking_ops.resolve_kyc(row['user_id'], "APPROVE")
                        st.rerun()
                    if c2.button("Reject Account", key=f"kyc_rej_{row['user_id']}"):
                        banking_ops.resolve_kyc(row['user_id'], "REJECT")
                        st.rerun()
        else:
            st.info("No pending KYC approvals.")
        st.markdown("---")
        
        # 2. Cryptographic Security Audit
        st.subheader("🔐 Cryptographic Ledger Audit")
        st.write("Scan the SHA-256 hash chain to verify immutable database integrity.")
        if st.button("Verify Hash Chain"):
            with st.spinner("Calculating hashes..."):
                audit = banking_ops.verify_ledger_integrity()
                if audit['status'] == 'secure':
                    st.success("✅ Ledger Intact. No database tampering detected.")
                else:
                    st.error(f"🚨 {audit['error']}")
        st.markdown("---")
        
        # 3. AI Loan Underwriting Review
        st.subheader("📝 Pending AI Loan Applications")
        loans_df = pd.read_sql_query("SELECT * FROM LoanApplications WHERE status = 'PENDING'", conn)
        if not loans_df.empty:
            for _, row in loans_df.iterrows():
                with st.expander(f"Request: ₹{row['amount']} | Risk Score: {row['ai_risk_score']}/100"):
                    st.write(f"**Account:** {row['account_id']}")
                    st.write(f"**AI Logic:** {row['ai_summary']}")
                    c1, c2 = st.columns(2)
                    if c1.button("Approve Loan", key=f"app_{row['app_id']}"):
                        banking_ops.resolve_loan(row['app_id'], "APPROVE")
                        st.rerun()
                    if c2.button("Reject Loan", key=f"rej_{row['app_id']}"):
                        banking_ops.resolve_loan(row['app_id'], "REJECT")
                        st.rerun()
        else:
            st.info("Queue is empty.")
        st.markdown("---")
        
        # 4. Global Lookup
        st.subheader("🔍 Global Account Lookup")
        search_id = st.text_input("Enter Account ID:")
        if st.button("Inspect Data"):
            details = banking_ops.admin_get_account_details(search_id)
            if details:
                st.success(f"User: {details['name']} | KYC Score: {details['kyc_confidence']}%")
                st.metric("Balance", f"₹ {details['balance']:,.2f}")
                txns = pd.read_sql_query("SELECT txn_id, amount, txn_type, timestamp, current_hash FROM Transactions WHERE account_id = ? ORDER BY timestamp DESC LIMIT 10", conn, params=(search_id,))
                st.dataframe(txns, use_container_width=True)
            else:
                st.error("Account ID not found.")
            
        conn.close()
