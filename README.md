# Moomoo Portfolio Tracker & Analyzer

A tool that interfaces with the Moomoo OpenD gateway to store portfolio data into SQLite database and display a dashboard using Streamlit. This project is designed to automatically track daily portfolio value, positions, cash flow, and historical orders to track Time-Weighted Returns.

## 🛠️ Prerequisites

Before running this project, you need the following:

1.  **Python 3.10+**
2.  **Moomoo Account**

## Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/chuahengli/Stock-Portfolio-project.git
```
### 2. OpenD Configuration (`OpenD.xml`)
Look for the OpenD folder"moomoo_OpenD_9.6.5618_Windows" to configure the `OpenD.xml` file:
1. Rename OpenD.example.xml from this repo to OpenD.xml
1.  Set `YOUR_LOGIN_HERE` to your Moomoo login.
2.  Set `YOUR_PASSWORD_HERE` to your password.
3.  Set `RSA__KEY_FILEPATH_HERE` to the absolute path of your generated private key (see below).
<img width="1098" height="601" alt="image" src="https://github.com/user-attachments/assets/e04e0d43-5e80-4050-96e0-bb6b3056e726" />

### 3. RSA Key Generation
For security, this project uses RSA encryption.
1.  Generate a private/public key pair by following [Moomoo's Protocol Encryption Process](https://openapi.moomoo.com/moomoo-api-doc/en/qa/other.html#1479)
3.  Copy and paste the private key into a text file on your local machine.
4.  Enter the abosolute file path of your text file in `RSA__KEY_FILEPATH_HERE` as above in OpenD.xml


### 4. Install Dependencies
This project uses `pipenv` for dependency management. Run this line
```bash
pipenv install
```




## 📂 Project Structure

```text
.
├── config/
│   └── settings.py       # Paths and configuration constants
├── db/                   # Database storage (Ignored by Git)
├── source/
│   ├── cleanup.py        # Data transformation and cleaning logic
│   ├── db.py             # SQLite database interactions
│   └── moomoo_api.py     # Moomoo OpenD API interface
├── main.py               # Entry point
├── Pipfile               # Dependency definitions
└── README.md             # Documentation
```
