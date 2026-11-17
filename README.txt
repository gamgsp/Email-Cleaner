================================================================================
              EMAIL SUITE: MAILSWEEP & UNSUBBOT (CROSS-PLATFORM)
================================================================================

A complete desktop email management suite featuring:
  1. MailSweep : Intelligent domain-based email cleaner (bulk delete unwanted mail)
  2. UnsubBot  : Automated unsubscribe & survey solving engine (RFC 8058 + web forms)

Available with native support for both:
  - macOS (Apple Mail & Universal IMAP)
  - Windows (Microsoft Outlook & Universal IMAP)

================================================================================
NEW IN THIS UPDATE:
================================================================================
  ✅ Real-time Terminal Logging: Full transparency with timestamps and icons for
     every scan, unsubscription attempt (RFC One-Click, GET, Mailto, Forms),
     and bulk deletion operation on both Windows and macOS.
  ✅ Universal IMAP Engine: Built-in support for any mailbox (Outlook.com,
     Office 365, Gmail, Yahoo, iCloud, etc.) solving the Windows "New Outlook"
     COM limitation.
  ✅ Multi-Protocol Unsubscribe Engine: RFC 8058 One-Click, RFC 2369 GET,
     native mailto dispatch, web form/survey auto-solver, and direct manual action
     links for CAPTCHA/login-protected sites.
  ✅ Auto-detect Python executable / launcher (`py` & `python.exe`) on Windows.

================================================================================
FOLDER STRUCTURE
================================================================================

Email Cleaner/
│
├── start_macos_suite.command        [Double-click on Mac to start]
├── start_windows_suite.bat          [Double-click on Windows to start]
├── README.txt                       [This file]
│
├── MacOs/                           [Apple Mail & IMAP Edition]
│   ├── INSTRUCTIONS.txt             [Detailed Mac setup & troubleshooting]
│   ├── requirements.txt             [requests, beautifulsoup4]
│   ├── start_macos_suite.command    [Mac suite launcher]
│   ├── MailSweep/                   [Email Cleaner for Mac (Port 7890)]
│   │   ├── backend.py
│   │   ├── run_cleaner.command
│   │   └── static/
│   └── UnsubBot/                    [Auto-Unsubscriber for Mac (Port 7891)]
│       ├── backend.py
│       ├── run_unsubscriber.command
│       └── static/
│
└── Windows/                         [Microsoft Outlook & IMAP Edition]
    ├── INSTRUCTIONS.txt             [Detailed Windows setup & troubleshooting]
    ├── requirements.txt             [pywin32, requests, beautifulsoup4]
    ├── start_windows_suite.bat      [Windows suite launcher]
    ├── MailSweep/                   [Email Cleaner for Windows (Port 7890)]
    │   ├── backend.py
    │   ├── run_cleaner.bat
    │   └── static/
    └── UnsubBot/                    [Auto-Unsubscriber for Windows (Port 7891)]
        ├── backend.py
        ├── run_unsubscriber.bat
        └── static/

================================================================================
QUICK START GUIDE
================================================================================

--------------------------------------------------------------------------------
🍎 FOR MACOS USERS
--------------------------------------------------------------------------------
1. Prerequisites:
   - macOS with Apple Mail or any IMAP account.
   - Python 3 installed.
   - Install dependencies:
       cd MacOs
       pip3 install -r requirements.txt

2. Run:
   - Double-click `start_macos_suite.command` (or inside `MacOs/`).

--------------------------------------------------------------------------------
🪟 FOR WINDOWS USERS
--------------------------------------------------------------------------------
1. Prerequisites:
   - Python 3.8+ installed.
   - Install dependencies in Command Prompt:
       py -m pip install -r Windows\requirements.txt

2. Run:
   - Double-click `start_windows_suite.bat` (or inside `Windows/`).
   - If using "New Outlook for Windows", click "+ Add Account" in the web UI
     to connect via Universal IMAP mode (works with Outlook.com, Office 365, etc.).
