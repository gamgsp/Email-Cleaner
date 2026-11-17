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

---

## 📦 Suite Architecture

```
Email Cleaner/
├── Windows/
│   ├── MailSweep/               # Bulk email categorization & deletion engine (Port 7890)
│   │   ├── backend.py
│   │   └── static/              # Modern glassmorphism dark-theme web dashboard
│   ├── UnsubBot/                # Multi-protocol automated unsubscriber (Port 7891)
│   │   ├── backend.py
│   │   └── static/
│   ├── requirements.txt
│   ├── start_windows_suite.bat  # 1-Click launcher menu for Windows
│   └── stop_servers.bat         # Clean shutdown script
│
├── MacOs/
│   ├── MailSweep/               # Apple Mail & Thunderbird cleaner for macOS (Port 7890)
│   │   ├── backend.py
│   │   └── static/
│   ├── UnsubBot/                # Apple Mail & Thunderbird unsubscriber for macOS (Port 7891)
│   │   ├── backend.py
│   │   └── static/
│   ├── requirements.txt
│   ├── start_macos_suite.command# 1-Click launcher for macOS
│   └── INSTRUCTIONS.txt
│
└── README.md
```

---

## 🛠️ Installation & Setup

### Prerequisites

- **Python 3.8+** installed.
- **Mozilla Thunderbird** (Recommended for easiest 1-click modern Google & Microsoft account connection) OR native **Apple Mail** (on Mac) / **Classic Outlook** (on Windows).
- **Google Chrome** browser (for UnsubBot's headless form solver).

### 1. Install Dependencies

#### On Windows:
```cmd
cd Windows
pip install -r requirements.txt
```

#### On macOS:
```bash
cd MacOs
pip install -r requirements.txt
```

*(Note: Playwright utilizes your installed Google Chrome browser to automate web unsubscription portals).*

---

## 🚦 How to Run

### Windows
Double-click `start_windows_suite.bat` (or run it via Command Prompt/PowerShell):
```cmd
start_windows_suite.bat
```
Choose from the interactive menu:
1. **Launch MailSweep** (`http://localhost:7890`)
2. **Launch UnsubBot** (`http://localhost:7891`)
3. **Launch Both Applications** (Opens side-by-side terminal windows with live logging)

### macOS
Double-click `start_macos_suite.command` or run in Terminal:
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

## 🔒 Privacy & Security

- **100% Local & Offline First**: Runs entirely on your local machine (`localhost`).
- **No Third-Party Cloud Servers**: Your emails, credentials, and data are never transmitted to external services.
- **Safe Deletion**: Deletions move messages to your account's standard Trash/Deleted Items folder rather than permanently purging them without recovery.

---

## 📄 License

MIT License. Free and open source for personal and commercial productivity.
