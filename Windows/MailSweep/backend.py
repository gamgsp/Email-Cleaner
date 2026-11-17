import http.server
import socketserver
import json
import urllib.parse
import re
import os
import sys
import email
from email.header import decode_header
import mailbox
import threading
import time
import datetime
import imaplib
import glob
from collections import Counter, defaultdict

PORT = 7890
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounts_config.json')

# Check pywin32 availability
try:
    import win32com.client
    import pythoncom
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


def log_event(tag, message, level="INFO"):
    """Formatted, timestamped terminal logging with immediate flush."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    icons = {
        "INFO": "ℹ️ ",
        "SUCCESS": "✅",
        "WARNING": "⚠️ ",
        "ERROR": "❌",
        "DELETE": "🗑️ ",
        "SCAN": "🔍",
        "ACCOUNTS": "📫",
        "IMAP": "🌐",
        "OUTLOOK": "📧",
        "THUNDERBIRD": "🦅"
    }
    icon = icons.get(tag, icons.get(level, "• "))
    print(f"[{ts}] {icon} [{tag}] {message}", flush=True)


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

    # 1. Auto-discover Mozilla Thunderbird accounts first (offline local storage ready)
    tb_accounts = discover_thunderbird_accounts()
    for acc in tb_accounts:
        acc_key = acc['name'].lower()
        if acc_key not in seen:
            accounts.append(acc)
            seen.add(acc_key)
            if acc.get('email'):
                seen.add(acc['email'].lower())

    # 2. Check Classic Outlook COM
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
                com_error = "Classic Outlook COM is not registered. 'New Outlook for Windows' (olk.exe) detected."
                log_event("ACCOUNTS", com_error, level="INFO")
            else:
                com_error = f"Outlook COM error: {err_str}"
                log_event("ACCOUNTS", com_error, level="WARNING")

    # 3. Load saved configs
    saved_imap = load_saved_accounts()
    saved_by_email = {a.get('email', '').lower(): a for a in saved_imap if a.get('email')}

    # 4. Auto-discover Windows Outlook / Live accounts
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
        if ("junk" in mb_lower or "spam" in mb_lower) and ("junk" in s_lower or "spam" in s_lower):
            return sub
        if ("trash" in mb_lower or "delete" in mb_lower) and ("trash" in s_lower or "deleted" in s_lower):
            return sub

    if "inbox" in mb_lower:
        return mapi.GetDefaultFolder(6)
    elif "junk" in mb_lower or "spam" in mb_lower:
        return mapi.GetDefaultFolder(23)
    elif "trash" in mb_lower or "delete" in mb_lower:
        return mapi.GetDefaultFolder(3)

    return target_root.Folders.Item(1)


# ==============================================================================
# SCAN & CLASSIFY
# ==============================================================================
def categorize_domains(dom_counts, dom_senders):
    """Categorize domains into standard groups (Spam, Ads, Shopping, etc.)."""
    categories = {
        "spam_scam": {"name": "🚨 Spam & Casino", "domains": []},
        "ad_marketing": {"name": "📢 Ad Networks & Marketing", "domains": []},
        "retail_promos": {"name": "🛍️ Shopping & Travel Promos", "domains": []},
        "trading_crypto": {"name": "📈 Trading, Forex & Crypto", "domains": []},
        "banking_finance": {"name": "🏦 Banking & Investments", "domains": []},
        "tech_cloud": {"name": "💻 Tech, Cloud & AI Tools", "domains": []},
        "social_community": {"name": "🌐 Social & Community", "domains": []},
        "personal_contacts": {"name": "👤 Personal Contacts", "domains": []},
        "miscellaneous": {"name": "📦 Miscellaneous", "domains": []}
    }

    spam_kw = ['viagra', 'prostate', 'brain fog', 'sleep disorder', 'medication', 'casino', 'betting', 'crorebet', 
               'carshield', 'african growth', 'vertigo relief', 'patriot power', 'generator', 'stake.com', 'king billy',
               'first-access-card', 'bitcoin opportunity', 'paellademarisco', 'badbetabrain', 'sportsdirection']
    ad_kw = ['froggyads', 'richads', 'exoclick', 'monetag', 'ezmob', 'zeydoo', 'rankingcoach', 'activerevenue',
             'globaladsmedia', 'gg.agency', 'vrume', 'apkasewak', 'kochava', 'coschedule']
    retail_kw = ['baapstore', 'skechers', 'goibibo', 'swiggy', 'goindigo', 'zoomin', 'ajio', 'bluestone', 
                'makemytrip', 'booking.com', 'cabbazar', 'dominos', 'crunchyroll', 'halfwheel', 'unsplash', 
                'canva', 'primeabgb', 'provilac', 'envato', 'alpinewearshop', 'redbus.in', 'tatacliq', '1mg', 'apollo247']
    trade_kw = ['kucoin', 'octa', 'the5ers', 'zebpay', 'expert4x', '5paisa', 'vantagemarkets', 'binance', 
                'fundingpips', 'wazirx', 'tickmill', 'myfxbook', 'primexbt', 'upstox', 'angelbroking', 
                'angeltrade', 'mstock', 'nuvama', 'goatfundedtrader', 'blueguardian', 'aliceblue', 
                'instantfunding', 'fundyourfx', 'coinswitch', 'valerytrading', 'bitget', 'coinex', 'mexc', 
                'ultimamarkets', 'citytraders', 'blackbull', 'easyalgos', 'tradingview', 'definedge', 'fxreplay', 'exness']
    bank_kw = ['axis.bank.in', 'axisbankmail', 'hdfcbank', 'yesbank', 'yes.bank.in', 'bankofbaroda', 'indusind', 
               'sbi.bank.in', 'nse.co.in', 'bseindia', 'liquiloans', 'olamoney', 'paisabazaar', 'creditmantri', 
               'cibil', 'open.money', 'payu', 'starinsurance', 'indmoney', 'cdslindia', 'irctc', 'razorpay',
               'cred.club', 'lendenclub', 'federal.bank.in', 'slicebank']
    tech_kw = ['replit', 'cloudflare', 'jio.com', 'cyberpanel', 'tawk.to', 'mxtoolbox', 'hetzner', 'contabo', 
               'docker', 'interserver', 'aapanel', 'stackblitz', 'gcore', 'b12.io', 'onedrive', 'intel', 'dell', 
               'apidog', 'shiprocket', 'augmentcode', 'lovable.dev', 'mongodb', 'nginx', 'pentest-tools', 'grafana', 'ollama']
    social_kw = ['instagram.com', 'mastodon.social', 'intch.org', 'theonevalley.com', 'goglobal.world', 
                 'quora.com', 'redditmail.com', 'tumblr.com', 'tourbar.com', 'chess.com', 'x.com', 'rumble.com']
    personal_kw = ['gmail.com', 'live.com', 'outlook.com', 'hotmail.com', 'yahoo.com', 'icloud.com', 'me.com', 'proton.me']

    for dom, count in dom_counts.most_common():
        top_sender = dom_senders[dom].most_common(1)[0][0] if dom_senders[dom] else ""
        item = {
            "domain": dom,
            "count": count,
            "sample_sender": top_sender
        }
        
        assigned = False
        for k in spam_kw:
            if k in dom or k in top_sender.lower():
                categories["spam_scam"]["domains"].append(item)
                assigned = True
                break
        if assigned: continue

        for k in ad_kw:
            if k in dom or k in top_sender.lower():
                categories["ad_marketing"]["domains"].append(item)
                assigned = True
                break
        if assigned: continue

        for k in retail_kw:
            if k in dom or k in top_sender.lower():
                categories["retail_promos"]["domains"].append(item)
                assigned = True
                break
        if assigned: continue

        for k in trade_kw:
            if k in dom or k in top_sender.lower():
                categories["trading_crypto"]["domains"].append(item)
                assigned = True
                break
        if assigned: continue

        for k in bank_kw:
            if k in dom or k in top_sender.lower():
                categories["banking_finance"]["domains"].append(item)
                assigned = True
                break
        if assigned: continue

        for k in tech_kw:
            if k in dom or k in top_sender.lower():
                categories["tech_cloud"]["domains"].append(item)
                assigned = True
                break
        if assigned: continue

        for k in social_kw:
            if k in dom or k in top_sender.lower():
                categories["social_community"]["domains"].append(item)
                assigned = True
                break
        if assigned: continue

        for k in personal_kw:
            if k == dom or dom.endswith('.' + k):
                categories["personal_contacts"]["domains"].append(item)
                assigned = True
                break
        if assigned: continue

        categories["miscellaneous"]["domains"].append(item)

    return categories


def resolve_thunderbird_mbox_path(mbox_dir, mailbox_name):
    """Find the exact mbox file path, handling subdirectories like [Gmail].sbd/All Mail."""
    if not mbox_dir or not os.path.exists(mbox_dir):
        return None

    norm_name = mailbox_name.replace('/', os.sep).replace('\\', os.sep)
    direct = os.path.join(mbox_dir, norm_name)
    if os.path.isfile(direct):
        return direct

    # Search case-insensitively across all subdirectories
    mb_clean = os.path.basename(mailbox_name).lower().strip()
    for root, dirs, files in os.walk(mbox_dir):
        for f in files:
            if f.endswith('.msf') or f.endswith('.dat'):
                continue
            if f.lower() == mb_clean or f.lower() == mailbox_name.lower():
                return os.path.join(root, f)

    return None


def scan_thunderbird_account(account_cfg, mailbox_name="INBOX"):
    """Scan local Thunderbird mbox store for senders and domains using ultra-fast streaming."""
    log_event("THUNDERBIRD", f"Scanning Thunderbird mailbox: '{account_cfg.get('name')}', Folder: '{mailbox_name}'...")
    mbox_dir = account_cfg.get("directory", "")
    if not mbox_dir or not os.path.exists(mbox_dir):
        return {"error": f"Thunderbird directory not found: {mbox_dir}", "domains": []}

    mbox_files_to_scan = []
    if mailbox_name.strip().lower() in ["__all__", "full mailbox (all folders)", "all folders", "full mailbox"]:
        # Scan all mbox files for this account
        for root, dirs, files in os.walk(mbox_dir):
            for item in files:
                if not item.endswith('.msf') and not item.endswith('.dat'):
                    mbox_files_to_scan.append(os.path.join(root, item))
    else:
        mbox_path = resolve_thunderbird_mbox_path(mbox_dir, mailbox_name)
        if not mbox_path or not os.path.isfile(mbox_path):
            return {"error": f"Mailbox file '{mailbox_name}' not found in Thunderbird storage.", "domains": []}
        mbox_files_to_scan.append(mbox_path)

    dom_counts = Counter()
    dom_senders = defaultdict(lambda: Counter())
    processed_count = 0

    try:
        for file_path in mbox_files_to_scan:
            rel_name = os.path.relpath(file_path, mbox_dir).replace('\\', '/')
            log_event("THUNDERBIRD", f"Reading Thunderbird storage file: '{rel_name}'...")
            
            with open(file_path, 'rb') as f:
                current_status_val = b'0001'
                current_from = ''
                in_header = False

                def commit_entry(from_str, status_val):
                    nonlocal processed_count
                    try:
                        s_int = int(status_val, 16)
                    except Exception:
                        s_int = 1
                    # Skip messages marked as deleted in Thunderbird (flag 0x0008)
                    if s_int & 0x0008:
                        return
                    processed_count += 1
                    name = ""
                    email_addr = ""
                    m = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', from_str)
                    if m:
                        email_addr = m.group(0).lower()
                    name_match = re.match(r'^\"?([^\"<]+)\"?\s*<', from_str)
                    if name_match:
                        name = name_match.group(1).strip()
                    if not email_addr:
                        email_addr = from_str.lower()
                    dom = email_addr.split('@')[-1] if '@' in email_addr else "unknown"
                    dom_counts[dom] += 1
                    disp = f"{name} <{email_addr}>" if name else email_addr
                    dom_senders[dom][disp] += 1

                for line in f:
                    if line.startswith(b'From - '):
                        if in_header or current_from:
                            commit_entry(current_from, current_status_val)
                        current_status_val = b'0001'
                        current_from = ''
                        in_header = True
                        continue

                    if in_header:
                        if line == b'\r\n' or line == b'\n':
                            in_header = False
                        elif line.startswith(b'X-Mozilla-Status:'):
                            current_status_val = line[len(b'X-Mozilla-Status:'):].strip()
                        elif line.lower().startswith(b'from:'):
                            current_from = line[5:].decode('latin-1', errors='replace').strip()
                        elif current_from and (line.startswith(b' ') or line.startswith(b'\t')):
                            current_from += ' ' + line.decode('latin-1', errors='replace').strip()

                if in_header or current_from:
                    commit_entry(current_from, current_status_val)

        categories = categorize_domains(dom_counts, dom_senders)
        log_event("THUNDERBIRD", f"Scan complete! Classified {processed_count} messages across {len(dom_counts)} domains.", level="SUCCESS")

        return {
            "account": account_cfg.get("name"),
            "mailbox": mailbox_name,
            "total_messages": processed_count,
            "total_domains": len(dom_counts),
            "categories": categories
        }
    except Exception as e:
        log_event("THUNDERBIRD", f"Error scanning mbox: {e}", level="ERROR")
        return {"error": f"Failed reading Thunderbird mailbox: {e}", "domains": []}


def scan_account(account_name, mailbox_name="Inbox"):
    """Fetch senders and domains from Thunderbird, Outlook COM or IMAP."""
    log_event("SCAN", f"Scanning Account: '{account_name}', Folder: '{mailbox_name}'...")

    # 1. Check Thunderbird accounts first
    tb_accounts = discover_thunderbird_accounts()
    tb_target = next((a for a in tb_accounts if a.get('name') == account_name or a.get('email') == account_name), None)
    if tb_target:
        return scan_thunderbird_account(tb_target, mailbox_name)

    saved_accounts = load_saved_accounts()
    auto_accounts = discover_windows_email_accounts()
    all_known = saved_accounts + auto_accounts
    target_cfg = next((a for a in all_known if a.get('name') == account_name or a.get('email') == account_name), None)

    if target_cfg and (target_cfg.get('type') in ['imap', 'new_outlook'] or target_cfg.get('host')):
        if not target_cfg.get('password'):
            saved_match = next((s for s in saved_accounts if s.get('email', '').lower() == target_cfg.get('email', '').lower()), None)
            if saved_match and saved_match.get('password'):
                target_cfg['password'] = saved_match['password']
            else:
                return {
                    "error": f"Please open Mozilla Thunderbird and connect your '{target_cfg.get('email')}' account with 1-click browser sign-in.",
                    "needs_password": False,
                    "account": target_cfg.get("email"),
                    "domains": []
                }
        return scan_imap_account(target_cfg, mailbox_name)

    if not HAS_WIN32:
        return {
            "error": "pywin32 library is missing. Run 'pip install pywin32' on Windows, or use IMAP.",
            "domains": []
        }

    try:
        mapi = get_outlook_namespace()
        folder = get_target_folder(mapi, account_name, mailbox_name)
    except Exception as e:
        err_msg = str(e)
        log_event("SCAN", f"Failed to access folder: {err_msg}", level="ERROR")
        return {"error": f"Failed to access Outlook folder: {err_msg}", "domains": []}

    items = folder.Items
    total_items = items.Count
    log_event("SCAN", f"Folder '{folder.Name}' contains {total_items} messages.")

    dom_counts = Counter()
    dom_senders = defaultdict(lambda: Counter())
    processed_count = 0

    for i in range(1, total_items + 1):
        try:
            item = items.Item(i)
            if getattr(item, "Class", 0) != 43 and not hasattr(item, "SenderEmailAddress"):
                continue

            name, email_addr = get_sender_details(item)
            if not email_addr:
                continue

            processed_count += 1
            dom = email_addr.split('@')[-1] if '@' in email_addr else "unknown"
            dom_counts[dom] += 1
            disp = f"{name} <{email_addr}>" if name else email_addr
            dom_senders[dom][disp] += 1
        except Exception:
            continue

    categories = categorize_domains(dom_counts, dom_senders)
    log_event("SCAN", f"Classified {processed_count} messages across {len(dom_counts)} domains.", level="SUCCESS")

    return {
        "account": account_name,
        "mailbox": mailbox_name,
        "total_messages": processed_count,
        "total_domains": len(dom_counts),
        "categories": categories
    }


def scan_imap_account(account_cfg, mailbox_name="INBOX"):
    """Scan IMAP mailbox for senders and domains."""
    host = account_cfg.get("host", "outlook.office365.com")
    port = account_cfg.get("port", 993)
    user = account_cfg.get("username", account_cfg.get("email"))
    pwd = account_cfg.get("password")
    use_ssl = account_cfg.get("ssl", True)

    log_event("IMAP", f"Connecting to IMAP {host}:{port}...")
    try:
        client = imaplib.IMAP4_SSL(host, int(port), timeout=25) if use_ssl else imaplib.IMAP4(host, int(port), timeout=25)
        client.login(user, pwd)
    except Exception as e:
        log_event("IMAP", f"Connection error: {e}", level="ERROR")
        return {"error": f"IMAP Connection failed: {e}", "domains": []}

    try:
        safe_mb = f'"{mailbox_name}"' if ' ' in mailbox_name else mailbox_name
        status, _ = client.select(safe_mb, readonly=True)
        if status != 'OK':
            status, _ = client.select('INBOX', readonly=True)

        status, data = client.search(None, 'ALL')
        if status != 'OK' or not data or not data[0]:
            client.logout()
            return {"account": account_cfg.get("name"), "mailbox": mailbox_name, "total_messages": 0, "total_domains": 0, "categories": {}}

        msg_ids = data[0].split()
        total_items = len(msg_ids)
        log_event("IMAP", f"Found {total_items} messages. Batch fetching sender headers...")

        dom_counts = Counter()
        dom_senders = defaultdict(lambda: Counter())
        processed_count = 0

        batch_size = 100
        for i in range(0, total_items, batch_size):
            chunk = msg_ids[i:i+batch_size]
            id_set = b','.join(chunk)
            status, fetch_data = client.fetch(id_set, '(BODY.PEEK[HEADER.FIELDS (FROM)])')
            if status != 'OK': continue

            for item in fetch_data:
                if isinstance(item, tuple):
                    try:
                        raw = item[1].decode('utf-8', errors='ignore')
                        msg = email.message_from_string(raw)
                        from_hdr = msg.get('From', '')
                        m_email = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', from_hdr)
                        email_addr = m_email.group(0).lower() if m_email else "unknown"
                        dom = email_addr.split('@')[-1] if '@' in email_addr else "unknown"
                        dom_counts[dom] += 1
                        dom_senders[dom][from_hdr] += 1
                        processed_count += 1
                    except Exception:
                        continue

        client.logout()
        categories = categorize_domains(dom_counts, dom_senders)
        log_event("IMAP", f"Classified {processed_count} messages across {len(dom_counts)} domains.", level="SUCCESS")

        return {
            "account": account_cfg.get("name"),
            "mailbox": mailbox_name,
            "total_messages": processed_count,
            "total_domains": len(dom_counts),
            "categories": categories
        }
    except Exception as e:
        log_event("IMAP", f"Scan error: {e}", level="ERROR")
        try: client.logout()
        except Exception: pass
        return {"error": str(e), "domains": []}


def delete_thunderbird_domains(account_cfg, mailbox_name, domains):
    """Safely delete messages matching domains from local Thunderbird mbox store.
    Uses ultra-fast in-place MAPI X-Mozilla-Status flag marking (0x0008 = MSG_FLAG_EXPUNGED),
    which immediately expunges the emails in Thunderbird without file locking crashes."""
    mbox_dir = account_cfg.get("directory", "")
    if not mbox_dir or not os.path.exists(mbox_dir):
        return {"success": False, "deleted_domains": 0, "errors": [f"Thunderbird directory not found: {mbox_dir}"]}

    mbox_files_to_clean = []
    if mailbox_name.strip().lower() in ["__all__", "full mailbox (all folders)", "all folders", "full mailbox"]:
        for root, dirs, files in os.walk(mbox_dir):
            for item in files:
                if not item.endswith('.msf') and not item.endswith('.dat'):
                    mbox_files_to_clean.append(os.path.join(root, item))
    else:
        mbox_path = resolve_thunderbird_mbox_path(mbox_dir, mailbox_name)
        if not mbox_path or not os.path.isfile(mbox_path):
            return {"success": False, "deleted_domains": 0, "errors": [f"Mailbox '{mailbox_name}' not found."]}
        mbox_files_to_clean.append(mbox_path)

    domains_set = set(d.lower().strip() for d in domains)
    deleted_count = 0
    errors = []

    try:
        for file_path in mbox_files_to_clean:
            rel_name = os.path.relpath(file_path, mbox_dir).replace('\\', '/')
            log_event("THUNDERBIRD", f"Expunging target domains from '{rel_name}'...")
            
            mark_entries = [] # (pos, new_bytes)
            with open(file_path, 'rb') as f:
                byte_offset = 0
                current_status_pos = None
                current_status_val = b'0001'
                current_from = ''
                in_header = False

                for line in f:
                    line_len = len(line)
                    if line.startswith(b'From - '):
                        if current_status_pos is not None and current_from:
                            m = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', current_from)
                            ea = m.group(0).lower() if m else current_from.lower()
                            dom = ea.split('@')[-1] if '@' in ea else ''
                            if dom in domains_set or any(d in ea for d in domains_set):
                                try:
                                    val_int = int(current_status_val, 16)
                                except Exception:
                                    val_int = 1
                                # 0x0008 = MSG_FLAG_EXPUNGED (deleted in Thunderbird)
                                new_val = f'{val_int | 0x0008:04x}'.encode('ascii')
                                mark_entries.append((current_status_pos, new_val))
                                deleted_count += 1
                        current_status_pos = None
                        current_from = ''
                        in_header = True
                        byte_offset += line_len
                        continue

                    if in_header:
                        if line == b'\r\n' or line == b'\n':
                            in_header = False
                        elif line.startswith(b'X-Mozilla-Status:'):
                            current_status_pos = byte_offset + len(b'X-Mozilla-Status: ')
                            current_status_val = line[len(b'X-Mozilla-Status: '):].strip()
                        elif line.lower().startswith(b'from:'):
                            current_from = line[5:].decode('latin-1', errors='replace').strip()
                        elif current_from and (line.startswith(b' ') or line.startswith(b'\t')):
                            current_from += ' ' + line.decode('latin-1', errors='replace').strip()

                    byte_offset += line_len

                # Check last message
                if current_status_pos is not None and current_from:
                    m = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', current_from)
                    ea = m.group(0).lower() if m else current_from.lower()
                    dom = ea.split('@')[-1] if '@' in ea else ''
                    if dom in domains_set or any(d in ea for d in domains_set):
                        try:
                            val_int = int(current_status_val, 16)
                        except Exception:
                            val_int = 1
                        new_val = f'{val_int | 0x0008:04x}'.encode('ascii')
                        mark_entries.append((current_status_pos, new_val))
                        deleted_count += 1

            if mark_entries:
                log_event("DELETE", f"Marking {len(mark_entries)} messages as deleted in '{rel_name}'...")
                with open(file_path, 'r+b') as f:
                    for pos, new_bytes in mark_entries:
                        f.seek(pos)
                        f.write(new_bytes)
                    f.flush()

        log_event("DELETE", f"COMPLETED: Deleted {deleted_count} messages across Thunderbird storage.", level="SUCCESS")
        return {"success": True, "deleted_domains": len(domains), "deleted_count": deleted_count}
    except Exception as e:
        log_event("THUNDERBIRD", f"Error during deletion: {e}", level="ERROR")
        return {"success": False, "deleted_domains": 0, "errors": [str(e)]}


# ==============================================================================
# DELETING DOMAINS
# ==============================================================================
def delete_domains(account_name, mailbox_name, domains):
    """Safely delete messages from selected domains with full terminal logging."""
    print("\n" + "="*70, flush=True)
    log_event("DELETE", f"DELETION REQUEST: Account: '{account_name}', Folder: '{mailbox_name}'")
    log_event("DELETE", f"Target Domains ({len(domains)}): {domains[:5]}{'...' if len(domains) > 5 else ''}")
    print("="*70, flush=True)

    # 1. Check Thunderbird accounts
    tb_accounts = discover_thunderbird_accounts()
    tb_target = next((a for a in tb_accounts if a.get('name') == account_name or a.get('email') == account_name), None)
    if tb_target:
        return delete_thunderbird_domains(tb_target, mailbox_name, domains)

    saved_accounts = load_saved_accounts()
    auto_accounts = discover_windows_email_accounts()
    all_known = saved_accounts + auto_accounts
    target_cfg = next((a for a in all_known if a.get('name') == account_name or a.get('email') == account_name), None)

    if target_cfg and (target_cfg.get('type') in ['imap', 'new_outlook'] or target_cfg.get('host')):
        if not target_cfg.get('password'):
            saved_match = next((s for s in saved_accounts if s.get('email', '').lower() == target_cfg.get('email', '').lower()), None)
            if saved_match and saved_match.get('password'):
                target_cfg['password'] = saved_match['password']
        return delete_imap_domains(target_cfg, mailbox_name, domains)

    if not HAS_WIN32:
        return {"success": False, "deleted_domains": 0, "errors": ["pywin32 is not installed."]}

    try:
        mapi = get_outlook_namespace()
        folder = get_target_folder(mapi, account_name, mailbox_name)
    except Exception as e:
        log_event("DELETE", f"Access error: {e}", level="ERROR")
        return {"success": False, "deleted_domains": 0, "errors": [str(e)]}

    items = folder.Items
    total_items = items.Count
    domains_set = set(d.lower().strip() for d in domains)
    deleted_count = 0
    errors = []

    log_event("DELETE", f"Scanning {total_items} items in folder '{folder.Name}' for matches...")

    for i in range(total_items, 0, -1):
        try:
            item = items.Item(i)
            name, email_addr = get_sender_details(item)
            dom = email_addr.split('@')[-1] if '@' in email_addr else ""
            if dom.lower() in domains_set or any(d in email_addr for d in domains_set):
                subj = getattr(item, "Subject", "") or "No Subject"
                item.Delete()
                deleted_count += 1
                if deleted_count <= 10 or deleted_count % 25 == 0:
                    log_event("DELETE", f"Deleted #{deleted_count}: [{dom}] '{subj[:40]}'")
        except Exception as e:
            errors.append(str(e))

    remaining = folder.Items.Count
    print("="*70, flush=True)
    log_event("DELETE", f"COMPLETED: Deleted {deleted_count} messages matching {len(domains)} domains. Remaining in folder: {remaining}", level="SUCCESS")
    print("="*70 + "\n", flush=True)

    return {
        "success": len(errors) == 0,
        "deleted_domains": len(domains),
        "deleted_count": deleted_count,
        "new_count": remaining,
        "errors": errors[:10]
    }


def delete_imap_domains(account_cfg, mailbox_name, domains):
    """Delete messages matching domains via IMAP."""
    host = account_cfg.get("host", "outlook.office365.com")
    port = account_cfg.get("port", 993)
    user = account_cfg.get("username", account_cfg.get("email"))
    pwd = account_cfg.get("password")
    use_ssl = account_cfg.get("ssl", True)

    log_event("IMAP", f"Connecting to IMAP {host}:{port} for deletion...")
    try:
        client = imaplib.IMAP4_SSL(host, int(port), timeout=30) if use_ssl else imaplib.IMAP4(host, int(port), timeout=30)
        client.login(user, pwd)
    except Exception as e:
        log_event("IMAP", f"Connection failed: {e}", level="ERROR")
        return {"success": False, "deleted_domains": 0, "errors": [str(e)]}

    try:
        safe_mb = f'"{mailbox_name}"' if ' ' in mailbox_name else mailbox_name
        status, _ = client.select(safe_mb, readonly=False)
        if status != 'OK':
            status, _ = client.select('INBOX', readonly=False)

        domains_set = set(d.lower().strip() for d in domains)
        deleted_count = 0

        for dom in domains_set:
            status, data = client.search(None, f'(FROM "{dom}")')
            if status == 'OK' and data and data[0]:
                ids = data[0].split()
                if ids:
                    id_str = b','.join(ids)
                    client.store(id_str, '+FLAGS', '\\Deleted')
                    deleted_count += len(ids)
                    log_event("DELETE", f"Marked {len(ids)} messages from '{dom}' as \\Deleted.")

        log_event("DELETE", f"Expunging marked messages from server...")
        client.expunge()

        status, data = client.search(None, 'ALL')
        remaining = len(data[0].split()) if (status == 'OK' and data and data[0]) else 0

        client.logout()
        print("="*70, flush=True)
        log_event("DELETE", f"IMAP DELETION FINISHED: Deleted {deleted_count} messages. Remaining: {remaining}", level="SUCCESS")
        print("="*70 + "\n", flush=True)

        return {
            "success": True,
            "deleted_domains": len(domains),
            "deleted_count": deleted_count,
            "new_count": remaining,
            "errors": []
        }
    except Exception as e:
        log_event("IMAP", f"Error during deletion: {e}", level="ERROR")
        try: client.logout()
        except Exception: pass
        return {"success": False, "deleted_domains": 0, "errors": [str(e)]}


# ==============================================================================
# HTTP REQUEST HANDLER
# ==============================================================================
class CleanerHandler(http.server.SimpleHTTPRequestHandler):
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
            data = scan_account(acc, mb)
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
            log_event("ACCOUNTS", f"Removed credentials for '{email_addr}'")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode())
            return

        elif parsed.path == '/api/delete':
            acc = body.get('account')
            mb = body.get('mailbox', 'Inbox')
            doms = body.get('domains', [])
            res = delete_domains(acc, mb, doms)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode())
            return

        self.send_error(404)


def run():
    print("="*70, flush=True)
    print("   🧹 MailSweep (Universal Outlook & IMAP Cleaner)", flush=True)
    print("="*70, flush=True)
    log_event("INFO", f"Operating System: Windows ({sys.platform})")
    log_event("INFO", f"Classic Outlook COM (pywin32) Available: {HAS_WIN32}")
    log_event("INFO", f"Server starting on http://localhost:{PORT}")
    print("="*70, flush=True)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), CleanerHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == '__main__':
    run()
