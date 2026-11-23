/**
 * BHYT Clinical Copilot - Content Script
 * In-Browser DOM Inspector, Live Xuat Toan Audit & 1-Click Clinical Note Autofill
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
    const docText = document.body ? document.body.innerText : '';
    let icdCode = '';
    const icdSelectors = [
      'input[name*="icd" i]', 'input[id*="icd" i]', 'input[class*="icd" i]',
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

    const drugs = [];
    const drugSelectors = [
      'input[name*="thuoc" i]', 'input[id*="thuoc" i]', 'input[name*="drug" i]',
      '.drug-item', '.thuoc-item', 'table.don-thuoc tr', 'table.prescription tr',
      '[data-field="drug_name"]', '.prescription-row'
    ];

    drugSelectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        const txt = el.value || el.innerText || '';
        if (txt.trim() && txt.length > 2 && !drugs.includes(txt.trim())) {
          drugs.push(txt.trim());
        }
      });
    });

    if (catalog && catalog.thuoc_bhyt) {
      catalog.thuoc_bhyt.forEach(d => {
        const name = d.ten_hoat_chat.toLowerCase();
        if (docText.toLowerCase().includes(name) && !drugs.some(x => x.toLowerCase().includes(name))) {
          drugs.push(d.ten_hoat_chat);
        }
      });
    }

    const procedures = [];
    const procKeywords = [
      { name: 'Điện châm điều trị', match: ['điện châm', 'dien cham'] },
      { name: 'Xoa bóp bấm huyệt điều trị', match: ['xoa bóp', 'xoa bop', 'bấm huyệt', 'bam huyet'] },
      { name: 'Cứu ngải (hoặc chiếu đèn hồng ngoại)', match: ['cứu ngải', 'cuu ngai', 'hồng ngoại', 'hong ngoai'] },
      { name: 'Kéo nắn, kéo dãn cột sống', match: ['kéo nắn', 'keo nan', 'kéo dãn', 'keo dan'] },
      { name: 'Thủy châm vào huyệt', match: ['thủy châm', 'thuy cham'] }
    ];

    procKeywords.forEach(pk => {
      for (const m of pk.match) {
        if (docText.toLowerCase().includes(m)) {
          procedures.push(pk.name);
          break;
        }
      }
    });

    document.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
      const label = cb.closest('label') ? cb.closest('label').innerText : (cb.parentElement ? cb.parentElement.innerText : '');
      procKeywords.forEach(pk => {
        if (pk.match.some(m => label.toLowerCase().includes(m)) && !procedures.includes(pk.name)) {
          procedures.push(pk.name);
        }
      });
    });

    const labTests = [];
    const labKeywords = ['lipid', 'cholesterol', 'triglyceride', 'ldl', 'hdl', 'glucose', 'hba1c', 'x-quang', 'mri', 'huyết áp'];
    labKeywords.forEach(kw => {
      if (docText.toLowerCase().includes(kw)) {
        labTests.push(kw);
      }
    });

    let procedureDays = 1;
    const daysInput = document.querySelector('input[name*="so_ngay" i], input[id*="so_ngay" i], input[name*="days" i]');
    if (daysInput && daysInput.value) {
      procedureDays = parseInt(daysInput.value, 10) || 1;
    } else {
      const matchDays = docText.match(/(\d+)\s*(ngày|buổi|đợt)/i);
      if (matchDays && parseInt(matchDays[1], 10) > 1) {
        procedureDays = parseInt(matchDays[1], 10);
      }
    }

    return {
      icdCode,
      drugs,
      procedures,
      labTests,
      procedureDays
    };
  }

  function performAudit(ctx) {
    if (!catalog) return null;

    const alerts = [];
    const hospitalLevel = '4';

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
      const allText = (ctx.drugs.join(' ') + ' ' + ctx.procedures.join(' ') + ' ' + (document.body ? document.body.innerText : '')).toLowerCase();
      catalog.thuoc_yhct.forEach(h => {
        if (h.tuong_tac_tay_y) {
          const herbKey = h.ten_vi_thuoc.split(' ')[0].toLowerCase();
          if (allText.includes(herbKey)) {
            if (h.tuong_tac_tay_y.includes('xuất huyết') || h.tuong_tac_tay_y.includes('chống đông')) {
              if (allText.includes('aspirin') || allText.includes('clopidogrel') || allText.includes('warfarin')) {
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
    let dock = document.getElementById('bhyt-copilot-dock');
    if (!dock) {
      dock = document.createElement('div');
      dock.id = 'bhyt-copilot-dock';
      document.body.appendChild(dock);
    }

    if (!audit || (!audit.icdCode && audit.alerts.length === 0)) {
      dock.innerHTML = '<div class="bhyt-copilot-pill" id="bhyt-pill-trigger"><div class="bhyt-copilot-indicator"></div><span class="bhyt-copilot-title">BHYT Copilot</span><span class="bhyt-copilot-pill-badge">Sẵn sàng</span></div>';
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
      cardHtml = '<div class="bhyt-copilot-card">' +
        '<div class="bhyt-card-header">' +
          '<div class="bhyt-card-header-title">' +
            '<div class="bhyt-copilot-indicator ' + statusClass + '"></div>' +
            '<div><h4>Giám Sát Xuất Toán Thời Gian Thực</h4><span>Phòng khám Tài Sanh • Tuyến 4</span></div>' +
          '</div>' +
          '<button class="bhyt-close-btn" id="bhyt-close-card">&times;</button>' +
        '</div>' +
        '<div class="bhyt-card-body">' +
          '<div class="bhyt-context-summary">' +
            '<div class="bhyt-context-row"><span class="bhyt-context-label">Mã bệnh ICD-10:</span><span class="bhyt-context-value">' + (audit.icdCode || 'Chưa nhập') + ' - ' + audit.diseaseName + '</span></div>' +
            '<div class="bhyt-context-row"><span class="bhyt-context-label">Thủ thuật YHCT:</span><span class="bhyt-context-value">' + (audit.procedures.join(', ') || 'Không có') + ' (' + audit.procedureDays + ' ngày)</span></div>' +
            '<div class="bhyt-context-row"><span class="bhyt-context-label">Thuốc kê đơn:</span><span class="bhyt-context-value">' + audit.drugs.length + ' thuốc</span></div>' +
          '</div>' +
          '<div class="bhyt-alerts-container">' + alertsHtml + '</div>' +
        '</div>' +
        '<div class="bhyt-autofill-section">' +
          '<button class="bhyt-autofill-btn" id="bhyt-btn-autofill">⚡ 1-Click Điền Bệnh Án Chuẩn BHYT</button>' +
        '</div>' +
      '</div>';
    }

    dock.innerHTML = '<div class="bhyt-copilot-pill" id="bhyt-pill-trigger">' +
      '<div class="bhyt-copilot-indicator ' + statusClass + '"></div>' +
      '<span class="bhyt-copilot-title">BHYT Copilot</span>' +
      (audit.icdCode ? '<span style="font-weight:700;color:#0d9488;">' + audit.icdCode + '</span>' : '') +
      '<span class="bhyt-copilot-pill-badge ' + badgeClass + '">' + badgeText + '</span>' +
      '</div>' + cardHtml;

    attachPillEvents();
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

    const autofillBtn = document.getElementById('bhyt-btn-autofill');
    if (autofillBtn) {
      autofillBtn.onclick = () => {
        performClinicalAutofill();
      };
    }
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

  function performClinicalAutofill() {
    const note = generateClinicalNote(currentAudit ? currentAudit.icdCode : '', currentAudit ? currentAudit.procedures : []);

    const noteSelectors = [
      'textarea[name*="dien_bien" i]', 'textarea[id*="dien_bien" i]',
      'textarea[name*="kham" i]', 'textarea[id*="kham" i]',
      'textarea[name*="lam_sang" i]', 'textarea[id*="lam_sang" i]',
      'textarea[name*="clinical" i]', 'textarea[id*="clinical" i]',
      'textarea[name*="mo_ta" i]', 'textarea[id*="mo_ta" i]',
      'textarea[name*="tom_tat" i]', 'textarea.clinical-note',
      '#clinical-notes', '#medical-record-text', 'textarea'
    ];

    let targetEl = null;
    for (const sel of noteSelectors) {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) {
        targetEl = el;
        break;
      }
    }

    if (!targetEl) {
      showToast('⚠️ Không tìm thấy ô nhập Diễn biến/Khám bệnh trên trang này');
      return;
    }

    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
    if (nativeSetter) {
      nativeSetter.call(targetEl, note);
    } else {
      targetEl.value = note;
    }

    targetEl.dispatchEvent(new Event('input', { bubbles: true }));
    targetEl.dispatchEvent(new Event('change', { bubbles: true }));
    targetEl.dispatchEvent(new Event('blur', { bubbles: true }));

    targetEl.classList.add('bhyt-autofill-highlight');
    targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => {
      targetEl.classList.remove('bhyt-autofill-highlight');
    }, 2500);

    showToast('✅ Đã điền diễn biến bệnh & khám lâm sàng chuẩn BHYT thành công!');
    chrome.runtime.sendMessage({ type: 'RECORD_AUTOFILL_EVENT' });
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
    if (message.type === 'TRIGGER_AUTOFILL') {
      performClinicalAutofill();
      sendResponse({ success: true });
    } else if (message.type === 'GET_DOM_STATE') {
      runAudit();
      sendResponse({ success: true, audit: currentAudit });
    }
    return true;
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadCatalog);
  } else {
    loadCatalog();
  }
})();
