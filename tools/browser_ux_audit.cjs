const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const base = (process.env.EXPLORER_URL || 'http://localhost:3030').replace(/\/$/, '');
const repoRoot = path.resolve(__dirname, '..');
const canonicalPath = path.join(repoRoot, 'data', 'processed', 'canonical.jsonl');
let snapshotId = null;
if (fs.existsSync(canonicalPath)) {
  const first = fs.readFileSync(canonicalPath, 'utf8').split(/\r?\n/).find((line) => line.trim());
  if (first) snapshotId = JSON.parse(first).coverage_snapshot || null;
}
const runId = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
const output = process.env.UX_REPORT_DIR || path.resolve('reports', runId);
fs.mkdirSync(path.join(output, 'screenshots'), { recursive: true });

const checks = [];
const check = (name, passed, details = {}) => {
  checks.push({ name, status: passed ? 'PASS' : 'FAIL', details });
  return passed;
};

async function audit() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ locale: 'vi-VN' });
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  const viewports = [
    [320, 800],
    [768, 1024],
    [1280, 800],
    [1440, 900],
  ];

  const viewportResults = [];
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height });
    await page.goto(`${base}/`, { waitUntil: 'networkidle' });
    await page.waitForSelector('#home-title');
    const layout = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      missingButtonNames: [...document.querySelectorAll('button')].filter((el) => !(el.textContent || '').trim() && !el.getAttribute('aria-label')).length,
      missingImageAlt: [...document.querySelectorAll('img')].filter((el) => !el.hasAttribute('alt')).length,
      hasMain: Boolean(document.querySelector('main#app')),
      hasNavLabel: Boolean(document.querySelector('nav[aria-label]')),
    }));
    const shot = path.join(output, 'screenshots', `home-${width}x${height}.png`);
    await page.screenshot({ path: shot, fullPage: true });
    viewportResults.push({ width, height, screenshot: shot, ...layout });
  }
  check('responsive_viewports', viewportResults.every((item) => !item.horizontalOverflow && item.missingButtonNames === 0 && item.missingImageAlt === 0), { viewports: viewportResults });
  check('semantic_landmarks', viewportResults.every((item) => item.hasMain && item.hasNavLabel));

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${base}/`, { waitUntil: 'networkidle' });
  let keyboardSearch = false;
  for (let index = 0; index < 20; index += 1) {
    await page.keyboard.press('Tab');
    const active = await page.evaluate(() => ({ href: document.activeElement?.getAttribute('href'), text: document.activeElement?.textContent?.trim() }));
    if (active.href === '#/search') {
      keyboardSearch = true;
      await page.keyboard.press('Enter');
      break;
    }
  }
  await page.waitForSelector('#search-title');
  const searchAccessible = await page.evaluate(() => ({
    labels: [...document.querySelectorAll('input,select')].every((control) => control.id && document.querySelector(`label[for="${control.id}"]`)),
    liveResults: Boolean(document.querySelector('#results[aria-live="polite"]')),
    skipLink: Boolean(document.querySelector('.skip-link')),
  }));
  check('keyboard_search_navigation', keyboardSearch && searchAccessible.labels && searchAccessible.liveResults && searchAccessible.skipLink, { keyboardSearch, searchAccessible });

  await page.locator('#search-q').fill('Huế');
  await page.locator('#search-q').press('Enter');
  await page.waitForSelector('#results .card');
  const firstResult = page.locator('#results .card h2 a').first();
  await firstResult.focus();
  await firstResult.press('Enter');
  await page.waitForSelector('#semantics-title');
  const accessibilityTree = await page.locator('body').ariaSnapshot();
  check('accessibility_tree', accessibilityTree.includes('VietHeritageLOD') && accessibilityTree.includes('Điều hướng chính') && accessibilityTree.includes('main'), { snapshot_length: accessibilityTree.length });
  const semanticDetail = await page.evaluate(() => ({
    canonical: Boolean(document.querySelector('a[rel="canonical"]')),
    turtle: Boolean(document.querySelector('a[type="text/turtle"]')),
    jsonld: Boolean(document.querySelector('a[type="application/ld+json"]')),
    asserted: document.body.textContent.includes('Asserted từ dữ liệu nguồn'),
    inferred: document.body.textContent.includes('Inferred bởi reasoning'),
    provenance: document.body.textContent.includes('Provenance and external identity'),
  }));
  check('semantic_detail_navigation', Object.values(semanticDetail).every(Boolean), semanticDetail);

  const errorPage = await context.newPage();
  await errorPage.route('**/api/stats', async (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Fuseki unavailable' } }) }));
  await errorPage.goto(`${base}/`, { waitUntil: 'networkidle' });
  const errorState = await errorPage.locator('[role="alert"]').count();
  check('network_error_state', errorState === 1, { alert_count: errorState });
  await errorPage.close();

  check('browser_console_errors', pageErrors.length === 0, { errors: pageErrors });
  const result = {
    run_id: runId,
    snapshot_id: snapshotId,
    status: checks.every((item) => item.status === 'PASS') ? 'PASS' : 'FAIL',
    environment: { browser: 'Chromium via Playwright 1.55.0', explorer: base, headless: true },
    viewports: viewportResults,
    checks,
    warnings: ['Automated browser evidence does not replace a human screen-reader audit.'],
  };
  fs.writeFileSync(path.join(output, 'browser_ux.json'), JSON.stringify(result, null, 2) + '\n', 'utf8');
  fs.writeFileSync(path.join(output, 'visual_regression.json'), JSON.stringify({ run_id: runId, snapshot_id: snapshotId, status: result.status, browser: result.environment.browser, viewports: viewportResults, checks: ['responsive_viewports', 'semantic_landmarks'] }, null, 2) + '\n', 'utf8');
  await browser.close();
  console.log(`browser-ux-audit: ${result.status} (${checks.filter((item) => item.status === 'PASS').length}/${checks.length})`);
  console.log(`browser-ux-report: ${path.join(output, 'browser_ux.json')}`);
  process.exitCode = result.status === 'PASS' ? 0 : 1;
}

audit().catch((error) => { console.error(error); process.exitCode = 1; });
