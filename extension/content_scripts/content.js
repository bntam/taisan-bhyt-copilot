// In-browser DOM Content Script for TaiSanh BHYT Copilot
console.log("[TaiSanh BHYT Copilot] Injected successfully into HIS/EMR web interface.");

// 1. Create floating Copilot Badge
const badge = document.createElement("div");
badge.id = "taisan-bhyt-badge";
badge.innerHTML = `
  <div class="taisan-badge-inner" id="taisanBadgeToggle">
    <span class="taisan-icon">🛡️</span>
    <span class="taisan-title">BHYT Copilot</span>
    <span class="taisan-status-dot" id="taisanDot"></span>
  </div>
`;
document.body.appendChild(badge);

// 2. Listen for Auto-fill messages from Popup
chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
  if (req.action === 'INJECT_CLINICAL_NOTE') {
    const textareas = document.querySelectorAll("textarea, div[contenteditable='true']");
    let target = null;
    
    // Look for clinical examination textareas
    for (const el of textareas) {
      const name = (el.name || el.id || el.placeholder || el.className || '').toLowerCase();
      if (/khám|kham|triệu chứng|trieu_chung|lâm sàng|lam_sang|bệnh sử|benh_su|mô tả|mo_ta|note/i.test(name)) {
        target = el;
        break;
      }
    }
    
    // Fallback to active element or first textarea
    if (!target) {
      target = document.activeElement && (document.activeElement.tagName === 'TEXTAREA' || document.activeElement.isContentEditable) 
        ? document.activeElement 
        : textareas[0];
    }

    if (target) {
      if (target.isContentEditable) {
        target.innerText = req.note;
      } else {
        target.value = req.note;
      }
      target.dispatchEvent(new Event('input', { bubbles: true }));
      target.dispatchEvent(new Event('change', { bubbles: true }));
      target.style.outline = "2px solid #10b981";
      setTimeout(() => target.style.outline = "", 2000);
      alert("✅ Đã tự động điền mô tả lâm sàng hợp thức hóa BHYT!");
    } else {
      alert("⚠️ Không tìm thấy ô nhập Bệnh án / Khám lâm sàng trên trang hiện tại. Vui lòng bấm chuột vào ô cần điền rồi thử lại!");
    }
  }
});
