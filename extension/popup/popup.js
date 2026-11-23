/**
 * BHYT Clinical Copilot - Popup Script
 * Real-time HIS Audit Display, Catalog Search & Configuration
 */

(function () {
  'use strict';

  let catalog = null;
  let currentActiveTabId = null;
  let activeFilter = 'all';
  let searchDebounceTimer = null;

  // DOM Elements
  const tabs = document.querySelectorAll('.nav-tab');
  const tabContents = document.querySelectorAll('.tab-content');

  // Audit Tab Elements
  const headerStatusDot = document.getElementById('headerStatusDot');
  const headerStatusLabel = document.getElementById('headerStatusLabel');
  const auditIcdCode = document.getElementById('auditIcdCode');
  const auditIcdName = document.getElementById('auditIcdName');
  const auditRiskBadge = document.getElementById('auditRiskBadge');
  const auditProcCount = document.getElementById('auditProcCount');
  const auditDrugCount = document.getElementById('auditDrugCount');
  const auditProcDays = document.getElementById('auditProcDays');
  const alertsList = document.getElementById('alertsList');
  const alertCounter = document.getElementById('alertCounter');
  const btnAutofillCurrentTab = document.getElementById('btnAutofillCurrentTab');

  // Search Tab Elements
  const searchInput = document.getElementById('searchInput');
  const searchClearBtn = document.getElementById('searchClearBtn');
  const filterChips = document.querySelectorAll('.chip');
  const searchResultsList = document.getElementById('searchResultsList');

  // Settings Tab Elements
  const statAudits = document.getElementById('statAudits');
  const statPrevented = document.getElementById('statPrevented');
  const statAutofilled = document.getElementById('statAutofilled');
  const cfgAutoAudit = document.getElementById('cfgAutoAudit');
  const cfgHerbCheck = document.getElementById('cfgHerbCheck');
  const btnOpenSimulator = document.getElementById('btnOpenSimulator');

  // 1. Tab Navigation
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      tabs.forEach(t => t.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));

      tab.classList.add('active');
      const targetContent = document.getElementById(target);
      if (targetContent) targetContent.classList.add('active');

      if (target === 'tab-search' && !catalog) {
        loadCatalogData();
      } else if (target === 'tab-settings') {
        loadSettingsAndStats();
      }
    });
  });

  // 2. Load Live Audit Data from Active Tab
  async function loadActiveAudit() {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) return;
      currentActiveTabId = tab.id;

      // First query content script directly for live DOM state
      chrome.tabs.sendMessage(tab.id, { type: 'GET_DOM_STATE' }, (response) => {
        if (chrome.runtime.lastError || !response || !response.audit) {
          // Fallback to service worker stored state
          chrome.runtime.sendMessage({ type: 'GET_CURRENT_AUDIT', tabId: tab.id }, (swResp) => {
            if (swResp && swResp.data) {
              renderAuditUI(swResp.data);
            } else {
              renderEmptyAuditUI();
            }
          });
        } else {
          renderAuditUI(response.audit);
        }
      });
    } catch (err) {
      console.error('[Popup] Error loading audit:', err);
      renderEmptyAuditUI();
    }
  }

  function renderAuditUI(audit) {
    if (!audit || (!audit.icdCode && (!audit.alerts || audit.alerts.length === 0))) {
      renderEmptyAuditUI();
      return;
    }

    const highRisk = audit.highRiskCount || (audit.alerts ? audit.alerts.filter(a => a.severity === 'HIGH').length : 0);
    const totalAlerts = audit.alertCount !== undefined ? audit.alertCount : (audit.alerts ? audit.alerts.length : 0);

    // Header Status Dot
    headerStatusDot.className = 'status-dot ' + (highRisk > 0 ? 'dot-danger' : 'dot-pass');
    headerStatusLabel.textContent = highRisk > 0 ? `${highRisk} nguy cơ xuất toán` : (totalAlerts > 0 ? `${totalAlerts} lưu ý` : 'Hồ sơ hợp lệ');

    // ICD Box
    auditIcdCode.textContent = audit.icdCode || 'Chưa nhận diện';
    auditIcdName.textContent = audit.diseaseName || 'Không tìm thấy tên bệnh chuẩn';

    // Risk Badge
    if (highRisk > 0) {
      auditRiskBadge.className = 'risk-badge badge-danger';
      auditRiskBadge.textContent = '⚠️ NGUY CƠ CAO';
    } else if (totalAlerts > 0) {
      auditRiskBadge.className = 'risk-badge';
      auditRiskBadge.style.background = '#fef3c7';
      auditRiskBadge.style.color = '#d97706';
      auditRiskBadge.textContent = 'CẦN LƯU Ý';
    } else {
      auditRiskBadge.className = 'risk-badge badge-pass';
      auditRiskBadge.textContent = '🟢 HỢP LỆ';
    }

    // Meta Numbers
    auditProcCount.textContent = audit.procedures ? audit.procedures.length : 0;
    auditDrugCount.textContent = audit.drugs ? audit.drugs.length : 0;
    auditProcDays.textContent = audit.procedureDays || 1;

    // Counter
    alertCounter.textContent = `${totalAlerts} cảnh báo`;

    // Alerts List
    if (!audit.alerts || audit.alerts.length === 0) {
      alertsList.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">🛡️</span>
          <p><strong>Hồ sơ chuẩn chỉ BHYT!</strong><br>Chỉ định thuốc và thủ thuật hoàn toàn phù hợp với tuyến chuyên môn kỹ thuật phòng khám.</p>
        </div>
      `;
    } else {
      alertsList.innerHTML = audit.alerts.map(a => `
        <div class="popup-alert-card ${a.severity}">
          <div class="popup-alert-card-title">${a.severity === 'HIGH' ? '⚠️ XUẤT TOÁN 100%' : 'ℹ️ LƯU Ý'}: ${a.title}</div>
          <div class="popup-alert-card-desc">${a.detail}</div>
          ${a.remedy ? `<div class="popup-alert-card-remedy">👉 Giải pháp: ${a.remedy}</div>` : ''}
        </div>
      `).join('');
    }
  }

  function renderEmptyAuditUI() {
    headerStatusDot.className = 'status-dot';
    headerStatusLabel.textContent = 'Chờ dữ liệu HIS';
    auditIcdCode.textContent = 'Chưa nhận diện';
    auditIcdName.textContent = 'Mở tab có form bệnh án HIS để kích hoạt giám sát';
    auditRiskBadge.className = 'risk-badge badge-neutral';
    auditRiskBadge.textContent = 'CHỜ DỮ LIỆU';
    auditProcCount.textContent = '0';
    auditDrugCount.textContent = '0';
    auditProcDays.textContent = '1';
    alertCounter.textContent = '0 cảnh báo';
    alertsList.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">🩺</span>
        <p>BHYT Clinical Copilot đang lắng nghe DOM.<br>Khi bạn chọn mã ICD hoặc kê đơn trên HIS, hệ thống sẽ kiểm tra tự động tức thì.</p>
      </div>
    `;
  }

  // 3. 1-Click Autofill Trigger
  btnAutofillCurrentTab.addEventListener('click', async () => {
    if (!currentActiveTabId) {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab) currentActiveTabId = tab.id;
    }

    if (currentActiveTabId) {
      btnAutofillCurrentTab.disabled = true;
      btnAutofillCurrentTab.innerHTML = '<span class="btn-icon">⏳</span> Đang điền bệnh án...';

      chrome.tabs.sendMessage(currentActiveTabId, { type: 'TRIGGER_AUTOFILL' }, (response) => {
        setTimeout(() => {
          btnAutofillCurrentTab.disabled = false;
          btnAutofillCurrentTab.innerHTML = '<span class="btn-icon">⚡</span> 1-Click Điền Bệnh Án Chuẩn BHYT';
          window.close(); // Close popup so user sees the filled textarea
        }, 300);
      });
    }
  });

  // 4. Catalog Search Engine
  async function loadCatalogData() {
    if (catalog) return;
    try {
      searchResultsList.innerHTML = '<div class="search-placeholder">Đang tải danh mục BHYT...</div>';
      const url = chrome.runtime.getURL('data/catalog.json');
      const resp = await fetch(url);
      catalog = await resp.json();
      renderSearchResults('');
    } catch (err) {
      searchResultsList.innerHTML = '<div class="search-placeholder text-danger">Lỗi nạp danh mục: ' + err.message + '</div>';
    }
  }

  filterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      filterChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter;
      renderSearchResults(searchInput.value.trim());
    });
  });

  searchInput.addEventListener('input', () => {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      renderSearchResults(searchInput.value.trim());
    }, 200);
  });

  searchClearBtn.addEventListener('click', () => {
    searchInput.value = '';
    renderSearchResults('');
    searchInput.focus();
  });

  function renderSearchResults(query) {
    if (!catalog) return;
    const q = query.toLowerCase();
    const results = [];
    const limit = 30;

    // Search ICD-10
    if (activeFilter === 'all' || activeFilter === 'icd10') {
      if (catalog.icd10) {
        for (const item of catalog.icd10) {
          if (!q || item.code.toLowerCase().includes(q) || item.name_vn.toLowerCase().includes(q) || (item.name_en && item.name_en.toLowerCase().includes(q))) {
            results.push({
              type: 'ICD-10',
              typeTag: 'ICD',
              code: item.code,
              name: item.name_vn,
              sub: item.chapter_name || item.name_en || 'Danh mục chuẩn Bộ Y tế'
            });
            if (results.length >= limit) break;
          }
        }
      }
    }

    // Search Thuốc Tân Dược BHYT
    if ((activeFilter === 'all' || activeFilter === 'thuoc') && results.length < limit) {
      if (catalog.thuoc_bhyt) {
        for (const item of catalog.thuoc_bhyt) {
          if (!q || item.ten_hoat_chat.toLowerCase().includes(q) || (item.ghi_chu_xuat_toan && item.ghi_chu_xuat_toan.toLowerCase().includes(q))) {
            results.push({
              type: 'Thuốc Tân Dược',
              typeTag: 'TÂN DƯỢC',
              code: item.ma_hoat_chat,
              name: item.ten_hoat_chat,
              sub: `Tuyến được kê: ${item.hang_bv_duoc_ke} • ĐK: ${item.dieu_kien_thanh_toan || 'Theo hướng dẫn BYT'}`
            });
            if (results.length >= limit) break;
          }
        }
      }
    }

    // Search Thuốc & Vị YHCT
    if ((activeFilter === 'all' || activeFilter === 'yhct') && results.length < limit) {
      if (catalog.thuoc_yhct) {
        for (const item of catalog.thuoc_yhct) {
          if (!q || item.ten_vi_thuoc.toLowerCase().includes(q) || (item.cong_dung && item.cong_dung.toLowerCase().includes(q))) {
            results.push({
              type: 'Vị thuốc YHCT',
              typeTag: 'YHCT',
              code: item.ma_vi_thuoc,
              name: item.ten_vi_thuoc,
              sub: `Công dụng: ${item.cong_dung} ${item.tuong_tac_tay_y ? `• ⚠️ ${item.tuong_tac_tay_y}` : ''}`
            });
            if (results.length >= limit) break;
          }
        }
      }
    }

    // Search Thủ Thuật BHYT
    if ((activeFilter === 'all' || activeFilter === 'thu_thuat') && results.length < limit) {
      if (catalog.thu_thuat_bhyt) {
        for (const item of catalog.thu_thuat_bhyt) {
          if (!q || item.ten_dich_vu.toLowerCase().includes(q) || (item.dieu_kien_chi_dinh && item.dieu_kien_chi_dinh.toLowerCase().includes(q))) {
            results.push({
              type: 'Thủ thuật',
              typeTag: 'KỸ THUẬT',
              code: item.ma_dich_vu,
              name: item.ten_dich_vu,
              sub: `Định mức tối đa: ${item.so_ngay_toi_da} ngày/đợt • ${item.dieu_kien_chi_dinh}`
            });
            if (results.length >= limit) break;
          }
        }
      }
    }

    if (results.length === 0) {
      searchResultsList.innerHTML = `
        <div class="search-placeholder">
          Không tìm thấy kết quả nào phù hợp với từ khóa "${query}".
        </div>
      `;
      return;
    }

    searchResultsList.innerHTML = results.map(r => `
      <div class="search-result-card">
        <div class="search-result-header">
          <span class="search-code">${r.code}</span>
          <span class="search-type-tag">${r.typeTag}</span>
        </div>
        <div class="search-name">${r.name}</div>
        <div class="search-sub">${r.sub}</div>
      </div>
    `).join('');
  }

  // 5. Settings & Statistics
  async function loadSettingsAndStats() {
    chrome.runtime.sendMessage({ type: 'GET_CONFIG' }, (resp) => {
      if (resp && resp.config) {
        const cfg = resp.config;
        statAudits.textContent = cfg.stats?.total_audits || 0;
        statPrevented.textContent = cfg.stats?.warnings_prevented || 0;
        statAutofilled.textContent = cfg.stats?.notes_autofilled || 0;

        cfgAutoAudit.checked = cfg.auto_audit_enabled !== false;
        cfgHerbCheck.checked = cfg.herb_drug_check_enabled !== false;
      }
    });
  }

  cfgAutoAudit.addEventListener('change', () => {
    chrome.runtime.sendMessage({
      type: 'UPDATE_CONFIG',
      payload: { auto_audit_enabled: cfgAutoAudit.checked }
    });
  });

  cfgHerbCheck.addEventListener('change', () => {
    chrome.runtime.sendMessage({
      type: 'UPDATE_CONFIG',
      payload: { herb_drug_check_enabled: cfgHerbCheck.checked }
    });
  });

  btnOpenSimulator.addEventListener('click', () => {
    chrome.tabs.create({ url: chrome.runtime.getURL('test_bed.html') });
  });

  // Initial Boot
  loadActiveAudit();
})();
