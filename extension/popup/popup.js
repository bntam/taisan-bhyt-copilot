// Popup Logic for TaiSanh BHYT Clinical Copilot

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const target = tab.dataset.tab;
    document.getElementById('tab-validate').style.display = target === 'validate' ? 'block' : 'none';
    document.getElementById('tab-search').style.display = target === 'search' ? 'block' : 'none';
    document.getElementById('tab-autofill').style.display = target === 'autofill' ? 'block' : 'none';
  });
});

// Validate
document.getElementById('btnValidate').addEventListener('click', () => {
  const icd = document.getElementById('valIcd').value.trim();
  const drugs = document.getElementById('valDrugs').value.split(',').map(s => s.trim()).filter(Boolean);
  const procs = document.getElementById('valProcs').value.split(',').map(s => s.trim()).filter(Boolean);
  const level = document.getElementById('valLevel').value;
  const days = parseInt(document.getElementById('valDays').value || '1', 10);

  chrome.runtime.sendMessage({
    action: 'VALIDATE_PRESCRIPTION',
    payload: { icd_code: icd, drugs, procedures: procs, hospital_level: level, procedure_days: days }
  }, (response) => {
    const out = document.getElementById('valOutput');
    if (!response || !response.success) {
      out.innerHTML = `<div class="alert-box alert-danger">Lỗi kết nối bộ kiểm tra: ${response?.error || 'Unknown'}</div>`;
      return;
    }
    const data = response.data;
    if (data.status === 'PASS') {
      out.innerHTML = `<div class="alert-box alert-success">✅ <b>Hồ sơ hợp lệ!</b> Không phát hiện nguy cơ xuất toán cho mã ${data.icd_code} (${data.disease_name}).</div>`;
    } else {
      let html = `<div class="alert-box alert-danger">⚠️ <b>Phát hiện ${data.total_alerts} nguy cơ xuất toán nghiêm trọng:</b><br><ul style="margin-left:14px; margin-top:4px;">`;
      data.alerts.forEach(a => {
        html += `<li><b>[${a.rule}]</b> ${a.title}: <span style="color:#64748b;">${a.remedy}</span></li>`;
      });
      html += `</ul></div>`;
      out.innerHTML = html;
    }
  });
});

// Search ICD
let searchTimer = null;
document.getElementById('searchKeyword').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  const kw = e.target.value.trim();
  if (kw.length < 2) return;
  searchTimer = setTimeout(() => {
    chrome.runtime.sendMessage({
      action: 'SEARCH_ICD',
      payload: { keyword: kw }
    }, (resp) => {
      const container = document.getElementById('searchResults');
      if (!resp || !resp.success || !resp.data.length) {
        container.innerHTML = `<div style="padding:8px; color:#94a3b8;">Không tìm thấy mã phù hợp</div>`;
        return;
      }
      container.innerHTML = resp.data.map(r => `
        <div class="res-item" onclick="selectIcd('${r.code}')">
          <span class="code-tag">${r.code}</span> — ${r.name_vn}
          ${r.must_use_subcode ? '<span style="color:#ef4444; font-size:9px;">(Cần mã chi tiết)</span>' : ''}
          ${r.not_allowed_primary ? '<span style="color:#f59e0b; font-size:9px;">(Không làm bệnh chính)</span>' : ''}
        </div>
      `).join('');
    });
  }, 250);
});

// Autofill
document.getElementById('btnGenNote').addEventListener('click', () => {
  const icd = document.getElementById('autoIcd').value.trim();
  const procs = document.getElementById('autoProcs').value.split(',').map(s => s.trim()).filter(Boolean);
  
  chrome.runtime.sendMessage({
    action: 'SUGGEST_NOTE',
    payload: { icd_code: icd, procedures: procs }
  }, (resp) => {
    if (resp && resp.success) {
      document.getElementById('noteContent').value = resp.data.suggested_note;
    }
  });
});

document.getElementById('btnInjectNote').addEventListener('click', () => {
  const note = document.getElementById('noteContent').value;
  if (!note) return;
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]?.id) {
      chrome.tabs.sendMessage(tabs[0].id, {
        action: 'INJECT_CLINICAL_NOTE',
        note: note
      });
    }
  });
});
