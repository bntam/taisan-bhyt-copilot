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
  const filterChips = document.querySelectorAll('.filter-chips .chip');
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
  function sendTabMsgAsync(tabId, msg, opts) {
    return new Promise((resolve) => {
      const cb = (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ __error: chrome.runtime.lastError.message });
        } else {
          resolve(resp || {});
        }
      };
      if (opts) chrome.tabs.sendMessage(tabId, msg, opts, cb);
      else chrome.tabs.sendMessage(tabId, msg, cb);
    });
  }

  btnAutofillCurrentTab.addEventListener('click', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) return;
    currentActiveTabId = tab.id;

    btnAutofillCurrentTab.disabled = true;
    btnAutofillCurrentTab.innerHTML = '<span class="btn-icon">⏳</span> Đang điền bệnh án...';

    let response = await sendTabMsgAsync(tab.id, { type: 'TRIGGER_AUTOFILL' }, { frameId: 0 });
    if (response.__error && tab.url && /^(https?|file):/i.test(tab.url) && chrome.scripting) {
      try {
        await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ['content/content.css'] }).catch(() => {});
        await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content/content.js'] });
        await new Promise(r => setTimeout(r, 250));
        response = await sendTabMsgAsync(tab.id, { type: 'TRIGGER_AUTOFILL' }, { frameId: 0 });
      } catch (_) {}
    }

    btnAutofillCurrentTab.disabled = false;
    if (response && response.filled) {
      btnAutofillCurrentTab.innerHTML = '<span class="btn-icon">✅</span> Đã Điền Bệnh Án HIS!';
      setTimeout(() => {
        btnAutofillCurrentTab.innerHTML = '<span class="btn-icon">⚡</span> 1-Click Điền Bệnh Án Chuẩn BHYT';
        window.close();
      }, 450);
    } else {
      if (response && response.note && navigator.clipboard) {
        try { await navigator.clipboard.writeText(response.note); } catch (_) {}
        btnAutofillCurrentTab.innerHTML = '<span class="btn-icon">📋</span> Đã chép mẫu (Không thấy ô HIS)';
      } else {
        btnAutofillCurrentTab.innerHTML = '<span class="btn-icon">⚠️</span> Không tìm thấy ô bệnh án';
      }
      setTimeout(() => {
        btnAutofillCurrentTab.innerHTML = '<span class="btn-icon">⚡</span> 1-Click Điền Bệnh Án Chuẩn BHYT';
      }, 2400);
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

  function normText(str) {
    return (str || '')
      .toString()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/đ/g, 'd')
      .replace(/Đ/g, 'D')
      .toLowerCase()
      .trim();
  }

  function matchesQuery(fields, rawQ, normQ) {
    if (!rawQ) return true;
    for (const f of fields) {
      if (!f) continue;
      const s = String(f);
      if (s.toLowerCase().includes(rawQ) || normText(s).includes(normQ)) {
        return true;
      }
    }
    return false;
  }

  function renderSearchResults(query) {
    if (!catalog) return;
    const rawQ = (query || '').toLowerCase().trim();
    const normQ = normText(rawQ);
    const results = [];
    const perBucketCap = activeFilter === 'all' ? (rawQ ? 10 : 5) : 40;

    // Search ICD-10
    if (activeFilter === 'all' || activeFilter === 'icd10') {
      if (catalog.icd10) {
        let count = 0;
        for (const item of catalog.icd10) {
          if (matchesQuery([item.code, item.name_vn, item.name_en, item.chapter_name], rawQ, normQ)) {
            results.push({
              type: 'ICD-10',
              typeTag: 'ICD',
              code: item.code,
              name: item.name_vn,
              sub: item.chapter_name || item.name_en || 'Danh mục chuẩn Bộ Y tế'
            });
            count++;
            if (count >= perBucketCap) break;
          }
        }
      }
    }

    // Search Thuốc Tân Dược BHYT
    if (activeFilter === 'all' || activeFilter === 'thuoc') {
      if (catalog.thuoc_bhyt) {
        let count = 0;
        for (const item of catalog.thuoc_bhyt) {
          if (matchesQuery([item.ma_hoat_chat, item.ten_hoat_chat, item.nhom_duoc_ly, item.dieu_kien_thanh_toan, item.ghi_chu_xuat_toan], rawQ, normQ)) {
            results.push({
              type: 'Thuốc Tân Dược',
              typeTag: 'TÂN DƯỢC',
              code: item.ma_hoat_chat,
              name: item.ten_hoat_chat,
              sub: `Tuyến được kê: ${item.hang_bv_duoc_ke} • ĐK: ${item.dieu_kien_thanh_toan || 'Theo hướng dẫn BYT'}`
            });
            count++;
            if (count >= perBucketCap) break;
          }
        }
      }
    }

    // Search Thuốc & Vị YHCT
    if (activeFilter === 'all' || activeFilter === 'yhct') {
      if (catalog.thuoc_yhct) {
        let count = 0;
        for (const item of catalog.thuoc_yhct) {
          if (matchesQuery([item.ma_vi_thuoc, item.ten_vi_thuoc, item.ten_khoa_hoc, item.cong_dung, item.tinh_vi_quy_kinh, item.tuong_tac_tay_y], rawQ, normQ)) {
            results.push({
              type: 'Vị thuốc YHCT',
              typeTag: 'YHCT',
              code: item.ma_vi_thuoc,
              name: item.ten_vi_thuoc,
              sub: `Công dụng: ${item.cong_dung} ${item.tuong_tac_tay_y ? `• ⚠️ ${item.tuong_tac_tay_y}` : ''}`
            });
            count++;
            if (count >= perBucketCap) break;
          }
        }
      }
    }

    // Search Thủ Thuật BHYT
    if (activeFilter === 'all' || activeFilter === 'thu_thuat') {
      if (catalog.thu_thuat_bhyt) {
        let count = 0;
        for (const item of catalog.thu_thuat_bhyt) {
          if (matchesQuery([item.ma_dich_vu, item.ten_dich_vu, item.chuyen_khoa, item.dieu_kien_chi_dinh, item.icd_phu_hop], rawQ, normQ)) {
            results.push({
              type: 'Thủ thuật',
              typeTag: 'KỸ THUẬT',
              code: item.ma_dich_vu,
              name: item.ten_dich_vu,
              sub: `Định mức tối đa: ${item.so_ngay_toi_da} ngày/đợt • ${item.dieu_kien_chi_dinh}`
            });
            count++;
            if (count >= perBucketCap) break;
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

  // 5. Chatbox Q&A Controller
  const popupChatInput = document.getElementById('popupChatInput');
  const popupChatSendBtn = document.getElementById('popupChatSendBtn');
  const popupChatMessages = document.getElementById('popupChatMessages');

  function sendPopupChatMessage(q) {
    if (!q) return;
    if (popupChatInput) popupChatInput.value = '';

    // Append user message
    const userDiv = document.createElement('div');
    userDiv.className = 'popup-chat-msg user';
    userDiv.style.cssText = 'background:#0284c7; color:#fff; align-self:flex-end; border-radius:8px; padding:8px 12px; font-size:12px; margin-bottom:4px; max-width:85%;';
    userDiv.textContent = q;
    popupChatMessages.appendChild(userDiv);
    popupChatMessages.scrollTop = popupChatMessages.scrollHeight;

    // Send to background service worker with active tab context
    const currentIcd = auditIcdCode ? auditIcdCode.textContent : '';
    chrome.runtime.sendMessage({
      type: 'ASK_CHAT_COPILOT',
      payload: { 
        query: q, 
        context: { 
          hospital_level: '4',
          icdCode: currentIcd && currentIcd !== 'Chưa nhận diện' ? currentIcd : ''
        } 
      }
    }, (resp) => {
      const botDiv = document.createElement('div');
      botDiv.className = 'popup-chat-msg assistant';
      botDiv.style.cssText = 'background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px; font-size:12px; line-height:1.45; align-self:flex-start; margin-bottom:4px; max-width:92%;';

      if (resp && resp.success && resp.data) {
        const d = resp.data;
        const formatted = d.answer
          .replace(/### (.*?)\n/g, '<strong style="display:block;margin-bottom:4px;color:#0f172a;">$1</strong>')
          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
          .replace(/\n\n/g, '<div style="height:6px;"></div>')
          .replace(/\n/g, '<br>');
        
        let snippetHtml = '';
        if (d.suggested_snippet) {
          snippetHtml = `
            <div style="background:#f1f5f9;border-left:3px solid #0284c7;padding:6px;border-radius:4px;margin-top:6px;font-family:monospace;font-size:11px;">
              ${d.suggested_snippet}
            </div>
            <div style="display:flex; gap:6px; margin-top:6px;">
              <button class="btn-snippet-copy" style="background:#0284c7;color:#fff;border:none;border-radius:4px;padding:4px 8px;font-size:11px;cursor:pointer;flex:1;">
                📋 Sao Chép
              </button>
              <button class="btn-snippet-inject" style="background:#0d9488;color:#fff;border:none;border-radius:4px;padding:4px 8px;font-size:11px;cursor:pointer;flex:1;">
                ⚡ Điền Vào HIS
              </button>
            </div>
          `;
        }
        botDiv.innerHTML = formatted + snippetHtml;

        const copyBtn = botDiv.querySelector('.btn-snippet-copy');
        if (copyBtn) {
          copyBtn.onclick = () => {
            navigator.clipboard.writeText(d.suggested_snippet);
            copyBtn.textContent = '✅ Đã Chép!';
            setTimeout(() => copyBtn.textContent = '📋 Sao Chép', 2000);
          };
        }

        const injectBtn = botDiv.querySelector('.btn-snippet-inject');
        if (injectBtn) {
          injectBtn.onclick = () => {
            if (currentActiveTabId) {
              chrome.tabs.sendMessage(currentActiveTabId, {
                type: 'INJECT_SNIPPET',
                snippet: d.suggested_snippet
              }, (injResp) => {
                injectBtn.textContent = '✅ Đã Điền HIS!';
                setTimeout(() => injectBtn.textContent = '⚡ Điền Vào HIS', 2000);
              });
            } else {
              injectBtn.textContent = '⚠️ Mở Tab HIS';
            }
          };
        }
      } else {
        botDiv.textContent = '⚠️ ' + (resp?.error || 'Không thể kết nối bộ giải đáp lâm sàng.');
      }
      popupChatMessages.appendChild(botDiv);
      popupChatMessages.scrollTop = popupChatMessages.scrollHeight;
    });
  }

  if (popupChatSendBtn && popupChatInput) {
    popupChatSendBtn.addEventListener('click', () => sendPopupChatMessage(popupChatInput.value.trim()));
    popupChatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendPopupChatMessage(popupChatInput.value.trim());
    });
  }

  document.querySelectorAll('[data-chat-q]').forEach(btn => {
    btn.addEventListener('click', () => sendPopupChatMessage(btn.dataset.chatQ));
  });

  // 6. Settings & Statistics
  const POPUP_LLM_PRESETS = {
    openai_compat: { url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
    openrouter: { url: 'https://openrouter.ai/api/v1', model: 'anthropic/claude-3.5-sonnet' },
    gemini: { url: 'https://generativelanguage.googleapis.com/v1beta', model: 'gemini-2.5-flash' },
    anthropic: { url: 'https://api.anthropic.com/v1', model: 'claude-sonnet-4-20250514' },
    deepseek: { url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
    groq: { url: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile' },
    ollama: { url: 'http://127.0.0.1:11434/v1', model: 'qwen2.5:14b' }
  };

  const popupLlmToggle = document.getElementById('popupLlmToggle');
  const popupLlmProvider = document.getElementById('popupLlmProvider');
  const popupLlmUrl = document.getElementById('popupLlmUrl');
  const popupLlmModel = document.getElementById('popupLlmModel');
  const popupLlmKey = document.getElementById('popupLlmKey');
  const popupBtnSaveLlm = document.getElementById('popupBtnSaveLlm');

  async function loadSettingsAndStats() {
    chrome.runtime.sendMessage({ type: 'GET_CONFIG' }, (resp) => {
      if (resp && resp.config) {
        const cfg = resp.config;
        statAudits.textContent = cfg.stats?.total_audits || 0;
        statPrevented.textContent = cfg.stats?.warnings_prevented || 0;
        statAutofilled.textContent = cfg.stats?.notes_autofilled || 0;

        cfgAutoAudit.checked = cfg.auto_audit_enabled !== false;
        cfgHerbCheck.checked = cfg.herb_drug_check_enabled !== false;

        const llm = cfg.llm_config || {};
        if (popupLlmToggle) popupLlmToggle.checked = Boolean(llm.enabled);
        if (popupLlmProvider && llm.provider) popupLlmProvider.value = llm.provider;
        if (popupLlmUrl) popupLlmUrl.value = llm.api_url || (POPUP_LLM_PRESETS[popupLlmProvider?.value || 'openai_compat']?.url || '');
        if (popupLlmModel) popupLlmModel.value = llm.model || (POPUP_LLM_PRESETS[popupLlmProvider?.value || 'openai_compat']?.model || '');
        if (popupLlmKey) popupLlmKey.value = llm.api_key || '';
      }
    });
  }

  if (popupLlmProvider) {
    popupLlmProvider.addEventListener('change', () => {
      const preset = POPUP_LLM_PRESETS[popupLlmProvider.value];
      if (preset) {
        if (popupLlmUrl) popupLlmUrl.value = preset.url;
        if (popupLlmModel) popupLlmModel.value = preset.model;
      }
    });
  }

  if (popupBtnSaveLlm) {
    popupBtnSaveLlm.addEventListener('click', () => {
      const newLlm = {
        enabled: Boolean(popupLlmToggle?.checked),
        provider: popupLlmProvider?.value || 'openai_compat',
        api_url: popupLlmUrl?.value.trim() || '',
        api_key: popupLlmKey?.value.trim() || '',
        model: popupLlmModel?.value.trim() || ''
      };
      chrome.runtime.sendMessage({
        type: 'UPDATE_CONFIG',
        payload: { llm_config: newLlm }
      }, (resp) => {
        popupBtnSaveLlm.textContent = '✅ Đã Lưu Cài Đặt!';
        setTimeout(() => { popupBtnSaveLlm.textContent = '💾 Lưu Cài Đặt AI'; }, 2000);
      });
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
