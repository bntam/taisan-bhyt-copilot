const { chromium } = require('playwright');
const http = require('http');
const path = require('path');
const fs = require('fs');

async function testSidePanelAndAutofill() {
  console.log('--- TESTING SIDEPANEL SEARCH TABS & 1-CLICK AUTOFILL E2E ---');
  const pathToExtension = path.resolve(__dirname, '../extension');

  // Start HTTP server for HIS Test Bed
  const PORT = 4577;
  const server = http.createServer((req, res) => {
    let reqUrl = req.url.split('?')[0];
    if (reqUrl === '/' || reqUrl === '/test_bed') reqUrl = '/test_bed.html';
    const filePath = path.join(pathToExtension, reqUrl);
    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      const ext = path.extname(filePath);
      const mimes = {
        '.html': 'text/html; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.png': 'image/png'
      };
      res.writeHead(200, { 'Content-Type': mimes[ext] || 'text/plain' });
      res.end(fs.readFileSync(filePath));
    } else {
      res.writeHead(404);
      res.end('Not found');
    }
  });
  await new Promise(resolve => server.listen(PORT, '127.0.0.1', resolve));

  const context = await chromium.launchPersistentContext('/tmp/bhyt_sp_prof_' + Date.now(), {
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
    viewport: { width: 1280, height: 800 }
  });

  try {
    const sw = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
    const extId = sw.url().split('/')[2];
    const sidePanelUrl = `chrome-extension://${extId}/sidepanel/sidepanel.html`;
    const testBedUrl = `http://127.0.0.1:${PORT}/test_bed.html`;

    // Open SidePanel in Tab 1 (before HIS tab is even opened!)
    const spPage = await context.newPage();
    await spPage.goto(sidePanelUrl, { waitUntil: 'networkidle' });
    await spPage.waitForTimeout(400);

    // 1. Test Search Tab & All Filter Buttons
    await spPage.click('.sp-tab-btn[data-tab="tab-search"]');
    await spPage.waitForTimeout(400);

    // Click ICD-10
    await spPage.click('.sp-filter-btn[data-filter="icd10"]');
    await spPage.waitForTimeout(250);
    let items = await spPage.locator('#spSearchResults .sp-search-item').allInnerTexts();
    if (items.length === 0 || !items.some(t => t.includes('ICD-10'))) {
      throw new Error('SidePanel ICD-10 filter failed');
    }
    console.log(`  [PASS] SidePanel ICD-10 tab rendered ${items.length} items.`);

    // Click Thuốc Tây
    await spPage.click('.sp-filter-btn[data-filter="thuoc"]');
    await spPage.waitForTimeout(250);
    items = await spPage.locator('#spSearchResults .sp-search-item').allInnerTexts();
    if (items.length === 0 || !items.some(t => t.includes('Thuốc Tây'))) {
      throw new Error('SidePanel Thuốc Tây filter failed');
    }
    console.log(`  [PASS] SidePanel Thuốc Tây tab rendered ${items.length} items.`);

    // Click Vị YHCT & search accentless "dan sam"
    await spPage.click('.sp-filter-btn[data-filter="yhct"]');
    await spPage.waitForTimeout(250);
    items = await spPage.locator('#spSearchResults .sp-search-item').allInnerTexts();
    if (items.length === 0 || !items.some(t => t.includes('Vị YHCT'))) {
      throw new Error('SidePanel Vị YHCT filter failed');
    }
    await spPage.fill('#spSearchInput', 'dan sam');
    await spPage.waitForTimeout(250);
    items = await spPage.locator('#spSearchResults .sp-search-item').allInnerTexts();
    if (items.length === 0 || !items.some(t => t.includes('Đan sâm'))) {
      throw new Error('SidePanel Vị YHCT accentless search for "dan sam" failed');
    }
    console.log(`  [PASS] SidePanel Vị YHCT tab + search "dan sam" -> ${items[0].replace(/\n/g, ' | ')}`);

    // Click Thủ thuật & search accentless "dien cham"
    await spPage.fill('#spSearchInput', '');
    await spPage.click('.sp-filter-btn[data-filter="thu_thuat"]');
    await spPage.waitForTimeout(250);
    items = await spPage.locator('#spSearchResults .sp-search-item').allInnerTexts();
    if (items.length === 0 || !items.some(t => t.includes('Thủ thuật'))) {
      throw new Error('SidePanel Thủ thuật filter failed');
    }
    await spPage.fill('#spSearchInput', 'dien cham');
    await spPage.waitForTimeout(250);
    items = await spPage.locator('#spSearchResults .sp-search-item').allInnerTexts();
    if (items.length === 0 || !items.some(t => t.includes('Điện châm'))) {
      throw new Error('SidePanel Thủ thuật accentless search for "dien cham" failed');
    }
    console.log(`  [PASS] SidePanel Thủ thuật tab + search "dien cham" -> ${items[0].replace(/\n/g, ' | ')}`);

    // Click Tất cả and search "điện châm" -> ensure Thủ thuật is not starved by ICD-10
    await spPage.click('.sp-filter-btn[data-filter="all"]');
    await spPage.fill('#spSearchInput', 'điện châm');
    await spPage.waitForTimeout(250);
    items = await spPage.locator('#spSearchResults .sp-search-item').allInnerTexts();
    if (!items.some(t => t.includes('Điện châm'))) {
      throw new Error('SidePanel "Tất cả" search starved Thủ thuật');
    }
    console.log('  [PASS] SidePanel "Tất cả" balanced search includes Thủ thuật.');

    // 2. Test 1-Click Autofill from SidePanel onto newly opened HIS Test Bed tab!
    await spPage.click('.sp-tab-btn[data-tab="tab-audit"]');
    await spPage.waitForTimeout(200);

    const hisPage = await context.newPage();
    await hisPage.goto(testBedUrl, { waitUntil: 'networkidle' });
    await hisPage.waitForTimeout(800);

    // Override chrome.tabs.query inside spPage so it resolves to the HIS tab (simulating Chrome SidePanel attached to HIS tab)
    await spPage.evaluate(async (url) => {
      const tabs = await chrome.tabs.query({});
      const target = tabs.find(t => t.url && t.url.includes('test_bed.html'));
      if (!target) throw new Error('Could not locate test_bed.html tab');
      const origQuery = chrome.tabs.query.bind(chrome.tabs);
      chrome.tabs.query = async (queryInfo) => {
        if (queryInfo && queryInfo.active) return [target];
        return origQuery(queryInfo);
      };
    }, testBedUrl);

    await spPage.click('#spBtnAutofill');
    await spPage.waitForTimeout(600);

    const spBtnText = await spPage.locator('#spBtnAutofill').innerText();
    const filledVal = await hisPage.locator('#clinical-notes').inputValue();
    console.log('  -> SidePanel Autofill Button Text:', spBtnText.trim());
    if (!spBtnText.includes('Đã Điền') || !filledVal.includes('LÝ DO VÀO VIỆN')) {
      throw new Error(`SidePanel 1-Click Autofill failed! btn="${spBtnText}", val="${filledVal}"`);
    }
    console.log('  [PASS] SidePanel 1-Click Autofill filled HIS textarea cleanly!');

    // 3. Test 1-Click Autofill when test_bed.html is opened as chrome-extension:// URL!
    const extTestBedUrl = `chrome-extension://${extId}/test_bed.html`;
    const extHisPage = await context.newPage();
    await extHisPage.goto(extTestBedUrl, { waitUntil: 'networkidle' });
    await extHisPage.waitForTimeout(600);

    await spPage.evaluate(async () => {
      const tabs = await chrome.tabs.query({});
      const target = tabs.find(t => t.url && t.url.startsWith('chrome-extension://') && t.url.includes('test_bed.html'));
      if (!target) throw new Error('Could not locate chrome-extension test_bed.html tab');
      chrome.tabs.query = async (queryInfo) => {
        if (queryInfo && queryInfo.active) return [target];
        return [target];
      };
    });

    await spPage.click('#spBtnAutofill');
    await spPage.waitForTimeout(600);

    const spBtnText2 = await spPage.locator('#spBtnAutofill').innerText();
    const extFilledVal = await extHisPage.locator('#clinical-notes').inputValue();
    if (!spBtnText2.includes('Đã Điền') || !extFilledVal.includes('LÝ DO VÀO VIỆN')) {
      throw new Error(`chrome-extension:// test_bed.html 1-Click Autofill failed! btn="${spBtnText2}", val="${extFilledVal}"`);
    }
    console.log('  [PASS] SidePanel 1-Click Autofill works on chrome-extension:// test_bed.html too!');

    console.log('✅ ALL SIDEPANEL SEARCH & 1-CLICK AUTOFILL E2E TESTS PASSED!');
  } finally {
    await context.close();
    server.close();
  }
}

testSidePanelAndAutofill().then(() => process.exit(0)).catch(err => {
  console.error('❌ SidePanel E2E failed:', err);
  process.exit(1);
});
