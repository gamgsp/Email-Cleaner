let scannedSubscriptions = [];
let selectedIndexSet = new Set();
let accountDataMap = {};

const accountSelect = document.getElementById('accountSelect');
const mailboxSelect = document.getElementById('mailboxSelect');
const targetEmailInput = document.getElementById('targetEmailInput');
const limitSelect = document.getElementById('limitSelect');
const btnScan = document.getElementById('btnScan');

const accountNotice = document.getElementById('accountNotice');
const btnNoticeAddAccount = document.getElementById('btnNoticeAddAccount');
const linkAddAccount = document.getElementById('linkAddAccount');
const btnOpenAccountModal = document.getElementById('btnOpenAccountModal');

// Modal Elements
const accountModal = document.getElementById('accountModal');
const btnCloseModal = document.getElementById('btnCloseModal');
const btnCancelModal = document.getElementById('btnCancelModal');
const providerPreset = document.getElementById('providerPreset');
const imapEmail = document.getElementById('imapEmail');
const imapPassword = document.getElementById('imapPassword');
const imapHost = document.getElementById('imapHost');
const imapPort = document.getElementById('imapPort');
const btnSaveImap = document.getElementById('btnSaveImap');
const modalStatus = document.getElementById('modalStatus');

const statsBar = document.getElementById('statsBar');
const statFoundCount = document.getElementById('statFoundCount');
const statScannedCount = document.getElementById('statScannedCount');
const statSelectedCount = document.getElementById('statSelectedCount');

const actionToolbar = document.getElementById('actionToolbar');
const searchInput = document.getElementById('searchInput');
const btnSelectAll = document.getElementById('btnSelectAll');
const btnDeselectAll = document.getElementById('btnDeselectAll');
const btnExecuteUnsub = document.getElementById('btnExecuteUnsub');
const unsubCountBadge = document.getElementById('unsubCountBadge');

const resultsContainer = document.getElementById('resultsContainer');
const subTableBody = document.getElementById('subTableBody');
const masterCheckbox = document.getElementById('masterCheckbox');

const loadingOverlay = document.getElementById('loadingOverlay');
const loadingText = document.getElementById('loadingText');
const loadingSubtext = document.getElementById('loadingSubtext');

// 1. Initialize Accounts
async function initAccounts() {
  try {
    const res = await fetch('/api/accounts');
    const data = await res.json();
    const accounts = Array.isArray(data) ? data : (data.accounts || []);
    
    accountSelect.innerHTML = '';
    accountDataMap = {};

    if (accounts.length === 0) {
      if (accountNotice) accountNotice.classList.remove('hidden');
      accountSelect.innerHTML = '<option value="">No Accounts Found (Click + Add Account)</option>';
    } else {
      if (accountNotice) accountNotice.classList.add('hidden');
      accounts.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.name;
        const typeBadge = a.type === 'imap' ? ' [IMAP]' : ' [Apple Mail]';
        opt.textContent = `${a.name} (${a.email})${typeBadge}`;
        accountSelect.appendChild(opt);
        accountDataMap[a.name] = a;
      });

      // Auto-select first
      accountSelect.value = accounts[0].name;
      targetEmailInput.value = accounts[0].email;
      updateMailboxFolders(accounts[0]);
    }
  } catch (err) {
    console.error('Failed to load accounts', err);
    if (accountNotice) accountNotice.classList.remove('hidden');
  }
}

function updateMailboxFolders(acc) {
  if (!acc || !acc.folders || acc.folders.length === 0) return;
  mailboxSelect.innerHTML = '';

  // Add Full Mailbox option first
  const fullOpt = document.createElement('option');
  fullOpt.value = '__all__';
  fullOpt.textContent = '⚡ Full Mailbox (All Folders)';
  mailboxSelect.appendChild(fullOpt);

  acc.folders.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f;
    opt.textContent = f;
    mailboxSelect.appendChild(opt);
  });

  mailboxSelect.value = '__all__';
}

accountSelect.addEventListener('change', () => {
  const chosen = accountSelect.value;
  const acc = accountDataMap[chosen];
  if (acc) {
    targetEmailInput.value = acc.email;
    updateMailboxFolders(acc);
  }
});

// Modal Logic
function openModal() {
  accountModal.classList.remove('hidden');
  modalStatus.classList.add('hidden');
  modalStatus.textContent = '';
}
function closeModal() {
  accountModal.classList.add('hidden');
}

if (btnOpenAccountModal) btnOpenAccountModal.addEventListener('click', openModal);
if (linkAddAccount) linkAddAccount.addEventListener('click', (e) => { e.preventDefault(); openModal(); });
if (btnNoticeAddAccount) btnNoticeAddAccount.addEventListener('click', openModal);
if (btnCloseModal) btnCloseModal.addEventListener('click', closeModal);
if (btnCancelModal) btnCancelModal.addEventListener('click', closeModal);

const presets = {
  outlook: { host: 'outlook.office365.com', port: 993, placeholder: 'yourname@outlook.com' },
  gmail: { host: 'imap.gmail.com', port: 993, placeholder: 'yourname@gmail.com' },
  yahoo: { host: 'imap.mail.yahoo.com', port: 993, placeholder: 'yourname@yahoo.com' },
  icloud: { host: 'imap.mail.me.com', port: 993, placeholder: 'yourname@icloud.com' },
  custom: { host: '', port: 993, placeholder: 'user@domain.com' }
};

if (providerPreset) {
  providerPreset.addEventListener('change', () => {
    const p = presets[providerPreset.value] || presets.custom;
    imapHost.value = p.host;
    imapPort.value = p.port;
    imapEmail.placeholder = p.placeholder;
  });
}

if (btnSaveImap) {
  btnSaveImap.addEventListener('click', async () => {
    const emailVal = imapEmail.value.trim();
    const pwdVal = imapPassword.value.trim();
    const hostVal = imapHost.value.trim();
    const portVal = parseInt(imapPort.value.trim(), 10) || 993;

    if (!emailVal || !pwdVal || !hostVal) {
      alert('Please enter your email, password, and host.');
      return;
    }

    btnSaveImap.disabled = true;
    btnSaveImap.textContent = 'Testing connection...';
    modalStatus.classList.remove('hidden');
    modalStatus.className = 'modal-status info';
    modalStatus.textContent = 'Connecting to IMAP server... Check terminal for logs.';

    try {
      const res = await fetch('/api/imap/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: jsonBody({
          email: emailVal,
          username: emailVal,
          password: pwdVal,
          host: hostVal,
          port: portVal,
          ssl: true
        })
      });
      const data = await res.json();
      if (data.success) {
        modalStatus.className = 'modal-status success';
        modalStatus.textContent = 'Connected successfully! Account saved.';
        setTimeout(() => {
          closeModal();
          initAccounts();
        }, 1000);
      } else {
        modalStatus.className = 'modal-status error';
        modalStatus.textContent = `Connection failed: ${data.message}`;
      }
    } catch (err) {
      modalStatus.className = 'modal-status error';
      modalStatus.textContent = `Error: ${err.message}`;
    } finally {
      btnSaveImap.disabled = false;
      btnSaveImap.textContent = 'Test & Connect Account';
    }
  });
}

function jsonBody(obj) {
  return JSON.stringify(obj);
}

// 2. Scan Subscriptions
btnScan.addEventListener('click', async () => {
  const account = accountSelect.value;
  const mailbox = mailboxSelect.value;
  const limit = limitSelect.value;
  const targetEmail = targetEmailInput.value.trim();

  if (!account) {
    alert('Please select an email account or add one using "+ Add Account".');
    return;
  }
  if (!targetEmail) {
    alert('Please enter your email address for survey and confirmation forms.');
    return;
  }

  const depthText = limit === "0" ? "Full Mailbox" : `Latest ${limit} messages`;
  showLoading('Scanning for Subscriptions...', `Analyzing ${account} > ${mailbox} (${depthText}). Check terminal for real-time output.`);

  try {
    const res = await fetch(`/api/scan?account=${encodeURIComponent(account)}&mailbox=${encodeURIComponent(mailbox)}&limit=${encodeURIComponent(limit)}`);
    const data = await res.json();

    if (data.error) {
      alert(`Scan failed: ${data.error}`);
      return;
    }

    scannedSubscriptions = data.subscriptions || [];
    statScannedCount.textContent = Number(data.total_scanned).toLocaleString();
    selectedIndexSet.clear();
    renderSubscriptions();
  } catch (err) {
    alert(`Scan error: ${err.message}`);
  } finally {
    hideLoading();
  }
});

function renderSubscriptions() {
  statsBar.classList.remove('hidden');
  actionToolbar.classList.remove('hidden');
  resultsContainer.classList.remove('hidden');

  statFoundCount.textContent = scannedSubscriptions.length;
  updateSelection();

  subTableBody.innerHTML = '';
  if (scannedSubscriptions.length === 0) {
    subTableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 40px; color: var(--text-muted);">No active marketing subscriptions detected in scanned messages. Check terminal logs.</td></tr>`;
    return;
  }

  scannedSubscriptions.forEach((sub, idx) => {
    const tr = document.createElement('tr');
    tr.id = `sub-row-${idx}`;
    tr.dataset.domain = sub.domain.toLowerCase();
    tr.dataset.sender = sub.sender.toLowerCase();

    let methodBadge = '<span class="badge-tag web-link">Web Link</span>';
    if (sub.rfc_one_click) {
      methodBadge = '<span class="badge-tag one-click">⚡ RFC 8058 One-Click</span>';
    } else if (sub.rfc_http) {
      methodBadge = '<span class="badge-tag rfc-direct">RFC GET</span>';
    } else if (sub.rfc_mailto) {
      methodBadge = '<span class="badge-tag mailto">✉️ RFC Mailto</span>';
    }

    const emailCount = sub.email_count ? Number(sub.email_count).toLocaleString() : '1';

    tr.innerHTML = `
      <td class="col-check">
        <input type="checkbox" class="sub-checkbox" data-index="${idx}">
      </td>
      <td>
        <div style="font-weight: 600; font-family: var(--font-mono);">${escapeHtml(sub.domain)}</div>
        <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(sub.sender)}</div>
      </td>
      <td>
        <span class="count-badge">${emailCount} emails</span>
      </td>
      <td style="max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
        ${escapeHtml(sub.subject)}
      </td>
      <td>${methodBadge}</td>
      <td class="status-cell">
        <span class="status-badge pending">Ready</span>
      </td>
    `;
    subTableBody.appendChild(tr);
  });

  attachCheckboxListeners();
}

function attachCheckboxListeners() {
  const checkboxes = document.querySelectorAll('.sub-checkbox');
  checkboxes.forEach(cb => {
    cb.addEventListener('change', (e) => {
      const idx = parseInt(e.target.dataset.index, 10);
      if (e.target.checked) {
        selectedIndexSet.add(idx);
      } else {
        selectedIndexSet.delete(idx);
      }
      updateSelection();
    });
  });
}

function updateSelection() {
  const visibleRows = Array.from(subTableBody.querySelectorAll('tr')).filter(tr => tr.style.display !== 'none');
  const count = selectedIndexSet.size;
  statSelectedCount.textContent = count;
  unsubCountBadge.textContent = count;
  btnExecuteUnsub.disabled = count === 0;

  if (visibleRows.length > 0 && selectedIndexSet.size === scannedSubscriptions.length) {
    masterCheckbox.checked = true;
    masterCheckbox.indeterminate = false;
  } else if (selectedIndexSet.size > 0) {
    masterCheckbox.checked = false;
    masterCheckbox.indeterminate = true;
  } else {
    masterCheckbox.checked = false;
    masterCheckbox.indeterminate = false;
  }
}

masterCheckbox.addEventListener('change', () => {
  const isChecked = masterCheckbox.checked;
  const checkboxes = document.querySelectorAll('.sub-checkbox');
  checkboxes.forEach(cb => {
    const tr = cb.closest('tr');
    if (tr && tr.style.display !== 'none') {
      cb.checked = isChecked;
      const idx = parseInt(cb.dataset.index, 10);
      if (isChecked) selectedIndexSet.add(idx);
      else selectedIndexSet.delete(idx);
    }
  });
  updateSelection();
});

btnSelectAll.addEventListener('click', () => {
  document.querySelectorAll('.sub-checkbox').forEach(cb => {
    const tr = cb.closest('tr');
    if (tr && tr.style.display !== 'none') {
      cb.checked = true;
      selectedIndexSet.add(parseInt(cb.dataset.index, 10));
    }
  });
  updateSelection();
});

btnDeselectAll.addEventListener('click', () => {
  document.querySelectorAll('.sub-checkbox').forEach(cb => {
    cb.checked = false;
  });
  selectedIndexSet.clear();
  updateSelection();
});

searchInput.addEventListener('input', () => {
  const q = searchInput.value.toLowerCase().trim();
  const rows = subTableBody.querySelectorAll('tr');
  rows.forEach(tr => {
    const d = tr.dataset.domain || '';
    const s = tr.dataset.sender || '';
    if (d.includes(q) || s.includes(q)) {
      tr.style.display = '';
    } else {
      tr.style.display = 'none';
    }
  });
  updateSelection();
});

// 3. Execute Unsubscribe
btnExecuteUnsub.addEventListener('click', async () => {
  const targetEmail = targetEmailInput.value.trim();
  if (!targetEmail) {
    alert('Please enter your email address for survey and verification forms.');
    return;
  }

  const selectedIndices = Array.from(selectedIndexSet);
  if (selectedIndices.length === 0) return;

  const targetSubs = selectedIndices.map(i => scannedSubscriptions[i]);
  const confirmMsg = `Are you sure you want to trigger automated unsubscription for ${targetSubs.length} newsletters/senders? Check terminal for live step-by-step progress.`;
  if (!confirm(confirmMsg)) return;

  btnExecuteUnsub.disabled = true;
  btnExecuteUnsub.textContent = 'Processing in Terminal...';

  // Mark pending rows
  selectedIndices.forEach(idx => {
    const row = document.getElementById(`sub-row-${idx}`);
    if (row) {
      const cell = row.querySelector('.status-cell');
      cell.innerHTML = '<span class="status-badge running">Processing...</span>';
    }
  });

  try {
    const res = await fetch('/api/unsubscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_email: targetEmail,
        subscriptions: targetSubs
      })
    });

    const results = await res.json();

    results.forEach((r, i) => {
      const originalIdx = selectedIndices[i];
      const row = document.getElementById(`sub-row-${originalIdx}`);
      if (!row) return;

      const cell = row.querySelector('.status-cell');
      if (r.success) {
        cell.innerHTML = `
          <span class="status-badge success">✓ ${escapeHtml(r.method || 'Unsubscribed')}</span>
          <div style="font-size:10px; color:var(--text-muted); margin-top:2px;">${escapeHtml(r.details || '')}</div>
        `;
        row.classList.add('completed-row');
      } else {
        let actionBtn = '';
        if (r.manual_url) {
          actionBtn = `<a href="${escapeHtml(r.manual_url)}" target="_blank" class="btn-manual-link" title="Open direct unsubscribe page">Open Link ↗</a>`;
        }
        cell.innerHTML = `
          <div style="display:flex; align-items:center; gap:6px;">
            <span class="status-badge manual">⚠️ Manual Required</span>
            ${actionBtn}
          </div>
          <div style="font-size:10px; color:#f87171; margin-top:2px;">${escapeHtml(r.details || '')}</div>
        `;
      }
    });

    selectedIndexSet.clear();
    document.querySelectorAll('.sub-checkbox').forEach(cb => cb.checked = false);
    updateSelection();
  } catch (err) {
    alert(`Unsubscribe failed: ${err.message}`);
  } finally {
    btnExecuteUnsub.disabled = false;
    btnExecuteUnsub.innerHTML = '<span class="btn-icon">⚡</span> Auto-Unsubscribe (<span id="unsubCountBadge">0</span>)';
    updateSelection();
  }
});

function showLoading(title, subtext) {
  loadingText.textContent = title;
  loadingSubtext.textContent = subtext;
  loadingOverlay.classList.remove('hidden');
}

function hideLoading() {
  loadingOverlay.classList.add('hidden');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Start
initAccounts();
