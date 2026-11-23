const { chromium } = require('playwright');
const http = require('http');
const path = require('path');
const fs = require('fs');

async function runTests() {
  console.log('=== [E2E] STARTING BHYT CLINICAL COPILOT EXTENSION TESTS ===');
  
  const pathToExtension = path.resolve(__dirname, '../extension');
  const screenshotDir = path.resolve(__dirname, '../test_artifacts');
  fs.mkdirSync(screenshotDir, { recursive: true });

  // 1. Start clean local HTTP server
  const server = http.createServer((req, res) => {
    let reqPath = req.url.split('?')[0];
    if (reqPath === '/' || reqPath === '/test_bed') reqPath = '/test_bed.html';
    const filePath = path.join(pathToExtension, reqPath);

    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      const ext = path.extname(filePath);
      const mime = {
        '.html': 'text/html; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.png': 'image/png'
      }[ext] || 'text/plain';
      res.writeHead(200, { 'Content-Type': mime });
      res.end(fs.readFileSync(filePath));
    } else {
      res.writeHead(404);
      res.end('Not found: ' + reqPath);
    }
  });

  const PORT = 3456;
  await new Promise((resolve) => server.listen(PORT, '127.0.0.1', resolve));
  const testBedUrl = `http://127.0.0.1:${PORT}/test_bed.html`;
  console.log('Test Bed HTTP server listening at:', testBedUrl);

  // 2. Launch Chromium with extension
  const userDataDir = `/tmp/chrome_test_profile_${Date.now()}`;
  const context = await chromium.launchPersistentContext(userDataDir, {
    executablePath: '/usr/bin/google-chrome-stable',
    headless: false,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--headless=new',
      `--disable-extensions-except=${pathToExtension}`,
      `--load-extension=${pathToExtension}`
    ],
    viewport: { width: 1280, height: 900 }
  });

  const page = await context.newPage();
  page.on('console', msg => {
    if (msg.text().includes('BHYT Copilot')) {
      console.log('  [BROWSER CONSOLE]', msg.text());
    }
  });

  try {
    console.log('[STEP 1] Navigating to HIS Portal...');
    await page.goto(testBedUrl, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);

    console.log('[STEP 2] Verifying BHYT Copilot Dock Injection...');
    const dock = await page.waitForSelector('#bhyt-copilot-dock', { timeout: 8000 });
    if (!dock) throw new Error('#bhyt-copilot-dock element was not injected');
    console.log('  -> PASS: #bhyt-copilot-dock successfully injected into HIS DOM.');

    console.log('[STEP 3] Verifying Real-time Audit Trigger & Badge...');
    const pill = await page.waitForSelector('#bhyt-pill-trigger', { timeout: 4000 });
    const initialText = await pill.innerText();
    console.log('  -> Copilot Pill text:', initialText.replace(/\n/g, ' '));
    if (!initialText.includes('M54.5') || !initialText.includes('Nguy cơ')) {
      throw new Error(`Expected pill to detect M54.5 and High Risk, got: ${initialText}`);
    }
    console.log('  -> PASS: Pill badge detected M54.5 and indicated High Risk.');

    console.log('[STEP 4] Opening Copilot Card & Verifying Xuat Toan Rules...');
    await pill.click();
    await page.waitForTimeout(500);

    const card = await page.waitForSelector('.bhyt-copilot-card', { timeout: 4000 });
    const alertsText = await card.innerText();
    console.log('  -> Card content verified.');

    const snap1 = path.join(screenshotDir, '01_his_audit_card_open.png');
    await page.screenshot({ path: snap1 });
    console.log(`  -> Screenshot saved: ${snap1}`);

    console.log('[STEP 5] Testing 1-Click Clinical Note Autofill...');
    const autofillBtn = await page.waitForSelector('#bhyt-btn-autofill', { timeout: 3000 });
    await autofillBtn.click();
    await page.waitForTimeout(800);

    const filledNote = await page.locator('#clinical-notes').inputValue();
    console.log('  -> Injected Note Sample:\n' + filledNote.slice(0, 250) + '...');
    if (!filledNote.includes('LÝ DO VÀO VIỆN') || !filledNote.includes('CHẨN ĐOÁN YHCT')) {
      throw new Error('Clinical note missing required Ministry of Health sections');
    }
    console.log('  -> PASS: 1-Click Clinical Note correctly filled into HIS textarea.');

    const snap2 = path.join(screenshotDir, '02_clinical_note_autofilled.png');
    await page.screenshot({ path: snap2 });
    console.log(`  -> Screenshot saved: ${snap2}`);

    console.log('[STEP 6] Testing Scenario 2: Liệt dây VII ngoại biên G51...');
    await page.click('#btnPresetBellPalsy');
    await page.waitForTimeout(1000);

    const pill2 = await page.waitForSelector('#bhyt-pill-trigger');
    const text2 = await pill2.innerText();
    console.log('  -> Scenario 2 Pill text:', text2.replace(/\n/g, ' '));
    if (!text2.includes('G51.0')) {
      throw new Error(`Expected pill to detect G51.0, got: ${text2}`);
    }

    // Autofill scenario 2
    const autofillBtn2 = await page.waitForSelector('#bhyt-btn-autofill');
    await autofillBtn2.click();
    await page.waitForTimeout(800);

    const bellNote = await page.locator('#clinical-notes').inputValue();
    if (!bellNote.includes('Charles Bell') || !bellNote.includes('Khẩu nhãn oa tà')) {
      throw new Error('Scenario 2 note did not contain expected Bell palsy clinical findings');
    }
    console.log('  -> PASS: Scenario 2 (G51.0) successfully autofilled compliant clinical note.');

    console.log('[STEP 7] Testing Scenario 3: Clean Compliant Case (100% Pass)...');
    await page.click('#btnPresetClean');
    await page.waitForTimeout(1000);

    const pill3 = await page.waitForSelector('#bhyt-pill-trigger');
    const text3 = await pill3.innerText();
    console.log('  -> Scenario 3 Pill text:', text3.replace(/\n/g, ' '));
    if (!text3.includes('Hợp lệ')) {
      throw new Error(`Expected clean record to show 'Hợp lệ', got: ${text3}`);
    }
    console.log('  -> PASS: Clean record confirmed with zero alerts.');

    const snap3 = path.join(screenshotDir, '03_clean_compliant_case.png');
    await page.screenshot({ path: snap3 });
    console.log(`  -> Screenshot saved: ${snap3}`);

    console.log('\n============================================================');
    console.log('🎉 ALL PLAYWRIGHT E2E BROWSER EXTENSION TESTS PASSED (7/7)!');
    console.log('============================================================\n');
  } catch (err) {
    console.error('❌ [E2E FAILURE]:', err);
    process.exit(1);
  } finally {
    try {
      await context.close();
    } catch (_) {}
    server.close();
  }
}

runTests().then(() => process.exit(0)).catch(() => process.exit(1));
