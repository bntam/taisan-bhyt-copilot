/**
 * BHYT Clinical Copilot - Background Service Worker
 * Manifest V3 compliant, ephemeral-safe lifecycle.
 */

// Default configuration
const DEFAULT_CONFIG = {
  hospital_level: '4', // Tuyến 4 (Phòng khám đa khoa / Trạm Y tế)
  clinic_name: 'Phòng khám YHCT Tài Sanh',
  auto_audit_enabled: true,
  herb_drug_check_enabled: true,
  autofill_template_mode: 'standard_moh',
  api_endpoint: 'http://127.0.0.1:8123/api',
  stats: {
    total_audits: 0,
    warnings_prevented: 0,
    notes_autofilled: 0
  }
};

// Lifecycle initialization
chrome.runtime.onInstalled.addListener(async (details) => {
  console.log('[BHYT Copilot] Extension installed/updated:', details.reason);
  const existing = await chrome.storage.local.get('config');
  if (!existing.config) {
    await chrome.storage.local.set({ config: DEFAULT_CONFIG });
  }
  await chrome.action.setBadgeText({ text: '' });
});

// Clean up tab-specific state on close
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const key = `audit_tab_${tabId}`;
  await chrome.storage.local.remove(key);
});

// Reset badge on tab navigation
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (changeInfo.status === 'loading') {
    await chrome.action.setBadgeText({ tabId, text: '' });
  }
});

// Central message routing hub
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      const tabId = sender.tab?.id || message.tabId;

      switch (message.type) {
        case 'AUDIT_STATUS_CHANGED': {
          const { alertCount = 0, highRiskCount = 0, icdCode = '', diseaseName = '', alerts = [] } = message.payload || {};
          
          if (tabId) {
            // Update Tab Badge
            if (highRiskCount > 0) {
              await chrome.action.setBadgeText({ tabId, text: `${highRiskCount}!` });
              await chrome.action.setBadgeBackgroundColor({ tabId, color: '#DC2626' }); // Red-600
            } else if (alertCount > 0) {
              await chrome.action.setBadgeText({ tabId, text: `${alertCount}` });
              await chrome.action.setBadgeBackgroundColor({ tabId, color: '#D97706' }); // Amber-600
            } else if (icdCode) {
              await chrome.action.setBadgeText({ tabId, text: 'OK' });
              await chrome.action.setBadgeBackgroundColor({ tabId, color: '#059669' }); // Emerald-600
            } else {
              await chrome.action.setBadgeText({ tabId, text: '' });
            }

            // Persist audit payload for popup
            const key = `audit_tab_${tabId}`;
            await chrome.storage.local.set({
              [key]: {
                timestamp: Date.now(),
                tabId,
                icdCode,
                diseaseName,
                alertCount,
                highRiskCount,
                alerts
              }
            });
          }

          // Increment statistics
          const { config = DEFAULT_CONFIG } = await chrome.storage.local.get('config');
          config.stats = config.stats || { total_audits: 0, warnings_prevented: 0, notes_autofilled: 0 };
          config.stats.total_audits = (config.stats.total_audits || 0) + 1;
          if (highRiskCount > 0) {
            config.stats.warnings_prevented = (config.stats.warnings_prevented || 0) + highRiskCount;
          }
          await chrome.storage.local.set({ config });

          sendResponse({ success: true });
          break;
        }

        case 'GET_CURRENT_AUDIT': {
          let targetTabId = message.tabId;
          if (!targetTabId) {
            const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
            targetTabId = activeTab?.id;
          }
          if (targetTabId) {
            const key = `audit_tab_${targetTabId}`;
            const stored = await chrome.storage.local.get(key);
            sendResponse({ success: true, data: stored[key] || null, tabId: targetTabId });
          } else {
            sendResponse({ success: false, error: 'No active tab found' });
          }
          break;
        }

        case 'RECORD_AUTOFILL_EVENT': {
          const { config = DEFAULT_CONFIG } = await chrome.storage.local.get('config');
          config.stats = config.stats || { total_audits: 0, warnings_prevented: 0, notes_autofilled: 0 };
          config.stats.notes_autofilled = (config.stats.notes_autofilled || 0) + 1;
          await chrome.storage.local.set({ config });
          sendResponse({ success: true, count: config.stats.notes_autofilled });
          break;
        }

        case 'ASK_CHAT_COPILOT': {
          const { query, context = {} } = message.payload || {};
          const { config = DEFAULT_CONFIG } = await chrome.storage.local.get('config');
          const apiEndpoint = config.api_endpoint || 'http://127.0.0.1:8123/api';

          try {
            const resp = await fetch(`${apiEndpoint}/chat`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ message: query, context })
            });
            if (resp.ok) {
              const data = await resp.json();
              sendResponse({ success: true, data });
              return;
            }
          } catch (e) {
            console.log('[BHYT Copilot] Local API offline, using built-in offline RAG response');
          }

          // Offline fallback response generator based on query keywords
          const qLower = (query || '').toLowerCase();
          let answer = '';
          let snippet = '';
          let refs = ['Thông tư 20/2022/TT-BYT', 'Thông tư 27/2020/TT-BYT', 'Thông tư 13/2019/TT-BYT'];

          if (qLower.includes('cam thảo') && (qLower.includes('huyết áp') || qLower.includes('tăng huyết áp'))) {
            answer = '### ⚠️ Cảnh Báo: Cam Thảo & Bệnh Nhân Tăng Huyết Áp\n\n' +
                     '**1. Cơ chế:** Vị thuốc **Cam thảo** (*Glycyrrhizin*) làm giảm đào thải Natri và tăng thải Kali qua thận, gây tăng thể tích dịch tuần hoàn và hạ Kali máu.\n\n' +
                     '**2. Tương tác:** Triệt tiêu hoặc làm giảm rõ rệt hiệu quả của các nhóm thuốc hạ áp (Amlodipine, Enalapril, Losartan) và gây nguy cơ loạn nhịp khi dùng chung thuốc lợi tiểu.\n\n' +
                     '**3. Khuyến nghị:** Loại bỏ Cam thảo khỏi bài thuốc YHCT ở người tăng huyết áp; thay thế bằng Bạch truật hoặc Đảng sâm.';
            snippet = 'LƯU Ý DƯỢC LÂM SÀNG: Bệnh nhân có tiền sử Tăng huyết áp. Đơn thuốc YHCT đã điều chỉnh loại bỏ Cam thảo để tránh nguy cơ giữ muối nước và tương tác hạ Kali máu.';
          } else if (qLower.includes('m54') || qLower.includes('đau lưng')) {
            answer = '### 📋 Quy Định Kê Đơn Tuyến 4 (Mã M54.5 - Đau Thắt Lưng)\n\n' +
                     '**1. Thuốc được BHYT chi trả 100% tại Tuyến 4:** Paracetamol 500mg, Meloxicam 7.5mg/15mg (uống), Esomeprazole 20mg (bảo vệ dạ dày).\n\n' +
                     '**2. Thuốc cấm kê tại Tuyến 4 (Xuất toán 100%):** Kháng sinh tiêm Ceftriaxone 1g (chỉ dành cho BV Tuyến 1-3).\n\n' +
                     '**3. Thủ thuật YHCT:** Điện châm + Xoa bóp bấm huyệt tối đa không quá 15 ngày/đợt ngoại trú.';
            snippet = 'CHẨN ĐOÁN: Đau thắt lưng (ICD-10: M54.5). ĐIỀU TRỊ TUYẾN 4: Paracetamol 500mg (2v/ngày), Meloxicam 7.5mg (1v/ngày sau ăn), kết hợp Điện châm giảm đau thắt lưng 25 phút/ngày.';
          } else if (qLower.includes('bao nhiêu ngày') || qLower.includes('điện châm') || qLower.includes('định mức')) {
            answer = '### ⏱️ Định Mức Ngày Điều Trị Thủ Thuật YHCT (Thông Tư 13/2019/TT-BYT)\n\n' +
                     '**1. Số ngày tối đa 1 đợt ngoại trú:** Điện châm và Xoa bóp bấm huyệt tối đa **15 ngày liên tục**.\n\n' +
                     '**2. Mở đợt 2:** Sau 15 ngày, bắt buộc cho bệnh nhân nghỉ ngắt quãng tối thiểu 5–7 ngày và có biên bản đánh giá lại triệu chứng lâm sàng trước khi ký chỉ định đợt tiếp theo.';
            snippet = 'ĐÁNH GIÁ KẾT THÚC ĐỢT 1: Bệnh nhân đã hoàn thành 15 ngày điện châm. Triệu chứng đau lưng giảm từ VAS 7/10 xuống VAS 3/10. Cho bệnh nhân tạm dừng thủ thuật 7 ngày trước khi tái khám đánh giá đợt 2.';
          } else {
            answer = `### 💡 Trợ Lý BHYT & YHCT Tái Sanh\n\nBạn có thể hỏi về:\n- Danh mục thuốc tân dược thanh toán BHYT Tuyến 4 (Phòng khám tư)\n- Tương tác thảo dược YHCT và thuốc Tây y\n- Định mức số ngày điều trị kỹ thuật, thủ thuật theo Thông tư 13/2019\n- Yêu cầu kết quả xét nghiệm để tránh bị xuất toán.`;
          }

          sendResponse({
            success: true,
            data: {
              query,
              answer,
              suggested_snippet: snippet,
              references: refs,
              related_queries: [
                'Mã M54.5 được kê những thuốc gì tuyến 4?',
                'Cam thảo có ảnh hưởng thuốc hạ áp không?',
                'Điện châm tối đa bao nhiêu ngày trong 1 đợt?'
              ]
            }
          });
          break;
        }

        case 'GET_CONFIG': {
          const { config = DEFAULT_CONFIG } = await chrome.storage.local.get('config');
          sendResponse({ success: true, config });
          break;
        }

        case 'UPDATE_CONFIG': {
          const { config = DEFAULT_CONFIG } = await chrome.storage.local.get('config');
          const updated = { ...config, ...message.payload };
          await chrome.storage.local.set({ config: updated });
          sendResponse({ success: true, config: updated });
          break;
        }

        default:
          sendResponse({ success: false, error: `Unknown message type: ${message.type}` });
      }
    } catch (err) {
      console.error('[BHYT Copilot SW Error]', err);
      sendResponse({ success: false, error: err.message });
    }
  })();
  return true; // Keep channel open for async response
});
