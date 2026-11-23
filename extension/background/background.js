// Background Service Worker for TaiSanh BHYT Copilot
const API_BASE = "http://127.0.0.1:8123/api";

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'VALIDATE_PRESCRIPTION') {
    fetch(`${API_BASE}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request.payload)
    })
    .then(r => r.json())
    .then(data => sendResponse({ success: true, data }))
    .catch(err => sendResponse({ success: false, error: err.message }));
    return true; // Keep channel open for async response
  }

  if (request.action === 'SEARCH_ICD') {
    fetch(`${API_BASE}/search-icd?q=${encodeURIComponent(request.payload.keyword)}&limit=10`)
    .then(r => r.json())
    .then(data => sendResponse({ success: true, data }))
    .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (request.action === 'SUGGEST_NOTE') {
    fetch(`${API_BASE}/suggest-note`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request.payload)
    })
    .then(r => r.json())
    .then(data => sendResponse({ success: true, data }))
    .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});
