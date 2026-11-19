# 🧹 Email Cleaner & Unsubscriber Desktop Suite

A fast, lightweight, and automated desktop email cleaning suite for **Windows** and **macOS**.  
Designed to help you clean up thousands of cluttered emails, categorize senders, and **reliably unsubscribe** from marketing lists, newsletters, and spam networks without tedious manual effort.

Supports **Mozilla Thunderbird** (1-click zero-setup modern OAuth2), **Apple Mail**, **Microsoft Classic Outlook**, and **Universal IMAP**.

---

## 🚀 Key Benefits & Superpowers

- **🦅 Zero-Password / Zero-Credential Setup via Thunderbird**:
  - Connect your Google (`@gmail.com`), Microsoft (`@outlook.com`, `@live.com`, `@hotmail.com`), Yahoo, or iCloud accounts in **Mozilla Thunderbird** using standard browser sign-in.
  - Email Cleaner automatically discovers Thunderbird profiles and scans your local mailboxes directly. No developer API keys, Azure portal apps, or App Passwords required!
- **⚡ Two Dedicated Desktop Applications**:
  1. **MailSweep** (`http://localhost:7890`): Intelligent domain classifier that groups emails into 9 categories (Spam, Marketing, Retail, Trading/Crypto, Tech, Banking, etc.) and executes bulk deletions.
  2. **UnsubBot** (`http://localhost:7891`): Multi-protocol automated unsubscriber with headless Chrome automation to genuinely opt-out of newsletters.
- **🤖 Real Headless Chrome Automation (Playwright)**:
  - Unlike naive unsubscription scripts that fail on modern React/Vue pages or count simple `HTTP 200` responses as false positives, UnsubBot launches a real headless browser instance in the background.
  - It loads the unsubscription portal, auto-fills your email address, selects *"Unsubscribe from all"*, clicks confirmation buttons, and verifies the final unsubscription notice.
- **🍎 macOS & 🪟 Windows Native Integration**:
  - **macOS**: Automatically interfaces with **Apple Mail** and local Thunderbird mboxes.
  - **Windows**: Automatically interfaces with **Thunderbird** and **Microsoft Outlook** stores.
- **📊 Real-Time Terminal & Web Telemetry**:
  - Live console output with timestamps and visual badges for each phase of scanning, batch deletions, and unsubscription attempts.
- **🛡️ Auto-Self-Healing Launchers**:
  - Launch scripts automatically detect Python, install it if missing, initialize a virtual environment (`venv`), and install all dependencies automatically.

---

## 📦 Suite Architecture

```
Email Cleaner/
├── Windows/
│   ├── MailSweep/               # Bulk email categorization & deletion engine (Port 7890)
│   │   ├── backend.py
│   │   ├── run_cleaner.bat      # Standalone cleaner launcher with auto-venv
│   │   └── static/              # Modern glassmorphism dark-theme web dashboard
│   ├── UnsubBot/                # Multi-protocol automated unsubscriber (Port 7891)
│   │   ├── backend.py
│   │   ├── run_unsubscriber.bat # Standalone unsubscriber launcher with auto-venv
│   │   └── static/
│   ├── requirements.txt
│   ├── start_windows_suite.bat  # 1-Click launcher menu for Windows (auto-python, auto-venv)
│   └── stop_servers.bat         # Clean shutdown script
│
├── MacOs/
│   ├── MailSweep/               # Apple Mail & Thunderbird cleaner for macOS (Port 7890)
│   │   ├── backend.py
│   │   ├── run_cleaner.command  # Standalone cleaner launcher for Mac
│   │   └── static/
│   ├── UnsubBot/                # Apple Mail & Thunderbird unsubscriber for macOS (Port 7891)
│   │   ├── backend.py
│   │   ├── run_unsubscriber.command # Standalone unsubscriber launcher for Mac
│   │   └── static/
│   ├── requirements.txt
│   ├── start_macos_suite.command# 1-Click launcher for macOS (auto-python, auto-venv)
│   └── INSTRUCTIONS.txt
│
└── README.md
```

---

## 🛠️ Installation & Setup

### Prerequisites

- **Python 3.8+** (Launchers will auto-install or guide you if not present).
- **Mozilla Thunderbird** (Recommended for easiest 1-click modern Google & Microsoft account connection) OR native **Apple Mail** (on Mac) / **Classic Outlook** (on Windows).
- **Google Chrome** browser (for UnsubBot's headless form solver).

### 🚦 How to Run

#### Windows
Simply double-click `start_windows_suite.bat`:
- It checks Python, creates a local `venv`, installs dependencies, and displays the launch menu.
- Choose:
  1. **Launch MailSweep** (`http://localhost:7890`)
  2. **Launch UnsubBot** (`http://localhost:7891`)
  3. **Launch Both Applications** (Side-by-side terminal windows with live telemetry)

#### macOS
Simply double-click `start_macos_suite.command` or execute in Terminal:
```bash
chmod +x start_macos_suite.command
./start_macos_suite.command
```

---

## 📖 Step-by-Step User Guide

### 1. Connecting Accounts Easily with Zero Passwords
1. Open **Mozilla Thunderbird** (or Apple Mail on Mac).
2. Add your email address (`name@gmail.com`, `name@live.com`, etc.) using the standard web login popup.
3. Allow Thunderbird to sync your folders.
4. Launch **Email Cleaner** — your accounts appear automatically in the dropdown!

### 2. Using MailSweep (Email Cleaner)
1. Select your email account from the dropdown.
2. Select the folder (e.g. `INBOX` or `All Mail`).
3. Click **⚡ Scan Account**.
4. Senders are automatically grouped into categorized domains:
   - 🚨 *Spam & Casino*
   - 📢 *Ad Networks & Marketing*
   - 🛍️ *Shopping & Travel Promos*
   - 📈 *Trading, Forex & Crypto*
   - 💻 *Tech, Cloud & AI Tools*
   - 👤 *Personal Contacts*
5. Check individual domains or click **Select All Spam & Ads**.
6. Click **Delete Selected** — messages are safely moved to Trash / Deleted Items.

### 3. Using UnsubBot (Automated Unsubscriber)
1. Select your email account and target mailbox folder.
2. Select the **Scan Depth** (e.g., *Full Mailbox* or *Latest 500 emails*).
3. Click **🔍 Find Subscriptions**.
4. UnsubBot identifies all newsletters with:
   - **RFC 8058 One-Click Unsubscribe headers**
   - **RFC 2369 List-Unsubscribe web and mailto links**
   - **HTML body opt-out & preference center URLs**
5. Select the subscriptions you want to cancel and click **Auto-Unsubscribe**.
6. Watch the live terminal as it executes:
   - **Phase 1**: Silent RFC 8058 One-Click HTTP POST
   - **Phase 2**: RFC 2369 Header Web GET
   - **Phase 3**: RFC Mailto dispatch
   - **Phase 4**: Automated web form & preference solver
   - **Phase 5**: Real Headless Chrome automation for dynamic JavaScript/React portals
7. If a portal requires CAPTCHA verification or account login, UnsubBot provides an **[Open Link ↗]** button for instant manual completion.

---

## 🏢 Parent Company & Commercial Subsidiaries Matrix

Email Cleaner is proudly engineered and maintained under the digital infrastructure and technology umbrella of **Global Ads Media, LLC**.

### Global Ads Media, LLC (Parent Organization)
<p align="center">
  <a href="https://globaladsmedia.us" target="_blank">
    <img src="https://github.com/gamgsp/globaldata/blob/main/Global%20Ads%20Media/globaladsmedia-black-1024-300.png?raw=true" alt="Global Ads Media, LLC" width="280" />
  </a>
</p>

* **Website:** <a href="https://globaladsmedia.us" target="_blank" rel="noopener noreferrer">https://globaladsmedia.us</a>
* **Sector:** Enterprise Digital Marketing, AdTech Infrastructure & Global Traffic Aggregation
* **Overview:** Global Ads Media operates automated programmatic advertising, high-volume Real-Time Bidding (RTB), and audience segmentation engines, linking next-generation web technologies, fintech, and digital media platforms into a unified commercial ecosystem.

---

### Commercial Subsidiaries

<table>
  <thead>
    <tr>
      <th width="200">Subsidiary</th>
      <th width="140">Sector</th>
      <th>Commercial Description & Official Website</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td align="center">
        <a href="https://1dollarcloud.com" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/1dollarcloud/1dollarcloud-black-1024-210.png?raw=true" alt="1 Dollar Cloud" width="140" /><br />
          <strong>1 Dollar Cloud</strong>
        </a>
      </td>
      <td><strong>Cloud & Hosting</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://1dollarcloud.com" target="_blank">1dollarcloud.com</a><br />
        Affordable, high-performance NVMe cloud hosting, Cloud VPS, dedicated infrastructure, and domain registration starting at just $1 per month.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://gspcoin.us" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/GSP%20Coin/gspcname%201024x452%20black.png?raw=true" alt="GSP Coin" width="140" /><br />
          <strong>GSP Coin</strong>
        </a>
      </td>
      <td><strong>Layer-1 Blockchain</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://gspcoin.us" target="_blank">gspcoin.us</a><br />
        An enterprise-grade, decentralized Layer-1 cryptocurrency designed for global commercial transactions, high-yield Smartnodes, and AdTech settlement.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://gspcexchange.com" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/GSPC%20Exchange/gspcexc-dark-logo.png?raw=true" alt="GSPC Exchange" width="140" /><br />
          <strong>GSPC Exchange</strong>
        </a>
      </td>
      <td><strong>DeFi & P2P Trading</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://gspcexchange.com" target="_blank">gspcexchange.com</a><br />
        A secure, non-custodial P2P cryptocurrency escrow exchange featuring automated order matching, multi-chain settlement, and zero middleman risk.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://1url.my" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/1url/1url-black-1024-380.png?raw=true" alt="1url" width="140" /><br />
          <strong>1url</strong>
        </a>
      </td>
      <td><strong>Enterprise SaaS</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://1url.my" target="_blank">1url.my</a><br />
        A high-performance URL shortening and link management service that allows businesses and individuals to create custom, branded, and trackable smart links.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://globaltradepulse.com" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/Global%20Trade%20Pulse/gtp-logo-black.png?raw=true" alt="Global Trade Pulse" width="140" /><br />
          <strong>Global Trade Pulse</strong>
        </a>
      </td>
      <td><strong>Quantitative Intelligence</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://globaltradepulse.com" target="_blank">globaltradepulse.com</a><br />
        An algorithmic financial intelligence and multi-market scanner platform providing real-time technical analysis across US equities, Indian markets, gold, and forex.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://worldnewsguru.us" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/World%20News%20Guru/wnglogo-black-1024-330.png?raw=true" alt="World News Guru" width="140" /><br />
          <strong>World News Guru</strong>
        </a>
      </td>
      <td><strong>Global Journalism</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://worldnewsguru.us" target="_blank">worldnewsguru.us</a><br />
        A premier digital media platform that aggregates news from multiple verified global sources in a comprehensive, fast, and unbiased manner.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://globalcricinfo.com" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/Global%20Cric%20Info/global%20cric%20info%20logo%20black.png?raw=true" alt="Global Cric Info" width="140" /><br />
          <strong>Global Cric Info</strong>
        </a>
      </td>
      <td><strong>Sports Media</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://globalcricinfo.com" target="_blank">globalcricinfo.com</a><br />
        An international sports media portal offering real-time ball-by-ball updates on cricket scores, breaking tournament news, schedules, and player telemetry.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://globalsocialpost.com" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/Global%20Social%20Post/globalsocialpost-black-1024-300.png?raw=true" alt="Global Social Post" width="140" /><br />
          <strong>Global Social Post</strong>
        </a>
      </td>
      <td><strong>Social Automation</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://globalsocialpost.com" target="_blank">globalsocialpost.com</a><br />
        An omni-channel social media automation platform that allows businesses and agencies to design, schedule, and automate posts across multiple channels simultaneously.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://globalsmtpmail.com" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/Global%20Smtp%20Mail/gsm-black-1024-320.png?raw=true" alt="Global SMTP Mail" width="140" /><br />
          <strong>Global SMTP Mail</strong>
        </a>
      </td>
      <td><strong>Email Infrastructure</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://globalsmtpmail.com" target="_blank">globalsmtpmail.com</a><br />
        A reliable, high-throughput email delivery service and enterprise SMTP relay infrastructure that guarantees superior inbox deliverability rates.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://globalintelinvest.com" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/Global%20Intel%20Invest/glob_int_inv_black_logo.png?raw=true" alt="Global Intel Invest" width="140" /><br />
          <strong>Global Intel Invest</strong>
        </a>
      </td>
      <td><strong>Financial Insights</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://globalintelinvest.com" target="_blank">globalintelinvest.com</a><br />
        An intelligent investment research platform delivering real-time economic data, institutional market analysis, and actionable macroeconomic insights.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://traffixpert.com" target="_blank">
          <img src="https://github.com/gamgsp/globaldata/blob/main/Traffixpert/traffixpert-black-1024-410.png?raw=true" alt="Traffixpert" width="140" /><br />
          <strong>Traffixpert</strong>
        </a>
      </td>
      <td><strong>AdTech & Traffic</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://traffixpert.com" target="_blank">traffixpert.com</a><br />
        A performance digital marketing network that connects web publishers and advertisers to drive high-converting, targeted organic and paid traffic.
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://tryyourluck.today" target="_blank" rel="noopener noreferrer">
          <img src="https://github.com/gamgsp/globaldata/blob/main/Try%20Your%20Luck/tryyourluck-logo.png?raw=true" alt="Try Your Luck" width="140" /><br />
          <strong>Try Your Luck</strong>
        </a>
      </td>
      <td><strong>Digital Goods & Draws</strong></td>
      <td>
        <strong>Website:</strong> <a href="https://tryyourluck.today" target="_blank" rel="noopener noreferrer">tryyourluck.today</a><br />
        A modern digital marketplace offering $1.00 utility software and digital downloads bundled with bonus tickets into provably fair prize draws.
      </td>
    </tr>
  </tbody>
</table>

---

## 📄 License

MIT License. Developed and maintained by <a href="https://globaladsmedia.us" target="_blank" rel="noopener noreferrer">Global Ads Media, LLC</a>. Free and open-source for personal and commercial productivity.
