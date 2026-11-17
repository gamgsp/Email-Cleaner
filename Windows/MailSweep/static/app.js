let scanData = null;
let selectedDomains = new Set();
let accountDataMap = {};

const accountSelect = document.getElementById('accountSelect');
const customAccountInput = document.getElementById('customAccountInput');
const mailboxSelect = document.getElementById('mailboxSelect');
const btnScan = document.getElementById('btnScan');
const statsBar = document.getElementById('statsBar');
const actionToolbar = document.getElementById('actionToolbar');
const categoryContainer = document.getElementById('categoryContainer');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingText = document.getElementById('loadingText');
const loadingSubtext = document.getElementById('loadingSubtext');

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

const statTotalMsgs = document.getElementById('statTotalMsgs');
const statTotalDomains = document.getElementById('statTotalDomains');
const statSelectedCount = document.getElementById('statSelectedCount');
const deleteCountBadge = document.getElementById('deleteCountBadge');
const btnExecuteDelete = document.getElementById('btnExecuteDelete');
const searchInput = document.getElementById('searchInput');

const btnSelectAllSpam = document.getElementById('btnSelectAllSpam');
const btnSelectAll = document.getElementById('btnSelectAll');
const btnDeselectAll = document.getElementById('btnDeselectAll');

let pendingScanAfterAuth = false;

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
      accountSelect.innerHTML = '<option value="">No Accounts Found (Click Add Account)</option>';
    } else {
      if (accountNotice) accountNotice.classList.add('hidden');
      accounts.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.name;
        const typeBadge = a.type === 'imap' ? ' [IMAP]' : ' [Outlook]';
        const readyBadge = a.has_password === false ? ' [🔑 Needs Password]' : ' [✓ Ready]';
        opt.textContent = `${a.name} (${a.email})${typeBadge}${readyBadge}`;
        accountSelect.appendChild(opt);
        accountDataMap[a.name] = a;
      });

      // Auto-select first account
      accountSelect.value = accounts[0].name;
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
  
  // Default to Full Mailbox for complete coverage or Inbox
  mailboxSelect.value = '__all__';
}

accountSelect.addEventListener('change', () => {
  const chosen = accountSelect.value;
  const acc = accountDataMap[chosen];
  if (acc) {
    updateMailboxFolders(acc);
  }
});

// Modal Logic
function openModal(prefillEmail) {
  accountModal.classList.remove('hidden');
  modalStatus.classList.add('hidden');
  modalStatus.textContent = '';
  if (prefillEmail) {
    imapEmail.value = prefillEmail;
    if (providerPreset) providerPreset.value = 'outlook';
    if (imapHost) imapHost.value = 'outlook.office365.com';
    if (imapPort) imapPort.value = '993';
    setTimeout(() => { if (imapPassword) imapPassword.focus(); }, 100);
  }
}
function closeModal() {
  accountModal.classList.add('hidden');
}

if (btnOpenAccountModal) btnOpenAccountModal.addEventListener('click', () => openModal());
if (linkAddAccount) linkAddAccount.addEventListener('click', (e) => { e.preventDefault(); openModal(); });
if (btnNoticeAddAccount) btnNoticeAddAccount.addEventListener('click', () => openModal());
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
      modalStatus.className = 'modal-status error';
      modalStatus.textContent = 'Please fill in Email, Password, and Server Host.';
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
        body: JSON.stringify({
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
        setTimeout(async () => {
          closeModal();
          await initAccounts();
          if (pendingScanAfterAuth) {
            pendingScanAfterAuth = false;
            btnScan.click();
          }
        }, 800);
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

// 2. Scan Account
btnScan.addEventListener('click', async () => {
  const chosenAccount = customAccountInput ? (customAccountInput.value.trim() || accountSelect.value) : accountSelect.value;
  const mailbox = mailboxSelect.value;

  if (!chosenAccount) {
    alert('Please select an account from the dropdown or enter an email / account name.');
    return;
  }

  const currentAcc = accountDataMap[chosenAccount];
  if (currentAcc && currentAcc.has_password === false) {
    pendingScanAfterAuth = true;
    openModal(currentAcc.email);
    modalStatus.classList.remove('hidden');
    modalStatus.className = 'modal-status info';
    modalStatus.textContent = `Enter your Password or App Password for ${currentAcc.email} to scan messages.`;
    return;
  }

  showLoading('Scanning Messages...', `Fetching messages from ${chosenAccount} > ${mailbox}. Check terminal for live logs.`);
  try {
    const res = await fetch(`/api/scan?account=${encodeURIComponent(chosenAccount)}&mailbox=${encodeURIComponent(mailbox)}`);
    const data = await res.json();

    if (data.needs_password) {
      hideLoading();
      pendingScanAfterAuth = true;
      openModal(data.email || currentAcc?.email);
      modalStatus.classList.remove('hidden');
      modalStatus.className = 'modal-status error';
      modalStatus.textContent = data.error || 'Password required to connect via IMAP.';
      return;
    }

    if (data.error) {
      alert(`Error scanning account: ${data.error}`);
      return;
    }

    scanData = data;
    selectedDomains.clear();
    renderResults();
  } catch (err) {
    alert(`Failed to communicate with local engine: ${err.message}`);
  } finally {
    hideLoading();
  }
});

// 3. Render Results
function renderResults() {
  statsBar.classList.remove('hidden');
  actionToolbar.classList.remove('hidden');
  categoryContainer.classList.remove('hidden');

  statTotalMsgs.textContent = Number(scanData.total_messages).toLocaleString();
  statTotalDomains.textContent = Number(scanData.total_domains).toLocaleString();
  updateSelectionCount();

  categoryContainer.innerHTML = '';
  const cats = scanData.categories;

  for (const [key, cat] of Object.entries(cats)) {
    if (!cat.domains || cat.domains.length === 0) continue;

    const totalCatMsgs = cat.domains.reduce((sum, d) => sum + d.count, 0);

    const card = document.createElement('div');
    card.className = 'category-card card glass';
    card.dataset.category = key;

    card.innerHTML = `
      <div class="category-header">
        <div class="category-title-wrap">
          <input type="checkbox" class="category-master-check" data-cat="${key}">
          <h3>${cat.name}</h3>
          <span class="badge" style="background: rgba(255,255,255,0.06); color: var(--text-muted);">${cat.domains.length} domains · ${totalCatMsgs} msgs</span>
        </div>
        <button class="btn btn-sm btn-outline toggle-cat-btn" data-target="body-${key}">Toggle View</button>
      </div>
      <div class="category-body" id="body-${key}">
        <div class="domain-grid">
          ${cat.domains.map(d => `
            <label class="domain-pill" data-domain="${d.domain.toLowerCase()}">
              <input type="checkbox" class="domain-check" data-cat="${key}" data-domain="${d.domain}">
              <div class="pill-info">
                <span class="domain-name">${escapeHtml(d.domain)}</span>
                <span class="domain-sender">${escapeHtml(d.sample_sender || '')}</span>
              </div>
              <span class="count-badge">${d.count}</span>
            </label>
          `).join('')}
        </div>
      </div>
    `;

    categoryContainer.appendChild(card);
  }

  attachCardEvents();
}

function attachCardEvents() {
  document.querySelectorAll('.domain-check').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const dom = e.target.dataset.domain;
      if (e.target.checked) {
        selectedDomains.add(dom);
      } else {
        selectedDomains.delete(dom);
      }
      syncCategoryMasterCheck(e.target.dataset.cat);
      updateSelectionCount();
    });
  });

  document.querySelectorAll('.category-master-check').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const catKey = e.target.dataset.cat;
      const isChecked = e.target.checked;
      const childChecks = document.querySelectorAll(`.domain-check[data-cat="${catKey}"]`);

      childChecks.forEach(c => {
        const pill = c.closest('.domain-pill');
        if (pill && pill.style.display !== 'none') {
          c.checked = isChecked;
          if (isChecked) {
            selectedDomains.add(c.dataset.domain);
          } else {
            selectedDomains.delete(c.dataset.domain);
          }
        }
      });
      updateSelectionCount();
    });
  });

  document.querySelectorAll('.toggle-cat-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target;
      const body = document.getElementById(targetId);
      if (body) {
        body.classList.toggle('collapsed');
        btn.textContent = body.classList.contains('collapsed') ? 'Expand' : 'Collapse';
      }
    });
  });
}

function syncCategoryMasterCheck(catKey) {
  const master = document.querySelector(`.category-master-check[data-cat="${catKey}"]`);
  if (!master) return;
  const childChecks = Array.from(document.querySelectorAll(`.domain-check[data-cat="${catKey}"]`));
  const checkedCount = childChecks.filter(c => c.checked).length;

  if (checkedCount === 0) {
    master.checked = false;
    master.indeterminate = false;
  } else if (checkedCount === childChecks.length) {
    master.checked = true;
    master.indeterminate = false;
  } else {
    master.checked = false;
    master.indeterminate = true;
  }
}

function updateSelectionCount() {
  const count = selectedDomains.size;
  statSelectedCount.textContent = count;
  deleteCountBadge.textContent = count;
  btnExecuteDelete.disabled = count === 0;
}

// 4. Batch Selection Controls
btnSelectAllSpam.addEventListener('click', () => {
  ['spam_scam', 'ad_marketing'].forEach(catKey => {
    const checks = document.querySelectorAll(`.domain-check[data-cat="${catKey}"]`);
    checks.forEach(c => {
      const pill = c.closest('.domain-pill');
      if (pill && pill.style.display !== 'none') {
        c.checked = true;
        selectedDomains.add(c.dataset.domain);
      }
    });
    syncCategoryMasterCheck(catKey);
  });
  updateSelectionCount();
});

btnSelectAll.addEventListener('click', () => {
  document.querySelectorAll('.domain-check').forEach(c => {
    const pill = c.closest('.domain-pill');
    if (pill && pill.style.display !== 'none') {
      c.checked = true;
      selectedDomains.add(c.dataset.domain);
    }
  });
  document.querySelectorAll('.category-master-check').forEach(m => {
    m.checked = true;
    m.indeterminate = false;
  });
  updateSelectionCount();
});

btnDeselectAll.addEventListener('click', () => {
  document.querySelectorAll('.domain-check').forEach(c => {
    c.checked = false;
  });
  document.querySelectorAll('.category-master-check').forEach(m => {
    m.checked = false;
    m.indeterminate = false;
  });
  selectedDomains.clear();
  updateSelectionCount();
});

// Search Filter
searchInput.addEventListener('input', () => {
  const q = searchInput.value.toLowerCase().trim();
  document.querySelectorAll('.domain-pill').forEach(pill => {
    const d = pill.dataset.domain || '';
    if (d.includes(q)) {
      pill.style.display = '';
    } else {
      pill.style.display = 'none';
    }
  });
});

// 5. Execute Delete
btnExecuteDelete.addEventListener('click', async () => {
  const chosenAccount = customAccountInput.value.trim() || accountSelect.value;
  const mailbox = mailboxSelect.value;
  const domainsList = Array.from(selectedDomains);

  if (domainsList.length === 0) return;

  const confirmMsg = `WARNING: Are you sure you want to delete all emails matching ${domainsList.length} domains from ${chosenAccount} > ${mailbox}?\n\n(Safety: Messages will be moved to Deleted Items / Trash. Check terminal for live progress.)`;
  if (!confirm(confirmMsg)) return;

  showLoading('Deleting Messages...', `Processing ${domainsList.length} domains. Check terminal for real-time progress.`);
  try {
    const res = await fetch('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account: chosenAccount,
        mailbox: mailbox,
        domains: domainsList
      })
    });
    const result = await res.json();

    if (result.success) {
      alert(`Success! Deleted ${result.deleted_count} messages matching ${result.deleted_domains} domains.\nRemaining messages: ${result.new_count ?? 'N/A'}`);
      btnScan.click();
    } else {
      alert(`Delete encountered errors:\n${(result.errors || []).join('\n')}`);
    }
  } catch (err) {
    alert(`Failed to execute deletion: ${err.message}`);
  } finally {
    hideLoading();
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
