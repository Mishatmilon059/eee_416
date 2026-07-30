// Bangla Braille Tutor -- MVP session driver.
//
// This app is a data-collection instrument first and a tutor second. Every
// decision below favours getting clean, complete, correctly-timed rows over
// polish. The rule engine it calls is GENERATED from spec/engine_spec.json --
// the same spec that generates the ESP32's rule engine.

import {
  SPEC_VERSION, TEACHING_ACTION, TEACHING_ACTION_NAMES,
  CONFIDENCE_STATE, CONFIDENCE_STATE_NAMES,
  evaluateTeachingAction, evaluateConfidence,
  SESSION_TARGET_ATTEMPTS,
} from './rule_engine.js';
import { BrailleCell, KeyPad, dotsToMask, maskToDots } from './braille_cell.js';
import { LearnerState, AttemptLogger, deviceId, uuid } from './storage.js';

import { FALLBACK_MAP } from './braille_map_fallback.js';

const MAX_TRIES_PER_PROMPT = 4;   // then move on regardless
const $ = (id) => document.getElementById(id);

// ং ঃ ঁ are combining marks. Rendered alone a font shows them over a dotted
// circle, which reads as a broken glyph. Attach U+25CC explicitly so it is
// clearly the standard "combining mark shown in isolation" notation.
const COMBINING = new Set(['ঁ', 'ং', 'ঃ']);
const displayChar = (ch) => (COMBINING.has(ch) ? '◌' + ch : ch);

const ui = {
  mapWarning: $('mapWarning'), syncStatus: $('syncStatus'),
  setup: $('setup'), practice: $('practice'),
  userId: $('userId'), mode: $('mode'), setLen: $('setLen'), charSet: $('charSet'),
  startBtn: $('startBtn'), exportBtn: $('exportBtn'), flushBtn: $('flushBtn'),
  resetBtn: $('resetBtn'), modeNote: $('modeNote'),
  attemptNo: $('attemptNo'), attemptTotal: $('attemptTotal'), diffLevel: $('diffLevel'),
  promptChar: $('promptChar'), promptName: $('promptName'),
  replayBtn: $('replayBtn'), submitBtn: $('submitBtn'), clearBtn: $('clearBtn'),
  hintBtn: $('hintBtn'), stopBtn: $('stopBtn'),
  hintBox: $('hintBox'), feedback: $('feedback'), unverifiedTag: $('unverifiedTag'),
  stRows: $('stRows'), stAcc: $('stAcc'), stSess: $('stSess'), stDays: $('stDays'),
  stChars: $('stChars'), stQueue: $('stQueue'),
  taTable: $('taTable'), csTable: $('csTable'), charTable: $('charTable'),
};

const MODE_NOTES = {
  normal: 'Weighted toward weaker characters. Produces the natural class distribution.',
  targeted: 'Biases selection toward genuinely stale and genuinely weak characters so the rare rules (REVIEW_PREVIOUS, GUESSING) fire on their own. It does NOT fake feature values — the rows stay real.',
  review: 'Only characters already seen with mastery below 0.5. Use for follow-up sessions on a later day.',
};

const state = {
  letters: [], mapVerified: false, active: [],
  learner: null, logger: null, cell: null, pad: null,
  audio: new Map(),
  session: null, current: null, running: false,
};

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------

async function boot() {
  let map = null;
  try {
    let res = await fetch('./data/braille_map.json').catch(() => null);
    if (!res || !res.ok) res = await fetch('../data/braille_map.json').catch(() => null);
    if (!res || !res.ok) res = await fetch('/data/braille_map.json').catch(() => null);
    if (res && res.ok) map = await res.json().catch(() => null);
  } catch (e) {
    console.warn('Network map fetch failed, using fallback:', e);
  }
  if (!map) map = FALLBACK_MAP;
  state.letters = map.letters;
  state.mapVerified = Boolean(map.verified);
  renderMapBanner(map);

  state.cell = new BrailleCell($('cell'));
  state.pad = new KeyPad(document.querySelector('.keys'), {
    onChange: (mask) => state.cell.setMask(mask, { pulse: true }),
  });

  state.logger = new AttemptLogger((kind, msg) => {
    ui.syncStatus.className = kind === 'ok' ? 'ok' : kind === 'error' ? 'error'
      : kind === 'pending' ? 'pending' : '';
    ui.syncStatus.textContent = msg;
  });

  ui.userId.value = localStorage.getItem('braille.lastUser') || 'P01';
  ui.setLen.value = SESSION_TARGET_ATTEMPTS;
  loadLearner();

  wireEvents();
  renderAll();
}

/**
 * Verification is per letter, because images arrive in batches. A blanket
 * "everything is unverified" banner would stay up for weeks while genuinely
 * verified characters were already usable, and would train everyone to ignore it.
 */
function renderMapBanner(map) {
  const total = map.letters.length;
  const n = map.letters.filter((l) => l.verified).length;
  const el = ui.mapWarning;
  el.classList.add('show');

  if (n === total) {
    el.classList.add('ok');
    el.innerHTML = `<b>✓ Braille mapping verified.</b> All ${total} letters were read from
      supplied reference images. Safe to use with real learners.`;
    return;
  }
  el.classList.remove('ok');
  const missing = map.letters.filter((l) => !l.verified);
  const vowels = missing.filter((l) => l.category === 'vowel').length;
  el.innerHTML = `<b>⚠ Braille mapping verified for ${n} of ${total} letters.</b>
    The remaining ${total - n} (${vowels} vowel, ${missing.length - vowels} consonant)
    still carry <b>Bharati placeholder</b> patterns not checked against the Bangladesh
    National Braille code. Practising a placeholder character is marked on the prompt,
    and every logged row records whether <i>that character</i> was verified — so
    verified rows stay usable while the rest of the alphabet is confirmed.
    Add images to <span class="mono">braille_img/</span> and run
    <span class="mono">tools/import_braille_images.py</span>.`;
}

function loadLearner() {
  const id = (ui.userId.value || 'P01').trim();
  state.learner = new LearnerState(id);
  localStorage.setItem('braille.lastUser', id);
}

function wireEvents() {
  ui.userId.addEventListener('change', () => { loadLearner(); renderAll(); });
  ui.mode.addEventListener('change', () => { ui.modeNote.textContent = MODE_NOTES[ui.mode.value]; });
  ui.modeNote.textContent = MODE_NOTES[ui.mode.value];

  ui.startBtn.addEventListener('click', startSession);
  ui.stopBtn.addEventListener('click', () => endSession('stopped'));
  ui.submitBtn.addEventListener('click', submit);
  ui.clearBtn.addEventListener('click', clearEntry);
  ui.hintBtn.addEventListener('click', useHint);
  ui.replayBtn.addEventListener('click', () => playPrompt(false));
  ui.exportBtn.addEventListener('click', () => state.logger.downloadCSV());
  ui.flushBtn.addEventListener('click', () => state.logger.flush());
  ui.resetBtn.addEventListener('click', resetParticipant);

  addEventListener('keydown', (e) => {
    if (!state.running) return;
    if (e.key === 'Enter') { e.preventDefault(); submit(); }
    else if (e.key === 'Escape') { e.preventDefault(); clearEntry(); }
    else if (e.key.toLowerCase() === 'h') { e.preventDefault(); useHint(); }
  });
}

function resetParticipant() {
  const id = state.learner.userId;
  if (!confirm(`Reset ALL stored progress for ${id}?\n\n` +
               'Logged rows and the offline queue are NOT deleted — only this ' +
               "participant's mastery/streak history.")) return;
  state.learner.reset();
  renderAll();
}

// ---------------------------------------------------------------------------
// audio
// ---------------------------------------------------------------------------

function audioFor(track) {
  const key = String(track);
  if (!state.audio.has(key)) {
    const a = new Audio(`./audio/${String(track).padStart(4, '0')}.mp3`);
    a.preload = 'auto';
    state.audio.set(key, a);
  }
  return state.audio.get(key);
}

/**
 * Plays the prompt and starts the response-time clock when playback ENDS, not
 * when it starts -- otherwise response_time silently includes the clip length
 * and stops being comparable to the ESP32, where the same rule applies.
 */
function playPrompt(startClock = true) {
  const letter = state.current?.letter;
  if (!letter) return;
  const a = audioFor(letter.id + 1);
  const begin = () => { if (startClock) state.current.promptEndMs = performance.now(); };
  a.onended = begin;
  a.onerror = begin;                                   // missing clip must not stall the session
  a.currentTime = 0;
  a.play().catch(begin);                               // autoplay blocked -> still start the clock
  setTimeout(() => { if (startClock && state.current && state.current.promptEndMs === null) begin(); }, 4000);
}

function playCue(track) {
  const a = audioFor(track);
  a.currentTime = 0;
  a.play().catch(() => {});
}

// ---------------------------------------------------------------------------
// session
// ---------------------------------------------------------------------------

function activeSet() {
  const which = ui.charSet.value;
  if (which === 'vowels') return state.letters.filter((l) => l.category === 'vowel');
  if (which === 'consonants') return state.letters.filter((l) => l.category === 'consonant');
  return state.letters;
}

function startSession() {
  loadLearner();
  state.active = activeSet();
  const total = Math.max(1, Number(ui.setLen.value) || SESSION_TARGET_ATTEMPTS);
  state.session = {
    id: uuid(),
    number: state.learner.startSession(),
    attemptIndex: 0,
    total,
    mode: ui.mode.value,
  };
  state.running = true;
  ui.practice.classList.add('show');
  ui.setup.querySelectorAll('input,select').forEach((el) => { el.disabled = true; });
  ui.startBtn.disabled = true;
  ui.attemptTotal.textContent = total;
  state.pad.enable();
  playCue(59);                                        // "শুরু করা যাক"
  setTimeout(nextPrompt, 900);
}

function endSession(reason) {
  state.running = false;
  state.pad.disable();
  ui.practice.classList.remove('show');
  ui.setup.querySelectorAll('input,select').forEach((el) => { el.disabled = false; });
  ui.startBtn.disabled = false;
  state.current = null;
  if (reason !== 'stopped') playCue(60);
  state.logger.flush();
  renderAll();
}

/** Pick the next character, honouring the previous teaching action. */
function pickLetter(prevAction, prevLetter) {
  const seen = state.active.filter((l) => state.learner.char(l.id).seen > 0);

  if (prevAction === TEACHING_ACTION.REPEAT || prevAction === TEACHING_ACTION.HINT) {
    return prevLetter;
  }
  if (prevAction === TEACHING_ACTION.REVIEW_PREVIOUS && seen.length) {
    const weak = seen.filter((l) => state.learner.char(l.id).mastery < 0.6);
    const pool = weak.length ? weak : seen;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  if (state.session.mode === 'review') {
    const weak = seen.filter((l) => state.learner.char(l.id).mastery < 0.5);
    if (weak.length) return weak[Math.floor(Math.random() * weak.length)];
  }

  if (state.session.mode === 'targeted') {
    // Bias toward genuinely stale or genuinely weak characters so the rare
    // rules fire naturally. Feature values are never fabricated.
    const now = Date.now();
    const scored = state.active.map((l) => {
      const c = state.learner.char(l.id);
      const staleS = c.lastPracticeMs == null ? 0 : (now - c.lastPracticeMs) / 1000;
      const staleness = Math.min(1, staleS / 86400);
      const weakness = 1 - c.mastery;
      const wrongPressure = Math.min(1, c.wrongStreak / 3);
      return { l, score: weakness * 2 + staleness * 2 + wrongPressure * 3 + Math.random() * 0.5 };
    });
    scored.sort((a, b) => b.score - a.score);
    return scored[Math.floor(Math.random() * Math.min(5, scored.length))].l;
  }

  // normal: weight inversely to mastery, so weak characters recur more often
  const weights = state.active.map((l) => 0.15 + (1 - state.learner.char(l.id).mastery));
  const total = weights.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < state.active.length; i++) {
    r -= weights[i];
    if (r <= 0) return state.active[i];
  }
  return state.active[state.active.length - 1];
}

function nextPrompt(prevAction = null, prevLetter = null) {
  if (!state.running) return;
  if (state.session.attemptIndex >= state.session.total) return endSession('complete');

  const letter = pickLetter(prevAction, prevLetter);
  state.current = {
    letter,
    promptEndMs: null,
    tries: 0,          // tries within this prompt -> retry_count
    hints: 0,          // hints within this prompt -> hint_count
  };

  state.cell.clear();
  state.pad.reset();
  ui.hintBox.classList.remove('show');
  ui.feedback.classList.remove('show');
  ui.promptChar.textContent = displayChar(letter.char);
  ui.promptChar.classList.remove('prompt-hidden');
  ui.promptName.textContent = `${letter.name} — enter the dots you hear`;
  ui.unverifiedTag.classList.toggle('show', !letter.verified);
  ui.attemptNo.textContent = state.session.attemptIndex + 1;
  ui.diffLevel.textContent = state.learner.data.difficulty;
  playPrompt(true);
}

function clearEntry() {
  state.pad.reset();
  state.cell.clear();
}

function useHint() {
  if (!state.running || !state.current) return;
  state.current.hints += 1;
  const dots = state.current.letter.dots;
  ui.hintBox.textContent = `Hint: ${dots.length} dot${dots.length > 1 ? 's' : ''} — ${dots.join(', ')}`;
  ui.hintBox.classList.add('show');
  playCue(54);
}

// ---------------------------------------------------------------------------
// scoring -- the part that must mirror the firmware exactly
// ---------------------------------------------------------------------------

function submit() {
  if (!state.running || !state.current) return;
  const cur = state.current;
  const letter = cur.letter;
  const now = performance.now();
  const nowMs = Date.now();

  const enteredMask = state.pad.mask;
  if (enteredMask === 0 && state.pad.firstPressMs === null) return;   // nothing entered yet

  const expectedMask = dotsToMask(letter.dots);
  const correct = enteredMask === expectedMask;

  // --- feature sampling, per spec _feature_timing_contract ---------------
  // pre-attempt history, read BEFORE applyOutcome()
  const c = state.learner.char(letter.id);
  const pre = {
    prev_accuracy: state.learner.accuracy(letter.id),
    prev_mastery: c.mastery,
    prev_mistakes: c.mistakes,
    prev_confidence: c.lastConfidence,
    time_since_last_practice: state.learner.timeSinceLastPractice(letter.id, nowMs),
  };

  // current-attempt measurements
  const promptEnd = cur.promptEndMs === null ? now : cur.promptEndMs;
  const responseTime = state.pad.firstPressMs === null
    ? now - promptEnd
    : Math.max(0, state.pad.firstPressMs - promptEnd);

  // post-attempt: update history, THEN read the streaks
  const confidencePlaceholder = c.lastConfidence;
  state.learner.applyOutcome(letter.id, correct, confidencePlaceholder, nowMs);
  const after = state.learner.char(letter.id);

  const f = {
    char_id: letter.id,
    response_time: responseTime,
    press_duration: state.pad.meanPressDuration(now),
    retry_count: cur.tries,
    prev_accuracy: pre.prev_accuracy,
    prev_mastery: pre.prev_mastery,
    hint_count: cur.hints,
    session_number: state.session.number,
    difficulty_level: state.learner.data.difficulty,
    time_since_last_practice: pre.time_since_last_practice,
    prev_confidence: pre.prev_confidence,
    current_streak: after.streak,        // post-attempt: >0 means this attempt was correct
    wrong_streak: after.wrongStreak,     // post-attempt: >0 means this attempt was wrong
    prev_mistakes: pre.prev_mistakes,
  };

  // --- labels from the generated rule engine -----------------------------
  const confidence = evaluateConfidence(f);
  const action = evaluateTeachingAction(f);

  // store the confidence we actually computed, for the next attempt's feature 11
  after.lastConfidence = confidence;
  state.learner.save();

  applyDifficulty(action);

  state.logger.log({
    created_at: new Date().toISOString(),
    user_id: state.learner.userId,
    session_id: state.session.id,
    device_id: deviceId(),
    attempt_index: state.session.attemptIndex,
    ...f,
    teaching_action: action,
    confidence_state: confidence,
    expected_pattern: expectedMask,
    entered_pattern: enteredMask,
    is_correct: correct,
    press_order: JSON.stringify(state.pad.pressOrder),
    source: 'web',
    is_synthetic: false,
    spec_version: SPEC_VERSION,
    // Per-CHARACTER, not per-map. A row for a verified letter is usable even
    // while other letters are unconfirmed, so you can filter at training time
    // instead of discarding whole collection sessions.
    braille_map_verified: Boolean(letter.verified),
  });

  showFeedback(correct, action, confidence, expectedMask, enteredMask);
  state.session.attemptIndex += 1;
  cur.tries += 1;
  renderAll();

  const retryThisPrompt = !correct && cur.tries < MAX_TRIES_PER_PROMPT &&
    (action === TEACHING_ACTION.REPEAT || action === TEACHING_ACTION.HINT);

  setTimeout(() => {
    if (!state.running) return;
    if (state.session.attemptIndex >= state.session.total) return endSession('complete');
    if (retryThisPrompt) {
      if (action === TEACHING_ACTION.HINT) useHint();
      state.pad.reset();
      state.cell.clear();
      cur.promptEndMs = performance.now();
      ui.attemptNo.textContent = state.session.attemptIndex + 1;
      ui.feedback.classList.remove('show');
    } else {
      nextPrompt(action, letter);
    }
  }, correct ? 1100 : 1800);
}

function applyDifficulty(action) {
  const d = state.learner.data;
  if (action === TEACHING_ACTION.INCREASE_DIFFICULTY) d.difficulty = Math.min(5, d.difficulty + 1);
  else if (action === TEACHING_ACTION.REVIEW_PREVIOUS) d.difficulty = Math.max(1, d.difficulty - 1);
  state.learner.save();
}

function showFeedback(correct, action, confidence, expectedMask, enteredMask) {
  state.cell.showComparison(expectedMask, enteredMask);
  ui.feedback.className = 'feedback show ' + (correct ? 'ok' : 'bad');
  const want = maskToDots(expectedMask).join(',') || '—';
  const got = maskToDots(enteredMask).join(',') || '—';
  ui.feedback.innerHTML = correct
    ? `<b>সঠিক — correct.</b> dots ${want}` +
      `<span class="act">action: ${TEACHING_ACTION_NAMES[action]} · confidence: ${CONFIDENCE_STATE_NAMES[confidence]}</span>`
    : `<b>ভুল — expected dots ${want}, got ${got}</b>` +
      `<span class="act">action: ${TEACHING_ACTION_NAMES[action]} · confidence: ${CONFIDENCE_STATE_NAMES[confidence]}</span>`;
  playCue(correct ? 51 : 52);
}

// ---------------------------------------------------------------------------
// rendering
// ---------------------------------------------------------------------------

function barClass(v) { return v < 0.34 ? 'low' : v < 0.67 ? 'mid' : 'good'; }

function renderAll() {
  const s = state.learner.summary();
  ui.stRows.textContent = state.logger.rowCount;
  ui.stAcc.textContent = s.accuracy === null ? '—' : (s.accuracy * 100).toFixed(0) + '%';
  ui.stSess.textContent = s.sessions;
  ui.stDays.textContent = Math.max(s.days, state.logger.distinctDays());
  ui.stChars.textContent = s.charsSeen;
  ui.stQueue.textContent = state.logger.queueLength;

  renderClassTable(ui.taTable, TEACHING_ACTION_NAMES,
    state.logger.classCounts('teaching_action', TEACHING_ACTION_NAMES.length));
  renderClassTable(ui.csTable, CONFIDENCE_STATE_NAMES,
    state.logger.classCounts('confidence_state', CONFIDENCE_STATE_NAMES.length));
  renderCharTable();
}

function renderClassTable(table, names, counts) {
  const tbody = table.querySelector('tbody');
  const max = Math.max(30, ...counts);
  tbody.innerHTML = names.map((n, i) => {
    const v = counts[i];
    const pill = v >= 30 ? 'ok' : v > 0 ? 'warn' : 'bad';
    return `<tr>
      <td>${n}</td>
      <td class="num"><span class="pill ${pill}">${v}</span></td>
      <td><div class="bar"><i class="${v >= 30 ? 'good' : v > 0 ? 'mid' : 'low'}"
           style="width:${Math.min(100, (v / max) * 100)}%"></i></div></td>
    </tr>`;
  }).join('');
}

function renderCharTable() {
  const tbody = ui.charTable.querySelector('tbody');
  const rows = state.letters
    .map((l) => ({ l, c: state.learner.char(l.id) }))
    .filter((x) => x.c.seen > 0)
    .sort((a, b) => a.c.mastery - b.c.mastery);

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="color:var(--muted)">No attempts yet for this participant.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(({ l, c }) => {
    const acc = c.seen ? c.correct / c.seen : 0;
    return `<tr>
      <td style="font-size:1.2rem">${displayChar(l.char)}</td>
      <td style="color:var(--muted)">${l.name}</td>
      <td class="num">${c.seen}</td>
      <td class="num">${(acc * 100).toFixed(0)}%</td>
      <td><div class="bar"><i class="${barClass(c.mastery)}" style="width:${(c.mastery * 100).toFixed(0)}%"></i></div></td>
      <td class="num">${c.streak > 0 ? '+' + c.streak : c.wrongStreak > 0 ? '-' + c.wrongStreak : '0'}</td>
      <td class="num">${c.mistakes}</td>
    </tr>`;
  }).join('');
}

boot();
