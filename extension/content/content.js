/**
 * BHYT Clinical Copilot - Content Script
 * In-Browser DOM Inspector, Live Xuat Toan Audit, 1-Click Clinical Note Autofill
 * and Clinical AI Q&A Chatbox Drawer (Alt+Q)
 */

(function () {
  'use strict';

  if (window.__BHYT_COPILOT_INJECTED__) return;
  window.__BHYT_COPILOT_INJECTED__ = true;

  console.log('[BHYT Copilot] Activated on:', window.location.href);

  let catalog = null;
  let currentAudit = null;
  let debounceTimer = null;
  let isCardOpen = false;
  let activeCardTab = 'audit'; // 'audit' | 'chat'
  let activeTier = '4';
  let tierSource = 'Tự động';
  let facilityInfo = { name: 'Phòng Khám YHCT Tài Sanh', code: '54-012', tier: '4' };

  // Load saved tier override if exists
  try {
    if (chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(['activeHospitalTier', 'tierSource'], (res) => {
        if (res && res.activeHospitalTier) {
          activeTier = res.activeHospitalTier;
          tierSource = res.tierSource || 'Chọn thủ công';
          if (currentAudit) runAudit();
        }
      });
    }
  } catch (_) {}

  let chatHistory = [
    {
      sender: 'assistant',
      text: '### 🩺 Chào Bác sĩ!\nTôi là Trợ lý Lâm sàng BHYT & YHCT. Bác sĩ có thể bấm nhanh câu hỏi gợi ý bên dưới hoặc hỏi bất kỳ thắc mắc nào về quy chế kê đơn, định mức thủ thuật, hay tương tác thuốc.',
      snippet: null
    }
  ];

  async function loadCatalog() {
    try {
      const url = chrome.runtime.getURL('data/catalog.json');
      const resp = await fetch(url);
      catalog = await resp.json();
      console.log('[BHYT Copilot] Catalog loaded:', {
        icd10: catalog.icd10 ? catalog.icd10.length : 0,
        drugs: catalog.thuoc_bhyt ? catalog.thuoc_bhyt.length : 0
      });
      runAudit();
    } catch (err) {
      console.error('[BHYT Copilot] Catalog error:', err);
    }
  }

  function extractPageContext() {
    // 0. Detect Facility & Auto-infer Hospital Tier
    let facilityText = '';
    const facEl = document.querySelector('.his-facility, .facility-name, .hospital-name, #hospital_name, nav, header');
    if (facEl) facilityText = facEl.innerText || '';
    if (!facilityText && document.title) facilityText = document.title;

    const codeMatch = facilityText.match(/(\d{2}[-\.]?\d{3})/);
    const facCode = codeMatch ? codeMatch[1].replace(/[-\.]/, '') : '';
    const normFac = facilityText.toLowerCase();

    let autoTier = '4';
    if (normFac.includes('bạch mai') || normFac.includes('chợ rẫy') || normFac.includes('việt đức') || normFac.includes('trung ương') || normFac.includes('hạng đặc biệt')) {
      autoTier = '1';
    } else if (normFac.includes('đa khoa tỉnh') || normFac.includes('bvdk tỉnh') || normFac.includes('sản nhi') || normFac.includes('115') || normFac.includes('gia định')) {
      autoTier = '2';
    } else if (normFac.includes('trung tâm y tế') || normFac.includes('ttyt') || normFac.includes('quận') || normFac.includes('huyện')) {
      autoTier = '3';
    } else if (normFac.includes('phòng khám') || normFac.includes('trạm y tế') || normFac.includes('pkdk') || normFac.includes('tyt')) {
      autoTier = '4';
    }

    if (tierSource !== 'Chọn thủ công') {
      activeTier = autoTier;
      tierSource = 'Tự động';
    }

    facilityInfo = {
      name: (facEl ? facEl.innerText.split('•')[0].replace(/Cơ sở:/i, '').trim() : '') || 'Cơ sở KCB BHYT',
      code: facCode,
      tier: activeTier,
      source: tierSource
    };

    // A. Detect ICD-10 Code across ASP.NET WebForms, DevExpress, Telerik and standard HIS
    let icdCode = '';
    const icdSelectors = [
      'input[name*="icd" i]', 'input[id*="icd" i]', 'input[class*="icd" i]',
      'input[id*="txtICD" i]', 'input[id*="txtChanDoan" i]', 'input[id*="txtMaBenh" i]',
      'input[name*="ctl00" i][name*="icd" i]', 'input[id*="ctl00" i][id*="icd" i]',
      '.dxeEditSys input', '.dxic input', '.RadTextBox', '.riTextBox',
      'input[name*="chan_doan" i]', 'input[id*="chan_doan" i]', 'input[name*="ma_benh" i]',
      'select[name*="icd" i]', '.icd-input', '#icd10-code', '[data-field="icd10"]'
    ];

    for (const sel of icdSelectors) {
      const el = document.querySelector(sel);
      if (el && el.value && el.value.trim()) {
        const match = el.value.trim().match(/([A-Z][0-9]{2}(\.[0-9]{1,2})?)/i);
        if (match) {
          icdCode = match[1].toUpperCase();
          break;
        }
      }
    }

    if (!icdCode) {
      const allInputs = document.querySelectorAll('input[type="text"], input:not([type])');
      for (const input of allInputs) {
        const val = (input.value || '').trim();
        if (/^[A-Z][0-9]{2}(\.[0-9]{1,2})?$/i.test(val)) {
          icdCode = val.toUpperCase();
          break;
        }
      }
    }

    // B. Detect Prescribed Drugs
    const drugs = [];
    const rxContainer = document.querySelector('table.don-thuoc, table.prescription, #prescriptionTable, .don-thuoc, .prescription-list') || document.body;
    const rxText = rxContainer ? rxContainer.innerText.toLowerCase() : '';

    if (catalog && catalog.thuoc_bhyt) {
      catalog.thuoc_bhyt.forEach(d => {
        const name = d.ten_hoat_chat.toLowerCase();
        const primary = name.split('+')[0].trim().split(' ')[0].trim();
        if (rxText.includes(name) || (primary.length > 4 && rxText.includes(primary))) {
          if (!drugs.some(x => x.toLowerCase() === name)) {
            drugs.push(d.ten_hoat_chat);
          }
        }
      });
    }

    // C. Detect YHCT Procedures (Thủ thuật)
    const procedures = [];
    const procKeywords = [
      { name: 'Điện châm điều trị', match: ['điện châm', 'dien cham'] },
      { name: 'Xoa bóp bấm huyệt điều trị', match: ['xoa bóp', 'xoa bop', 'bấm huyệt', 'bam huyet'] },
      { name: 'Cứu ngải (hoặc chiếu đèn hồng ngoại)', match: ['cứu ngải', 'cuu ngai', 'hồng ngoại', 'hong ngoai'] },
      { name: 'Kéo nắn, kéo dãn cột sống', match: ['kéo nắn', 'keo nan', 'kéo dãn', 'keo dan'] },
      { name: 'Thủy châm vào huyệt', match: ['thủy châm', 'thuy cham'] }
    ];

    document.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
      const label = cb.closest('label') ? cb.closest('label').innerText : (cb.parentElement ? cb.parentElement.innerText : '');
      procKeywords.forEach(pk => {
        if (pk.match.some(m => label.toLowerCase().includes(m)) && !procedures.includes(pk.name)) {
          procedures.push(pk.name);
        }
      });
    });

    const procContainer = document.querySelector('.thu-thuat, [name*="thu_thuat"], .procedure-section');
    if (procContainer) {
      const pText = procContainer.innerText.toLowerCase();
      procKeywords.forEach(pk => {
        if (pk.match.some(m => pText.includes(m)) && !procedures.includes(pk.name)) {
          procedures.push(pk.name);
        }
      });
    }

    // D. Detect Lab Tests (Cận lâm sàng)
    const labTests = [];
    const labKeywords = ['lipid', 'cholesterol', 'triglyceride', 'ldl', 'hdl', 'glucose', 'hba1c', 'x-quang', 'mri', 'huyết áp'];
    const labContainer = document.querySelector('.can-lam-sang, .lab-results, table.xet-nghiem');
    const labText = labContainer ? labContainer.innerText.toLowerCase() : '';
    labKeywords.forEach(kw => {
      if (labText.includes(kw)) {
        labTests.push(kw);
      }
    });

    // E. Detect Procedure Days
    let procedureDays = 1;
    const daysInput = document.querySelector('input[name*="so_ngay" i], input[id*="so_ngay" i], input[name*="days" i]');
    if (daysInput && daysInput.value) {
      procedureDays = parseInt(daysInput.value, 10) || 1;
    }

    return {
      icdCode,
      drugs,
      procedures,
      labTests,
      procedureDays,
      rxText
    };
  }

  function performAudit(ctx) {
    if (!catalog) return null;

    const alerts = [];
    const hospitalLevel = activeTier; // Dynamic hospital tier (1, 2, 3, or 4)

    let diseaseName = '';
    if (ctx.icdCode) {
      const found = catalog.icd10 ? catalog.icd10.find(x => x.code === ctx.icdCode) : null;
      if (found) {
        diseaseName = found.name_vn;
      } else {
        alerts.push({
          severity: 'HIGH',
          rule: 'INVALID_ICD',
          title: 'Mã ICD-10 không hợp lệ',
          detail: 'Mã "' + ctx.icdCode + '" không tồn tại trong danh mục chuẩn Bộ Y tế. Cổng giám định BHYT sẽ từ chối thanh toán toàn bộ hồ sơ.',
          remedy: 'Tra cứu mã bệnh chuẩn từ thanh tìm kiếm Copilot để cập nhật đúng mã.'
        });
      }

      if (ctx.icdCode.length === 3) {
        const hasSub = catalog.icd10 ? catalog.icd10.some(x => x.code.startsWith(ctx.icdCode + '.')) : false;
        if (hasSub) {
          alerts.push({
            severity: 'HIGH',
            rule: 'MUST_USE_SUBCODE',
            title: 'Sử dụng mã ICD 3 ký tự chung chung',
            detail: 'Mã "' + ctx.icdCode + '" là mã nhóm bệnh chương. Bộ Y tế bắt buộc phải chọn mã 4 ký tự chi tiết.',
            remedy: 'Ví dụ: M54.5 (Đau lưng dưới) thay vì M54 chung chung.'
          });
        }
      }
    }

    ctx.drugs.forEach(drugStr => {
      const dLower = drugStr.toLowerCase();
      const match = catalog.thuoc_bhyt ? catalog.thuoc_bhyt.find(d => dLower.includes(d.ten_hoat_chat.toLowerCase())) : null;
      if (match) {
        const allowed = match.hang_bv_duoc_ke.split(',').map(s => s.trim());
        if (!allowed.includes(hospitalLevel)) {
          alerts.push({
            severity: 'HIGH',
            rule: 'HOSPITAL_LEVEL_EXCEEDED',
            title: 'Thuốc "' + match.ten_hoat_chat + '" vượt tuyến chuyên môn kỹ thuật',
            detail: 'Thuốc chỉ được thanh toán tại Bệnh viện (Tuyến ' + match.hang_bv_duoc_ke + '). Cơ sở Hạng 4 kê đơn sẽ bị xuất toán 100%.',
            remedy: match.ghi_chu_xuat_toan || 'Thay thế bằng thuốc nhóm uống tương đương cho phép tại Tuyến 4.'
          });
        }

        if (dLower.includes('statin') || dLower.includes('atorvastatin')) {
          const hasLipid = ctx.labTests.some(t => t.includes('lipid') || t.includes('cholesterol') || t.includes('triglyceride'));
          if (!hasLipid) {
            alerts.push({
              severity: 'HIGH',
              rule: 'MISSING_REQUIRED_LAB',
              title: 'Kê đơn ' + match.ten_hoat_chat + ' nhưng thiếu xét nghiệm Lipid máu',
              detail: 'Quy chế giám định BHYT bắt buộc phải có kết quả xét nghiệm mỡ máu để bảo vệ chỉ định thuốc nhóm Statin.',
              remedy: 'Bổ sung chỉ định xét nghiệm bộ mỡ máu hoặc ghi kết quả xét nghiệm gần nhất vào phần tóm tắt bệnh án.'
            });
          }
        }
      }
    });

    ctx.procedures.forEach(proc => {
      const match = catalog.thu_thuat_bhyt ? catalog.thu_thuat_bhyt.find(p => proc.toLowerCase().includes(p.ten_dich_vu.toLowerCase())) : null;
      if (match) {
        if (ctx.procedureDays > match.so_ngay_toi_da) {
          alerts.push({
            severity: 'HIGH',
            rule: 'PROCEDURE_DAYS_EXCEEDED',
            title: 'Chỉ định "' + match.ten_dich_vu + '" vượt quá ' + match.so_ngay_toi_da + ' ngày/đợt',
            detail: 'Hồ sơ ghi nhận ngày điều trị thứ ' + ctx.procedureDays + '. Định mức BHYT tối đa là ' + match.so_ngay_toi_da + ' ngày/đợt điều trị ngoại trú.',
            remedy: 'Tạm dừng đợt 1, cho bệnh nhân nghỉ tối thiểu 5-7 ngày và tái khám mở đợt điều trị mới có đánh giá lâm sàng.'
          });
        }
      }
    });

    if (catalog.thuoc_yhct) {
      const rxText = ctx.rxText || '';
      catalog.thuoc_yhct.forEach(h => {
        if (h.tuong_tac_tay_y) {
          const herbKey = h.ten_vi_thuoc.split(' ')[0].toLowerCase();
          if (rxText.includes(herbKey)) {
            if (h.tuong_tac_tay_y.includes('xuất huyết') || h.tuong_tac_tay_y.includes('chống đông')) {
              if (rxText.includes('aspirin') || rxText.includes('clopidogrel') || rxText.includes('warfarin')) {
                alerts.push({
                  severity: 'HIGH',
                  rule: 'HERB_DRUG_INTERACTION',
                  title: 'Nguy cơ xuất huyết: ' + h.ten_vi_thuoc + ' + Thuốc chống đông',
                  detail: h.tuong_tac_tay_y,
                  remedy: 'Cân nhắc ngưng vị thuốc hoặc giảm liều và theo dõi sát chỉ số đông máu PT/INR.'
                });
              }
            }
          }
        }
      });
    }

    const highRiskCount = alerts.filter(a => a.severity === 'HIGH').length;

    return {
      icdCode: ctx.icdCode,
      diseaseName: diseaseName || 'Chưa nhận diện mã',
      drugs: ctx.drugs,
      procedures: ctx.procedures,
      procedureDays: ctx.procedureDays,
      alerts,
      alertCount: alerts.length,
      highRiskCount,
      status: highRiskCount > 0 ? 'DANGER' : alerts.length > 0 ? 'WARNING' : 'PASS'
    };
  }

  function renderDock(audit) {
    if (window !== window.top) return;
    let dock = document.getElementById('bhyt-copilot-dock');
    if (!dock) {
      dock = document.createElement('div');
      dock.id = 'bhyt-copilot-dock';
      dock.dataset.extId = chrome.runtime.id;
      document.body.appendChild(dock);
    }

    if (!audit || (!audit.icdCode && (!audit.alerts || audit.alerts.length === 0))) {
      dock.innerHTML = '<div class="bhyt-copilot-pill" id="bhyt-pill-trigger"><div class="bhyt-copilot-indicator"></div><span class="bhyt-copilot-title">BHYT Copilot</span><span class="bhyt-copilot-pill-badge">Sẵn sàng (Alt+Q)</span></div>';
      attachPillEvents();
      return;
    }

    const statusClass = audit.highRiskCount > 0 ? 'status-danger' : (audit.alertCount > 0 ? 'status-warning' : 'status-pass');
    const badgeClass = audit.highRiskCount > 0 ? 'badge-danger' : 'badge-pass';
    const badgeText = audit.highRiskCount > 0 ? (audit.highRiskCount + ' Nguy cơ') : (audit.alertCount > 0 ? (audit.alertCount + ' Lưu ý') : 'Hợp lệ');

    let alertsHtml = '';
    if (audit.alerts.length === 0) {
      alertsHtml = '<div class="bhyt-alert-item severity-PASS"><div class="bhyt-alert-title">🟢 Hồ sơ đạt chuẩn BHYT</div><div class="bhyt-alert-detail">Không phát hiện nguy cơ xuất toán. Chỉ định thuốc và thủ thuật phù hợp với tuyến chuyên môn kỹ thuật.</div></div>';
    } else {
      audit.alerts.forEach(a => {
        alertsHtml += '<div class="bhyt-alert-item severity-' + a.severity + '">' +
          '<div class="bhyt-alert-title">' + (a.severity === 'HIGH' ? '⚠️ XUẤT TOÁN 100%' : 'ℹ️ LƯU Ý BHYT') + ': ' + a.title + '</div>' +
          '<div class="bhyt-alert-detail">' + a.detail + '</div>' +
          (a.remedy ? '<div class="bhyt-alert-remedy">👉 Giải pháp: ' + a.remedy + '</div>' : '') +
          '</div>';
      });
    }

    let cardHtml = '';
    if (isCardOpen) {
      const activeIcd = audit.icdCode || 'M54.5';

      let bodyContentHtml = '';
      if (activeCardTab === 'audit') {
        bodyContentHtml = `
          <div class="bhyt-context-summary">
            <div class="bhyt-context-row"><span class="bhyt-context-label">Mã bệnh ICD-10:</span><span class="bhyt-context-value">${audit.icdCode || 'Chưa nhập'} - ${audit.diseaseName}</span></div>
            <div class="bhyt-context-row"><span class="bhyt-context-label">Thủ thuật YHCT:</span><span class="bhyt-context-value">${audit.procedures.join(', ') || 'Không có'} (${audit.procedureDays} ngày)</span></div>
            <div class="bhyt-context-row"><span class="bhyt-context-label">Thuốc kê đơn:</span><span class="bhyt-context-value">${audit.drugs.length} thuốc</span></div>
          </div>
          <div class="bhyt-alerts-container">${alertsHtml}</div>
        `;
      } else {
        // Chat View
        const chatMsgsHtml = chatHistory.map((m, idx) => `
          <div class="bhyt-chat-msg ${m.sender}">
            ${formatChatText(m.text)}
            ${m.snippet ? `<div class="bhyt-snippet-box">${m.snippet}</div><button class="bhyt-chat-action-btn" data-snippet-idx="${idx}">📋 Điền Đoạn Này Vào Bệnh Án</button>` : ''}
          </div>
        `).join('');

        bodyContentHtml = `
          <div class="bhyt-chat-container">
            <div class="bhyt-chat-context-bar">
              <span>🩺 Ngữ cảnh: <strong>${audit.icdCode || 'Toàn khoa'}</strong> (Tuyến 4 - PK Tư)</span>
              <span>⚡ RAG Catalog</span>
            </div>
            <div class="bhyt-chat-quick-chips">
              <button class="bhyt-quick-chip" data-q="Mã ${activeIcd} ở tuyến 4 được kê thuốc gì?">💊 Thuốc mã ${activeIcd}</button>
              <button class="bhyt-quick-chip" data-q="Bệnh nhân tăng huyết áp có dùng được Cam thảo không?">⚠️ Cam thảo & Huyết áp</button>
              <button class="bhyt-quick-chip" data-q="Điện châm và xoa bóp bấm huyệt tối đa bao nhiêu ngày trong 1 đợt?">⏱️ Giới hạn ngày YHCT</button>
              <button class="bhyt-quick-chip" data-q="Kê thuốc hạ mỡ máu Atorvastatin cần xét nghiệm gì?">🧪 Cận lâm sàng Statin</button>
              <button class="bhyt-quick-chip" data-q="Đan sâm có dùng chung được với Aspirin không?">🩸 Đan sâm & Xuất huyết</button>
            </div>
            <div class="bhyt-chat-messages" id="bhytChatMessagesList">
              ${chatMsgsHtml}
            </div>
            <div class="bhyt-chat-input-bar">
              <input type="text" id="bhytChatInput" class="bhyt-chat-input" placeholder="Hỏi BHYT, thuốc, thủ thuật, tương tác... (Enter)">
              <button class="bhyt-chat-send-btn" id="bhytChatSendBtn">Gửi</button>
            </div>
          </div>
        `;
      }

      cardHtml = `
        <div class="bhyt-copilot-card">
          <div class="bhyt-card-header">
            <div class="bhyt-card-header-title">
              <div class="bhyt-copilot-indicator ${statusClass}"></div>
              <div><h4>BHYT Clinical Copilot</h4><span>${facilityInfo.name}</span></div>
            </div>
            <button class="bhyt-close-btn" id="bhyt-close-card" title="Đóng (Esc)">&times;</button>
          </div>
          <div style="background:#f1f5f9; padding:4px 12px; display:flex; align-items:center; justify-content:space-between; font-size:11px; border-bottom:1px solid #e2e8f0;">
            <span style="color:#64748b;">Phân tuyến: <strong>Tuyến ${activeTier}</strong> (${tierSource})</span>
            <div style="display:flex; gap:3px;">
              <button class="bhyt-tier-btn-sm ${activeTier==='1'?'active':''}" data-set-tier="1" style="border:1px solid #cbd5e1; background:${activeTier==='1'?'#dc2626':'#fff'}; color:${activeTier==='1'?'#fff':'#334155'}; border-radius:3px; padding:1px 5px; font-size:10px; font-weight:700; cursor:pointer;">T1</button>
              <button class="bhyt-tier-btn-sm ${activeTier==='2'?'active':''}" data-set-tier="2" style="border:1px solid #cbd5e1; background:${activeTier==='2'?'#d97706':'#fff'}; color:${activeTier==='2'?'#fff':'#334155'}; border-radius:3px; padding:1px 5px; font-size:10px; font-weight:700; cursor:pointer;">T2</button>
              <button class="bhyt-tier-btn-sm ${activeTier==='3'?'active':''}" data-set-tier="3" style="border:1px solid #cbd5e1; background:${activeTier==='3'?'#2563eb':'#fff'}; color:${activeTier==='3'?'#fff':'#334155'}; border-radius:3px; padding:1px 5px; font-size:10px; font-weight:700; cursor:pointer;">T3</button>
              <button class="bhyt-tier-btn-sm ${activeTier==='4'?'active':''}" data-set-tier="4" style="border:1px solid #cbd5e1; background:${activeTier==='4'?'#059669':'#fff'}; color:${activeTier==='4'?'#fff':'#334155'}; border-radius:3px; padding:1px 5px; font-size:10px; font-weight:700; cursor:pointer;">T4</button>
            </div>
          </div>
          <div class="bhyt-card-nav-tabs">
            <button class="bhyt-card-tab ${activeCardTab === 'audit' ? 'active' : ''}" id="bhyt-tab-audit-btn">🩺 Giám Sát HIS</button>
            <button class="bhyt-card-tab ${activeCardTab === 'chat' ? 'active' : ''}" id="bhyt-tab-chat-btn">💬 Hỏi Đáp AI (Chatbox)</button>
          </div>
          <div class="bhyt-card-body" id="bhytCardBodyMain">
            ${bodyContentHtml}
          </div>
          ${activeCardTab === 'audit' ? `
            <div class="bhyt-autofill-section">
              <button class="bhyt-autofill-btn" id="bhyt-btn-autofill">⚡ 1-Click Điền Bệnh Án Chuẩn BHYT</button>
            </div>
          ` : ''}
        </div>
      `;
    }

    dock.innerHTML = '<div class="bhyt-copilot-pill" id="bhyt-pill-trigger">' +
      '<div class="bhyt-copilot-indicator ' + statusClass + '"></div>' +
      '<span class="bhyt-copilot-title">BHYT Copilot</span>' +
      (audit.icdCode ? '<span style="font-weight:700;color:#0d9488;">' + audit.icdCode + '</span>' : '') +
      '<span class="bhyt-copilot-pill-badge ' + badgeClass + '">' + badgeText + '</span>' +
      '</div>' + cardHtml;

    attachPillEvents();
  }

  function formatChatText(text) {
    if (!text) return '';
    return text
      .replace(/### (.*?)\n/g, '<h3>$1</h3>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n\n/g, '<p></p>')
      .replace(/\n/g, '<br>');
  }

  function attachPillEvents() {
    const trigger = document.getElementById('bhyt-pill-trigger');
    if (trigger) {
      trigger.onclick = () => {
        isCardOpen = !isCardOpen;
        renderDock(currentAudit);
      };
    }

    const closeBtn = document.getElementById('bhyt-close-card');
    if (closeBtn) {
      closeBtn.onclick = () => {
        isCardOpen = false;
        renderDock(currentAudit);
      };
    }

    const tabAuditBtn = document.getElementById('bhyt-tab-audit-btn');
    if (tabAuditBtn) {
      tabAuditBtn.onclick = () => {
        activeCardTab = 'audit';
        renderDock(currentAudit);
      };
    }

    const tabChatBtn = document.getElementById('bhyt-tab-chat-btn');
    if (tabChatBtn) {
      tabChatBtn.onclick = () => {
        activeCardTab = 'chat';
        renderDock(currentAudit);
        setTimeout(scrollChatToBottom, 100);
      };
    }

    const autofillBtn = document.getElementById('bhyt-btn-autofill');
    if (autofillBtn) {
      autofillBtn.onclick = () => {
        performClinicalAutofill();
      };
    }

    // Tier Selector in Drawer Header
    document.querySelectorAll('.bhyt-tier-btn-sm').forEach(btn => {
      btn.onclick = () => {
        activeTier = btn.dataset.setTier;
        tierSource = 'Chọn thủ công';
        try {
          if (chrome.storage && chrome.storage.local) {
            chrome.storage.local.set({ activeHospitalTier: activeTier, tierSource });
          }
        } catch (_) {}
        runAudit();
      };
    });

    // Chat events
    const chatInput = document.getElementById('bhytChatInput');
    const chatSendBtn = document.getElementById('bhytChatSendBtn');
    if (chatInput && chatSendBtn) {
      chatSendBtn.onclick = () => sendUserChatMessage(chatInput.value.trim());
      chatInput.onkeydown = (e) => {
        if (e.key === 'Enter') {
          sendUserChatMessage(chatInput.value.trim());
        }
      };
    }

    // Quick chips
    document.querySelectorAll('.bhyt-quick-chip').forEach(btn => {
      btn.onclick = () => {
        const q = btn.dataset.q;
        sendUserChatMessage(q);
      };
    });

    // Snippet inject buttons
    document.querySelectorAll('.bhyt-chat-action-btn').forEach(btn => {
      btn.onclick = () => {
        const idx = parseInt(btn.dataset.snippetIdx, 10);
        const msg = chatHistory[idx];
        if (msg && msg.snippet) {
          performSnippetAutofill(msg.snippet);
        }
      };
    });
  }

  function scrollChatToBottom() {
    const list = document.getElementById('bhytChatMessagesList');
    if (list) list.scrollTop = list.scrollHeight;
  }

  function sendUserChatMessage(query) {
    if (!query) return;
    const input = document.getElementById('bhytChatInput');
    if (input) input.value = '';

    chatHistory.push({ sender: 'user', text: query, snippet: null });
    renderDock(currentAudit);
    scrollChatToBottom();

    chrome.runtime.sendMessage({
      type: 'ASK_CHAT_COPILOT',
      payload: {
        query,
        context: {
          icdCode: currentAudit ? currentAudit.icdCode : '',
          procedures: currentAudit ? currentAudit.procedures : [],
          drugs: currentAudit ? currentAudit.drugs : [],
          hospital_level: '4'
        }
      }
    }, (resp) => {
      if (resp && resp.success && resp.data) {
        chatHistory.push({
          sender: 'assistant',
          text: resp.data.answer,
          snippet: resp.data.suggested_snippet
        });
      } else {
        chatHistory.push({
          sender: 'assistant',
          text: '⚠️ Không thể kết nối bộ giải đáp lâm sàng: ' + (resp?.error || 'Lỗi không xác định'),
          snippet: null
        });
      }
      renderDock(currentAudit);
      scrollChatToBottom();
    });
  }

  function generateClinicalNote(icdCode, procedures) {
    const code = (icdCode || '').toUpperCase();
    if (code.includes('M54') || code.includes('M47') || code.includes('M51')) {
      return 'LÝ DO VÀO VIỆN: Đau buốt mỏi vùng thắt lưng lan xuống hông đùi, vận động cúi ngửa khó khăn, đau tăng khi thời tiết chuyển mùa.\n' +
             'KHÁM THỰC THỂ LÂM SÀNG: Bệnh nhân tỉnh táo, tiếp xúc tốt. Cột sống thắt lưng giảm biên độ cúi ngửa. Co cứng cơ cạnh sống hai bên. Dấu hiệu Schober (+) 10/12cm. Nghiệm pháp Lasegue 60 độ. Điểm đau Valleix ấn đau rõ rệt (VAS 6/10). Không teo cơ, phản xạ gân xương bình thường.\n' +
             'CHẨN ĐOÁN YHCT: Tọa cốt phong / Yêu thống - Thể Khí trệ huyết ứ kết hợp Can Thận âm hư.\n' +
             'CHẨN ĐOÁN YHHĐ: Thoái hóa cột sống thắt lưng, đau dây thần kinh tọa (ICD-10: ' + (code || 'M54.5') + ').\n' +
             'PHƯƠNG PHÁP ĐIỀU TRỊ CHỈ ĐỊNH: Kết hợp điều trị bảo tồn YHCT và phục hồi chức năng: Điện châm huyệt Thận du, Đại trường du, Trật biên, Hoàn khiêu, Ủy trung (25 phút/lần); Xoa bóp bấm huyệt giải cơ vùng thắt lưng (20 phút/lần). Dặn dò bệnh nhân tránh mang vác nặng, tập bài tập vận động cột sống nhẹ nhàng tại nhà.';
    }

    if (code.includes('G51')) {
      return 'LÝ DO VÀO VIỆN: Đột ngột méo miệng, mắt phải nhắm không kín, ăn uống rơi vãi sau khi ngủ dậy gặp gió lạnh.\n' +
             'KHÁM THỰC THỂ: Mất nếp nhăn trán bên tổn thương, rãnh mũi má mờ, nhân trung lệch sang bên lành, dấu hiệu Charles Bell (+). Trương lực cơ nửa mặt giảm. Cảm giác vị giác 2/3 trước lưỡi bình thường. Không yếu liệt tay chân, dấu hiệu màng não (-).\n' +
             'CHẨN ĐOÁN YHCT: Khẩu nhãn oa tà - Thể Phong hàn phạm kinh lạc.\n' +
             'CHẨN ĐOÁN YHHĐ: Liệt dây thần kinh số VII ngoại biên vô căn (Bell\'s palsy) (ICD-10: G51.0).\n' +
             'HƯỚNG ĐIỀU TRỊ: Điện châm các huyệt Tình minh, Toản trúc, Dương bạch, Địa thương, Giáp xa (dòng xung êm dịu, 20 phút); Ôn châm / Cứu ngải ấm vùng mặt bên liệt; Hướng dẫn đeo kính bảo vệ mắt, nhỏ nước muối sinh lý thường xuyên.';
    }

    if (code.includes('I10')) {
      return 'LÝ DO VÀO VIỆN: Đau đầu vùng chẩm, chóng mặt hoa mắt từng cơn khi thay đổi tư thế.\n' +
             'KHÁM LÂM SÀNG: Bệnh nhân tỉnh, thể trạng trung bình. Huyết áp đo lúc khám: 155/95 mmHg, Mạch: 78 ck/phút. Tim T1, T2 đều rõ, không tiếng tim bệnh lý. Phổi thông khí tốt, không rale. Bụng mềm, không phù ngoại biên.\n' +
             'CHẨN ĐOÁN: Tăng huyết áp nguyên phát giai đoạn 2 (ICD-10: I10). Thể Can hỏa thượng viêm (YHCT).\n' +
             'KẾ HOẠCH ĐIỀU TRỊ: Dùng thuốc hạ áp nhóm chẹn kênh calci phối hợp điều chỉnh lối sống, giảm muối trong khẩu phần ăn, theo dõi huyết áp hàng ngày tại nhà.';
    }

    return 'LÝ DO VÀO VIỆN: Khám và điều trị theo bệnh cảnh lâm sàng mã ICD-10 ' + (code || 'BHYT') + '.\n' +
           'KHÁM THỰC THỂ LÂM SÀNG: Bệnh nhân tỉnh táo, tiếp xúc tốt. Dấu hiệu sinh tồn ổn định (HA: 120/80 mmHg, Mạch: 75 l/p). Tổn thương khu trú, tầm vận động trong giới hạn bệnh lý. Các cơ quan tuần hoàn, hô hấp, tiêu hóa chưa phát hiện bất thường cấp tính.\n' +
           'CHẨN ĐOÁN: Bệnh lý theo phân loại ICD-10: ' + (code || 'N/A') + '.\n' +
           'CHỈ ĐỊNH ĐIỀU TRỊ: Chỉ định thủ thuật phục hồi chức năng và thuốc điều trị nội khoa ngoại trú đúng theo phác đồ quy chuẩn của Bộ Y tế.';
  }

  function getAccessibleDocuments() {
    const docs = [document];
    const seen = new Set([document]);
    function walk(doc) {
      try {
        const frames = doc.querySelectorAll('iframe, frame');
        for (const frame of frames) {
          try {
            const subDoc = frame.contentDocument || frame.contentWindow?.document;
            if (subDoc && !seen.has(subDoc)) {
              seen.add(subDoc);
              docs.push(subDoc);
              walk(subDoc);
            }
          } catch (_) {
            // Cross-origin iframe - ignore silently
          }
        }
      } catch (_) {}
    }
    walk(document);
    return docs;
  }

  function isFieldEditableAndVisible(el) {
    if (!el || el.disabled || el.readOnly) return false;
    try {
      const win = el.ownerDocument?.defaultView || window;
      const style = win.getComputedStyle(el);
      if (!style || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
        return false;
      }
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    } catch (_) {
      return el.offsetParent !== null;
    }
  }

  function performClinicalAutofill() {
    let icdCode = currentAudit ? currentAudit.icdCode : '';
    let procedures = currentAudit ? currentAudit.procedures : [];
    if (!icdCode) {
      try {
        const freshCtx = extractPageContext();
        icdCode = freshCtx.icdCode || '';
        procedures = freshCtx.procedures || [];
      } catch (_) {}
    }
    const note = generateClinicalNote(icdCode, procedures);
    return injectTextIntoActiveHis(note, 'Đã điền diễn biến bệnh & khám lâm sàng chuẩn BHYT thành công!');
  }

  function performSnippetAutofill(snippet) {
    if (!snippet) return { filled: false, error: 'Nội dung chèn trống' };
    return injectTextIntoActiveHis(snippet, 'Đã điền trích dẫn nghiệp vụ vào hồ sơ bệnh án!');
  }

  function injectTextIntoActiveHis(text, successMsg) {
    const docs = getAccessibleDocuments();
    const noteSelectors = [
      'textarea[name*="dien_bien" i]', 'textarea[id*="dien_bien" i]',
      'textarea[name*="dienBien" i]', 'textarea[id*="dienBien" i]',
      'textarea[name*="kham" i]', 'textarea[id*="kham" i]',
      'textarea[name*="lam_sang" i]', 'textarea[id*="lam_sang" i]',
      'textarea[name*="benh_su" i]', 'textarea[id*="benh_su" i]',
      'textarea[name*="ly_do" i]', 'textarea[id*="ly_do" i]',
      'textarea[name*="tom_tat" i]', 'textarea[id*="tom_tat" i]',
      'textarea[name*="mo_ta" i]', 'textarea[id*="mo_ta" i]',
      'textarea[name*="clinical" i]', 'textarea[id*="clinical" i]',
      'textarea[name*="note" i]', 'textarea[id*="note" i]',
      'textarea.clinical-note', '#clinical-notes', '#medical-record-text',
      'textarea',
      '[contenteditable="true"][name*="dien_bien" i]',
      '[contenteditable="true"][id*="dien_bien" i]',
      '[contenteditable="true"][id*="clinical" i]',
      '[contenteditable="true"]',
      'input[type="text"][name*="dien_bien" i]',
      'input[type="text"][id*="dien_bien" i]',
      'input[type="text"][name*="kham" i]',
      'input[type="text"][id*="kham" i]',
      'input[type="text"][name*="ly_do" i]'
    ];

    let targetEl = null;

    // Priority 1: Currently focused editable element across accessible docs
    for (const doc of docs) {
      try {
        const active = doc.activeElement;
        if (active && (
          active.tagName === 'TEXTAREA' ||
          active.isContentEditable ||
          (active.tagName === 'INPUT' && /^(text|search|)$/i.test(active.type || ''))
        ) && isFieldEditableAndVisible(active)) {
          targetEl = active;
          break;
        }
      } catch (_) {}
    }

    // Priority 2: Best matching selector in main document & same-origin iframes
    if (!targetEl) {
      for (const sel of noteSelectors) {
        for (const doc of docs) {
          try {
            const candidates = doc.querySelectorAll(sel);
            for (const el of candidates) {
              if (el.closest && el.closest('#bhyt-copilot-dock')) continue;
              if (isFieldEditableAndVisible(el)) {
                targetEl = el;
                break;
              }
            }
          } catch (_) {}
          if (targetEl) break;
        }
        if (targetEl) break;
      }
    }

    // Priority 3: Rich-text editor iframe body (TinyMCE / CKEditor classic)
    if (!targetEl) {
      for (const doc of docs) {
        try {
          if (doc !== document && doc.body && doc.body.isContentEditable) {
            targetEl = doc.body;
            break;
          }
        } catch (_) {}
      }
    }

    if (!targetEl) {
      showToast('⚠️ Không tìm thấy ô nhập Diễn biến/Khám bệnh trên trang này');
      return {
        filled: false,
        text,
        error: 'Không tìm thấy ô nhập Diễn biến/Khám bệnh trên trang hiện tại'
      };
    }

    const docWin = targetEl.ownerDocument?.defaultView || window;
    if (targetEl.isContentEditable && targetEl.tagName !== 'TEXTAREA' && targetEl.tagName !== 'INPUT') {
      targetEl.focus();
      targetEl.innerText = text;
    } else {
      const proto = targetEl.tagName === 'TEXTAREA'
        ? docWin.HTMLTextAreaElement?.prototype
        : docWin.HTMLInputElement?.prototype;
      const nativeSetter = proto ? Object.getOwnPropertyDescriptor(proto, 'value')?.set : null;
      if (nativeSetter) {
        nativeSetter.call(targetEl, text);
      } else {
        targetEl.value = text;
      }
    }

    targetEl.dispatchEvent(new Event('input', { bubbles: true }));
    targetEl.dispatchEvent(new Event('change', { bubbles: true }));
    targetEl.dispatchEvent(new Event('blur', { bubbles: true }));

    try {
      targetEl.classList.add('bhyt-autofill-highlight');
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => {
        try { targetEl.classList.remove('bhyt-autofill-highlight'); } catch (_) {}
      }, 2500);
    } catch (_) {}

    showToast('✅ ' + successMsg);
    try {
      chrome.runtime.sendMessage({ type: 'RECORD_AUTOFILL_EVENT' });
    } catch (_) {}

    return {
      filled: true,
      targetId: targetEl.id || targetEl.name || targetEl.tagName,
      text
    };
  }

  function showToast(msg) {
    const existing = document.querySelector('.bhyt-copilot-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'bhyt-copilot-toast';
    toast.innerText = msg;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-16px)';
      toast.style.transition = 'all 0.25s ease';
      setTimeout(() => toast.remove(), 250);
    }, 3200);
  }

  function runAudit() {
    const ctx = extractPageContext();
    currentAudit = performAudit(ctx);

    if (currentAudit) {
      renderDock(currentAudit);
      chrome.runtime.sendMessage({
        type: 'AUDIT_STATUS_CHANGED',
        payload: {
          alertCount: currentAudit.alertCount,
          highRiskCount: currentAudit.highRiskCount,
          icdCode: currentAudit.icdCode,
          diseaseName: currentAudit.diseaseName,
          alerts: currentAudit.alerts
        }
      });
    }
  }

  function scheduleAudit() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      requestAnimationFrame(runAudit);
    }, 300);
  }

  // Keyboard shortcut Alt+Q to toggle drawer
  document.addEventListener('keydown', (e) => {
    if (e.altKey && e.key.toLowerCase() === 'q') {
      e.preventDefault();
      isCardOpen = !isCardOpen;
      renderDock(currentAudit);
    }
  });

  document.addEventListener('input', scheduleAudit, true);
  document.addEventListener('change', scheduleAudit, true);

  const observer = new MutationObserver((mutations) => {
    let shouldScan = false;
    for (const m of mutations) {
      if (m.target && m.target.closest && m.target.closest('#bhyt-copilot-dock')) continue;
      if (m.addedNodes.length > 0 || m.type === 'attributes') {
        shouldScan = true;
        break;
      }
    }
    if (shouldScan) scheduleAudit();
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['value', 'class', 'checked']
  });

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (window !== window.top) {
      return false;
    }
    if (message.type === 'TRIGGER_AUTOFILL') {
      const res = performClinicalAutofill();
      sendResponse({ success: Boolean(res?.filled), ...res });
    } else if (message.type === 'INJECT_SNIPPET') {
      const res = performSnippetAutofill(message.snippet);
      sendResponse({ success: Boolean(res?.filled), ...res });
    } else if (message.type === 'SET_HOSPITAL_TIER') {
      activeTier = message.tier;
      tierSource = 'Chọn thủ công';
      try {
        if (chrome.storage && chrome.storage.local) {
          chrome.storage.local.set({ activeHospitalTier: activeTier, tierSource });
        }
      } catch (_) {}
      runAudit();
      sendResponse({ success: true, audit: currentAudit, facility: facilityInfo });
    } else if (message.type === 'GET_DOM_STATE') {
      runAudit();
      sendResponse({ success: true, audit: currentAudit, facility: facilityInfo });
    } else if (message.type === 'TOGGLE_DRAWER') {
      isCardOpen = !isCardOpen;
      renderDock(currentAudit);
      sendResponse({ success: true, isOpen: isCardOpen });
    }
    return true;
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadCatalog);
  } else {
    loadCatalog();
  }
})();
