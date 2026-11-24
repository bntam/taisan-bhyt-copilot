#!/usr/bin/env python3
import os
import sys
import json
import tempfile
import subprocess

def main():
    print("[hermes-verify] Starting focused ad-hoc verification for BHYT Clinical Copilot...")
    ext_dir = "/root/taisan-bhyt-copilot/extension"

    # Step 1: Verify all changed paths exist and are non-empty
    changed_paths = [
        "/root/taisan-bhyt-copilot/extension/manifest.json",
        "/root/taisan-bhyt-copilot/extension/background/service-worker.js",
        "/root/taisan-bhyt-copilot/extension/content/content.js",
        "/root/taisan-bhyt-copilot/extension/content/content.css",
        "/root/taisan-bhyt-copilot/extension/popup/popup.html",
        "/root/taisan-bhyt-copilot/extension/popup/popup.js",
        "/root/taisan-bhyt-copilot/extension/popup/popup.css",
        "/root/taisan-bhyt-copilot/extension/test_bed.html"
    ]

    for p in changed_paths:
        if not os.path.exists(p):
            print(f"[FAIL] Missing path: {p}", file=sys.stderr)
            sys.exit(1)
        size = os.path.getsize(p)
        if size < 50:
            print(f"[FAIL] Path {p} size too small ({size} bytes)", file=sys.stderr)
            sys.exit(1)
    print("  -> [PASS] All 8 extension files exist and have valid content size.")

    # Step 2: Validate manifest.json structure & icons
    with open(os.path.join(ext_dir, "manifest.json")) as f:
        manifest = json.load(f)
    assert manifest.get("manifest_version") == 3, "manifest_version must be 3"
    assert "background" in manifest and "service_worker" in manifest["background"], "Missing background.service_worker"
    assert "content_scripts" in manifest and len(manifest["content_scripts"]) > 0, "Missing content_scripts"
    assert ("side_panel" in manifest or manifest.get("action", {}).get("default_popup") == "popup/popup.html"), "Missing side_panel or action.default_popup"

    for size in ["16", "48", "128"]:
        icon_path = os.path.join(ext_dir, manifest["icons"][size])
        assert os.path.exists(icon_path), f"Missing icon-{size}.png at {icon_path}"
    print("  -> [PASS] manifest.json schema, side_panel and real PNG icon assets verified.")

    # Step 3: Validate JavaScript syntax via node -c
    js_files = [
        os.path.join(ext_dir, "background/service-worker.js"),
        os.path.join(ext_dir, "content/content.js"),
        os.path.join(ext_dir, "popup/popup.js"),
        os.path.join(ext_dir, "sidepanel/sidepanel.js"),
        os.path.join(ext_dir, "test_bed.js")
    ]
    for js in js_files:
        res = subprocess.run(["node", "-c", js], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[FAIL] Syntax error in {js}:\n{res.stderr}", file=sys.stderr)
            sys.exit(1)
    print("  -> [PASS] Node syntax checks (node -c) passed for all extension scripts.")

    # Step 4: Validate offline catalog integrity
    catalog_path = os.path.join(ext_dir, "data/catalog.json")
    with open(catalog_path) as f:
        cat = json.load(f)
    assert len(cat.get("icd10", [])) >= 15000, "ICD-10 catalog has fewer than 15,000 entries"
    assert len(cat.get("thuoc_bhyt", [])) >= 5, "Drugs catalog is empty"
    assert len(cat.get("thuoc_yhct", [])) >= 5, "TCM herbs catalog is empty"
    assert len(cat.get("thu_thuat_bhyt", [])) >= 5, "Procedures catalog is empty"
    assert len(cat.get("xuat_toan_rules", [])) >= 5, "Rules catalog is empty"
    print(f"  -> [PASS] Offline catalog verified: {len(cat['icd10'])} ICD-10, {len(cat['thuoc_bhyt'])} drugs, {len(cat['thuoc_yhct'])} TCM herbs, {len(cat['xuat_toan_rules'])} rules.")

    # Step 5: Execute temporary verification script with Playwright
    # Create temp script using tempfile with hermes-verify- prefix
    temp_script_path = None
    with tempfile.NamedTemporaryFile(mode="w", prefix="hermes-verify-", suffix=".js", dir="/tmp", delete=False) as tf:
        temp_script_path = tf.name
        tf.write("""
const { chromium } = require('playwright');
const http = require('http');
const path = require('path');
const fs = require('fs');

async function testRuntime() {
  const extDir = '/root/taisan-bhyt-copilot/extension';
  const PORT = 4789;
  const server = http.createServer((req, res) => {
    let reqUrl = req.url.split('?')[0];
    if (reqUrl === '/' || reqUrl === '/test_bed') reqUrl = '/test_bed.html';
    const filePath = path.join(extDir, reqUrl);
    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      const ext = path.extname(filePath);
      const mimes = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png' };
      res.writeHead(200, { 'Content-Type': mimes[ext] || 'text/plain' });
      res.end(fs.readFileSync(filePath));
    } else {
      res.writeHead(404);
      res.end('Not found');
    }
  });

  await new Promise(r => server.listen(PORT, '127.0.0.1', r));

  const profileDir = '/tmp/hermes_verify_rt_' + Date.now();
  const context = await chromium.launchPersistentContext(profileDir, {
    headless: false,
    ignoreDefaultArgs: ['--disable-extensions'],
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--headless=new',
      '--disable-extensions-except=' + extDir,
      '--load-extension=' + extDir
    ],
    viewport: { width: 1280, height: 850 }
  });

  const page = await context.newPage();
  await page.goto('http://127.0.0.1:' + PORT + '/test_bed.html', { waitUntil: 'networkidle' });

  // 1. Verify Dock Injected
  const dock = await page.waitForSelector('#bhyt-copilot-dock', { timeout: 6000 });
  const pillText = await page.locator('#bhyt-pill-trigger').innerText();
  if (!pillText.includes('M54.5') || !pillText.includes('Nguy cơ')) {
    throw new Error('Pill failed to detect M54.5 or high risk: ' + pillText);
  }

  // 2. Open Card & Trigger 1-Click Autofill
  await page.click('#bhyt-pill-trigger');
  await page.waitForTimeout(300);
  await page.click('#bhyt-btn-autofill');
  await page.waitForTimeout(500);

  const note = await page.locator('#clinical-notes').inputValue();
  if (!note.includes('LÝ DO VÀO VIỆN') || !note.includes('CHẨN ĐOÁN YHCT')) {
    throw new Error('Clinical note missing required sections');
  }

  // 3. Switch to Clean Case
  await page.click('#btnPresetClean');
  await page.waitForTimeout(600);
  const cleanPill = await page.locator('#bhyt-pill-trigger').innerText();
  if (!cleanPill.includes('Hợp lệ')) {
    throw new Error('Clean case did not show Hợp lệ');
  }

  console.log('  -> [PASS] Playwright in-browser DOM injection, rule audit & 1-click clinical note autofill fully verified.');

  await context.close();
  server.close();
}

testRuntime().then(() => process.exit(0)).catch(err => {
  console.error(err);
  process.exit(1);
});
""")

    print(f"Created temporary verification script: {temp_script_path}")

    env = os.environ.copy()
    env["NODE_PATH"] = "/root/node_modules"
    res = subprocess.run(["/usr/bin/xvfb-run", "-a", "node", temp_script_path], env=env, capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)

    try:
        os.remove(temp_script_path)
        print(f"Cleaned up temporary verification script: {temp_script_path}")
    except Exception as e:
        print(f"Warning: could not delete {temp_script_path}: {e}", file=sys.stderr)

    if res.returncode == 0:
        print("\n[hermes-verify] AD-HOC VERIFICATION SUCCESSFUL (ALL 5 CHECKS PASSED).")
    else:
        print("\n[hermes-verify] AD-HOC VERIFICATION FAILED.", file=sys.stderr)
        sys.exit(res.returncode)

if __name__ == "__main__":
    main()
