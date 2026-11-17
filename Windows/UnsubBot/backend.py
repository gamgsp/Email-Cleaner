import http.server
import socketserver
import json
import urllib.parse
import urllib.request
import re
import os
import sys
import email
from email import policy
from email.header import decode_header
import mailbox
import threading
import time
import datetime
import imaplib
import glob
from collections import defaultdict, Counter
import requests
from bs4 import BeautifulSoup

PORT = 7891
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounts_config.json')

# Check pywin32 availability
try:
    import win32com.client
    import pythoncom
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# Check Playwright availability for browser-level automation
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def log_event(tag, message, level="INFO"):
    """Formatted, timestamped terminal logging with immediate flush."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    icons = {
        "INFO": "ℹ️ ",
        "SUCCESS": "✅",
        "WARNING": "⚠️ ",
        "ERROR": "❌",
        "UNSUB": "🔕",
        "SCAN": "🔍",
        "ACCOUNTS": "📫",
        "IMAP": "🌐",
        "OUTLOOK": "📧",
        "THUNDERBIRD": "🦅",
        "FORM": "📝",
        "RFC": "⚡"
    }
    icon = icons.get(tag, icons.get(level, "• "))
    print(f"[{ts}] {icon} [{tag}] {message}", flush=True)


# ==============================================================================
# CONFIG & IMAP STORAGE
# ==============================================================================
def load_saved_accounts():
    """Load saved IMAP accounts from JSON configuration file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log_event("ACCOUNTS", f"Failed to read {CONFIG_FILE}: {e}", level="WARNING")
    return []


def save_saved_accounts(accounts):
    """Save IMAP accounts to JSON configuration file."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=2)
        return True
    except Exception as e:
        log_event("ACCOUNTS", f"Failed to save {CONFIG_FILE}: {e}", level="ERROR")
        return False


def test_imap_connection(host, port, username, password, use_ssl=True):
    """Test IMAP credentials and return available folders."""
    log_event("IMAP", f"Testing connection to {host}:{port} (SSL: {use_ssl}) for '{username}'...")
    try:
        if use_ssl:
            client = imaplib.IMAP4_SSL(host, int(port), timeout=15)
        else:
            client = imaplib.IMAP4(host, int(port), timeout=15)

        client.login(username, password)
        status, folder_data = client.list()
        folders = []
        if status == 'OK':
            for item in folder_data:
                s = item.decode('utf-8', errors='ignore') if isinstance(item, bytes) else str(item)
                m = re.search(r'\((?P<flags>[^\)]*)\)\s+\"(?P<delim>[^\"]+)\"\s+(?P<name>.+)', s)
                if m:
                    fname = m.group('name').strip(' "')
                    folders.append(fname)
                else:
                    parts = s.split(' ')
                    folders.append(parts[-1].strip(' "'))
        client.logout()
        log_event("IMAP", f"Connection successful! Found {len(folders)} folders.", level="SUCCESS")
        return True, folders, "Connected successfully"
    except Exception as e:
        log_event("IMAP", f"Connection failed: {str(e)}", level="ERROR")
        return False, [], str(e)


# ==============================================================================
# AUTOMATIC WINDOWS ACCOUNT DISCOVERY (New Outlook / Live / Office)
# ==============================================================================
def discover_windows_email_accounts():
    """Auto-discover accounts from New Outlook (OneAuth), Substrate, and Windows Registry."""
    accounts = []
    seen = set()

    # 1. OneAuth accounts (New Outlook for Windows - olk.exe)
    oneauth_dir = os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\OneAuth\accounts')
    if os.path.exists(oneauth_dir):
        for fname in os.listdir(oneauth_dir):
            fpath = os.path.join(oneauth_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    email_addr = data.get('email') or data.get('login_name')
                    disp_name = data.get('display_name') or email_addr
                    if email_addr and email_addr.lower() not in seen:
                        accounts.append({
                            'name': disp_name,
                            'username': email_addr,
                            'email': email_addr,
                            'type': 'new_outlook',
                            'host': 'outlook.office365.com',
                            'port': 993,
                            'ssl': True,
                            'folders': ['Inbox', 'Junk Email', 'Deleted Items', 'Archive']
                        })
                        seen.add(email_addr.lower())
            except Exception:
                pass

    # 2. Substrate Profile Aliases
    blobs_dir = os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\OneAuth\blobs')
    if os.path.exists(blobs_dir):
        for fpath in glob.glob(os.path.join(blobs_dir, '*_substrate_profile')):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    pdata = json.load(f)
                    for em in pdata.get('emails', []):
                        ea = em.get('emailAddress')
                        if ea and ea.lower() not in seen:
                            accounts.append({
                                'name': f'Outlook ({ea})',
                                'username': ea,
                                'email': ea,
                                'type': 'new_outlook',
                                'host': 'outlook.office365.com',
                                'port': 993,
                                'ssl': True,
                                'folders': ['Inbox', 'Junk Email', 'Deleted Items', 'Archive']
                            })
                            seen.add(ea.lower())
            except Exception:
                pass

    # 3. Windows IdentityCRL
    try:
        import winreg
        key_path = r'Software\Microsoft\IdentityCRL\UserExtendedProperties'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            i = 0
            while True:
                try:
                    subkey = winreg.EnumKey(key, i)
                    if '@' in subkey and subkey.lower() not in seen:
                        accounts.append({
                            'name': f'Microsoft Account ({subkey})',
                            'username': subkey,
                            'email': subkey,
                            'type': 'new_outlook',
                            'host': 'outlook.office365.com',
                            'port': 993,
                            'ssl': True,
                            'folders': ['Inbox', 'Junk Email', 'Deleted Items', 'Archive']
                        })
                        seen.add(subkey.lower())
                    i += 1
                except OSError:
                    break
    except Exception:
        pass

    return accounts


# ==============================================================================
# THUNDERBIRD ACCOUNT AUTO-DISCOVERY & MBOX ENGINE
# ==============================================================================
def discover_thunderbird_accounts():
    """Auto-discover email accounts and local mbox stores from Mozilla Thunderbird."""
    tb_profiles_dir = os.path.expandvars(r'%APPDATA%\Thunderbird\Profiles')
    if not os.path.exists(tb_profiles_dir):
        return []

    accounts = []
    seen = set()

    try:
        for prof in os.listdir(tb_profiles_dir):
            prof_dir = os.path.join(tb_profiles_dir, prof)
            prefs_file = os.path.join(prof_dir, 'prefs.js')
            if not os.path.isfile(prefs_file):
                continue

            servers = {}
            with open(prefs_file, 'r', encoding='latin-1') as f:
                for line in f:
                    line = line.strip()
                    m = re.match(r'user_pref\("mail\.server\.(server\d+)\.(userName|hostname|directory|name)",\s*"([^"]+)"\);', line)
                    if m:
                        sid, key, val = m.groups()
                        servers.setdefault(sid, {})[key] = val.replace('\\\\', '\\')

            for sid, sdata in servers.items():
                username = sdata.get('userName', '').strip()
                if not username or username.lower() == 'nobody':
                    continue

                hostname = sdata.get('hostname', '')
                mbox_dir = sdata.get('directory', '')
                if not mbox_dir or not os.path.exists(mbox_dir):
                    cand = os.path.join(prof_dir, 'ImapMail', hostname)
                    if os.path.exists(cand):
                        mbox_dir = cand

                folders = []
                if os.path.exists(mbox_dir):
                    for root, dirs, files in os.walk(mbox_dir):
                        for item in files:
                            if not item.endswith('.msf') and not item.endswith('.dat'):
                                rel = os.path.relpath(os.path.join(root, item), mbox_dir).replace('\\', '/')
                                folders.append(rel)

                if not folders:
                    folders = ['INBOX', 'All Mail', 'Trash', 'Sent']

                display_name = sdata.get('name') or username
                acc_key = f"{username}@{hostname}".lower()
                if acc_key in seen:
                    continue
                seen.add(acc_key)

                email_addr = username if '@' in username else f"{username}@{hostname}"
                accounts.append({
                    'name': f"Thunderbird: {display_name}",
                    'username': username,
                    'email': email_addr,
                    'type': 'thunderbird',
                    'hostname': hostname,
                    'directory': mbox_dir,
                    'has_password': True,  # Uses local synced mbox, no basic auth or app password needed!
                    'folders': folders
                })
                log_event("THUNDERBIRD", f"Found Thunderbird Account: {display_name} <{email_addr}> ({len(folders)} folders)")
    except Exception as e:
        log_event("THUNDERBIRD", f"Error scanning Thunderbird profiles: {e}", level="WARNING")

    return accounts


# ==============================================================================
# OUTLOOK COM MAPI ENGINE
# ==============================================================================
def is_outlook_configured():
    """Checks Windows Registry to verify if an active email account is configured in Outlook."""
    import winreg
    keys = [
        r"Software\Microsoft\Office\16.0\Outlook\Profiles",
        r"Software\Microsoft\Office\15.0\Outlook\Profiles",
        r"Software\Microsoft\Office\14.0\Outlook\Profiles",
        r"Software\Microsoft\Windows NT\CurrentVersion\Windows Messaging Subsystem\Profiles"
    ]
    for key_path in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
                num_subkeys, _, _ = winreg.QueryInfoKey(k)
                for i in range(num_subkeys):
                    prof_name = winreg.EnumKey(k, i)
                    try:
                        acc_path = f"{key_path}\\{prof_name}\\9375CFF0413111d3B88A00104B2A6676"
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, acc_path) as ak:
                            n_acc, _, _ = winreg.QueryInfoKey(ak)
                            for j in range(n_acc):
                                sub = winreg.EnumKey(ak, j)
                                try:
                                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{acc_path}\\{sub}") as sk:
                                        svc_name, _ = winreg.QueryValueEx(sk, "Service Name")
                                        if svc_name and svc_name.upper() != "CONTAB":
                                            return True
                                except Exception:
                                    pass
                    except Exception:
                        pass
        except Exception:
            pass
    return False


def get_outlook_namespace():
    """Initializes COM and returns the Outlook MAPI namespace, if Outlook is configured."""
    if not HAS_WIN32:
        raise RuntimeError("pywin32 is not installed. Install via: pip install pywin32")
    if not is_outlook_configured():
        raise RuntimeError("No configured email accounts found in Microsoft Outlook profile.")
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
    except Exception:
        outlook = win32com.client.gencache.EnsureDispatch("Outlook.Application")
    return outlook.GetNamespace("MAPI")


def get_sender_details(item):
    """Extract clean sender email and display name from an Outlook MailItem."""
    name = ""
    email_addr = ""
    try:
        name = getattr(item, "SenderName", "") or ""
    except Exception:
        pass

    try:
        email_type = getattr(item, "SenderEmailType", "")
        if email_type == "SMTP":
            email_addr = getattr(item, "SenderEmailAddress", "") or ""
        elif email_type == "EX":
            try:
                sender = getattr(item, "Sender", None)
                if sender:
                    ex_user = sender.GetExchangeUser()
                    if ex_user:
                        email_addr = getattr(ex_user, "PrimarySmtpAddress", "") or ""
            except Exception:
                pass

            if not email_addr:
                try:
                    pa = item.PropertyAccessor
                    email_addr = pa.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x5D01001E")
                except Exception:
                    pass
        else:
            email_addr = getattr(item, "SenderEmailAddress", "") or ""
    except Exception:
        pass

    if not email_addr:
        try:
            email_addr = getattr(item, "SenderEmailAddress", "") or ""
        except Exception:
            pass

    m = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', email_addr)
    if m:
        clean_email = m.group(0).lower()
    else:
        m2 = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', name)
        clean_email = m2.group(0).lower() if m2 else email_addr.lower()

    return name, clean_email


def get_mail_accounts():
    """Discover all accounts from Classic Outlook COM, Windows auto-discovery, and saved IMAP."""
    accounts = []
    seen = set()
    com_error = None
    com_available = False

    # 1. Try Classic Outlook COM
    if HAS_WIN32:
        try:
            mapi = get_outlook_namespace()
            com_available = True

            for acc in mapi.Accounts:
                name = acc.DisplayName
                email_addr = getattr(acc, "SmtpAddress", "") or name
                if name and name.lower() not in seen:
                    accounts.append({
                        "name": name,
                        "username": name,
                        "email": email_addr,
                        "type": "outlook",
                        "has_password": True,
                        "folders": ["Inbox", "Junk Email", "Deleted Items", "Archive"]
                    })
                    seen.add(name.lower())
                    seen.add(email_addr.lower())
                    log_event("ACCOUNTS", f"Found Outlook MAPI Account: {name} <{email_addr}>")

            for folder in mapi.Folders:
                fname = folder.Name
                if fname.lower() not in seen:
                    subfolders = [f.Name for f in folder.Folders] or ["Inbox", "Junk Email"]
                    accounts.append({
                        "name": fname,
                        "username": fname,
                        "email": fname,
                        "type": "outlook",
                        "has_password": True,
                        "folders": subfolders
                    })
                    seen.add(fname.lower())
                    log_event("ACCOUNTS", f"Found Outlook Store Folder: {fname}")

        except Exception as e:
            err_str = str(e)
            if "-2147221005" in err_str or "Invalid class string" in err_str:
                com_error = "Classic Outlook COM not registered. 'New Outlook for Windows' (olk.exe) detected."
                log_event("ACCOUNTS", com_error, level="INFO")
            else:
                com_error = f"Outlook COM error: {err_str}"
                log_event("ACCOUNTS", com_error, level="WARNING")

    # 2. Load saved configs
    saved_imap = load_saved_accounts()
    saved_by_email = {a.get('email', '').lower(): a for a in saved_imap if a.get('email')}

    # 3. Auto-discover Windows Outlook / Live accounts
    auto_accounts = discover_windows_email_accounts()
    for acc in auto_accounts:
        em = acc['email'].lower()
        if em not in seen:
            if em in saved_by_email:
                saved = saved_by_email[em]
                acc['has_password'] = True
                acc['password'] = saved.get('password')
                acc['host'] = saved.get('host', acc.get('host'))
                acc['port'] = saved.get('port', acc.get('port'))
                if saved.get('folders'):
                    acc['folders'] = saved['folders']
            else:
                acc['has_password'] = False
            accounts.append(acc)
            seen.add(em)
            seen.add(acc['name'].lower())
            log_event("ACCOUNTS", f"Auto-discovered Windows Outlook account: {acc['name']} <{acc['email']}>")

    # 4. Auto-discover Mozilla Thunderbird accounts
    tb_accounts = discover_thunderbird_accounts()
    for acc in tb_accounts:
        acc_key = acc['name'].lower()
        if acc_key not in seen:
            accounts.append(acc)
            seen.add(acc_key)
            if acc.get('email'):
                seen.add(acc['email'].lower())

    # 5. Any other saved IMAP accounts
    for acc in saved_imap:
        em = acc.get('email', '').lower()
        acc_name = acc.get('name') or em
        if em not in seen and acc_name.lower() not in seen:
            accounts.append({
                "name": acc_name,
                "username": acc.get("username", em),
                "email": em,
                "type": "imap",
                "host": acc.get("host"),
                "port": acc.get("port", 993),
                "has_password": bool(acc.get("password")),
                "folders": acc.get("folders", ["INBOX", "Junk", "Spam", "Archive", "Trash"])
            })
            seen.add(em)
            seen.add(acc_name.lower())

    log_event("ACCOUNTS", f"Accounts query complete. Total ready: {len(accounts)}")
    return {
        "accounts": accounts,
        "com_available": com_available,
        "com_error": com_error
    }


def get_target_folder(mapi, account_name, mailbox_name="Inbox"):
    """Locate the target mailbox folder inside the specified Outlook account."""
    target_root = None

    if account_name:
        clean_acc = account_name.strip().lower()
        for f in mapi.Folders:
            if f.Name.strip().lower() == clean_acc:
                target_root = f
                break
        if not target_root:
            for f in mapi.Folders:
                if clean_acc in f.Name.lower() or f.Name.lower() in clean_acc:
                    target_root = f
                    break

    if not target_root:
        try:
            target_root = mapi.GetDefaultFolder(6).Parent
        except Exception:
            if mapi.Folders.Count > 0:
                target_root = mapi.Folders.Item(1)

    if not target_root:
        raise ValueError(f"Could not locate store for account '{account_name}'")

    mb_lower = mailbox_name.strip().lower()

    for sub in target_root.Folders:
        if sub.Name.lower() == mb_lower:
            return sub

    for sub in target_root.Folders:
        s_lower = sub.Name.lower()
        if "inbox" in mb_lower and "inbox" in s_lower:
            return sub
        if ("all" in mb_lower or "mail" in mb_lower) and "all" in s_lower:
            return sub
        if ("junk" in mb_lower or "spam" in mb_lower) and ("junk" in s_lower or "spam" in s_lower):
            return sub

    if "inbox" in mb_lower:
        return mapi.GetDefaultFolder(6)
    elif "junk" in mb_lower or "spam" in mb_lower:
        return mapi.GetDefaultFolder(23)

    return target_root.Folders.Item(1)


# ==============================================================================
# HEADER & LINK PARSERS
# ==============================================================================
def parse_list_unsubscribe_headers(headers_str):
    """Extract ALL unsubscribe endpoints from RFC 2369 & RFC 8058 headers."""
    if not headers_str:
        return None, None, False

    http_url = None
    mailto_url = None
    is_one_click = False

    m_unsub = re.search(r'List-Unsubscribe:\s*([^\r\n]+)', headers_str, re.I)
    if m_unsub:
        raw_val = m_unsub.group(1).strip()
        urls = re.findall(r'<([^>]+)>', raw_val)
        if not urls:
            urls = [u.strip() for u in raw_val.split(',') if u.strip()]

        for u in urls:
            u_clean = u.strip()
            if u_clean.lower().startswith('http') and not http_url:
                http_url = u_clean
            elif u_clean.lower().startswith('mailto:') and not mailto_url:
                mailto_url = u_clean

    if re.search(r'List-Unsubscribe-Post:\s*List-Unsubscribe=One-Click', headers_str, re.I):
        is_one_click = True

    return http_url, mailto_url, is_one_click


def extract_web_unsubscribe_links(html_content):
    """Scan HTML body for marketing unsubscribe and preference center links."""
    links = []
    if not html_content:
        return links

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        text_pattern = re.compile(
            r'unsubscribe|opt.?out|manage preferences|email preferences|email settings|'
            r'subscription preferences|click here to stop|update your preferences|leave this list',
            re.I
        )
        url_pattern = re.compile(r'unsubscribe|optout|opt_out|preferences|manage_subscriptions', re.I)

        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text().strip().lower()
            if not href.startswith('http'):
                continue
            if text_pattern.search(text) or url_pattern.search(href):
                if not any(k in href.lower() for k in ['privacy', 'terms', 'facebook.com', 'twitter.com', 'instagram.com']):
                    links.append(href)
    except Exception:
        pass

    seen = set()
    deduped = []
    for l in links:
        if l not in seen:
            seen.add(l)
            deduped.append(l)
    return deduped[:5]


def decode_mime_header(header_val):
    """Safely decode RFC 2047 MIME-encoded headers."""
    if not header_val:
        return ""
    try:
        parts = decode_header(header_val)
        res = []
        for text, enc in parts:
            if isinstance(text, bytes):
                res.append(text.decode(enc or 'utf-8', errors='ignore'))
            else:
                res.append(str(text))
        return "".join(res)
    except Exception:
        return str(header_val)


def resolve_thunderbird_mbox_path(mbox_dir, mailbox_name):
    """Find the exact mbox file path, handling subdirectories like [Gmail].sbd/All Mail."""
    if not mbox_dir or not os.path.exists(mbox_dir):
        return None

    norm_name = mailbox_name.replace('/', os.sep).replace('\\', os.sep)
    direct = os.path.join(mbox_dir, norm_name)
    if os.path.isfile(direct):
        return direct

    mb_clean = os.path.basename(mailbox_name).lower().strip()
    for root, dirs, files in os.walk(mbox_dir):
        for f in files:
            if f.endswith('.msf') or f.endswith('.dat'):
                continue
            if f.lower() == mb_clean or f.lower() == mailbox_name.lower():
                return os.path.join(root, f)

    return None


def scan_thunderbird_subscriptions(account_cfg, mailbox_name="INBOX", limit=0):
    """Scan local Thunderbird mbox store for newsletter subscriptions & unsubscribe headers using fast streaming."""
    log_event("THUNDERBIRD", f"Scanning Thunderbird mailbox: '{account_cfg.get('name')}', Folder: '{mailbox_name}', Limit: {limit}...")
    mbox_dir = account_cfg.get("directory", "")
    if not mbox_dir or not os.path.exists(mbox_dir):
        return {"error": f"Thunderbird directory not found: {mbox_dir}", "subscriptions": [], "total_scanned": 0}

    mbox_files_to_scan = []
    if mailbox_name.strip().lower() in ["__all__", "full mailbox (all folders)", "all folders", "full mailbox"]:
        for root, dirs, files in os.walk(mbox_dir):
            for item in files:
                if not item.endswith('.msf') and not item.endswith('.dat'):
                    mbox_files_to_scan.append(os.path.join(root, item))
    else:
        mbox_path = resolve_thunderbird_mbox_path(mbox_dir, mailbox_name)
        if not mbox_path or not os.path.isfile(mbox_path):
            return {"error": f"Mailbox file '{mailbox_name}' not found in Thunderbird storage.", "subscriptions": [], "total_scanned": 0}
        mbox_files_to_scan.append(mbox_path)

    domain_msgs = defaultdict(int)
    domain_latest_meta = {}
    total_scanned = 0

    try:
        for file_path in mbox_files_to_scan:
            rel_name = os.path.relpath(file_path, mbox_dir).replace('\\', '/')
            log_event("THUNDERBIRD", f"Streaming messages from '{rel_name}'...")

            # Collect headers using streaming parser
            headers_list = []
            with open(file_path, 'r', encoding='latin-1', errors='replace') as f:
                in_header = False
                headers = {}
                curr_key = ''
                for line in f:
                    if line.startswith('From - '):
                        if in_header or headers:
                            headers_list.append(headers)
                            if limit > 0 and len(headers_list) > limit * 2:
                                headers_list = headers_list[-limit:]
                            headers = {}
                            curr_key = ''
                        in_header = True
                        continue

                    if in_header:
                        if line == '\n' or line == '\r\n':
                            in_header = False
                        elif line.startswith(' ') or line.startswith('\t'):
                            if curr_key and curr_key in headers:
                                headers[curr_key] += ' ' + line.strip()
                        elif ':' in line:
                            k, v = line.split(':', 1)
                            curr_key = k.lower().strip()
                            if curr_key in ['from', 'subject', 'list-unsubscribe', 'list-unsubscribe-post', 'x-mozilla-status']:
                                headers[curr_key] = v.strip()

                if in_header or headers:
                    headers_list.append(headers)
                    if limit > 0 and len(headers_list) > limit:
                        headers_list = headers_list[-limit:]

            # Inspect latest messages first
            headers_list.reverse()
            for idx, h in enumerate(headers_list):
                # Skip messages marked as deleted in Thunderbird (0x0008)
                stat_val = h.get('x-mozilla-status', '0001')
                try:
                    s_int = int(stat_val, 16)
                except Exception:
                    s_int = 1
                if s_int & 0x0008:
                    continue

                total_scanned += 1
                from_hdr = decode_mime_header(h.get('from', ''))
                subj = decode_mime_header(h.get('subject', ''))
                m = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', from_hdr)
                email_addr = m.group(0).lower() if m else from_hdr.lower()
                dom = email_addr.split('@')[-1] if '@' in email_addr else "unknown"

                domain_msgs[dom] += 1
                if dom not in domain_latest_meta:
                    domain_latest_meta[dom] = {
                        "sender": from_hdr,
                        "subject": subj,
                        "headers": h
                    }

        log_event("THUNDERBIRD", f"Sampled {total_scanned} emails across {len(domain_msgs)} unique sender domains.")

        sorted_domains = sorted(domain_msgs.keys(), key=lambda d: domain_msgs[d], reverse=True)
        discovered = []
        inspection_limit = 150

        for dom in sorted_domains[:inspection_limit]:
            meta = domain_latest_meta[dom]
            h = meta["headers"]

            # RFC List-Unsubscribe
            unsub_header = decode_mime_header(h.get('list-unsubscribe', ''))
            post_header = decode_mime_header(h.get('list-unsubscribe-post', ''))
            combined_headers = f"List-Unsubscribe: {unsub_header}\nList-Unsubscribe-Post: {post_header}"

            http_unsub, mailto_unsub, is_one_click = parse_list_unsubscribe_headers(combined_headers)

            if http_unsub or mailto_unsub:
                discovered.append({
                    "message_id": dom,
                    "domain": dom,
                    "email_count": domain_msgs[dom],
                    "sender": meta["sender"],
                    "subject": meta["subject"],
                    "rfc_unsubscribe": http_unsub or mailto_unsub,
                    "rfc_http": http_unsub,
                    "rfc_mailto": mailto_unsub,
                    "rfc_one_click": is_one_click,
                    "web_links": []
                })

        log_event("THUNDERBIRD", f"Scan complete! Discovered {len(discovered)} active subscriptions in Thunderbird.", level="SUCCESS")

        return {
            "account": account_cfg.get("name"),
            "mailbox": mailbox_name,
            "total_scanned": total_scanned,
            "unique_domains": len(domain_msgs),
            "subscriptions": discovered
        }
    except Exception as e:
        log_event("THUNDERBIRD", f"Error scanning subscriptions: {e}", level="ERROR")
        return {"error": f"Failed reading Thunderbird subscriptions: {e}", "subscriptions": [], "total_scanned": 0}


# ==============================================================================
# SCANNING SUBSCRIPTIONS
# ==============================================================================
def scan_subscriptions(account_name, mailbox_name="Inbox", limit=0):
    """Smart scan across Thunderbird, Outlook COM or IMAP accounts."""
    log_event("SCAN", f"Initiating scan for Account: '{account_name}', Folder: '{mailbox_name}', Limit: {limit}...")

    # 1. Check Thunderbird accounts first
    tb_accounts = discover_thunderbird_accounts()
    tb_target = next((a for a in tb_accounts if a.get('name') == account_name or a.get('email') == account_name), None)
    if tb_target:
        return scan_thunderbird_subscriptions(tb_target, mailbox_name, limit)

    # Check if this account is configured as IMAP or auto-discovered
    saved_accounts = load_saved_accounts()
    auto_accounts = discover_windows_email_accounts()
    all_known = saved_accounts + auto_accounts
    target_cfg = next((a for a in all_known if a.get('name') == account_name or a.get('email') == account_name), None)

    if target_cfg and (target_cfg.get('type') in ['imap', 'new_outlook'] or target_cfg.get('host')):
        # Ensure password exists
        if not target_cfg.get('password'):
            saved_match = next((s for s in saved_accounts if s.get('email', '').lower() == target_cfg.get('email', '').lower()), None)
            if saved_match and saved_match.get('password'):
                target_cfg['password'] = saved_match['password']
            else:
                return {
                    "error": f"Please open Mozilla Thunderbird and connect your '{target_cfg.get('email')}' account with 1-click browser sign-in.",
                    "needs_password": False,
                    "account": target_cfg.get("email"),
                    "subscriptions": [],
                    "total_scanned": 0
                }
        return scan_imap_subscriptions(target_cfg, mailbox_name, limit)

    # Otherwise scan via Outlook COM
    if not HAS_WIN32:
        return {
            "error": "pywin32 library is missing. Run 'pip install pywin32' on Windows, or use IMAP.",
            "subscriptions": [],
            "total_scanned": 0
        }

    try:
        mapi = get_outlook_namespace()
        folder = get_target_folder(mapi, account_name, mailbox_name)
    except Exception as e:
        err_msg = str(e)
        log_event("SCAN", f"Outlook access error: {err_msg}", level="ERROR")
        return {"error": f"Failed to access Outlook: {err_msg}", "subscriptions": [], "total_scanned": 0}

    items = folder.Items
    total_items = items.Count
    log_event("SCAN", f"Outlook folder '{folder.Name}' contains {total_items} total items.")

    if total_items == 0:
        return {"account": account_name, "mailbox": mailbox_name, "total_scanned": 0, "unique_domains": 0, "subscriptions": []}

    try:
        items.Sort("[ReceivedTime]", True)
    except Exception:
        pass

    scan_depth = total_items
    if limit > 0 and limit < total_items:
        scan_depth = limit

    domain_msgs = defaultdict(list)
    domain_latest_meta = {}
    total_scanned = 0

    log_event("SCAN", f"Reading up to {scan_depth} messages and grouping by sender domain...")

    for i in range(1, scan_depth + 1):
        try:
            item = items.Item(i)
            if getattr(item, "Class", 0) != 43 and not hasattr(item, "SenderEmailAddress"):
                continue

            entry_id = getattr(item, "EntryID", "")
            if not entry_id:
                continue

            sender_name, sender_email = get_sender_details(item)
            subject = getattr(item, "Subject", "") or ""

            dom = sender_email.split('@')[-1] if '@' in sender_email else "unknown"
            domain_msgs[dom].append(entry_id)
            total_scanned += 1

            if dom not in domain_latest_meta:
                domain_latest_meta[dom] = {
                    "entry_id": entry_id,
                    "sender": f"{sender_name} <{sender_email}>" if sender_name else sender_email,
                    "subject": subject
                }
        except Exception:
            continue

    log_event("SCAN", f"Sampled {total_scanned} emails across {len(domain_msgs)} unique sender domains.")

    sorted_domains = sorted(domain_msgs.keys(), key=lambda d: len(domain_msgs[d]), reverse=True)
    discovered = []
    inspection_limit = 100

    log_event("SCAN", f"Inspecting top {min(len(sorted_domains), inspection_limit)} domains for unsubscribe links & RFC headers...")

    for dom in sorted_domains[:inspection_limit]:
        meta = domain_latest_meta[dom]
        eid = meta["entry_id"]

        try:
            sample_item = mapi.GetItemFromID(eid)
        except Exception:
            continue

        headers_str = ""
        try:
            pa = sample_item.PropertyAccessor
            headers_str = pa.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x007D001E") or ""
        except Exception:
            headers_str = ""

        http_unsub, mailto_unsub, is_one_click = parse_list_unsubscribe_headers(headers_str)

        web_links = []
        try:
            html_body = getattr(sample_item, "HTMLBody", "") or ""
            web_links = extract_web_unsubscribe_links(html_body)
        except Exception:
            pass

        if http_unsub or mailto_unsub or web_links:
            discovered.append({
                "message_id": eid,
                "domain": dom,
                "email_count": len(domain_msgs[dom]),
                "sender": meta["sender"],
                "subject": meta["subject"],
                "rfc_unsubscribe": http_unsub or mailto_unsub,
                "rfc_http": http_unsub,
                "rfc_mailto": mailto_unsub,
                "rfc_one_click": is_one_click,
                "web_links": web_links
            })

    log_event("SCAN", f"Scan complete! Discovered {len(discovered)} active subscriptions.", level="SUCCESS")

    return {
        "account": account_name,
        "mailbox": mailbox_name,
        "total_scanned": total_scanned,
        "unique_domains": len(domain_msgs),
        "subscriptions": discovered
    }


def scan_imap_subscriptions(account_cfg, mailbox_name="INBOX", limit=0):
    """Scan subscriptions using direct IMAP connection."""
    host = account_cfg.get("host", "outlook.office365.com")
    port = account_cfg.get("port", 993)
    username = account_cfg.get("username", account_cfg.get("email"))
    password = account_cfg.get("password")
    use_ssl = account_cfg.get("ssl", True)

    log_event("IMAP", f"Connecting to IMAP {host}:{port} for {username}...")
    try:
        if use_ssl:
            client = imaplib.IMAP4_SSL(host, int(port), timeout=25)
        else:
            client = imaplib.IMAP4(host, int(port), timeout=25)
        client.login(username, password)
    except Exception as e:
        log_event("IMAP", f"IMAP connection failed: {e}", level="ERROR")
        return {"error": f"IMAP Connection failed: {str(e)}", "subscriptions": [], "total_scanned": 0}

    try:
        safe_mb = f'"{mailbox_name}"' if ' ' in mailbox_name else mailbox_name
        status, _ = client.select(safe_mb, readonly=True)
        if status != 'OK':
            status, _ = client.select('INBOX', readonly=True)

        status, search_data = client.search(None, 'ALL')
        if status != 'OK' or not search_data or not search_data[0]:
            client.logout()
            return {"account": account_cfg.get("name"), "mailbox": mailbox_name, "total_scanned": 0, "unique_domains": 0, "subscriptions": []}

        msg_ids = search_data[0].split()
        total_items = len(msg_ids)
        msg_ids.reverse()

        scan_depth = total_items
        if limit > 0 and limit < total_items:
            scan_depth = limit

        target_ids = msg_ids[:scan_depth]
        domain_msgs = defaultdict(list)
        domain_latest_meta = {}
        total_scanned = 0

        log_event("IMAP", f"Batch fetching headers for {len(target_ids)} messages...")

        batch_size = 50
        for i in range(0, len(target_ids), batch_size):
            chunk = target_ids[i:i+batch_size]
            id_set = b','.join(chunk)
            status, fetch_data = client.fetch(id_set, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT LIST-UNSUBSCRIBE LIST-UNSUBSCRIBE-POST DATE)])')
            if status != 'OK':
                continue

            for item in fetch_data:
                if isinstance(item, tuple):
                    try:
                        raw_headers = item[1].decode('utf-8', errors='ignore')
                        msg = email.message_from_string(raw_headers)
                        from_hdr = msg.get('From', '')
                        subj_hdr = msg.get('Subject', '')
                        
                        m_email = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', from_hdr)
                        email_addr = m_email.group(0).lower() if m_email else "unknown"
                        dom = email_addr.split('@')[-1] if '@' in email_addr else "unknown"

                        mid_match = re.search(r'^\s*(\d+)\s+FETCH', item[0].decode('utf-8', errors='ignore'))
                        mid = mid_match.group(1).encode() if mid_match else chunk[0]

                        domain_msgs[dom].append(mid)
                        total_scanned += 1

                        if dom not in domain_latest_meta:
                            http_unsub, mailto_unsub, is_one_click = parse_list_unsubscribe_headers(raw_headers)
                            domain_latest_meta[dom] = {
                                "mid": mid,
                                "sender": from_hdr,
                                "subject": subj_hdr,
                                "http_unsub": http_unsub,
                                "mailto_unsub": mailto_unsub,
                                "one_click": is_one_click
                            }
                    except Exception:
                        continue

        sorted_domains = sorted(domain_msgs.keys(), key=lambda d: len(domain_msgs[d]), reverse=True)
        discovered = []
        inspection_limit = 100

        log_event("IMAP", f"Fetching HTML bodies for top {min(len(sorted_domains), inspection_limit)} domains...")

        for dom in sorted_domains[:inspection_limit]:
            meta = domain_latest_meta[dom]
            mid = meta["mid"]
            http_unsub = meta["http_unsub"]
            mailto_unsub = meta["mailto_unsub"]
            is_one_click = meta["one_click"]
            web_links = []

            try:
                status, bdata = client.fetch(mid, '(BODY.PEEK[TEXT])')
                if status == 'OK' and bdata and isinstance(bdata[0], tuple):
                    html_text = bdata[0][1].decode('utf-8', errors='ignore')
                    web_links = extract_web_unsubscribe_links(html_text)
            except Exception:
                pass

            if http_unsub or mailto_unsub or web_links:
                discovered.append({
                    "message_id": mid.decode() if isinstance(mid, bytes) else str(mid),
                    "domain": dom,
                    "email_count": len(domain_msgs[dom]),
                    "sender": meta["sender"],
                    "subject": meta["subject"],
                    "rfc_unsubscribe": http_unsub or mailto_unsub,
                    "rfc_http": http_unsub,
                    "rfc_mailto": mailto_unsub,
                    "rfc_one_click": is_one_click,
                    "web_links": web_links
                })

        client.logout()
        log_event("IMAP", f"Scan finished! Found {len(discovered)} subscriptions across {len(domain_msgs)} domains.", level="SUCCESS")

        return {
            "account": account_cfg.get("name"),
            "mailbox": mailbox_name,
            "total_scanned": total_scanned,
            "unique_domains": len(domain_msgs),
            "subscriptions": discovered
        }
    except Exception as e:
        log_event("IMAP", f"Error during IMAP scan: {e}", level="ERROR")
        try: client.logout()
        except Exception: pass
        return {"error": str(e), "subscriptions": [], "total_scanned": 0}


# ==============================================================================
# MULTI-PROTOCOL AUTOMATED UNSUBSCRIBER
# ==============================================================================
def execute_unsubscribe(target_email, sub_info, job_index=1, total_jobs=1):
    """Multi-protocol unsubscribe engine with granular terminal logging."""
    domain = sub_info.get('domain', 'unknown')
    sender = sub_info.get('sender', '')
    rfc_http = sub_info.get('rfc_http')
    rfc_mailto = sub_info.get('rfc_mailto')
    is_one_click = sub_info.get('rfc_one_click', False)
    web_links = sub_info.get('web_links', [])

    rfc_raw = sub_info.get('rfc_unsubscribe', '')
    if not rfc_http and rfc_raw and rfc_raw.startswith('http'):
        rfc_http = rfc_raw
    if not rfc_mailto and rfc_raw and rfc_raw.startswith('mailto:'):
        rfc_mailto = rfc_raw

    log_event("UNSUB", f"[{job_index}/{total_jobs}] Processing unsubscription for: '{domain}' (Sender: {sender})")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'close'
    }

    # 1. Phase 1: RFC 8058 One-Click
    if rfc_http and is_one_click:
        log_event("RFC", f"Attempting Phase 1: RFC 8058 One-Click POST to {rfc_http}...")
        try:
            post_headers = headers.copy()
            post_headers['List-Unsubscribe'] = 'One-Click'
            r = requests.post(rfc_http, data={'List-Unsubscribe': 'One-Click'}, headers=post_headers, timeout=14, allow_redirects=True)
            log_event("RFC", f"Server response HTTP {r.status_code}")
            if r.status_code in [200, 201, 202, 204]:
                log_event("UNSUB", f"✅ [SUCCESS] RFC 8058 One-Click succeeded ({r.status_code}) for '{domain}'!", level="SUCCESS")
                return {
                    "success": True,
                    "method": "RFC 8058 One-Click",
                    "details": f"Silent HTTP POST succeeded ({r.status_code})"
                }
            else:
                log_event("RFC", f"One-Click returned non-success code {r.status_code}. Falling back...", level="WARNING")
        except Exception as e:
            log_event("RFC", f"One-Click request failed: {e}. Falling back...", level="WARNING")

    # 2. Phase 2: RFC 2369 Web GET
    if rfc_http:
        log_event("RFC", f"Attempting Phase 2: RFC List-Unsubscribe GET to {rfc_http}...")
        try:
            r = requests.get(rfc_http, headers=headers, timeout=14, allow_redirects=True)
            log_event("RFC", f"GET response HTTP {r.status_code} (Final URL: {r.url})")
            text_lower = r.text.lower()
            if r.status_code in [200, 202] and any(k in text_lower for k in [
                "unsubscribed", "successfully removed", "opt-out confirmed", "preferences updated", "removed from our list"
            ]):
                log_event("UNSUB", f"✅ [SUCCESS] RFC Web GET confirmed unsubscription for '{domain}'!", level="SUCCESS")
                return {
                    "success": True,
                    "method": "RFC List-Unsubscribe URL",
                    "details": "HTTP GET confirmed unsubscription"
                }
        except Exception as e:
            log_event("RFC", f"RFC GET failed: {e}. Falling back...", level="WARNING")

    # 3. Phase 3: RFC Mailto Unsubscribe Dispatch
    if rfc_mailto:
        log_event("RFC", f"Attempting Phase 3: Inspecting mailto unsubscribe address: {rfc_mailto}")
        parsed_mailto = urllib.parse.urlparse(rfc_mailto)
        recipient = parsed_mailto.path
        query_params = urllib.parse.parse_qs(parsed_mailto.query)
        unsub_subject = query_params.get('subject', ['Unsubscribe'])[0]

        if HAS_WIN32:
            try:
                log_event("OUTLOOK", f"Dispatching automated unsubscribe email to '{recipient}' via Outlook...")
                mapi = get_outlook_namespace()
                outlook = win32com.client.Dispatch("Outlook.Application")
                mail_item = outlook.CreateItem(0)
                mail_item.To = recipient
                mail_item.Subject = unsub_subject
                mail_item.Body = "Please unsubscribe me from this mailing list."
                mail_item.Send()
                log_event("UNSUB", f"✅ [SUCCESS] Sent unsubscribe email to {recipient} via Outlook!", level="SUCCESS")
                return {
                    "success": True,
                    "method": "RFC Mailto Dispatched",
                    "details": f"Dispatched unsubscribe email to {recipient}"
                }
            except Exception as e:
                log_event("OUTLOOK", f"Could not send mailto via Outlook: {e}", level="WARNING")

    # 4. Phase 4: Smart Web Form Solver
    candidate_urls = list(web_links)
    if rfc_http and rfc_http not in candidate_urls:
        candidate_urls.insert(0, rfc_http)

    for idx, url in enumerate(candidate_urls, 1):
        log_event("FORM", f"Attempting Phase 4 ({idx}/{len(candidate_urls)}): Fetching web link: {url}")
        try:
            session = requests.Session()
            session.headers.update(headers)
            r = session.get(url, timeout=15, allow_redirects=True)
            log_event("FORM", f"Page returned HTTP {r.status_code}")
            if r.status_code != 200:
                continue

            page_text = r.text.lower()
            soup = BeautifulSoup(r.text, 'html.parser')

            if any(k in page_text for k in [
                "you have been unsubscribed", "successfully unsubscribed", "opt-out successful",
                "removed from our list", "unsubscribed from all", "your email has been removed"
            ]):
                log_event("UNSUB", f"✅ [SUCCESS] Direct web link confirmed automatic unsubscription for '{domain}'!", level="SUCCESS")
                return {
                    "success": True,
                    "method": "Direct Web Link",
                    "details": "Page confirmed unsubscription upon visit"
                }

            if any(k in page_text for k in ["g-recaptcha", "h-captcha", "cf-turnstile", "sign in to continue", "log in to manage"]):
                log_event("UNSUB", f"⚠️ Manual action needed: Page requires CAPTCHA or Login at {url}", level="WARNING")
                return {
                    "success": False,
                    "method": "Requires Manual Attention",
                    "details": "Requires login or CAPTCHA verification",
                    "manual_url": url
                }

            forms = soup.find_all('form')
            target_form = None
            for f in forms:
                form_text = f.get_text().lower()
                action = f.get('action', '').lower()
                if 'search' in action or 'search' in f.get('id', '').lower():
                    continue
                if any(k in form_text or k in action for k in ['unsub', 'opt', 'email', 'preferences', 'submit']):
                    target_form = f
                    break
            if not target_form and forms:
                target_form = forms[0]

            if target_form:
                action = target_form.get('action') or url
                if not action.startswith('http'):
                    action = urllib.parse.urljoin(url, action)
                method = (target_form.get('method') or 'POST').upper()

                form_data = {}
                for inp in target_form.find_all('input'):
                    name = inp.get('name')
                    if not name: continue
                    val = inp.get('value', '')
                    t = (inp.get('type') or 'text').lower()

                    if t == 'hidden':
                        form_data[name] = val
                    elif t == 'email' or 'email' in name.lower():
                        form_data[name] = target_email
                    elif t == 'checkbox':
                        lbl = (inp.parent.get_text().lower() if inp.parent else "") + name.lower()
                        if any(k in lbl for k in ['all', 'opt', 'unsub', 'stop', 'every']):
                            form_data[name] = val or '1'
                    elif t == 'radio':
                        lbl = (inp.parent.get_text().lower() if inp.parent else "") + name.lower()
                        if any(reason in lbl for reason in ["too many", "no longer", "not relevant", "other", "frequency", "never"]):
                            form_data[name] = val

                radios = target_form.find_all('input', {'type': 'radio'})
                if radios and not any(r.get('name') in form_data for r in radios):
                    first_radio = radios[0]
                    form_data[first_radio.get('name')] = first_radio.get('value', '1')

                submit_btn = target_form.find('button', {'type': 'submit'}) or target_form.find('input', {'type': 'submit'})
                if submit_btn and submit_btn.get('name'):
                    form_data[submit_btn.get('name')] = submit_btn.get('value', 'Submit')

                log_event("FORM", f"Submitting {method} form to {action} (Fields: {list(form_data.keys())})...")
                post_headers = headers.copy()
                post_headers['Referer'] = url

                if method == 'POST':
                    res = session.post(action, data=form_data, headers=post_headers, timeout=15, allow_redirects=True)
                else:
                    res = session.get(action, params=form_data, headers=post_headers, timeout=15, allow_redirects=True)

                res_text = res.text.lower()
                log_event("FORM", f"Form submission returned HTTP {res.status_code}")

                if any(k in res_text for k in ["unsubscribed", "success", "preferences updated", "removed", "saved", "confirmed"]):
                    log_event("UNSUB", f"✅ [SUCCESS] Form submission confirmed unsubscription for '{domain}'!", level="SUCCESS")
                    return {
                        "success": True,
                        "method": "Automated Survey & Form Submission",
                        "details": "Filled email, selected survey reason, and confirmed"
                    }

        except Exception as e:
            log_event("FORM", f"Error processing URL {url}: {e}", level="WARNING")
            continue

    # 5. Phase 5: Headless Browser Execution (Handles JavaScript, React, Client-Side Forms)
    if HAS_PLAYWRIGHT and candidate_urls:
        target_url = candidate_urls[0]
        log_event("FORM", f"Attempting Phase 5: Real Chrome Headless Solver for '{domain}' at {target_url}...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page()
                page.goto(target_url, timeout=20000, wait_until="domcontentloaded")
                time.sleep(2)

                # Fill any email inputs
                if target_email:
                    email_inputs = page.locator('input[type="email"], input[name*="email" i], input[id*="email" i]')
                    if email_inputs.count() > 0:
                        for idx_inp in range(min(email_inputs.count(), 2)):
                            try:
                                email_inputs.nth(idx_inp).fill(target_email)
                            except Exception:
                                pass

                # Look for "Unsubscribe from all" checkboxes or buttons
                unsub_all_box = page.locator('input[type="checkbox"][id*="all" i], input[type="checkbox"][name*="all" i], label:has-text("Unsubscribe from all"), label:has-text("Opt-out of all")')
                if unsub_all_box.count() > 0:
                    try:
                        unsub_all_box.first.click(timeout=2000)
                    except Exception:
                        pass

                # Click submit or unsubscribe button
                btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Unsubscribe"), button:has-text("Save"), button:has-text("Confirm"), button:has-text("Update")')
                if btn.count() > 0:
                    btn.first.click(timeout=3000)
                    time.sleep(3)

                final_text = page.content().lower()
                browser.close()

                if any(k in final_text for k in ["unsubscribed", "success", "preferences updated", "removed from our list", "opt-out confirmed"]):
                    log_event("UNSUB", f"✅ [SUCCESS] Chrome Browser Automation confirmed unsubscription for '{domain}'!", level="SUCCESS")
                    return {
                        "success": True,
                        "method": "Real Chrome Headless Solver",
                        "details": "Chrome browser filled form, clicked confirm, and verified unsubscription"
                    }
        except Exception as e:
            log_event("FORM", f"Browser solver notice: {e}", level="INFO")

    # 6. Phase 6: Manual Action Link
    manual_link = candidate_urls[0] if candidate_urls else None
    log_event("UNSUB", f"⚠️ Automated methods exhausted for '{domain}'. Manual unsubscription link: {manual_link}", level="WARNING")
    return {
        "success": False,
        "method": "Requires Manual Attention",
        "details": "Automated methods could not confirm unsubscription",
        "manual_url": manual_link
    }


# ==============================================================================
# HTTP REQUEST HANDLER
# ==============================================================================
class UnsubHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        super().__init__(*args, directory=static_dir, **kwargs)

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/api/accounts':
            acc_data = get_mail_accounts()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(acc_data).encode())
            return

        elif parsed.path == '/api/scan':
            qs = urllib.parse.parse_qs(parsed.query)
            acc = qs.get('account', [''])[0]
            mb = qs.get('mailbox', ['Inbox'])[0]
            lim_raw = qs.get('limit', ['100'])[0]
            limit = int(lim_raw) if lim_raw.isdigit() else 0
            data = scan_subscriptions(acc, mb, limit)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(length).decode('utf-8', errors='ignore') if length > 0 else '{}'
        body = json.loads(raw_body) if raw_body else {}

        if parsed.path == '/api/imap/add':
            host = body.get('host', 'outlook.office365.com').strip()
            port = body.get('port', 993)
            user = body.get('username', '').strip()
            pwd = body.get('password', '').strip()
            name = body.get('name', '').strip() or user
            email_addr = body.get('email', '').strip() or user
            use_ssl = body.get('ssl', True)

            ok, folders, msg = test_imap_connection(host, port, user, pwd, use_ssl)
            if ok:
                accounts = load_saved_accounts()
                accounts = [a for a in accounts if a.get('email', '').lower() != email_addr.lower()]
                accounts.append({
                    "name": name,
                    "email": email_addr,
                    "username": user,
                    "password": pwd,
                    "host": host,
                    "port": port,
                    "ssl": use_ssl,
                    "folders": folders
                })
                save_saved_accounts(accounts)
                res = {"success": True, "message": "IMAP account connected successfully!", "folders": folders}
            else:
                res = {"success": False, "message": msg}

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode())
            return

        elif parsed.path == '/api/imap/remove':
            email_addr = body.get('email', '').strip()
            accounts = load_saved_accounts()
            accounts = [a for a in accounts if a.get('email', '').lower() != email_addr.lower()]
            save_saved_accounts(accounts)
            log_event("ACCOUNTS", f"Removed saved credentials for '{email_addr}'")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode())
            return

        elif parsed.path == '/api/unsubscribe':
            target_email = body.get('target_email')
            subscriptions = body.get('subscriptions', [])

            print("\n" + "="*70, flush=True)
            log_event("UNSUB", f"STARTING UNSUBSCRIBE JOB for {len(subscriptions)} subscription(s)")
            log_event("UNSUB", f"Target Email: {target_email}")
            print("="*70, flush=True)

            results = []
            total = len(subscriptions)
            for idx, sub in enumerate(subscriptions, 1):
                res = execute_unsubscribe(target_email, sub, job_index=idx, total_jobs=total)
                res['domain'] = sub.get('domain')
                res['sender'] = sub.get('sender')
                results.append(res)
                time.sleep(0.3)

            succeeded = sum(1 for r in results if r.get('success'))
            manual = total - succeeded
            print("="*70, flush=True)
            log_event("UNSUB", f"BATCH COMPLETED: {succeeded}/{total} succeeded, {manual} require manual attention.", level="SUCCESS" if manual == 0 else "INFO")
            print("="*70 + "\n", flush=True)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(results).encode())
            return

        self.send_error(404)


def run():
    print("="*70, flush=True)
    print("   🔕 UnsubBot (Universal Outlook & IMAP Engine)", flush=True)
    print("="*70, flush=True)
    log_event("INFO", f"Operating System: Windows ({sys.platform})")
    log_event("INFO", f"Classic Outlook COM (pywin32) Available: {HAS_WIN32}")
    log_event("INFO", f"Server starting on http://localhost:{PORT}")
    print("="*70, flush=True)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), UnsubHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == '__main__':
    run()
