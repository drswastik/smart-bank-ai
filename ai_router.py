"""
ai_router.py
The multi-agent brain of Smart Bank. Handles local intent routing (Flan-T5),
AI Firewalling & NL2SQL execution (Ollama), and complex reasoning tasks (Gemini).
"""

import os
import re
import ollama
import streamlit as st
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from google import genai
from dotenv import load_dotenv
from database import get_db_connection

load_dotenv()

@st.cache_resource
def load_models():
    """Loads PyTorch models into GPU memory locally, bypassing HuggingFace Hub network checks."""
    print("Loading Local Flan-T5 Dispatcher directly to GPU...")
    gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    tokenizer = AutoTokenizer.from_pretrained("./local_flan_t5_small", local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained("./local_flan_t5_small", local_files_only=True).to("cuda")
    return gemini_client, tokenizer, model

gemini_client, tokenizer, flan_model = load_models()

def nlp_kyc_extraction(user_text):
    """Uses a strict mathematical rubric to safely extract entities and score KYC confidence."""
    system_instruction = """
    Extract the Name and National ID from the user's text. 
    Calculate a KYC Confidence Score (0-100) using this EXACT mathematical rubric:
    1. Start at a base score of 50.
    2. Add +25 if the user provides a realistic human First and Last name.
    3. Add +25 if the National ID provided looks like a realistic formatted ID.
    4. Subtract -80 ONLY if the text is pure spam, gibberish, or uses an obviously fake joke name.
    
    Format your response EXACTLY as:
    NAME: [text] | ID: [text] | CONFIDENCE: [number]
    """
    res = gemini_client.models.generate_content(
        model='gemini-3.5-flash-lite', 
        contents=user_text,
        config={'system_instruction': system_instruction}
    ).text
    
    try:
        name = re.search(r'NAME:\s*(.*?)\s*\|', res).group(1).strip()
        # Clean trailing punctuation
        nid = re.search(r'ID:\s*(.*?)\s*\|', res).group(1).strip().strip('.,')
        conf = int(re.search(r'CONFIDENCE:\s*(\d+)', res).group(1))
        return name, nid, conf
    except:
        return "Unknown", "Unknown", 0

def mask_pii(text):
    """Zero-Trust sanitation block removing PII before external routing."""
    text = re.sub(r'\b\d{12,16}\b', '[REDACTED_ID]', text)
    text = re.sub(r'\S+@\S+', '[REDACTED_EMAIL]', text)
    return text

def execute_nl2sql(query):
    """Executes safe, verified SQL queries dynamically."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query)
        results = cursor.fetchall()
        return [dict(row) for row in results]
    except Exception as e:
        return f"Database execution error: {e}"
    finally:
        conn.close()

def format_history_for_gemini(chat_history):
    """Structures recent UI chat context for LLM memory."""
    if not chat_history: return "No prior context."
    return "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history[-4:]])

def route_query(user_input, account_id, chat_history=[]):
    """
    The Core Routing Engine.
    Uses Flan-T5 to classify the user's prompt, then mathematically routes it
    to the correct execution subsystem.
    """
    safe_input = mask_pii(user_input)
    recent_context = format_history_for_gemini(chat_history)
    
    # 1. Local Intent Classification
    prompt = f"Classify this text into one category: 'ledger', 'apply', 'transfer', or 'chat'. Text: {safe_input}\nCategory:"
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    outputs = flan_model.generate(**inputs, max_new_tokens=3)
    top_intent = tokenizer.decode(outputs[0], skip_special_tokens=True).lower().strip()
    
    # --- ROUTE 1: ACTION ENGINE (Fund Transfers) ---
    if "transfer" in top_intent or "send" in safe_input.lower() or "pay" in safe_input.lower():
        extraction_prompt = f"""
        Extract the transfer amount and receiver account ID from this text.
        Recent Context: {recent_context}
        Current Input: {safe_input}
        Format exactly as: AMOUNT: [number], RECEIVER: [ID]. If missing, write None.
        """
        res = gemini_client.models.generate_content(model='gemini-3.5-flash-lite', contents=extraction_prompt).text
        
        try:
            amt = float(re.search(r'AMOUNT:\s*([\d\.]+)', res).group(1))
            rec = re.search(r'RECEIVER:\s*([A-Za-z0-9\-]+)', res).group(1)
            
            if "NONE" in rec.upper() or amt <= 0:
                return {"routed_to": "Gemini 3.5 Lite", "intent": "Transfer Initiation", "response": "I can help send money. Please provide the exact amount and Receiver's Account ID.", "requires_rerun": False}
            
            import banking_ops
            transfer_res = banking_ops.process_transfer(account_id, rec, amt)
            if transfer_res['status'] == 'success':
                return {"routed_to": "Gemini 3.5 Lite (Action)", "intent": "Fund Transfer", "response": f"✅ Successfully transferred ₹{amt:,.2f} to {rec}. TXN ID: {transfer_res['txn_id']}", "requires_rerun": True}
            else:
                return {"routed_to": "Gemini 3.5 Lite", "intent": "Fund Transfer", "response": f"Transfer failed: {transfer_res['message']}", "requires_rerun": False}
        except:
            return {"routed_to": "Gemini 3.5 Lite", "intent": "Transfer Initiation", "response": "To send funds, please provide the amount and the receiver's exact account ID.", "requires_rerun": False}

    # --- ROUTE 2: GEMINI UNDERWRITER (Loan Analysis) ---
    elif ("loan" in safe_input.lower() or "apply" in top_intent) and not any(w in safe_input.lower() for w in ["taken", "history", "past"]):
        bank_policy = "Housing: 8.12% | Car: 11.12% | Edu: 5.12%"
        conn = get_db_connection()
        balance = conn.cursor().execute("SELECT balance FROM Accounts WHERE account_id = ?", (account_id,)).fetchone()['balance']
        conn.close()
        
        sys_inst = """
        You are an AI Underwriter. DO NOT invent UI elements. Answer directly.
        Format:
        AMOUNT_REQUESTED: [Numeric value]
        RISK_SCORE: [Number 1 to 100]
        SUMMARY: [2 sentences explaining logic]
        """
        prompt_txt = f"Context: {recent_context}\nPolicy: {bank_policy}\nBalance: Rs {balance}\nQuery: {safe_input}"
        response = gemini_client.models.generate_content(model='gemini-3.5-flash-lite', contents=prompt_txt, config={'system_instruction': sys_inst}).text
        
        try:
            amount = float(re.search(r'AMOUNT_REQUESTED:\s*(\d+)', response).group(1))
            score = int(re.search(r'RISK_SCORE:\s*(\d+)', response).group(1))
            summary = re.search(r'SUMMARY:\s*(.*)', response, re.DOTALL).group(1).strip()
            if amount > 0:
                import banking_ops
                banking_ops.submit_loan_application(account_id, amount, score, summary)
                return {"routed_to": "Gemini 3.5 Lite", "intent": "Loan App", "response": f"Loan application for ₹{amount:,.2f} submitted to Admin Queue. Risk score: {score}/100.", "requires_rerun": False}
        except: pass
        return {"routed_to": "Gemini 3.5 Lite", "intent": "Loan App", "response": "Could not determine exact amount. Please specify the loan amount.", "requires_rerun": False}
        
    # --- ROUTE 3: ZERO-TRUST NL2SQL FIREWALL (Ledger Lookups) ---
    elif "ledger" in top_intent or "account" in top_intent or any(w in safe_input.lower() for w in ['withdraw', 'deposit', 'balance', 'transaction', 'last', 'history', 'taken']):
        sql_prompt = f"""Output ONLY raw SQLite query. Tables: Accounts(account_id, balance), Transactions(txn_id, account_id, amount, txn_type, timestamp). 
        User: "{safe_input}"
        Constraint: ALWAYS filter by account_id = '{account_id}'"""
        
        raw_output = ollama.chat(model='llama3.1:latest', messages=[{'role': 'user', 'content': sql_prompt}])['message']['content']
        match = re.search(r'(SELECT.*?;)', raw_output, re.IGNORECASE | re.DOTALL)
        sql_query = match.group(1) if match else raw_output.replace('```sql', '').replace('```', '').strip()
        
        # Security Guardrail: Block prompt injections
        dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER']
        if any(kw in sql_query.upper() for kw in dangerous_keywords):
            return {"routed_to": "Firewall", "intent": "Security Threat", "response": "Query rejected by AI Firewall: Destructive SQL operations are prohibited.", "requires_rerun": False}
        if account_id not in sql_query:
            return {"routed_to": "Firewall", "intent": "Security Threat", "response": "Query rejected by AI Firewall: Cross-account data access violation.", "requires_rerun": False}
            
        print(f"DEBUG - Validated SQL: {sql_query}") 
        db_results = execute_nl2sql(sql_query)
        
        sum_prompt = f"Context: {recent_context}\nUser: {safe_input}\nDB: {db_results}. Write a concise 1-2 sentence summary. No markdown."
        sum_res = ollama.chat(model='llama3.1:latest', messages=[{'role': 'user', 'content': sum_prompt}])['message']['content']
        
        return {"routed_to": "Ollama (Secured NL2SQL)", "intent": "Account Ledger", "response": sum_res, "requires_rerun": False}
        
    # --- ROUTE 4: CONVERSATIONAL FALLBACK ---
    else:
        chat_prompt = f"Context: {recent_context}\nUser: '{safe_input}'. Reply naturally in 1-2 sentences. Do not mention UI buttons."
        chat_res = gemini_client.models.generate_content(model='gemini-3.5-flash-lite', contents=chat_prompt).text
        return {"routed_to": "Gemini 3.5 Lite", "intent": "Chat", "response": chat_res, "requires_rerun": False}