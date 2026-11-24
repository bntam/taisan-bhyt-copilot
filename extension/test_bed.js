/**
 * Test Bed Controller for HIS-PRO 2026 Simulation
 * External script file compliant with Chrome Extension Manifest V3 CSP (no inline scripts).
 */

document.addEventListener('DOMContentLoaded', () => {
  const icdInput = document.getElementById('icd10-code');
  const diseaseInput = document.getElementById('ten-benh');
  const daysInput = document.getElementById('so-ngay-dieu-tri');
  const notesTextarea = document.getElementById('clinical-notes');
  const rxTbody = document.getElementById('prescriptionTbody');

  const procDienCham = document.getElementById('proc-dien-cham');
  const procXoaBop = document.getElementById('proc-xoa-bop');
  const procCuuNgai = document.getElementById('proc-cuu-ngai');
  const procKeoNan = document.getElementById('proc-keo-nan');

  function dispatchChanges() {
    if (icdInput) {
      icdInput.dispatchEvent(new Event('input', { bubbles: true }));
      icdInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (daysInput) {
      daysInput.dispatchEvent(new Event('input', { bubbles: true }));
      daysInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  // Preset 1: High Risk (M54.5 + Ceftriaxone Tuyến 4 + 18 Ngày ĐT)
  const btnHighRisk = document.getElementById('btnPresetHighRisk');
  if (btnHighRisk) {
    btnHighRisk.addEventListener('click', () => {
      if (icdInput) icdInput.value = 'M54.5';
      if (diseaseInput) diseaseInput.value = 'Đau lưng dưới';
      if (daysInput) daysInput.value = 18;
      if (procDienCham) procDienCham.checked = true;
      if (procXoaBop) procXoaBop.checked = true;
      if (procCuuNgai) procCuuNgai.checked = false;
      if (procKeoNan) procKeoNan.checked = false;
      if (notesTextarea) notesTextarea.value = '';

      if (rxTbody) {
        rxTbody.innerHTML = `
          <tr class="drug-row"><td>1</td><td><strong>Ceftriaxone 1g</strong></td><td>Tiêm bắp/tĩnh mạch</td><td>1 lọ/ngày</td></tr>
          <tr class="drug-row"><td>2</td><td><strong>Atorvastatin 20mg</strong></td><td>Uống</td><td>1 viên/ngày buổi tối</td></tr>
          <tr class="drug-row"><td>3</td><td><strong>Paracetamol 500mg</strong></td><td>Uống</td><td>1 viên x 2 lần/ngày</td></tr>
          <tr class="drug-row"><td>4</td><td><strong>Đan sâm (Radix Salviae miltiorrhizae)</strong></td><td>Sắc uống</td><td>12g/ngày</td></tr>
          <tr class="drug-row"><td>5</td><td><strong>Aspirin 81mg</strong></td><td>Uống</td><td>1 viên/ngày</td></tr>
        `;
      }
      dispatchChanges();
    });
  }

  // Preset 2: Bell's Palsy (G51.0 - Cần Autofill YHCT)
  const btnBell = document.getElementById('btnPresetBellPalsy');
  if (btnBell) {
    btnBell.addEventListener('click', () => {
      if (icdInput) icdInput.value = 'G51.0';
      if (diseaseInput) diseaseInput.value = 'Liệt Bell / Liệt dây thần kinh số VII ngoại biên';
      if (daysInput) daysInput.value = 10;
      if (procDienCham) procDienCham.checked = true;
      if (procXoaBop) procXoaBop.checked = true;
      if (procCuuNgai) procCuuNgai.checked = true;
      if (procKeoNan) procKeoNan.checked = false;
      if (notesTextarea) notesTextarea.value = '';

      if (rxTbody) {
        rxTbody.innerHTML = `
          <tr class="drug-row"><td>1</td><td><strong>Paracetamol 500mg</strong></td><td>Uống</td><td>1 viên x 2 lần/ngày</td></tr>
          <tr class="drug-row"><td>2</td><td><strong>Cam thảo (Radix Glycyrrhizae)</strong></td><td>Sắc uống</td><td>6g/ngày</td></tr>
        `;
      }
      dispatchChanges();
    });
  }

  // Preset 3: Clean Compliant Record (Pass BHYT)
  const btnClean = document.getElementById('btnPresetClean');
  if (btnClean) {
    btnClean.addEventListener('click', () => {
      if (icdInput) icdInput.value = 'M54.5';
      if (diseaseInput) diseaseInput.value = 'Đau lưng dưới';
      if (daysInput) daysInput.value = 10;
      if (procDienCham) procDienCham.checked = true;
      if (procXoaBop) procXoaBop.checked = true;
      if (procCuuNgai) procCuuNgai.checked = false;
      if (procKeoNan) procKeoNan.checked = false;
      if (notesTextarea) notesTextarea.value = '';

      if (rxTbody) {
        rxTbody.innerHTML = `
          <tr class="drug-row"><td>1</td><td><strong>Meloxicam 7.5mg</strong></td><td>Uống</td><td>1 viên/ngày sau ăn</td></tr>
          <tr class="drug-row"><td>2</td><td><strong>Esomeprazole 20mg</strong></td><td>Uống</td><td>1 viên/ngày trước ăn sáng</td></tr>
          <tr class="drug-row"><td>3</td><td><strong>Paracetamol 500mg</strong></td><td>Uống</td><td>1 viên khi đau nhiều</td></tr>
        `;
      }
      dispatchChanges();
    });
  }

  // Preset 4: Legacy ASP.NET WebForms + DevExpress + Iframe HIS
  const btnLegacy = document.getElementById('btnPresetAspNetLegacy');
  if (btnLegacy) {
    btnLegacy.addEventListener('click', () => {
      if (icdInput) icdInput.value = 'M16.0';
      if (diseaseInput) diseaseInput.value = 'Thoái hóa khớp háng nguyên phát, hai bên (Bilateral primary coxarthrosis)';
      if (daysInput) daysInput.value = 12;
      if (procDienCham) procDienCham.checked = true;
      if (procXoaBop) procXoaBop.checked = true;
      if (procCuuNgai) procCuuNgai.checked = false;
      if (procKeoNan) procKeoNan.checked = false;
      if (notesTextarea) notesTextarea.value = '';

      if (rxTbody) {
        rxTbody.innerHTML = `
          <tr class="drug-row dxgvDataRow"><td>1</td><td><strong>Meloxicam 15mg</strong></td><td>Uống</td><td>1 viên/ngày sau ăn</td></tr>
          <tr class="drug-row dxgvDataRow"><td>2</td><td><strong>Celecoxib 200mg</strong></td><td>Uống</td><td>1 viên/ngày (⚠️ Cảnh báo trùng NSAID)</td></tr>
          <tr class="drug-row dxgvDataRow"><td>3</td><td><strong>Paracetamol 500mg</strong></td><td>Uống</td><td>1 viên x 2 lần/ngày</td></tr>
        `;
      }
      dispatchChanges();
    });
  }
});
