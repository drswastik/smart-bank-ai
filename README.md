# 🏦 Smart Bank: AI-Powered Core Banking Microservice

Smart Bank is a dual-interface neo-banking system that combines standard financial operations with an autonomous AI action engine. Built with a focus on mathematical data security and zero-trust AI architecture, it bridges the gap between traditional banking ledgers and modern Large Language Models.

## 🚀 Core Technical Features

* **Cryptographic Hash Chaining (Immutable Ledger):** Every SQLite transaction generates a SHA-256 hash mathematically linked to the previous transaction. An Admin auditing tool can instantly detect if the raw database file has been manually tampered with.
* **Zero-Trust NL2SQL Firewall:** Natural language queries are translated into SQLite via Llama 3.1. Before execution, a strict firewall intercepts the raw SQL, mathematically proving it is a read-only `SELECT` statement scoped strictly to the authenticated user.
* **Algorithmic KYC Verification:** Uses Gemini 3.5 Flash-Lite to extract NLP entities (Name, National ID) from user bios and calculates a 0-100 Confidence Score based on a strict mathematical rubric. Low-scoring accounts are automatically quarantined in a pending queue for human Admin review.
* **Multi-Agent Routing:** A local Google Flan-T5 model (running purely on PyTorch/CUDA) categorizes user intent and routes execution to either an Action Engine (fund transfers), an Underwriter (loans), or the NL2SQL Ledger.

## 🛠️ Tech Stack

* **Frontend:** Streamlit
* **Backend Database:** SQLite3 with bcrypt authentication
* **AI Router:** Google Flan-T5 (Local PyTorch Inference)
* **Local Data Engine:** Ollama (Llama 3.1)
* **Cloud Reasoning Engine:** Google Gemini 3.5 Flash-Lite

## ⚙️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/drswastik/smart-bank-ai.git](https://github.com/drswastik/smart-bank-ai.git)
   cd smart-bank-ai
   ```

2. **Install the core dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the environment variables:**
   * Rename the `.env.example` file to `.env`.
   * Open it and paste your Google Gemini API key.

4. **Stage the Local AI Router:**
   * Download the `google/flan-t5-small` model files.
   * Place them directly into a root folder named `local_flan_t5_small`.

5. **Boot the application:**
   ```bash
   streamlit run app.py --server.fileWatcherType=none
   ```

## 🔐 Default Access

On the first boot, the system automatically initializes the cryptographic ledger and generates a Master Admin account:

* **National ID:** `ADMIN-001`
* **Password:** `admin123`
