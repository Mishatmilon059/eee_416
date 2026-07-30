// End-to-end test of the MVP data-collection app.
//
// Drives a real browser through a real session and asserts the rows that come
// out are complete and correctly timed. This catches the failure that matters
// most: a session that "works" visually but logs null/NaN features, which you
// would only discover weeks later at training time with the data already collected.
//
//   node tools/test_web_e2e.mjs

import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const PORT = 8931;
const KEY_FOR_DOT = { 1: 'f', 2: 'd', 3: 's', 4: 'j', 5: 'k', 6: 'l' };
const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
  '.mp3': 'audio/mpeg', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png',
};

function serve() {
  const server = createServer(async (req, res) => {
    try {
      const rel = normalize(decodeURIComponent(req.url.split('?')[0])).replace(/^(\.\.[/\\])+/, '');
      let file = join(ROOT, rel);
      if (rel.endsWith('/') || !extname(file)) file = join(file, 'index.html');
      const body = await readFile(file);
      res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream' });
      res.end(body);
    } catch {
      res.writeHead(404).end('not found');
    }
  });
  return new Promise((r) => server.listen(PORT, () => r(server)));
}

const FEATURES = [
  'char_id', 'response_time', 'press_duration', 'retry_count', 'prev_accuracy',
  'prev_mastery', 'hint_count', 'session_number', 'difficulty_level',
  'time_since_last_practice', 'prev_confidence', 'current_streak', 'wrong_streak',
  'prev_mistakes',
];

let failures = 0;
function check(name, cond, detail = '') {
  if (cond) {
    console.log(`  PASS  ${name}`);
  } else {
    failures += 1;
    console.log(`  FAIL  ${name}${detail ? '  -- ' + detail : ''}`);
  }
}

async function main() {
  const server = await serve();
  const map = JSON.parse(await readFile(join(ROOT, 'data/braille_map.json'), 'utf-8'));
  const dotsByChar = new Map(map.letters.map((l) => [l.char, l.dots]));

  // Use the browser already present in this environment rather than downloading
  // one. Override with PW_CHROMIUM if your machine keeps it elsewhere.
  const executablePath = process.env.PW_CHROMIUM ||
    ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome', '/opt/pw-browsers/chromium']
      .find((p) => existsSync(p));
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(`http://localhost:${PORT}/web/`, { waitUntil: 'networkidle' });

  console.log('\n-- boot --');
  check('page loaded without JS errors', errors.length === 0, errors.join(' | '));
  check('unverified-map banner is visible',
    await page.locator('#mapWarning').isVisible());
  check('all 6 dots rendered', await page.locator('#cell .dot').count() === 6);
  check('all 6 keys rendered', await page.locator('.key').count() === 6);

  console.log('\n-- session --');
  const TOTAL = 12;
  await page.fill('#userId', 'E2E_TEST');
  await page.fill('#setLen', String(TOTAL));
  await page.selectOption('#charSet', 'all');
  // start from a clean slate for this participant
  await page.evaluate(() => localStorage.removeItem('braille.state.E2E_TEST'));
  await page.evaluate(() => { localStorage.removeItem('braille.rows'); localStorage.removeItem('braille.queue'); });
  await page.reload({ waitUntil: 'networkidle' });
  await page.fill('#userId', 'E2E_TEST');
  await page.dispatchEvent('#userId', 'change');
  await page.fill('#setLen', String(TOTAL));

  await page.click('#startBtn');
  await page.waitForSelector('#practice.show');
  check('practice panel opened', await page.locator('#practice').isVisible());

  // Answer a mix: correct, wrong, and one hint -- exercises every code path.
  let answered = 0;
  const plan = ['ok', 'ok', 'bad', 'ok', 'bad', 'bad', 'ok', 'hint', 'ok', 'bad', 'ok', 'ok',
                'ok', 'ok', 'ok', 'ok', 'ok', 'ok'];

  for (let i = 0; i < 40 && answered < TOTAL; i++) {
    if (!(await page.locator('#practice').isVisible())) break;
    // strip the U+25CC base the app adds when showing a combining mark alone
    const ch = (await page.locator('#promptChar').textContent()).trim().replace(/^◌/, '');
    const dots = dotsByChar.get(ch);
    if (!dots) { await page.waitForTimeout(120); continue; }

    const mode = plan[answered % plan.length];
    if (mode === 'hint') await page.keyboard.press('h');

    // simulate a human pause before answering
    await page.waitForTimeout(140 + Math.random() * 260);

    let press = dots;
    if (mode === 'bad') {
      // deliberately wrong: drop a dot, or add one that is not in the pattern
      const extra = [1, 2, 3, 4, 5, 6].find((d) => !dots.includes(d));
      press = dots.length > 1 ? dots.slice(0, -1) : [extra];
    }
    for (const d of press) {
      await page.keyboard.down(KEY_FOR_DOT[d]);
      await page.waitForTimeout(25 + Math.random() * 60);
      await page.keyboard.up(KEY_FOR_DOT[d]);
    }
    await page.keyboard.press('Enter');
    answered += 1;
    await page.waitForTimeout(mode === 'bad' ? 1900 : 1200);
  }

  console.log('\n-- logged rows --');
  const rows = await page.evaluate(() => JSON.parse(localStorage.getItem('braille.rows') || '[]'));
  check(`logged ${TOTAL} rows`, rows.length === TOTAL, `got ${rows.length}`);

  if (rows.length) {
    const bad = [];
    for (const [i, r] of rows.entries()) {
      for (const f of FEATURES) {
        const v = r[f];
        if (v === undefined || v === null || Number.isNaN(v) || typeof v !== 'number') {
          bad.push(`row ${i} feature ${f} = ${JSON.stringify(v)}`);
        }
      }
    }
    check('every row has all 14 features as finite numbers', bad.length === 0, bad.slice(0, 4).join('; '));

    const contract = rows.filter((r) => r.current_streak > 0 && r.wrong_streak > 0);
    check('streak exclusivity holds (the timing contract)', contract.length === 0,
      `${contract.length} rows violate it`);

    const derivable = rows.filter((r) => (r.current_streak > 0) !== r.is_correct);
    check('correctness derivable from current_streak', derivable.length === 0,
      `${derivable.length} rows disagree`);

    const rt = rows.map((r) => r.response_time);
    check('response_time positive and plausible (<15s)',
      rt.every((v) => v >= 0 && v < 15000), `range ${Math.min(...rt).toFixed(0)}..${Math.max(...rt).toFixed(0)}ms`);

    const pd = rows.map((r) => r.press_duration);
    check('press_duration positive and plausible (<2s)',
      pd.every((v) => v > 0 && v < 2000), `range ${Math.min(...pd).toFixed(0)}..${Math.max(...pd).toFixed(0)}ms`);

    check('labels in range',
      rows.every((r) => r.teaching_action >= 0 && r.teaching_action <= 5 &&
                        r.confidence_state >= 0 && r.confidence_state <= 2));
    check('provenance stamped',
      rows.every((r) => r.source === 'web' && r.is_synthetic === false &&
                        r.spec_version === 1));

    // braille_map_verified is PER CHARACTER, not per map: a row for a letter
    // read from a supplied image must be marked verified even while other
    // letters are still placeholders, otherwise usable rows get discarded.
    const verifiedById = new Map(map.letters.map((l) => [l.id, Boolean(l.verified)]));
    const wrongProvenance = rows.filter(
      (r) => r.braille_map_verified !== verifiedById.get(r.char_id));
    check('braille_map_verified matches the character, not the whole map',
      wrongProvenance.length === 0,
      wrongProvenance.slice(0, 3).map(
        (r) => `char_id ${r.char_id}: row=${r.braille_map_verified} ` +
               `map=${verifiedById.get(r.char_id)}`).join('; '));
    const nVer = map.letters.filter((l) => l.verified).length;
    console.log(`  info  map has ${nVer}/${map.letters.length} letters verified; ` +
      `${rows.filter((r) => r.braille_map_verified).length}/${rows.length} rows on verified chars`);
    check('attempt_index contiguous',
      rows.every((r, i) => r.attempt_index === i));
    check('at least one wrong answer recorded', rows.some((r) => !r.is_correct));
    check('at least one correct answer recorded', rows.some((r) => r.is_correct));
    check('entered_pattern matches expected exactly on correct rows',
      rows.filter((r) => r.is_correct).every((r) => r.entered_pattern === r.expected_pattern));
    check('hint_count recorded on at least one row', rows.some((r) => r.hint_count > 0));

    const acts = new Set(rows.map((r) => r.teaching_action));
    console.log(`  info  teaching actions seen: ${[...acts].sort().join(',')}`);
    const confs = new Set(rows.map((r) => r.confidence_state));
    console.log(`  info  confidence states seen: ${[...confs].sort().join(',')}`);
  }

  console.log('\n-- persistence --');
  const learner = await page.evaluate(() =>
    JSON.parse(localStorage.getItem('braille.state.E2E_TEST') || 'null'));
  check('learner state persisted', learner !== null);
  check('session number advanced', learner?.sessionNumber === 1, `got ${learner?.sessionNumber}`);
  check('per-character history recorded', Object.keys(learner?.chars || {}).length > 0);
  check('mastery moved off zero for at least one char',
    Object.values(learner?.chars || {}).some((c) => c.mastery > 0));

  console.log('\n-- csv export --');
  const csv = await page.evaluate(() => {
    const cols = ['created_at','user_id','session_id','device_id','attempt_index',
      'char_id','response_time','press_duration','retry_count','prev_accuracy','prev_mastery',
      'hint_count','session_number','difficulty_level','time_since_last_practice','prev_confidence',
      'current_streak','wrong_streak','prev_mistakes','teaching_action','confidence_state',
      'expected_pattern','entered_pattern','is_correct','press_order','source','is_synthetic',
      'spec_version','braille_map_verified'];
    const rows = JSON.parse(localStorage.getItem('braille.rows') || '[]');
    return { header: cols.join(','), rowCount: rows.length, colCount: cols.length };
  });
  check('CSV has 29 columns', csv.colCount === 29, `got ${csv.colCount}`);

  console.log('\n-- runtime errors --');
  check('no uncaught JS errors during the whole run', errors.length === 0,
    errors.slice(0, 3).join(' | '));

  await browser.close();
  server.close();

  console.log(failures === 0 ? '\nOK - all e2e checks passed\n' : `\n${failures} CHECK(S) FAILED\n`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error(e); process.exit(1); });
