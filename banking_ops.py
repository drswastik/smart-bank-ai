"""
banking_ops.py
Handles core financial logic, password hashing, and cryptographic ledger integrity.
"""

import sqlite3
import bcrypt
import uuid
import hashlib
from database import get_db_connection

def generate_txn_hash(txn_id, account_id, amount, txn_type, previous_hash):
    """Calculates a SHA-256 hash linking the current transaction to the previous one."""
    data = f"{txn_id}{account_id}{amount:.2f}{txn_type}{previous_hash}"
    return hashlib.sha256(data.encode('utf-8')).hexdigest()

def get_last_hash(cursor):
    """Retrieves the hash of the most recent transaction to maintain the chain."""
    cursor.execute("SELECT current_hash FROM Transactions ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row['current_hash'] if row else "0" * 64 

def create_user_and_account(name, password, national_id, role="user", kyc_confidence=100):
    """Registers a new user securely and initializes their savings account."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user_id = f"USR-{uuid.uuid4().hex[:6].upper()}"
        account_id = f"ACC-{uuid.uuid4().hex[:8].upper()}"
        
        # Route low-confidence KYC signups to the Admin queue
        status = "APPROVED" if int(kyc_confidence) >= 70 or role == "admin" else "PENDING"
        
        cursor.execute("INSERT INTO Users (user_id, name, password_hash, national_id, role, kyc_confidence, kyc_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (user_id, name, password_hash, national_id.strip().upper(), role, kyc_confidence, status))
        cursor.execute("INSERT INTO Accounts (account_id, user_id, balance, account_type) VALUES (?, ?, ?, ?)",
                       (account_id, user_id, 0.00, "SAVINGS"))
        conn.commit()
        return {"status": "success", "user_id": user_id, "account_id": account_id}
    except sqlite3.IntegrityError:
        conn.rollback()
        return {"status": "error", "message": "National ID already registered."}
    finally:
        conn.close()

def verify_login(national_id, password):
    """Authenticates users and validates their current KYC standing."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.user_id, u.password_hash, u.role, u.kyc_status, a.account_id 
        FROM Users u 
        JOIN Accounts a ON u.user_id = a.user_id 
        WHERE UPPER(u.national_id) = UPPER(?)
    """, (national_id.strip(),))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {"status": "error", "message": f"National ID '{national_id}' not found in database."}
        
    if bcrypt.checkpw(password.encode('utf-8'), row['password_hash'].encode('utf-8')):
        if row['kyc_status'] == 'PENDING':
            return {"status": "error", "message": "Your account is currently PENDING Admin KYC approval."}
        elif row['kyc_status'] == 'REJECTED':
            return {"status": "error", "message": "KYC was rejected. Account locked."}
            
        return {"status": "success", "user_id": row['user_id'], "account_id": row['account_id'], "role": row['role']}
    else:
        return {"status": "error", "message": "Incorrect password."}

def process_transaction(account_id, amount, txn_type):
    """Processes basic deposits and withdrawals, updating the crypto ledger."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM Accounts WHERE account_id = ?", (account_id,))
        current_balance = cursor.fetchone()['balance']
        
        if txn_type == "WITHDRAWAL" and current_balance < amount:
            return {"status": "error", "message": "Insufficient funds."}
            
        new_balance = current_balance + amount if txn_type == "DEPOSIT" else current_balance - amount
        txn_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"
        
        # Crypto Ledger Update
        prev_hash = get_last_hash(cursor)
        curr_hash = generate_txn_hash(txn_id, account_id, amount, txn_type, prev_hash)
        
        cursor.execute("UPDATE Accounts SET balance = ? WHERE account_id = ?", (new_balance, account_id))
        cursor.execute("INSERT INTO Transactions (txn_id, account_id, amount, txn_type, previous_hash, current_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       (txn_id, account_id, amount, txn_type, prev_hash, curr_hash))
        conn.commit()
        return {"status": "success", "new_balance": new_balance, "txn_id": txn_id}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def process_transfer(sender_id, receiver_id, amount):
    """Executes peer-to-peer transfers, maintaining hash chain integrity across two accounts."""
    if amount <= 0: return {"status": "error", "message": "Invalid amount."}
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM Accounts WHERE account_id = ?", (sender_id,))
        sender = cursor.fetchone()
        if not sender or sender['balance'] < amount: return {"status": "error", "message": "Insufficient funds."}
            
        cursor.execute("SELECT account_id FROM Accounts WHERE UPPER(account_id) = UPPER(?)", (receiver_id.strip(),))
        if not cursor.fetchone(): return {"status": "error", "message": "Receiver account not found."}
            
        cursor.execute("UPDATE Accounts SET balance = balance - ? WHERE account_id = ?", (amount, sender_id))
        cursor.execute("UPDATE Accounts SET balance = balance + ? WHERE UPPER(account_id) = UPPER(?)", (amount, receiver_id.strip()))
        
        # Hash Outbound Transaction
        txn_id_out = f"TXN-{uuid.uuid4().hex[:10].upper()}"
        prev_hash_out = get_last_hash(cursor)
        curr_hash_out = generate_txn_hash(txn_id_out, sender_id, amount, "IMPS_OUT", prev_hash_out)
        cursor.execute("INSERT INTO Transactions (txn_id, account_id, amount, txn_type, previous_hash, current_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       (txn_id_out, sender_id, amount, "IMPS_OUT", prev_hash_out, curr_hash_out))
        
        # Hash Inbound Transaction
        txn_id_in = txn_id_out.replace("TXN", "RXN")
        prev_hash_in = curr_hash_out 
        curr_hash_in = generate_txn_hash(txn_id_in, receiver_id.strip().upper(), amount, "IMPS_IN", prev_hash_in)
        cursor.execute("INSERT INTO Transactions (txn_id, account_id, amount, txn_type, previous_hash, current_hash) VALUES (?, ?, ?, ?, ?, ?)",
                       (txn_id_in, receiver_id.strip().upper(), amount, "IMPS_IN", prev_hash_in, curr_hash_in))
                       
        conn.commit()
        return {"status": "success", "txn_id": txn_id_out}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def verify_ledger_integrity():
    """Admin function: Recalculates the entire database hash chain to detect manual DB tampering."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Transactions ORDER BY id ASC")
    transactions = cursor.fetchall()
    conn.close()
    
    expected_prev = "0" * 64
    for txn in transactions:
        if txn['previous_hash'] != expected_prev:
            return {"status": "compromised", "error": f"Chain break detected before TXN {txn['txn_id']}"}
        
        calculated_hash = generate_txn_hash(txn['txn_id'], txn['account_id'], txn['amount'], txn['txn_type'], txn['previous_hash'])
        if calculated_hash != txn['current_hash']:
            return {"status": "compromised", "error": f"Data tampering detected at TXN {txn['txn_id']}. Hash mismatch."}
            
        expected_prev = txn['current_hash']
    return {"status": "secure"}

def submit_loan_application(account_id, amount, score, summary):
    """Pushes an AI-evaluated loan application to the database for Admin review."""
    conn = get_db_connection()
    cursor = conn.cursor()
    app_id = f"LOAN-{uuid.uuid4().hex[:8].upper()}"
    cursor.execute("INSERT INTO LoanApplications (app_id, account_id, amount, ai_risk_score, ai_summary) VALUES (?, ?, ?, ?, ?)",
                   (app_id, account_id, amount, score, summary))
    conn.commit()
    conn.close()

def resolve_loan(app_id, action):
    """Executes the Admin's decision on a pending AI loan application."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT account_id, amount FROM LoanApplications WHERE app_id = ?", (app_id,))
    loan = cursor.fetchone()
    
    if action == "APPROVE":
        cursor.execute("UPDATE LoanApplications SET status = 'APPROVED' WHERE app_id = ?", (app_id,))
        conn.commit()
        conn.close()
        process_transaction(loan['account_id'], loan['amount'], "LOAN_DISBURSEMENT")
    else:
        cursor.execute("UPDATE LoanApplications SET status = 'REJECTED' WHERE app_id = ?", (app_id,))
        conn.commit()
        conn.close()

def resolve_kyc(user_id, action):
    """Admin function to resolve a pending KYC application."""
    conn = get_db_connection()
    cursor = conn.cursor()
    status = 'APPROVED' if action == 'APPROVE' else 'REJECTED'
    cursor.execute("UPDATE Users SET kyc_status = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()

def admin_get_account_details(search_account_id):
    """Fetches comprehensive account details for Admin inspection."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.name, u.national_id, u.kyc_confidence, a.balance 
        FROM Accounts a JOIN Users u ON a.user_id = u.user_id WHERE UPPER(a.account_id) = UPPER(?)
    """, (search_account_id.strip(),))
    user_info = cursor.fetchone()
    conn.close()
    return dict(user_info) if user_info else None