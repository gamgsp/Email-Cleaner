import http.server
import socketserver
import json
import urllib.parse
import urllib.request
import subprocess
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

# Check Playwright availability
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
        "APPLEMAIL": "🍎",
        "THUNDERBIRD": "🦅",
        "FORM": "📝",
        "RFC": "⚡"
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


# ==============================================================================
# SCANNING SUBSCRIPTIONS
# ==============================================================================
def scan_subscriptions(account_name, mailbox_name="Inbox", limit=0):
    """Scan subscriptions from Thunderbird, Apple Mail or IMAP."""
    log_event("SCAN", f"Starting scan for Account: '{account_name}', Folder: '{mailbox_name}', Limit: {limit}...")

    # 1. Check Thunderbird accounts first
    tb_accounts = discover_thunderbird_accounts()
    tb_target = next((a for a in tb_accounts if a.get('name') == account_name or a.get('email') == account_name), None)
    if tb_target:
        return scan_thunderbird_subscriptions(tb_target, mailbox_name, limit)

    # 2. Check if IMAP account
    saved = load_saved_accounts()
    imap_cfg = next((a for a in saved if a.get('name') == account_name or a.get('email') == account_name), None)
    if imap_cfg:
        return scan_imap_subscriptions(imap_cfg, mailbox_name, limit)

    # Apple Mail AppleScript scan
    if limit > 0:
        cmd = f"""
        tell application "Mail"
            set acc to account "{account_name}"
            set mb to first mailbox of acc whose name is "{mailbox_name}"
            set tot to count of messages of mb
            if tot = 0 then return ""
            set maxM to {limit}
            if tot < maxM then set maxM to tot
            
            set res to {{}}
            repeat with i from 1 to maxM
                try
                    set m to message i of mb
                    set end of res to ((id of m as string) & "@@@" & (sender of m) & "@@@" & (subject of m))
                end try
            end repeat
            set AppleScript's text item delimiters to linefeed
            return res as text
        end tell
        """
    else:
        cmd = f"""
        tell application "Mail"
            set acc to account "{account_name}"
            set mb to first mailbox of acc whose name is "{mailbox_name}"
            set idList to id of every message of mb
            set sList to sender of every message of mb
            set subList to subject of every message of mb
            
            set res to {{}}
            repeat with i from 1 to (count of idList)
                set end of res to ((item i of idList as string) & "@@@" & (item i of sList) & "@@@" & (item i of subList))
            end repeat
            set AppleScript's text item delimiters to linefeed
            return res as text
        end tell
        """

    log_event("APPLEMAIL", f"Executing batch query in Apple Mail...")
    proc = subprocess.run(['osascript', '-e', cmd], capture_output=True, text=True, timeout=90)
    if proc.returncode != 0:
        err = proc.stderr.strip()
        log_event("APPLEMAIL", f"AppleScript error: {err}", level="ERROR")
        return {"error": err, "subscriptions": [], "total_scanned": 0}

    lines = [l for l in proc.stdout.splitlines() if '@@@' in l]
    total_scanned = len(lines)
    log_event("APPLEMAIL", f"Retrieved {total_scanned} messages from mailbox.")

    domain_msgs = defaultdict(list)
    domain_latest_meta = {}

    for line in lines:
        parts = line.split('@@@')
        mid = parts[0]
        sender = parts[1]
        subject = parts[2] if len(parts) > 2 else ""

        m_email = re.search(r'<([^>]+)>', sender)
        email_addr = m_email.group(1).lower() if m_email else sender.lower()
        dom = email_addr.split('@')[-1] if '@' in email_addr else "unknown"

        domain_msgs[dom].append(mid)
        if dom not in domain_latest_meta:
            domain_latest_meta[dom] = {
                "sample_mid": mid,
                "sender": sender,
                "subject": subject
            }

    log_event("SCAN", f"Grouped into {len(domain_msgs)} unique sender domains.")
    sorted_domains = sorted(domain_msgs.keys(), key=lambda d: len(domain_msgs[d]), reverse=True)

    discovered = []
    inspection_limit = 100
    log_event("SCAN", f"Inspecting headers and HTML bodies for top {min(len(sorted_domains), inspection_limit)} domains...")

    for dom in sorted_domains[:inspection_limit]:
        meta = domain_latest_meta[dom]
        mid = meta["sample_mid"]

        fetch_cmd = f"""
        tell application "Mail"
            set acc to account "{account_name}"
            set mb to first mailbox of acc whose name is "{mailbox_name}"
            set m to (first message of mb whose id is {mid})
            set h to (all headers of m)
            set src to (source of m)
            return h & "===SOURCE_SPLIT===" & src
        end tell
        """
        proc_fetch = subprocess.run(['osascript', '-e', fetch_cmd], capture_output=True, text=True, timeout=12)
        if proc_fetch.returncode != 0:
            continue

        split_parts = proc_fetch.stdout.split("===SOURCE_SPLIT===")
        headers_str = split_parts[0]
        raw_source = split_parts[1] if len(split_parts) > 1 else ""

        http_unsub, mailto_unsub, is_one_click = parse_list_unsubscribe_headers(headers_str)

        web_links = []
        if raw_source:
            try:
                msg = email.message_from_string(raw_source, policy=policy.default)
                for part in msg.walk():
                    if part.get_content_type() == 'text/html':
                        web_links.extend(extract_web_unsubscribe_links(part.get_content()))
            except Exception:
                pass

        if http_unsub or mailto_unsub or web_links:
            discovered.append({
                "message_id": mid,
                "domain": dom,
                "email_count": len(domain_msgs[dom]),
                "sender": meta["sender"],
                "subject": meta["subject"],
                "rfc_unsubscribe": http_unsub or mailto_unsub,
                "rfc_http": http_unsub,
                "rfc_mailto": mailto_unsub,
                "rfc_one_click": is_one_click,
                "web_links": list(set(web_links))[:5]
            })

    log_event("SCAN", f"Scan finished! Discovered {len(discovered)} active marketing subscriptions.", level="SUCCESS")

    return {
        "account": account_name,
        "mailbox": mailbox_name,
        "total_scanned": total_scanned,
        "unique_domains": len(domain_msgs),
        "subscriptions": discovered
    }


def scan_imap_subscriptions(account_cfg, mailbox_name="INBOX", limit=0):
    """Scan subscriptions using direct IMAP connection."""
    host = account_cfg.get("host")
    port = account_cfg.get("port", 993)
    username = account_cfg.get("username", account_cfg.get("email"))
    password = account_cfg.get("password")
    use_ssl = account_cfg.get("ssl", True)

    log_event("IMAP", f"Connecting to IMAP {host}:{port} for {username}...")
    try:
        client = imaplib.IMAP4_SSL(host, int(port), timeout=25) if use_ssl else imaplib.IMAP4(host, int(port), timeout=25)
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
            if status != 'OK': continue

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
        log_event("IMAP", f"Scan finished! Found {len(discovered)} subscriptions.", level="SUCCESS")

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
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'close'
    }

    # --------------------------------------------------------------------------
    # Phase 1: RFC 8058 One-Click (HTTP POST)
    # --------------------------------------------------------------------------
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
            log_event("RFC", f"One-Click failed: {e}. Falling back...", level="WARNING")

    # --------------------------------------------------------------------------
    # Phase 2: RFC 2369 Web GET
    # --------------------------------------------------------------------------
    if rfc_http:
        log_event("RFC", f"Attempting Phase 2: RFC List-Unsubscribe GET to {rfc_http}...")
        try:
            r = requests.get(rfc_http, headers=headers, timeout=14, allow_redirects=True)
            log_event("RFC", f"GET response HTTP {r.status_code}")
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

    # --------------------------------------------------------------------------
    # Phase 3: RFC Mailto Unsubscribe via Apple Mail AppleScript
    # --------------------------------------------------------------------------
    if rfc_mailto:
        log_event("RFC", f"Attempting Phase 3: Inspecting mailto address: {rfc_mailto}")
        parsed_mailto = urllib.parse.urlparse(rfc_mailto)
        recipient = parsed_mailto.path
        query_params = urllib.parse.parse_qs(parsed_mailto.query)
        unsub_subject = query_params.get('subject', ['Unsubscribe'])[0]

        send_cmd = f"""
        tell application "Mail"
            set newMsg to make new outgoing message with properties {{subject:"{unsub_subject}", content:"Unsubscribe", visible:false}}
            tell newMsg
                make new to recipient with properties {{address:"{recipient}"}}
                send
            end tell
        end tell
        """
        try:
            log_event("APPLEMAIL", f"Dispatching unsubscribe email to '{recipient}' via Apple Mail...")
            proc = subprocess.run(['osascript', '-e', send_cmd], capture_output=True, text=True, timeout=8)
            if proc.returncode == 0:
                log_event("UNSUB", f"✅ [SUCCESS] Sent unsubscribe email to {recipient} via Apple Mail!", level="SUCCESS")
                return {
                    "success": True,
                    "method": "RFC Mailto Dispatched",
                    "details": f"Dispatched unsubscribe email to {recipient}"
                }
            else:
                log_event("APPLEMAIL", f"Mail dispatch failed: {proc.stderr.strip()}", level="WARNING")
        except Exception as e:
            log_event("APPLEMAIL", f"Could not send email via Apple Mail: {e}", level="WARNING")

    # --------------------------------------------------------------------------
    # Phase 4: Smart Web Form & Preference Center Solver
    # --------------------------------------------------------------------------
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

    # --------------------------------------------------------------------------
    # Phase 5: Real Chrome Headless Automation (Playwright on macOS)
    # --------------------------------------------------------------------------
    if HAS_PLAYWRIGHT and candidate_urls:
        target_url = candidate_urls[0]
        log_event("FORM", f"Attempting Phase 5: Real Chrome Headless Solver for '{domain}' at {target_url}...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page()
                page.goto(target_url, timeout=20000, wait_until="domcontentloaded")
                time.sleep(2)

                if target_email:
                    email_inputs = page.locator('input[type="email"], input[name*="email" i], input[id*="email" i]')
                    if email_inputs.count() > 0:
                        for idx_inp in range(min(email_inputs.count(), 2)):
                            try:
                                email_inputs.nth(idx_inp).fill(target_email)
                            except Exception:
                                pass

                unsub_all_box = page.locator('input[type="checkbox"][id*="all" i], input[type="checkbox"][name*="all" i], label:has-text("Unsubscribe from all"), label:has-text("Opt-out of all")')
                if unsub_all_box.count() > 0:
                    try:
                        unsub_all_box.first.click(timeout=2000)
                    except Exception:
                        pass

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

    # --------------------------------------------------------------------------
    # Phase 6: Manual Action Link
    # --------------------------------------------------------------------------
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
    print("   🔕 UnsubBot (macOS Apple Mail & IMAP Engine)", flush=True)
    print("="*70, flush=True)
    log_event("INFO", f"Operating System: macOS ({sys.platform})")
    log_event("INFO", f"Server running at http://localhost:{PORT}")
    print("="*70, flush=True)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), UnsubHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == '__main__':
    run()
