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
