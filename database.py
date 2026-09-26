"""
database.py

This script is the absolute bedrock of the Smart Bank system. 
Instead of a massive, messy cloud database, we are using a lightweight 
SQLite file to securely manage users, track balances, and build our 
tamper-proof cryptographic ledger. Run this file once to build the house.
"""

import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

# This is the physical file that will be generated in your folder.
# If you ever want to completely wipe the bank and start fresh, just delete this file!
DB_FILE = "iit_smart_bank.db"

def get_db_connection():
    """
    Opens a secure pipeline to our database.
    We turn on 'foreign_keys' so SQLite enforces our relationship rules 
    (e.g., you can't have a bank account if you don't exist as a user).
    """
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # This row_factory lets us access columns by name (like row['balance']) 
    # instead of confusing index numbers (like row[2]). Much cleaner!
    conn.row_factory = sqlite3.Row 
    return conn

def initialize_database():
    """Builds the actual tables inside our empty database file."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. THE USERS TABLE
    # This holds our human identities. Notice we only store 'password_hash'. 
    # We never save raw passwords—if the database leaks, the passwords are still mathematically safe.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            national_id TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'user',
            kyc_confidence INTEGER DEFAULT 100,
            kyc_status TEXT DEFAULT 'APPROVED'
        )
    """)
    
    # 2. THE ACCOUNTS TABLE
    # A user can theoretically have multiple accounts (savings, checking).
    # The 'ON DELETE CASCADE' rule means if a user is deleted, their bank accounts vanish automatically.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Accounts (
            account_id TEXT PRIMARY KEY,
            user_id TEXT,
            balance REAL DEFAULT 0.00,
            account_type TEXT,
            FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
        )
    """)
    
    # 3. THE IMMUTABLE LEDGER (Transactions)
    # This isn't just a list of money moving. This is our blockchain-style ledger.
    # Every transaction records the 'previous_hash' and its own 'current_hash'.
    # If a hacker manually edits an amount here, the mathematical chain breaks instantly.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_id TEXT UNIQUE,
            account_id TEXT,
            amount REAL,
            txn_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            previous_hash TEXT,
            current_hash TEXT,
            FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
        )
    """)
    
    # 4. THE AI UNDERWRITING QUEUE (Loan Applications)
    # When Gemini acts as our loan officer, it drafts applications and drops them here.
    # The Admin can then review the AI's logic and click 'Approve' or 'Reject' from the dashboard.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS LoanApplications (
            app_id TEXT PRIMARY KEY,
            account_id TEXT,
            amount REAL,
            ai_risk_score INTEGER,
            ai_summary TEXT,
            status TEXT DEFAULT 'PENDING',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
        )
    """)
    
    # Lock in all the changes and close the door
    conn.commit()
    print(f"Architecture successfully deployed! {DB_FILE} is ready for action.")
    conn.close()

# Only run the initialization if we execute this script directly
if __name__ == "__main__":
    initialize_database()