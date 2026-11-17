import http.server
import socketserver
import json
import urllib.parse
import subprocess
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
        "APPLEMAIL": "🍎",
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
# THUNDERBIRD ACCOUNT AUTO-DISCOVERY & MBOX ENGINE (Cross-Platform)
# ==============================================================================
def discover_thunderbird_accounts():
    """Auto-discover email accounts and local mbox stores from Mozilla Thunderbird on macOS / Windows."""
    candidates = [
        os.path.expanduser('~/Library/Thunderbird/Profiles'),
        os.path.expandvars(r'%APPDATA%\Thunderbird\Profiles'),
        os.path.expanduser('~/.thunderbird')
    ]
    tb_profiles_dir = next((c for c in candidates if os.path.exists(c)), None)
    if not tb_profiles_dir:
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
                        servers.setdefault(sid, {})[key] = val.replace('\\\\', os.sep).replace('\\', os.sep)

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
                    'has_password': True,
                    'folders': folders
                })
                log_event("THUNDERBIRD", f"Found Thunderbird Account: {display_name} <{email_addr}> ({len(folders)} folders)")
    except Exception as e:
        log_event("THUNDERBIRD", f"Error scanning Thunderbird profiles: {e}", level="WARNING")

    return accounts


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


def scan_thunderbird_account(account_cfg, mailbox_name="INBOX"):
    """Scan local Thunderbird mbox store for senders and domains."""
    log_event("THUNDERBIRD", f"Scanning Thunderbird mailbox: '{account_cfg.get('name')}', Folder: '{mailbox_name}'...")
    mbox_dir = account_cfg.get("directory", "")
    if not mbox_dir or not os.path.exists(mbox_dir):
        return {"error": f"Thunderbird directory not found: {mbox_dir}", "domains": []}

    mbox_path = resolve_thunderbird_mbox_path(mbox_dir, mailbox_name)
    if not mbox_path or not os.path.isfile(mbox_path):
        return {"error": f"Mailbox file '{mailbox_name}' not found in Thunderbird storage.", "domains": []}

    dom_counts = Counter()
    dom_senders = defaultdict(lambda: Counter())
    processed_count = 0

    try:
        mbox = mailbox.mbox(mbox_path)
        log_event("THUNDERBIRD", f"Opened '{mbox_path}'. Total stored messages: {len(mbox)}")

        for msg in mbox:
            try:
                from_hdr = decode_mime_header(msg.get('From', ''))
                if not from_hdr:
                    continue

                processed_count += 1
                name = ""
                email_addr = ""
                m = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', from_hdr)
                if m:
                    email_addr = m.group(0).lower()
                name_match = re.match(r'^\"?([^\"<]+)\"?\s*<', from_hdr)
                if name_match:
                    name = name_match.group(1).strip()

                if not email_addr:
                    email_addr = from_hdr.lower()

                dom = email_addr.split('@')[-1] if '@' in email_addr else "unknown"
                dom_counts[dom] += 1
                disp = f"{name} <{email_addr}>" if name else email_addr
                dom_senders[dom][disp] += 1
            except Exception:
                continue

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


def delete_thunderbird_domains(account_cfg, mailbox_name, domains):
    """Safely delete messages matching domains from local Thunderbird mbox store."""
    mbox_dir = account_cfg.get("directory", "")
    if not mbox_dir or not os.path.exists(mbox_dir):
        return {"success": False, "deleted_domains": 0, "errors": [f"Thunderbird directory not found: {mbox_dir}"]}

    mbox_path = resolve_thunderbird_mbox_path(mbox_dir, mailbox_name)
    if not mbox_path or not os.path.isfile(mbox_path):
        return {"success": False, "deleted_domains": 0, "errors": [f"Mailbox '{mailbox_name}' not found."]}

    domains_set = set(d.lower().strip() for d in domains)
    deleted_count = 0
    errors = []

    try:
        mbox = mailbox.mbox(mbox_path)
        mbox.lock()
        keys_to_remove = []

        for key, msg in mbox.items():
            try:
                from_hdr = decode_mime_header(msg.get('From', ''))
                m = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', from_hdr)
                email_addr = m.group(0).lower() if m else from_hdr.lower()
                dom = email_addr.split('@')[-1] if '@' in email_addr else ""

                if dom.lower() in domains_set or any(d in email_addr for d in domains_set):
                    keys_to_remove.append(key)
            except Exception:
                continue

        log_event("THUNDERBIRD", f"Found {len(keys_to_remove)} matching messages to delete.")
        for key in keys_to_remove:
            mbox.remove(key)
            deleted_count += 1
            if deleted_count <= 10 or deleted_count % 25 == 0:
                log_event("DELETE", f"Deleted #{deleted_count} message from Thunderbird mbox.")

        mbox.flush()
        mbox.unlock()

        msf_path = mbox_path + '.msf'
        if os.path.exists(msf_path):
            try:
                os.remove(msf_path)
                log_event("THUNDERBIRD", "Removed summary file .msf for clean Thunderbird re-indexing.")
            except Exception:
                pass

        log_event("DELETE", f"COMPLETED: Deleted {deleted_count} messages from Thunderbird.", level="SUCCESS")
        return {"success": True, "deleted_domains": len(domains), "deleted_count": deleted_count, "remaining": len(mbox)}
    except Exception as e:
        log_event("THUNDERBIRD", f"Error during deletion: {e}", level="ERROR")
        return {"success": False, "deleted_domains": 0, "errors": [str(e)]}


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
# APPLE MAIL DISCOVERY
# ==============================================================================
def get_mail_accounts():
    """Discover all accounts configured in Apple Mail and saved IMAP configs."""
    accounts = []
    seen = set()

    # 1. Query Apple Mail
    cmd = """
    tell application "Mail"
        set accList to accounts
        set res to {}
        repeat with a in accList
            set end of res to ((name of a) & "###" & (user name of a) & "###" & ((email addresses of a) as string))
        end repeat
        set AppleScript's text item delimiters to linefeed
        return res as text
    end tell
    """
    log_event("ACCOUNTS", "Discovering accounts configured in Apple Mail...")
    try:
        proc = subprocess.run(['osascript', '-e', cmd], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if '###' in line:
                    parts = line.split('###')
                    acc_name = parts[0].strip()
                    acc_email = parts[2].strip() if len(parts) > 2 else parts[1].strip()
                    if acc_name.lower() not in seen:
                        accounts.append({
                            'name': acc_name,
                            'username': parts[1].strip(),
                            'email': acc_email,
                            'type': 'applemail',
                            'folders': ['Inbox', 'Junk', 'Trash', 'Archive']
                        })
                        seen.add(acc_name.lower())
                        seen.add(acc_email.lower())
                        log_event("ACCOUNTS", f"Found Apple Mail Account: {acc_name} <{acc_email}>")
        else:
            log_event("ACCOUNTS", f"AppleScript notice: {proc.stderr.strip()}", level="WARNING")
    except Exception as e:
        log_event("ACCOUNTS", f"Could not query Apple Mail: {e}", level="WARNING")

    # 2. Add Thunderbird accounts
    tb_accounts = discover_thunderbird_accounts()
    for acc in tb_accounts:
        acc_key = acc['name'].lower()
        if acc_key not in seen:
            accounts.append(acc)
            seen.add(acc_key)
            if acc.get('email'):
                seen.add(acc['email'].lower())

    # 3. Add saved IMAP accounts
    saved_imap = load_saved_accounts()
    for acc in saved_imap:
        acc_name = acc.get("name") or acc.get("email")
        if acc_name.lower() not in seen:
            accounts.append({
                "name": acc_name,
                "username": acc.get("username", acc.get("email")),
                "email": acc.get("email"),
                "type": "imap",
                "host": acc.get("host"),
                "port": acc.get("port", 993),
                "folders": acc.get("folders", ["INBOX", "Junk", "Spam", "Archive", "Trash"])
            })
            seen.add(acc_name.lower())
            seen.add(acc.get("email", "").lower())
            log_event("ACCOUNTS", f"Loaded saved IMAP Account: {acc_name} ({acc.get('email')})")

    return {
        "accounts": accounts,
        "com_available": True,
        "com_error": None
    }


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


def scan_account(account_name, mailbox_name="Inbox"):
    """Fetch senders and domains from Thunderbird, Apple Mail or IMAP."""
    log_event("SCAN", f"Scanning Account: '{account_name}', Folder: '{mailbox_name}'...")

    # 1. Check Thunderbird accounts first
    tb_accounts = discover_thunderbird_accounts()
    tb_target = next((a for a in tb_accounts if a.get('name') == account_name or a.get('email') == account_name), None)
    if tb_target:
        return scan_thunderbird_account(tb_target, mailbox_name)

    # 2. Check if IMAP account
    saved = load_saved_accounts()
    imap_cfg = next((a for a in saved if a.get('name') == account_name or a.get('email') == account_name), None)
    if imap_cfg:
        return scan_imap_account(imap_cfg, mailbox_name)

    # Apple Mail AppleScript scan
    cmd = f"""
    tell application "Mail"
        set acc to account "{account_name}"
        set mb to first mailbox of acc whose name is "{mailbox_name}"
        set sList to sender of every message of mb
        set AppleScript's text item delimiters to linefeed
        return sList as text
    end tell
    """
    log_event("APPLEMAIL", f"Executing AppleScript to fetch senders from '{mailbox_name}'...")
    proc = subprocess.run(['osascript', '-e', cmd], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        err = proc.stderr.strip()
        log_event("APPLEMAIL", f"AppleScript error: {err}", level="ERROR")
        return {"error": err, "domains": []}

    senders = [s for s in proc.stdout.splitlines() if s.strip()]
    log_event("APPLEMAIL", f"Retrieved {len(senders)} message senders. Categorizing...")

    dom_counts = Counter()
    dom_senders = defaultdict(lambda: Counter())

    for s in senders:
        m = re.search(r'<([^>]+)>', s)
        if m:
            email_addr = m.group(1).lower()
            name = s[:m.start()].strip(' "\'')
        else:
            m2 = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.\w+', s)
            if m2:
                email_addr = m2.group(0).lower()
                name = s.replace(m2.group(0), '').strip(' <"\'()[]')
            else:
                email_addr = s.lower()
                name = ""
        dom = email_addr.split('@')[-1] if '@' in email_addr else "unknown"
        dom_counts[dom] += 1
        disp = f"{name} <{email_addr}>" if name else email_addr
        dom_senders[dom][disp] += 1

    categories = categorize_domains(dom_counts, dom_senders)
    log_event("SCAN", f"Classified {len(senders)} messages across {len(dom_counts)} domains.", level="SUCCESS")

    return {
        "account": account_name,
        "mailbox": mailbox_name,
        "total_messages": len(senders),
        "total_domains": len(dom_counts),
        "categories": categories
    }


def scan_imap_account(account_cfg, mailbox_name="INBOX"):
    """Scan IMAP mailbox for senders and domains."""
    host = account_cfg.get("host")
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

    # 2. Check if IMAP account
    saved = load_saved_accounts()
    imap_cfg = next((a for a in saved if a.get('name') == account_name or a.get('email') == account_name), None)
    if imap_cfg:
        return delete_imap_domains(imap_cfg, mailbox_name, domains)

    # Apple Mail AppleScript Batch Deletion
    batch_size = 12
    batches = [domains[i:i + batch_size] for i in range(0, len(domains), batch_size)]
    deleted_count = 0
    errors = []

    for idx, b in enumerate(batches, 1):
        conditions = " or ".join([f'sender contains "{d}"' for d in b])
        cmd = f"""
        tell application "Mail"
            set acc to account "{account_name}"
            set mb to first mailbox of acc whose name is "{mailbox_name}"
            set msgs to (messages of mb whose {conditions})
            set c to count of msgs
            delete msgs
            return c
        end tell
        """
        log_event("APPLEMAIL", f"Executing Batch {idx}/{len(batches)} (Domains: {b})...")
        proc = subprocess.run(['osascript', '-e', cmd], capture_output=True, text=True, timeout=45)
        if proc.returncode == 0:
            try:
                batch_del = int(proc.stdout.strip())
                deleted_count += batch_del
                log_event("DELETE", f"Batch {idx} deleted {batch_del} messages.")
            except Exception:
                pass
        else:
            err = proc.stderr.strip()
            log_event("APPLEMAIL", f"Batch {idx} error: {err}", level="WARNING")
            errors.append(err)

    print("="*70, flush=True)
    log_event("DELETE", f"COMPLETED: Deleted {deleted_count} messages across {len(domains)} domains.", level="SUCCESS")
    print("="*70 + "\n", flush=True)

    return {
        "success": len(errors) == 0,
        "deleted_domains": len(domains),
        "deleted_count": deleted_count,
        "errors": errors[:10]
    }


def delete_imap_domains(account_cfg, mailbox_name, domains):
    """Delete messages matching domains via IMAP."""
    host = account_cfg.get("host")
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
            host = body.get('host', '').strip()
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
                res = {"success": True, "message": "IMAP account added and verified!", "folders": folders}
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
            log_event("ACCOUNTS", f"Removed IMAP account '{email_addr}'")
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
    print("   🧹 MailSweep (macOS Apple Mail & IMAP Cleaner)", flush=True)
    print("="*70, flush=True)
    log_event("INFO", f"Operating System: macOS ({sys.platform})")
    log_event("INFO", f"Server running at http://localhost:{PORT}")
    print("="*70, flush=True)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), CleanerHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == '__main__':
    run()
