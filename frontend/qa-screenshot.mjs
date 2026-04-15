// QA screenshot runner — visits each route, captures full-page screenshot + console errors.
// Usage: node qa-screenshot.mjs [iteration_number]
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ITER = process.argv[2] || '1';
const BASE = process.env.FRONTEND_URL || 'http://localhost:5173';
const OUT = resolve(process.cwd(), '..', '.omc', 'screenshots', `iter-${ITER}`);
mkdirSync(OUT, { recursive: true });

const ROUTES = [
  '/', '/login', '/dashboard', '/customers', '/resources',
  '/allocations', '/usage', '/alerts', '/bills', '/leads',
];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const report = [];

for (const route of ROUTES) {
  const page = await context.newPage();
  const consoleMsgs = [];
  const pageErrors = [];
  page.on('console', m => consoleMsgs.push({ type: m.type(), text: m.text() }));
  page.on('pageerror', e => pageErrors.push({ name: e.name, message: e.message, stack: e.stack }));

  const url = BASE + route;
  let status = null, finalUrl = null, err = null;
  try {
    const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
    status = resp ? resp.status() : null;
    finalUrl = page.url();
    // Wait for any antd Spin to settle
    await page.waitForTimeout(800);
    const slug = route === '/' ? 'root' : route.replace(/\//g, '_').replace(/^_/, '');
    await page.screenshot({ path: `${OUT}/${slug}.png`, fullPage: true });
  } catch (e) {
    err = String(e.message || e);
  }

  const errors = consoleMsgs.filter(m => m.type === 'error');
  const warnings = consoleMsgs.filter(m => m.type === 'warning');
  report.push({
    route, url, finalUrl, httpStatus: status, navError: err,
    consoleErrors: errors, consoleWarnings: warnings, pageErrors,
    consoleErrorCount: errors.length, pageErrorCount: pageErrors.length,
  });
  await page.close();
}

await browser.close();
writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 2));

// Print concise summary
console.log(`=== Iter ${ITER} Summary (out: ${OUT}) ===`);
for (const r of report) {
  const bad = r.navError || r.pageErrorCount > 0 || r.consoleErrorCount > 0;
  const mark = bad ? '✗' : '✓';
  console.log(`${mark} ${r.route.padEnd(14)} http=${r.httpStatus} console_err=${r.consoleErrorCount} page_err=${r.pageErrorCount}${r.navError ? ' NAV_ERR=' + r.navError : ''}`);
  for (const pe of r.pageErrors) console.log(`    page: ${pe.name}: ${pe.message.split('\n')[0]}`);
  for (const ce of r.consoleErrors.slice(0, 3)) console.log(`    console: ${ce.text.substring(0, 200)}`);
}
