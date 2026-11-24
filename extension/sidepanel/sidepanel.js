/**
 * BHYT Clinical Copilot - Chrome Side Panel Controller (v2.0)
 * Persistent in-browser companion for Hospital Information Systems (HIS).
 */

(function () {
  'use strict';

  let currentTabId = null;
  let currentAudit = null;
  let activeTier = '4';
  let tierSource = 'Tự động';
  let catalog = null;

  // DOM Elements
  const spFacilityName = document.getElementById('spFacilityName');
  const spGlobalStatus = document.getElementById('spGlobalStatus');
  const spTierSourceTag = document.getElementById('spTierSourceTag');
  const tierButtons = document.querySelectorAll('.sp-tier-btn');
  const spIcdTag = document.getElementById('spIcdTag');
  const spIcdName = document.getElementById('spIcdName');
  const spProcCount = document.getElementById('spProcCount');
  const spDrugCount = document.getElementById('spDrugCount');
  const spAlertCount = document.getElementById('spAlertCount');
  const spAuditBadge = document.getElementById('spAuditBadge');
  const spAlertsList = document.getElementById('spAlertsList');
  const spBtnAutofill = document.getElementById('spBtnAutofill');

  const navTabButtons = document.querySelectorAll('.sp-tab-btn');
  const tabContents = document.querySelectorAll('.sp-tab-content');

  const spChatMessages = document.getElementById('spChatMessages');
  const spChatInput = document.getElementById('spChatInput');
  const spChatSendBtn = document.getElementById('spChatSendBtn');
  const promptChips = document.querySelectorAll('.sp-prompt-chip');

  const spSearchInput = document.getElementById('spSearchInput');
  const spSearchResults = document.getElementById('spSearchResults');
  const filterButtons = document.querySelectorAll('.sp-filter-btn');

  // 1. Navigation Tabs
  navTabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      navTabButtons.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const targetEl = document.getElementById(target);
      if (targetEl) targetEl.classList.add('active');
    });
  });

  // 2. Hospital Tier Override Handler
  tierButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const selectedTier = btn.dataset.tier;
      setHospitalTier(selectedTier, 'Chọn thủ công');
    });
  });

  function setHospitalTier(tier, source) {
    activeTier = tier;
    tierSource = source;
    tierButtons.forEach(b => {
      b.className = 'sp-tier-btn';
      if (b.dataset.tier === tier) {
        b.classList.add('active', `tier-${tier}`);
      }
    });

    if (spTierSourceTag) {
      spTierSourceTag.textContent = `${source} (Tuyến ${tier})`;
    }

    // Persist tier in storage
    chrome.storage.local.set({ activeHospitalTier: tier, tierSource: source });

    // Notify active tab to re-run audit with new tier
    if (currentTabId) {
      chrome.tabs.sendMessage(currentTabId, {
        type: 'SET_HOSPITAL_TIER',
        tier: tier
      }, (resp) => {
        if (resp && resp.audit) {
          renderAudit(resp.audit);
        }
      });
    }

    // Notify chat system of tier switch
    appendChatMessage('assistant', `ℹ️ **Hệ thống:** Đã chuyển phân tuyến chuyên môn kỹ thuật sang **TUYẾN ${tier}**. Mọi quy tắc kê đơn và xuất toán thuốc sẽ được đối chiếu theo danh mục Tuyến ${tier}.`);
  }

  // 3. Connect to Active Tab and Sync Audit State
  async function connectActiveTab() {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) return;
      currentTabId = tab.id;

      // Query content script for live audit state
      chrome.tabs.sendMessage(tab.id, { type: 'GET_DOM_STATE' }, (resp) => {
        if (chrome.runtime.lastError || !resp || !resp.audit) {
          // Fallback to service worker storage
          chrome.runtime.sendMessage({ type: 'GET_CURRENT_AUDIT', tabId: tab.id }, (swResp) => {
            if (swResp && swResp.data) {
              renderAudit(swResp.data);
            }
          });
        } else {
          renderAudit(resp.audit);
          if (resp.facility) {
            spFacilityName.textContent = resp.facility.name || 'Cơ sở KCB BHYT';
            if (resp.facility.tier && tierSource !== 'Chọn thủ công') {
              setHospitalTier(resp.facility.tier, resp.facility.source || 'Tự động');
            }
          }
        }
      });
    } catch (e) {
      console.error('[SidePanel Connect Error]', e);
    }
  }

  // 4. Render Live Audit Results
  function renderAudit(audit) {
    if (!audit) return;
    currentAudit = audit;

    // ICD & Disease
    if (spIcdTag) spIcdTag.textContent = audit.icdCode || 'Chưa có';
    if (spIcdName) spIcdName.textContent = audit.diseaseName || 'Mở phần mềm HIS để quét hồ sơ';

    // Counts
    if (spProcCount) spProcCount.textContent = (audit.procedures || []).length;
    if (spDrugCount) spDrugCount.textContent = (audit.drugs || []).length;

    const highRisk = audit.highRiskCount || 0;
    const totalAlerts = audit.alertCount || (audit.alerts ? audit.alerts.length : 0);

    if (spAlertCount) spAlertCount.textContent = `${totalAlerts} cảnh báo`;
    if (spAuditBadge) {
      spAuditBadge.textContent = totalAlerts;
      spAuditBadge.style.display = totalAlerts > 0 ? 'inline-block' : 'none';
    }

    if (spGlobalStatus) {
      if (highRisk > 0) {
        spGlobalStatus.className = 'sp-status-badge status-danger';
        spGlobalStatus.textContent = `${highRisk} XUẤT TOÁN`;
      } else if (totalAlerts > 0) {
        spGlobalStatus.className = 'sp-status-badge status-warning';
        spGlobalStatus.textContent = 'CẦN LƯU Ý';
      } else {
        spGlobalStatus.className = 'sp-status-badge status-pass';
        spGlobalStatus.textContent = 'HỢP LỆ 100%';
      }
    }

    // Render alert cards
    if (spAlertsList) {
      if (!audit.alerts || audit.alerts.length === 0) {
        spAlertsList.innerHTML = `
          <div class="sp-alert-card severity-PASS">
            <div class="sp-alert-title">🟢 Hồ sơ đạt chuẩn BHYT</div>
            <div class="sp-alert-desc">Không phát hiện nguy cơ xuất toán. Danh mục thuốc và thủ thuật phù hợp với phân tuyến chuyên môn kỹ thuật.</div>
          </div>
        `;
      } else {
        spAlertsList.innerHTML = audit.alerts.map(a => `
          <div class="sp-alert-card severity-${a.severity}">
            <div class="sp-alert-title">${a.severity === 'HIGH' ? '🚨 XUẤT TOÁN 100%' : 'ℹ️ LƯU Ý BHYT'}: ${a.title}</div>
            <div class="sp-alert-desc">${a.detail}</div>
            ${a.remedy ? `<div class="sp-alert-remedy">👉 Giải pháp: ${a.remedy}</div>` : ''}
          </div>
        `).join('');
      }
    }
  }

  // 5. 1-Click Autofill Trigger
  if (spBtnAutofill) {
    spBtnAutofill.addEventListener('click', () => {
      if (!currentTabId) return;
      chrome.tabs.sendMessage(currentTabId, { type: 'TRIGGER_AUTOFILL' }, (resp) => {
        spBtnAutofill.innerHTML = '<span>✅</span> Đã Điền Bệnh Án HIS!';
        setTimeout(() => {
          spBtnAutofill.innerHTML = '<span>⚡</span> 1-Click Điền Bệnh Án Chuẩn BHYT';
        }, 2200);
      });
    });
  }

  // 6. Hybrid RAG + Live LLM Chat System
  function appendChatMessage(sender, text, snippet) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `sp-msg ${sender}`;

    const formatted = (text || '')
      .replace(/### (.*?)\n/g, '<strong style="display:block;margin-bottom:4px;color:#0f172a;">$1</strong>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n\n/g, '<div style="height:6px;"></div>')
      .replace(/\n/g, '<br>');

    let snippetHtml = '';
    if (snippet) {
      snippetHtml = `
        <div class="sp-snippet-block">${snippet}</div>
        <button class="sp-btn-inject-snippet">⚡ Điền Vào Bệnh Án HIS</button>
      `;
    }

    msgDiv.innerHTML = `
      <div class="sp-msg-header">
        <span>${sender === 'user' ? '👨‍⚕️ Bác Sĩ' : '🩺 Copilot'}</span>
      </div>
      <div class="sp-msg-body">${formatted}${snippetHtml}</div>
    `;

    const injectBtn = msgDiv.querySelector('.sp-btn-inject-snippet');
    if (injectBtn && snippet) {
      injectBtn.onclick = () => {
        if (currentTabId) {
          chrome.tabs.sendMessage(currentTabId, { type: 'INJECT_SNIPPET', snippet }, (res) => {
            injectBtn.textContent = '✅ Đã Điền Vào HIS!';
            setTimeout(() => injectBtn.textContent = '⚡ Điền Vào Bệnh Án HIS', 2000);
          });
        }
      };
    }

    spChatMessages.appendChild(msgDiv);
    spChatMessages.scrollTop = spChatMessages.scrollHeight;
  }

  function sendChatMessage(query) {
    if (!query) return;
    if (spChatInput) spChatInput.value = '';

    appendChatMessage('user', query);

    // Context payload
    const ctx = {
      hospital_level: activeTier,
      icdCode: currentAudit ? currentAudit.icdCode : '',
      drugs: currentAudit ? currentAudit.drugs : [],
      procedures: currentAudit ? currentAudit.procedures : [],
      procedureDays: currentAudit ? currentAudit.procedureDays : 1
    };

    chrome.runtime.sendMessage({
      type: 'ASK_CHAT_COPILOT',
      payload: { query, context: ctx }
    }, (resp) => {
      if (resp && resp.success && resp.data) {
        appendChatMessage('assistant', resp.data.answer, resp.data.suggested_snippet);
      } else {
        appendChatMessage('assistant', '⚠️ ' + (resp?.error || 'Không thể kết nối bộ giải đáp lâm sàng.'));
      }
    });
  }

  if (spChatSendBtn && spChatInput) {
    spChatSendBtn.addEventListener('click', () => sendChatMessage(spChatInput.value.trim()));
    spChatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendChatMessage(spChatInput.value.trim());
    });
  }

  // Quick Prompt Chips with Dynamic Context Interpolation
  promptChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const template = chip.dataset.q;
      const icd = (currentAudit && currentAudit.icdCode) ? currentAudit.icdCode : 'M54.5';
      const q = template.replace('{icd}', icd).replace('{tier}', activeTier);
      sendChatMessage(q);
    });
  });

  // 7. Catalog Search
  async function loadCatalog() {
    try {
      const url = chrome.runtime.getURL('data/catalog.json');
      const resp = await fetch(url);
      catalog = await resp.json();
    } catch (e) {
      console.warn('[SidePanel] Local catalog json fetch error:', e);
    }
  }

  if (spSearchInput) {
    spSearchInput.addEventListener('input', () => {
      const q = spSearchInput.value.toLowerCase().trim();
      if (!q || !catalog) {
        spSearchResults.innerHTML = '<div class="sp-search-empty">Nhập mã bệnh hoặc tên thuốc/vị thuốc để tra cứu tức thì...</div>';
        return;
      }

      const results = [];
      // ICD-10
      (catalog.icd10 || []).forEach(i => {
        if (i.code.toLowerCase().includes(q) || (i.name_vn && i.name_vn.toLowerCase().includes(q))) {
          results.push({ type: 'ICD-10', code: i.code, name: i.name_vn, sub: i.chapter_name });
        }
      });
      // Thuốc
      (catalog.thuoc_bhyt || []).forEach(d => {
        if (d.ten_hoat_chat.toLowerCase().includes(q)) {
          results.push({ type: 'Thuốc Tân Dược', code: `Tuyến ${d.hang_bv_duoc_ke}`, name: d.ten_hoat_chat, sub: `Thanh toán ${d.ty_le_thanh_toan}%` });
        }
      });
      // YHCT
      (catalog.thuoc_yhct || []).forEach(h => {
        if (h.ten_vi_thuoc.toLowerCase().includes(q)) {
          results.push({ type: 'Vị Thuốc YHCT', code: 'YHCT', name: h.ten_vi_thuoc, sub: h.tuong_tac_tay_y || h.cong_dung });
        }
      });

      if (results.length === 0) {
        spSearchResults.innerHTML = '<div class="sp-search-empty">Không tìm thấy kết quả nào phù hợp.</div>';
      } else {
        spSearchResults.innerHTML = results.slice(0, 20).map(r => `
          <div class="sp-alert-card severity-PASS" style="padding:6px 10px;">
            <div style="display:flex;justify-content:space-between;font-size:11px;font-weight:700;color:#0369a1;">
              <span>${r.code}</span><span>${r.type}</span>
            </div>
            <div style="font-weight:600;font-size:12px;margin:2px 0;">${r.name}</div>
            <div style="font-size:11px;color:#64748b;">${r.sub || ''}</div>
          </div>
        `).join('');
      }
    });
  }

  // Listen to live broadcast updates from content script
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'AUDIT_STATUS_CHANGED') {
      renderAudit(msg.payload);
    }
  });

  const spBtnOpenTestBed = document.getElementById('spBtnOpenTestBed');
  if (spBtnOpenTestBed) {
    spBtnOpenTestBed.addEventListener('click', () => {
      chrome.tabs.create({ url: chrome.runtime.getURL('test_bed.html') });
    });
  }

  // 8. BYOK Live LLM Settings Controller
  const LLM_PRESETS = {
    openai_compat: { url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
    openrouter: { url: 'https://openrouter.ai/api/v1', model: 'anthropic/claude-3.5-sonnet' },
    gemini: { url: 'https://generativelanguage.googleapis.com/v1beta', model: 'gemini-2.5-flash' },
    anthropic: { url: 'https://api.anthropic.com/v1', model: 'claude-sonnet-4-20250514' },
    deepseek: { url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
    groq: { url: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile' },
    ollama: { url: 'http://127.0.0.1:11434/v1', model: 'qwen2.5:14b' }
  };

  const spLlmToggle = document.getElementById('spLlmToggle');
  const spLlmToggleTrack = document.getElementById('spLlmToggleTrack');
  const spLlmProvider = document.getElementById('spLlmProvider');
  const spLlmBaseUrl = document.getElementById('spLlmBaseUrl');
  const spLlmApiKey = document.getElementById('spLlmApiKey');
  const spBtnToggleKeyView = document.getElementById('spBtnToggleKeyView');
  const spLlmModel = document.getElementById('spLlmModel');
  const spBtnTestLlm = document.getElementById('spBtnTestLlm');
  const spBtnSaveLlm = document.getElementById('spBtnSaveLlm');
  const spLlmStatusBox = document.getElementById('spLlmStatusBox');

  function updateToggleTrack(checked) {
    if (spLlmToggleTrack) {
      spLlmToggleTrack.style.backgroundColor = checked ? '#0284c7' : '#cbd5e1';
    }
  }

  // Load saved LLM config
  async function loadLlmSettings() {
    try {
      const { config } = await chrome.storage.local.get('config');
      const llm = config?.llm_config || {};
      if (spLlmToggle) {
        spLlmToggle.checked = Boolean(llm.enabled);
        updateToggleTrack(spLlmToggle.checked);
      }
      if (spLlmProvider && llm.provider) spLlmProvider.value = llm.provider;
      if (spLlmBaseUrl) spLlmBaseUrl.value = llm.api_url || (LLM_PRESETS[spLlmProvider?.value || 'openai_compat']?.url || '');
      if (spLlmApiKey) spLlmApiKey.value = llm.api_key || '';
      if (spLlmModel) spLlmModel.value = llm.model || (LLM_PRESETS[spLlmProvider?.value || 'openai_compat']?.model || '');
    } catch (e) {
      console.warn('[SidePanel] Could not load LLM settings:', e);
    }
  }

  if (spLlmToggle) {
    spLlmToggle.addEventListener('change', () => {
      updateToggleTrack(spLlmToggle.checked);
    });
  }

  if (spLlmProvider) {
    spLlmProvider.addEventListener('change', () => {
      const preset = LLM_PRESETS[spLlmProvider.value];
      if (preset) {
        if (spLlmBaseUrl) spLlmBaseUrl.value = preset.url;
        if (spLlmModel) spLlmModel.value = preset.model;
      }
    });
  }

  if (spBtnToggleKeyView && spLlmApiKey) {
    spBtnToggleKeyView.addEventListener('click', () => {
      const isPwd = spLlmApiKey.type === 'password';
      spLlmApiKey.type = isPwd ? 'text' : 'password';
      spBtnToggleKeyView.textContent = isPwd ? 'Ẩn Key' : 'Hiện Key';
    });
  }

  function showStatus(text, type) {
    if (!spLlmStatusBox) return;
    spLlmStatusBox.style.display = 'block';
    if (type === 'success') {
      spLlmStatusBox.style.background = '#dcfce7';
      spLlmStatusBox.style.color = '#15803d';
      spLlmStatusBox.style.border = '1px solid #86efac';
    } else if (type === 'error') {
      spLlmStatusBox.style.background = '#fee2e2';
      spLlmStatusBox.style.color = '#b91c1c';
      spLlmStatusBox.style.border = '1px solid #fca5a5';
    } else {
      spLlmStatusBox.style.background = '#f1f5f9';
      spLlmStatusBox.style.color = '#334155';
      spLlmStatusBox.style.border = '1px solid #cbd5e1';
    }
    spLlmStatusBox.textContent = text;
  }

  if (spBtnTestLlm) {
    spBtnTestLlm.addEventListener('click', () => {
      showStatus('⏳ Đang gửi truy vấn kiểm tra kết nối tới Model...', 'info');
      const payload = {
        provider: spLlmProvider.value,
        api_url: spLlmBaseUrl.value.trim(),
        api_key: spLlmApiKey.value.trim(),
        model: spLlmModel.value.trim(),
        enabled: true
      };
      chrome.runtime.sendMessage({ type: 'TEST_LLM_CONFIG', payload }, (resp) => {
        const res = resp?.data;
        if (res && res.ok) {
          showStatus(`✅ Kết nối thành công tới ${res.model || payload.model}! Phản hồi kiểm tra: "${res.reply_preview || 'OK'}"`, 'success');
        } else {
          showStatus(`❌ Lỗi kết nối: ${res?.error || resp?.error || 'Không thể gọi API model. Vui lòng kiểm tra lại URL/Key.'}`, 'error');
        }
      });
    });
  }

  if (spBtnSaveLlm) {
    spBtnSaveLlm.addEventListener('click', async () => {
      const newLlm = {
        enabled: Boolean(spLlmToggle?.checked),
        provider: spLlmProvider?.value || 'openai_compat',
        api_url: spLlmBaseUrl?.value.trim() || '',
        api_key: spLlmApiKey?.value.trim() || '',
        model: spLlmModel?.value.trim() || ''
      };

      try {
        const { config = {} } = await chrome.storage.local.get('config');
        config.llm_config = newLlm;
        await chrome.storage.local.set({ config });
        showStatus('💾 Đã lưu cấu hình Live AI Model an toàn vào bộ nhớ trình duyệt!', 'success');
        setTimeout(() => {
          if (spLlmStatusBox) spLlmStatusBox.style.display = 'none';
        }, 3500);
      } catch (err) {
        showStatus(`❌ Lỗi khi lưu: ${err.message}`, 'error');
      }
    });
  }

  // Boot
  connectActiveTab();
  loadCatalog();
  loadLlmSettings();
})();
