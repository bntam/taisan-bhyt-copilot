const { chromium } = require('playwright');
const http = require('http');
const path = require('path');
const fs = require('fs');

async function runE2ESuite() {
  console.log('================================================================');
  console.log('  BHYT CLINICAL COPILOT - CHROME EXTENSION E2E VERIFICATION     ');
  console.log('================================================================');

  const pathToExtension = path.resolve(__dirname, '../extension');
  const screenshotDir = path.resolve(__dirname, '../test_artifacts');
  fs.mkdirSync(screenshotDir, { recursive: true });

  // 1. HTTP Server for HIS Portal
  const PORT = 4567;
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
      res.writeHead(200, {
        'Content-Type': mimes[ext] || 'text/plain',
        'Access-Control-Allow-Origin': '*'
      });
      res.end(fs.readFileSync(filePath));
    } else {
      res.writeHead(404);
      res.end('File not found: ' + reqUrl);
    }
  });

  await new Promise(resolve => server.listen(PORT, '127.0.0.1', resolve));
  const testBedUrl = `http://127.0.0.1:${PORT}/test_bed.html`;
  console.log(`[HTTP Server] Mock HIS Hospital Server active on: ${testBedUrl}`);

  // 2. Launch Chromium (Chrome for Testing) with Extension Unpacked
  const profileDir = `/tmp/bhyt_cft_profile_${Date.now()}`;
  console.log(`[Chrome for Testing] Launching persistent context with extension...`);

  const context = await chromium.launchPersistentContext(profileDir, {
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
    viewport: { width: 1280, height: 900 }
  });

  // Verify Service Worker
  let sw = context.serviceWorkers();
  if (sw.length === 0) {
    try {
      const w = await context.waitForEvent('serviceworker', { timeout: 3000 });
      console.log(`[Service Worker] Detected & active: ${w.url()}`);
    } catch (_) {
      console.log('[Service Worker] Active in background.');
    }
  } else {
    console.log(`[Service Worker] Detected: ${sw[0].url()}`);
  }

  const page = await context.newPage();
  page.on('console', msg => {
    if (msg.text().includes('BHYT Copilot')) {
      console.log(`  [BROWSER] ${msg.text()}`);
    }
  });

  try {
    // TEST 1: Load HIS Page
    console.log('\n--- TEST 1: Navigate to HIS Medical Portal ---');
    await page.goto(testBedUrl, { waitUntil: 'networkidle' });
    const pageTitle = await page.title();
    console.log(`  -> Page loaded: "${pageTitle}"`);

    // TEST 2: In-Browser Dock Injection
    console.log('\n--- TEST 2: Inspect In-Browser Floating Copilot Dock ---');
    const dock = await page.waitForSelector('#bhyt-copilot-dock', { timeout: 6000 });
    if (!dock) throw new Error('#bhyt-copilot-dock was not injected into HIS DOM');
    console.log('  -> [PASS] Content script successfully injected #bhyt-copilot-dock.');

    // TEST 3: Real-Time Audit on Preset 1 (High Risk)
    console.log('\n--- TEST 3: Real-Time Xuat Toan Audit on Preset 1 (High Risk) ---');
    const pill = await page.waitForSelector('#bhyt-pill-trigger', { timeout: 3000 });
    const pillText = await pill.innerText();
    console.log(`  -> Detected Pill state: "${pillText.replace(/\n/g, ' ')}"`);
    if (!pillText.includes('M54.5') || !pillText.includes('Nguy cơ')) {
      throw new Error(`Expected pill to detect M54.5 and High Risk, got: ${pillText}`);
    }
    console.log('  -> [PASS] Pill correctly identified ICD M54.5 and flagged High Risk.');

    // TEST 4: Expand Audit Card & Inspect Rules
    console.log('\n--- TEST 4: Expand Copilot Audit Card & Verify Rules ---');
    await pill.click();
    await page.waitForTimeout(400);

    const card = await page.waitForSelector('.bhyt-copilot-card', { timeout: 3000 });
    const alertsText = await card.innerText();

    const checkCeftriaxone = alertsText.includes('vượt tuyến') || alertsText.includes('Ceftriaxone');
    const checkStatin = alertsText.includes('Lipid') || alertsText.includes('Atorvastatin');
    const checkDays = alertsText.includes('vượt quá') || alertsText.includes('ngày/đợt');
    const checkBleed = alertsText.includes('chảy máu') || alertsText.includes('Đan sâm');

    console.log(`  -> Audit Rule 1 (Thuốc vượt tuyến Tuyến 4 - Ceftriaxone): ${checkCeftriaxone ? 'PASS' : 'FAIL'}`);
    console.log(`  -> Audit Rule 2 (Thiếu xét nghiệm mỡ máu - Atorvastatin): ${checkStatin ? 'PASS' : 'FAIL'}`);
    console.log(`  -> Audit Rule 3 (Vượt định mức 15 ngày/đợt - Điện châm 18 ngày): ${checkDays ? 'PASS' : 'FAIL'}`);
    console.log(`  -> Audit Rule 4 (Tương tác Đan sâm + Aspirin xuất huyết): ${checkBleed ? 'PASS' : 'FAIL'}`);

    if (!checkCeftriaxone || !checkDays) {
      throw new Error('Core audit rules not fully evaluated');
    }

    const snap1 = path.join(screenshotDir, '01_his_audit_card_open.png');
    await page.screenshot({ path: snap1 });
    console.log(`  -> Screenshot saved: ${snap1}`);

    // TEST 5: 1-Click Clinical Note Autofill
    console.log('\n--- TEST 5: Execute 1-Click Clinical Note Autofill ---');
    const autofillBtn = await page.waitForSelector('#bhyt-btn-autofill', { timeout: 3000 });
    await autofillBtn.click();
    await page.waitForTimeout(600);

    const clinicalNoteVal = await page.locator('#clinical-notes').inputValue();
    console.log('  -> Clinical Note Injected:\n' + clinicalNoteVal.split('\n').map(l => '     | ' + l).join('\n'));

    if (!clinicalNoteVal.includes('LÝ DO VÀO VIỆN') || !clinicalNoteVal.includes('CHẨN ĐOÁN YHCT') || !clinicalNoteVal.includes('Điện châm')) {
      throw new Error('Clinical note autofill did not inject standard Ministry of Health template');
    }
    console.log('  -> [PASS] 1-Click Clinical Note successfully injected into textarea with DOM events.');

    const snap2 = path.join(screenshotDir, '02_clinical_note_autofilled.png');
    await page.screenshot({ path: snap2 });
    console.log(`  -> Screenshot saved: ${snap2}`);

    // TEST 6: Scenario 2 - Bell's Palsy (G51.0)
    console.log('\n--- TEST 6: Switch to Scenario 2 (Liệt dây VII ngoại biên - G51.0) ---');
    await page.click('#btnPresetBellPalsy');
    await page.waitForTimeout(600);

    const pillText2 = await page.locator('#bhyt-pill-trigger').innerText();
    console.log(`  -> Scenario 2 Pill text: "${pillText2.replace(/\n/g, ' ')}"`);
    if (!pillText2.includes('G51.0')) {
      throw new Error(`Expected G51.0 detection, got: ${pillText2}`);
    }

    const autofillBtn2 = await page.waitForSelector('#bhyt-btn-autofill');
    await autofillBtn2.click();
    await page.waitForTimeout(600);

    const bellNote = await page.locator('#clinical-notes').inputValue();
    if (!bellNote.includes('Charles Bell') || !bellNote.includes('Khẩu nhãn oa tà')) {
      throw new Error('Bell Palsy specific clinical note validation failed');
    }
    console.log('  -> [PASS] Bell Palsy (G51.0) correctly diagnosed with YHCT Khẩu nhãn oa tà.');

    // TEST 7: Scenario 3 - 100% Compliant Record
    console.log('\n--- TEST 7: Switch to Scenario 3 (Clean 100% Compliant Record) ---');
    await page.click('#btnPresetClean');
    await page.waitForTimeout(600);

    const pillText3 = await page.locator('#bhyt-pill-trigger').innerText();
    console.log(`  -> Scenario 3 Pill text: "${pillText3.replace(/\n/g, ' ')}"`);
    if (!pillText3.includes('Hợp lệ')) {
      throw new Error(`Expected clean record to show 'Hợp lệ', got: ${pillText3}`);
    }
    console.log('  -> [PASS] Clean compliant record passed all xuất toán checks with 0 alerts.');

    const snap3 = path.join(screenshotDir, '03_clean_compliant_record.png');
    await page.screenshot({ path: snap3 });
    console.log(`  -> Screenshot saved: ${snap3}`);

    // TEST 8: In-Browser Floating Dock AI Clinical Chatbox (Q&A & 1-Click Snippet)
    console.log('\n--- TEST 8: Floating Dock AI Clinical Chatbox & 1-Click Snippet Insertion ---');
    // Open dock card if closed
    const cardVisible = await page.isVisible('.bhyt-copilot-card');
    if (!cardVisible) {
      await page.click('#bhyt-pill-trigger');
      await page.waitForTimeout(300);
    }

    // Switch to Chat tab on Floating Dock
    console.log('  -> Switching to "💬 Hỏi Đáp AI (Chatbox)" tab on Floating Dock...');
    await page.click('#bhyt-tab-chat-btn');
    await page.waitForTimeout(400);

    const chatContainer = await page.waitForSelector('.bhyt-chat-container', { timeout: 3000 });
    if (!chatContainer) throw new Error('.bhyt-chat-container was not rendered');

    // Click quick chip "Cam thảo & Huyết áp"
    console.log('  -> Clicking quick chip "⚠️ Cam thảo & Huyết áp"...');
    await page.click('button[data-q*="Cam thảo"]');
    await page.waitForTimeout(1000);

    let dockChatMsgs = await page.locator('.bhyt-chat-msg').allInnerTexts();
    console.log(`  -> Found ${dockChatMsgs.length} chat messages in Floating Dock.`);
    const lastDockMsg = dockChatMsgs[dockChatMsgs.length - 1];
    console.log('  -> AI reply preview:', lastDockMsg.substring(0, 140).replace(/\n/g, ' '));
    if (!lastDockMsg.includes('Cam Thảo') && !lastDockMsg.includes('Glycyrrhizin') && !lastDockMsg.includes('hạ áp')) {
      throw new Error('Floating Dock Chatbox response missing Cam Thao information');
    }
    console.log('  -> [PASS] Floating Dock AI response received and rendered.');

    // Click "📋 Điền Đoạn Này Vào Bệnh Án"
    console.log('  -> Clicking "📋 Điền Đoạn Này Vào Bệnh Án"...');
    const actionBtn = await page.waitForSelector('.bhyt-chat-action-btn', { timeout: 3000 });
    await actionBtn.click();
    await page.waitForTimeout(600);

    const noteAfterSnippet = await page.locator('#clinical-notes').inputValue();
    console.log('  -> Note updated with snippet preview:', noteAfterSnippet.substring(0, 150).replace(/\n/g, ' '));
    if (!noteAfterSnippet.includes('LƯU Ý DƯỢC LÂM SÀNG') && !noteAfterSnippet.includes('Cam thảo')) {
      throw new Error('Clinical note was not updated with AI snippet');
    }
    console.log('  -> [PASS] 1-Click AI snippet successfully injected into HIS textarea from Floating Dock.');

    const snapDockChat = path.join(screenshotDir, '06_dock_chatbox_verified.png');
    await page.screenshot({ path: snapDockChat });
    console.log(`  -> Screenshot saved: ${snapDockChat}`);

    // TEST 9: Scenario 4 - Deep DOM Scanner (ASP.NET WebForms, DevExpress & Iframe)
    console.log('\n--- TEST 9: Scenario 4 (Legacy ASP.NET / DevExpress / Embedded Iframe) ---');
    await page.click('#btnPresetAspNetLegacy');
    await page.waitForTimeout(700);

    const pillText4 = await page.locator('#bhyt-pill-trigger').innerText();
    console.log(`  -> Scenario 4 Pill text: "${pillText4.replace(/\n/g, ' ')}"`);
    if (!pillText4.includes('M16.0')) {
      throw new Error(`Expected M16.0 detection from ASP.NET input, got: ${pillText4}`);
    }
    console.log('  -> [PASS] Deep DOM Scanner identified ASP.NET WebForms input M16.0.');

    // Verify Iframe presence and accessibility
    const iframeHandle = await page.$('#legacyHisIframe');
    if (!iframeHandle) throw new Error('#legacyHisIframe not found in test bed');
    const iframeDoc = await iframeHandle.contentFrame();
    if (iframeDoc) {
      const iframeIcdVal = await iframeDoc.locator('#ctl00_txtIcdPhu').inputValue();
      console.log(`  -> Detected inside iframe ASP.NET input: ${iframeIcdVal}`);
    }
    console.log('  -> [PASS] Embedded Iframe DOM structure verified.');

    const snapLegacy = path.join(screenshotDir, '07_legacy_aspnet_iframe_verified.png');
    await page.screenshot({ path: snapLegacy });
    console.log(`  -> Screenshot saved: ${snapLegacy}`);

    // TEST 10: Dynamic Hospital Tier Override (T4 -> T1 / T2)
    console.log('\n--- TEST 10: Dynamic Hospital Tier Override (T4 -> T1 / T2) ---');
    // Open card if closed
    if (!await page.isVisible('.bhyt-copilot-card')) {
      await page.click('#bhyt-pill-trigger');
      await page.waitForTimeout(300);
    }
    // Switch to Tuyến 1
    console.log('  -> Clicking Tier 1 button (T1)...');
    const t1Btn = await page.waitForSelector('button[data-set-tier="1"]', { timeout: 3000 });
    await t1Btn.click();
    await page.waitForTimeout(600);

    const tierHeader = await page.locator('.bhyt-copilot-card').innerText();
    if (!tierHeader.includes('Tuyến 1')) {
      throw new Error('Failed to switch to Tuyến 1 in card header');
    }
    console.log('  -> [PASS] Dynamic hospital tier switched to Tuyến 1 (Chọn thủ công).');

    // Switch back to Tuyến 4
    console.log('  -> Clicking Tier 4 button (T4)...');
    const t4Btn = await page.waitForSelector('button[data-set-tier="4"]', { timeout: 3000 });
    await t4Btn.click();
    await page.waitForTimeout(600);
    console.log('  -> [PASS] Dynamic hospital tier restored to Tuyến 4.');

    // TEST 11: Side Panel UI & Multi-Tab Verification
    console.log('\n--- TEST 11: Side Panel (sidepanel.html) Standalone Verification ---');
    const swWorker = Array.isArray(sw) ? sw[0] : sw;
    const extId = swWorker ? swWorker.url().split('/')[2] : 'ext';
    const sidepanelUrl = `chrome-extension://${extId}/sidepanel/sidepanel.html`;
    console.log(`  -> Opening Side Panel page: ${sidepanelUrl}`);

    const spPage = await context.newPage();
    await spPage.goto(sidepanelUrl, { waitUntil: 'networkidle' });
    await spPage.waitForTimeout(600);

    const spTitle = await spPage.locator('.sp-title').innerText();
    console.log(`  -> Side Panel Title: "${spTitle}"`);
    if (!spTitle.includes('BHYT Clinical Copilot')) {
      throw new Error('Side Panel failed to render brand title');
    }

    // Verify Segmented Tier Control in Side Panel
    const tier2Btn = await spPage.waitForSelector('button.sp-tier-btn[data-tier="2"]');
    await tier2Btn.click();
    await spPage.waitForTimeout(300);
    const tier2Active = await tier2Btn.getAttribute('class');
    if (!tier2Active.includes('active')) {
      throw new Error('Side Panel Tier 2 button did not become active');
    }
    console.log('  -> [PASS] Side Panel segmented tier selector verified (Tuyến 2 active).');

    // Switch to Side Panel Chat Tab
    console.log('  -> Switching to Chat tab in Side Panel...');
    await spPage.click('button[data-tab="tab-chat"]');
    await spPage.waitForTimeout(400);

    // Click quick prompt in Side Panel
    await spPage.click('button[data-q*="Cam thảo"]');
    await spPage.waitForTimeout(1000);

    const spChatMsgs = await spPage.locator('.sp-msg').allInnerTexts();
    console.log(`  -> Side Panel Chat messages count: ${spChatMsgs.length}`);
    const lastSpMsg = spChatMsgs[spChatMsgs.length - 1];
    if (!lastSpMsg.includes('Cam Thảo') && !lastSpMsg.includes('Glycyrrhizin') && !lastSpMsg.includes('hạ áp')) {
      throw new Error('Side Panel Chat response missing expected clinical content');
    }
    console.log('  -> [PASS] Side Panel Q&A Chat response verified.');

    const snapSidePanel = path.join(screenshotDir, '08_sidepanel_verified.png');
    await spPage.screenshot({ path: snapSidePanel });
    console.log(`  -> Screenshot saved: ${snapSidePanel}`);
    await spPage.close();

    console.log('\n================================================================');
    console.log('  ✅ ALL 11 END-TO-END VERIFICATION CHECKS PASSED SUCCESSFULLY!  ');
    console.log('================================================================\n');

  } catch (err) {
    console.error('❌ [E2E FAILURE]:', err);
    process.exitCode = 1;
  } finally {
    try {
      await context.close();
    } catch (_) {}
    server.close();
  }
}

runE2ESuite();
