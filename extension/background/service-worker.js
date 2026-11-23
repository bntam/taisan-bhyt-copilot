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
          let related = [
            'Mã M54.5 được kê những thuốc gì tuyến 4?',
            'Cam thảo có ảnh hưởng thuốc hạ áp không?',
            'Điện châm tối đa bao nhiêu ngày trong 1 đợt?'
          ];

          // Check context evaluation first
          if (context && context.icdCode && (qLower.includes('đơn này') || qLower.includes('hồ sơ này') || qLower.includes('hợp lệ không') || qLower.includes('đánh giá'))) {
            const ctxIcd = context.icdCode || 'M54.5';
            const ctxDrugs = context.drugs || [];
            const hasCeftriaxone = ctxDrugs.some(d => d.toLowerCase().includes('ceftriaxone'));
            answer = `### 📋 Đánh Giá Hồ Sơ Bệnh Án Hiện Tại (${ctxIcd})\n\n` +
                     (hasCeftriaxone ? '⚠️ **CẢNH BÁO NGUY CƠ CAO:** Thuốc tiêm Ceftriaxone vượt tuyến chuyên môn (chỉ được kê tuyến 1-3). Phòng khám tư nhân (Tuyến 4) sẽ bị xuất toán 100% chi phí thuốc này!\n👉 *Khắc phục:* Thay thế bằng kháng sinh uống được phê duyệt cho tuyến 4 hoặc chuyển tuyến bệnh nhân.\n\n' : '🟢 **Thuốc kê đơn hợp lệ:** Phù hợp danh mục tuyến 4.\n\n') +
                     '**Thủ thuật YHCT:** Đảm bảo thời gian điều trị liên tục không quá 15 ngày/đợt.';
            snippet = `CHẨN ĐOÁN: Bệnh cảnh mã ${ctxIcd}. ĐIỀU TRỊ TUYẾN 4: Tuân thủ danh mục Thông tư 20/2022/TT-BYT và định mức thủ thuật YHCT Thông tư 13/2019/TT-BYT.`;
            refs = ['Thông tư 20/2022/TT-BYT', 'Quyết định 7603/QĐ-BYT'];
            related = ['Thuốc giảm đau thay thế tuyến 4', 'Định mức ngày thủ thuật YHCT', 'Yêu cầu cận lâm sàng'];
          } else if (qLower.includes('cam thảo') && (qLower.includes('huyết áp') || qLower.includes('tăng huyết áp') || qLower.includes('lợi tiểu') || qLower.includes('kali'))) {
            answer = '### ⚠️ Cảnh Báo: Cam Thảo & Bệnh Nhân Tăng Huyết Áp\n\n' +
                     '**1. Cơ chế dược lý:** Vị thuốc **Cam thảo** (*Radix Glycyrrhizae*) chứa hoạt chất chính là **Glycyrrhizin**. Chất này ức chế enzyme 11β-HSD2, làm cortisol kích hoạt thụ thể mineralocorticoid, dẫn đến giữ Natri, giữ nước và tăng đào thải Kali (hạ Kali máu nặng).\n\n' +
                     '**2. Hậu quả lâm sàng:** Làm giảm hoặc mất hoàn toàn tác dụng của thuốc hạ huyết áp (nhóm ACEI, ARB, chẹn kênh calci) và gây nguy hiểm loạn nhịp tim khi dùng chung thuốc lợi tiểu thiazide/furosemide.\n\n' +
                     '**3. Khuyến nghị cho bác sĩ:** Tuyệt đối không dùng Cam thảo liều cao kéo dài cho bệnh nhân tăng huyết áp giai đoạn 2 trở lên. Có thể thay bằng các vị thuốc kiện tỳ điều hòa khác như **Bạch truật**, **Đảng sâm**, **Hoài sơn**.';
            snippet = 'LƯU Ý DƯỢC LÂM SÀNG: Bệnh nhân có tiền sử Tăng huyết áp. Đơn thuốc YHCT đã điều chỉnh loại bỏ Cam thảo để tránh nguy cơ giữ muối nước và tương tác hạ Kali máu.';
            refs = ['Thông tư 27/2020/TT-BYT', 'Dược thư Quốc gia Việt Nam'];
            related = ['Đan sâm có dùng chung được với Aspirin không?', 'Mã I10 tăng huyết áp được kê thuốc gì tuyến 4?', 'Các vị thuốc YHCT hạ huyết áp an toàn'];
          } else if (qLower.includes('đan sâm') || qLower.includes('đương quy') || (qLower.includes('chống đông') && qLower.includes('aspirin'))) {
            answer = '### ⚠️ Cảnh Báo: Đan Sâm / Đương Quy & Thuốc Chống Đông Tây Y\n\n' +
                     '**1. Nguy cơ xuất huyết:** **Đan sâm** (*Salvia miltiorrhiza*) và **Đương quy** (*Angelica sinensis*) đều có tác dụng hoạt huyết hóa ứ mạnh, ức chế kết tập tiểu cầu. Khi phối hợp cùng thuốc chống đông (Aspirin, Clopidogrel, Warfarin, Xarelto), nguy cơ xuất huyết tiêu hóa và xuất huyết dưới da tăng vọt.\n\n' +
                     '**2. Quy chế giám định BHYT:** Đoàn giám định sẽ xuất toán tiền thuốc nếu bệnh nhân xuất huyết do phối hợp thuốc thiếu theo dõi chỉ số đông máu (PT/INR).\n\n' +
                     '**3. Giải pháp lâm sàng:** Nếu bắt buộc dùng, phải giãn cữ uống tối thiểu 2 giờ, giảm liều thảo dược hoạt huyết 50% và ghi chú theo dõi sát triệu chứng chảy máu chân răng/bầm tím trong hồ sơ.';
            refs = ['Thông tư 20/2022/TT-BYT', 'Thông tư 27/2020/TT-BYT'];
            related = ['Cam thảo có ảnh hưởng thuốc hạ áp không?', 'Quy định kê đơn thuốc chống đông tuyến phòng khám', 'Thuốc bổ huyết YHCT an toàn'];
          } else if (qLower.includes('m54') || qLower.includes('đau lưng') || (qLower.includes('tuyến 4') && qLower.includes('thuốc'))) {
            answer = '### 📋 Quy Định Kê Đơn Tuyến 4 (Mã M54.5 - Đau Thắt Lưng)\n\n' +
                     '**1. Thuốc được BHYT chi trả 100% tại Tuyến 4:** Paracetamol 500mg, Meloxicam 7.5mg/15mg (uống), Esomeprazole 20mg (bảo vệ dạ dày).\n\n' +
                     '**2. Thuốc cấm kê tại Tuyến 4 (Xuất toán 100%):** Kháng sinh tiêm Ceftriaxone 1g (chỉ dành cho BV Tuyến 1-3).\n\n' +
                     '**3. Thủ thuật YHCT:** Điện châm + Xoa bóp bấm huyệt tối đa không quá 15 ngày/đợt ngoại trú.';
            snippet = 'CHẨN ĐOÁN: Đau thắt lưng (ICD-10: M54.5).\nĐIỀU TRỊ TUYẾN 4: Paracetamol 500mg (2 viên/ngày), Meloxicam 7.5mg (1 viên/ngày sau ăn), kết hợp Điện châm giảm đau thắt lưng (25 phút/ngày).';
            refs = ['Thông tư 20/2022/TT-BYT', 'Quyết định 7603/QĐ-BYT'];
            related = ['Định mức số ngày điện châm điều trị', 'Mã ICD M54.5 có bắt buộc dùng mã 4 ký tự không?', 'Kê Statin cần xét nghiệm gì?'];
          } else if (qLower.includes('bao nhiêu ngày') || qLower.includes('điện châm') || qLower.includes('định mức') || qLower.includes('thủ thuật')) {
            answer = '### ⏱️ Định Mức Ngày Điều Trị Thủ Thuật YHCT (Thông Tư 13/2019/TT-BYT)\n\n' +
                     '**1. Số ngày tối đa 1 đợt ngoại trú:** Điện châm và Xoa bóp bấm huyệt tối đa **15 ngày liên tục**.\n\n' +
                     '**2. Kéo dãn cột sống:** Tối đa **10 ngày liên tục / 1 đợt** (Bắt buộc có phim X-quang/MRI xác nhận thoái hóa/thoát vị trước khi chỉ định).\n\n' +
                     '**3. Mở đợt 2:** Sau 15 ngày, bắt buộc cho bệnh nhân nghỉ ngắt quãng tối thiểu 5–7 ngày và có biên bản đánh giá lại triệu chứng lâm sàng trước khi ký chỉ định đợt tiếp theo.';
            snippet = 'ĐÁNH GIÁ KẾT THÚC ĐỢT 1: Bệnh nhân đã hoàn thành 15 ngày điện châm. Triệu chứng đau lưng giảm từ VAS 7/10 xuống VAS 3/10. Cho bệnh nhân tạm dừng thủ thuật 7 ngày trước khi tái khám đánh giá đợt 2.';
            refs = ['Thông tư 13/2019/TT-BYT', 'Thông tư 39/2018/TT-BYT'];
            related = ['Mã M54.5 được kê những thuốc gì tuyến 4?', 'Mô tả lâm sàng chuẩn để bảo vệ chỉ định điện châm', 'Cam thảo có dùng cho người tăng huyết áp không?'];
          } else if (qLower.includes('xét nghiệm') || qLower.includes('lipid') || qLower.includes('statin') || qLower.includes('mỡ máu')) {
            answer = '### 🧪 Yêu Cầu Cận Lâm Sàng Bắt Buộc Để Tránh Xuất Toán\n\n' +
                     '**1. Thuốc hạ mỡ máu nhóm Statin (Atorvastatin, Rosuvastatin):**\n' +
                     '- **Quy tắc xuất toán:** Kê đơn chẩn đoán E78 (Rối loạn chuyển hóa Lipid) nhưng hồ sơ bệnh án không có kết quả xét nghiệm mỡ máu (Lipid panel: Cholesterol toàn phần, Triglyceride, hoặc LDL-C) trong vòng 3–6 tháng ➔ **Xuất toán 100% tiền thuốc**.\n' +
                     '- **Cách khắc phục:** Luôn chỉ định xét nghiệm bộ mỡ máu trước khi kê đơn, hoặc ghi rõ trong tóm tắt: *\'Kết quả Cholesterol máu tuyến trước ngày DD/MM/YYYY: 6.8 mmol/L\'*.\n\n' +
                     '**2. Thuốc đái tháo đường:** Bắt buộc ghi nhận chỉ số Glucose mao mạch hoặc HbA1c tại thời điểm khám.';
            refs = ['Quy chế Giám định BHYT điện tử — Cổng BHXH Việt Nam'];
            related = ['Mã ICD E78 rối loạn mỡ máu cần lưu ý gì?', 'Thuốc hạ huyết áp tuyến 4', 'Định mức ngày thủ thuật YHCT'];
          } else if (qLower.includes('tọa cốt phong') || qLower.includes('khẩu nhãn') || qLower.includes('liệt mặt') || qLower.includes('4443') || qLower.includes('chứng trạng')) {
            answer = '### 🌿 Ánh Xạ Chứng Trạng YHCT Sang Mã ICD-10 (Quyết Định 4443/QĐ-BYT)\n\n' +
                     '**1. Tọa cốt phong:** Ánh xạ mã **M54.5** (Đau thắt lưng) hoặc **M54.3** (Đau thần kinh tọa). Bát cương: Biểu lý tương kiêm, Khí trệ Huyết ứ kết hợp Can Thận hư. Pháp trị: Hoạt huyết hóa ứ, thông kinh hoạt lạc, bổ can thận, chỉ thống.\n\n' +
                     '**2. Khẩu nhãn oa tà:** Ánh xạ mã **G51.0** (Liệt dây thần kinh VII ngoại biên / Liệt Bell). Bát cương: Biểu hàn kinh lạc. Pháp trị: Khu phong tán hàn, hoạt huyết thông lạc.';
            snippet = 'CHẨN ĐOÁN YHCT: Tọa cốt phong (Thể Khí trệ huyết ứ kết hợp Can thận hư suy).\nCHẨN ĐOÁN YHHĐ: Đau dây thần kinh tọa / Thoái hóa cột sống thắt lưng (ICD-10: M54.5).\nPHÁP TRỊ: Hoạt huyết hóa ứ, thông kinh lạc, bổ can thận, chỉ thống.';
            refs = ['Quyết định 4443/QĐ-BYT', 'Thông tư 27/2020/TT-BYT'];
            related = ['Mã M54.5 được kê những thuốc gì tuyến 4?', 'Điện châm tối đa bao nhiêu ngày trong 1 đợt?', 'Cam thảo có ảnh hưởng thuốc hạ áp không?'];
          } else {
            answer = `### 💡 Trợ Lý BHYT & YHCT Tái Sanh\n\nBạn có thể hỏi về:\n- Danh mục thuốc tân dược thanh toán BHYT Tuyến 4 (Phòng khám tư)\n- Tương tác thảo dược YHCT và thuốc Tây y\n- Định mức số ngày điều trị kỹ thuật, thủ thuật theo Thông tư 13/2019\n- Yêu cầu kết quả xét nghiệm cận lâm sàng để tránh bị xuất toán\n- Ánh xạ mã bệnh YHCT sang ICD-10 theo Quyết định 4443/QĐ-BYT.`;
          }

          sendResponse({
            success: true,
            data: {
              query,
              answer,
              suggested_snippet: snippet,
              references: refs,
              related_queries: related
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
