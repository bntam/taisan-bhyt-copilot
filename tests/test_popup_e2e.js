const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function testPopup() {
  console.log('--- TESTING POPUP UI & CATALOG SEARCH ---');
  const pathToExtension = path.resolve(__dirname, '../extension');
  const screenshotDir = path.resolve(__dirname, '../test_artifacts');

  const context = await chromium.launchPersistentContext('/tmp/bhyt_popup_prof_' + Date.now(), {
    headless: false,
    ignoreDefaultArgs: ['--disable-extensions'],
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--headless=new',
      `--disable-extensions-except=${pathToExtension}`,
      `--load-extension=${pathToExtension}`
    ],
    viewport: { width: 450, height: 650 }
  });

  const sw = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  const extId = sw.url().split('/')[2];
  console.log('Extension ID:', extId);

  const popupUrl = `chrome-extension://${extId}/popup/popup.html`;
  console.log('Opening popup at:', popupUrl);

  const page = await context.newPage();
  await page.goto(popupUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);

  // 1. Verify Header
  const title = await page.locator('.brand-title').innerText();
  console.log('Popup brand title:', title);

  // 2. Click Search Tab
  console.log('Switching to Catalog Search tab...');
  await page.click('button[data-tab="tab-search"]');
  await page.waitForTimeout(600);

  // Type search query
  console.log('Searching "M54"...');
  await page.fill('#searchInput', 'M54.5');
  await page.waitForTimeout(500);

  const results = await page.locator('.search-result-card').allInnerTexts();
  console.log(`Found ${results.length} search results for M54.5:`);
  results.slice(0, 3).forEach(r => console.log('  -> ' + r.replace(/\n/g, ' • ')));

  if (results.length === 0 || !results[0].includes('M54.5')) {
    throw new Error('ICD-10 search failed for M54.5');
  }
  console.log('  -> [PASS] Fast ICD-10 Search verified.');

  // Search TCM Herbs
  console.log('Filtering by YHCT and searching "Đan sâm"...');
  await page.click('button[data-filter="yhct"]');
  await page.fill('#searchInput', 'Đan sâm');
  await page.waitForTimeout(500);

  const herbResults = await page.locator('.search-result-card').allInnerTexts();
  console.log('Found herb results:', herbResults.map(r => r.replace(/\n/g, ' • ')));
  if (herbResults.length === 0 || !herbResults[0].includes('Đan sâm')) {
    throw new Error('TCM herb search failed');
  }
  console.log('  -> [PASS] TCM Herb catalog search verified.');

  // 3. Switch to AI Clinical Chatbox Tab
  console.log('\n--- TESTING AI CLINICAL CHATBOX TAB ---');
  await page.click('button[data-tab="tab-chat"]');
  await page.waitForTimeout(500);

  // Click quick chip "Cam thảo"
  console.log('Clicking quick chip "Cam thảo"...');
  await page.click('button[data-chat-q*="Cam thảo"]');
  await page.waitForTimeout(1000);

  let chatMsgs = await page.locator('.popup-chat-msg').allInnerTexts();
  console.log(`Found ${chatMsgs.length} chat messages in popup.`);
  const lastMsg = chatMsgs[chatMsgs.length - 1];
  console.log('Chatbot response snippet:', lastMsg.substring(0, 160).replace(/\n/g, ' '));
  if (!lastMsg.toLowerCase().includes('cam thảo') && !lastMsg.toLowerCase().includes('glycyrrhizin')) {
    throw new Error('Chatbot response missing Cam Thảo knowledge');
  }
  console.log('  -> [PASS] Quick chip Q&A verified.');

  // Type custom question in Chatbox input
  console.log('Asking custom question: "Đan sâm có dùng chung với Aspirin không?"...');
  await page.fill('#popupChatInput', 'Đan sâm có dùng chung được với Aspirin không?');
  await page.click('#popupChatSendBtn');
  await page.waitForTimeout(1000);

  chatMsgs = await page.locator('.popup-chat-msg').allInnerTexts();
  const aspirinReply = chatMsgs[chatMsgs.length - 1];
  console.log('Aspirin response snippet:', aspirinReply.substring(0, 160).replace(/\n/g, ' '));
  if (!aspirinReply.toLowerCase().includes('xuất huyết') && !aspirinReply.toLowerCase().includes('tiểu cầu')) {
    throw new Error('Chatbot response missing bleeding risk warning');
  }
  console.log('  -> [PASS] Custom question & bleeding warning verified.');

  const snapChat = path.join(screenshotDir, '05_popup_chatbox_verified.png');
  await page.screenshot({ path: snapChat });
  console.log(`  -> Screenshot saved: ${snapChat}`);

  // 4. Switch to Settings Tab
  console.log('\nSwitching to Settings tab...');
  await page.click('button[data-tab="tab-settings"]');
  await page.waitForTimeout(400);

  const statVal = await page.locator('#statAudits').innerText();
  console.log('Stat audits displayed:', statVal);

  const snapPopup = path.join(screenshotDir, '04_popup_ui_search_verified.png');
  await page.screenshot({ path: snapPopup });
  console.log(`  -> Screenshot saved: ${snapPopup}`);

  console.log('✅ POPUP UI AND IN-EXTENSION SEARCH FULLY VERIFIED!\n');
  await context.close();
}

testPopup().then(() => process.exit(0)).catch(err => {
  console.error('❌ Popup test failed:', err);
  process.exit(1);
});
