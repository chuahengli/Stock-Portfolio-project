# 📈Moomoo Portfolio Tracker & Analyzer

A tool that interfaces with the **Moomoo OpenD gateway** to store portfolio data into SQLite database and display a dashboard using **Streamlit**. This project is designed to automatically track daily portfolio value, positions, cash flow, and historical orders to track Time-Weighted Returns.
<img width="1267" height="701" alt="image" src="https://github.com/user-attachments/assets/19b0c55f-c68b-412c-8e07-155af9e9be7c" />
## ✨ Features
**Real-time Monitoring:** Dashboard refreshes every 10 seconds
**Historical Performance:** Tracks daily snapshots of portfolio in database
**Visualisation:** Displays portfolio metrics to analyse and understand portfolio allocation
**Interactive Dashboard**: Elements in Streamlit dashboard are interactive

## 🛠️ Prerequisites

Before running this project, you need the following:

1.  **Python 3.10+**
2.  **Moomoo Account**

## 🚀 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/chuahengli/Stock-Portfolio-project.git
```
### 2. OpenD Configuration (`OpenD.xml`)
Look for the OpenD folder"moomoo_OpenD_9.6.5618_Windows" to configure the `OpenD.xml` file:
1. Rename OpenD.example.xml from this repo to OpenD.xml
2.  Set `YOUR_LOGIN_HERE` to your Moomoo login.
3.  Set `YOUR_PASSWORD_HERE` to your password.
4.  Set `RSA__KEY_FILEPATH_HERE` to the absolute path of your generated private key (see below).
```bash
		<!-- Login account -->
		<!-- 登录账号可以是用户ID，手机号，邮箱，其中手机号格式为：+86 13800138000 -->
		<!-- The login account can be user ID, phone number, or email. The phone number format is: +86 13800138000 -->
		<login_account>YOUR_LOGIN_HERE</login_account>
		<!-- 登录密码32位MD5加密16进制 -->
		<!-- Login password, 32-bit MD5 encrypted hexadecimal --> 
		<!-- <login_pwd_md5>6e55f158a827b1a1c4321a245aaaad88</login_pwd_md5> -->
		<!-- 登录密码明文，密码密文存在情况下只使用密文 -->
		<!-- Plain text of login password. When cypher text exists, the cypher text will be used. --> 
		<login_pwd>YOUR_PASSWORD_HERE</login_pwd>
		<!-- mo o mo o语言，en：英文，chs：简体中文 -->
		<!-- moomoo OpenD language. en: English, chs: Simplified Chinese -->
		<lang>en</lang>
	<!-- 进阶参数 -->
	<!-- Advanced parameters -->
		<!-- moomoo OpenD日志等级，no, debug, info, warning, error, fatal --> 
		<!-- moomoo OpenD log level: no, debug, info, warning, error, fatal --> 
		<log_level>info</log_level>
		<!-- moomoo OpenD日志路径，指定生成日志的路径，不设置时使用默认路径 --> 
		<!-- moomoo OpenD Log path, Specify the path to generate logs, Use default path if not set --> 
		<!-- <log_path>D:\log</log_path> -->
		<!-- API推送协议格式，0：pb, 1：json -->
		<!-- API push protocol format. 0: pb, 1: json -->
		<push_proto_type>0</push_proto_type>
		<!-- API订阅数据推送频率控制，单位毫秒，目前不包括K线和分时，不设置则不限制频率-->
		<!-- Data Push Frequency, in milliseconds. Candlesticks and timeframes are not included. If not set, the frequency will be unlimited. -->
		<!-- <qot_push_frequency>1000</qot_push_frequency> -->
		<!-- Telnet监听地址,不填默认127.0.0.1 -->
		<!-- Telnet listening address. 127.0.0.1 by default -->
		<!-- <telnet_ip>127.0.0.1</telnet_ip> -->
		<!-- Telnet监听端口 -->
		<!-- Telnet listening port -->
		<!-- <telnet_port>22222</telnet_port> -->
		<!-- API协议加密私钥文件路径,不设置则不加密 -->
		<!-- File path for private key for API protocol enctyption. If not set, it will not be encrypted. -->
		<rsa_private_key>RSA__KEY_FILEPATH_HERE</rsa_private_key>
```
### 3. RSA Key Generation
For security, this project uses RSA encryption.
1.  Generate a private/public key pair by following [Moomoo's Protocol Encryption Process](https://openapi.moomoo.com/moomoo-api-doc/en/qa/other.html#1479)
3.  Copy and paste the private key into a text file on your local machine.
4.  Enter the abosolute file path of your text file in `RSA__KEY_FILEPATH_HERE` as above in OpenD.xml

### 4. .env configuration(`.env`)
1. Rename .env.example from this repo to .env
2. Set `KEY_PATH` to the absolute file path of your RSA key .txt file by replacing `YOUR_RSA_KEY_PATH_HERE.txt`

### 5. Account Cashflow History:
Open your `.env` file and set `START_DATE` to the date you opened your Moomoo account (YYYY-MM-DD) as a string. This is to get all historical account cashflow data.



### 6. Install Dependencies
This project uses `pipenv` for dependency management. Run this line
```bash
pip install pipenv
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
│   ├── moomoo_api.py     # Moomoo OpenD API interface
│   └── dashboard.py      # Plotly/pandas visualization logic
├── main.py               # Entry point
├── streamlit_app.py      # Interactive Web UI
├── Pipfile               # Dependency definitions
└── README.md             
```
## 📊 Usage
1. Initialize/Update Database: Run the main script to fetch historical data and today's snapshot. Depending on how old the account is, obtaining account cashflow historically may take a while. Otherwise, after initialization, it should only take a few seconds.
```bash
pipenv run python main.py
```
3. Launch Dashboard:
```bash
streamlit run streamlit_app.py
```
