// Data integrity layer: learner state, the offline write queue, and CSV export.
//
// Design rule: a lost network connection must never lose a row and must never
// interrupt a session. Every attempt is written to localStorage first, then
// pushed to Supabase. Failed pushes stay queued and retry later.

import { SUPABASE_URL, SUPABASE_ANON_KEY, DEVICE_ID_KEY } from './config.js';
import { FEATURE_RANGES, MASTERY_INITIAL, updateMastery } from './rule_engine.js';

const QUEUE_KEY = 'braille.queue';
const ROWS_KEY = 'braille.rows';
const STATE_PREFIX = 'braille.state.';

// Column order for CSV export and for the Supabase payload.
export const CSV_COLUMNS = [
  'created_at', 'user_id', 'session_id', 'device_id', 'attempt_index',
  ...FEATURE_RANGES.map((r) => r.name),
  'teaching_action', 'confidence_state',
  'expected_pattern', 'entered_pattern', 'is_correct', 'press_order',
  'source', 'is_synthetic', 'spec_version', 'braille_map_verified',
];

function readJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (err) {
    // Quota exceeded is the realistic failure here. Surface it loudly rather
    // than silently dropping collected data.
    console.error('localStorage write failed', key, err);
    return false;
  }
}

export function deviceId() {
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = 'dev_' + Math.random().toString(36).slice(2, 10);
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}

export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return 'sess_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// ---------------------------------------------------------------------------
// Learner state -- per participant, per character. This is what feeds features
// 5, 6, 10, 12, 13, 14 (prev_accuracy, prev_mastery, time_since_last_practice,
// current_streak, wrong_streak, prev_mistakes) and it MUST persist across
// sessions and across days, or those features carry no signal.
// ---------------------------------------------------------------------------

export class LearnerState {
  constructor(userId) {
    this.userId = userId;
    this.key = STATE_PREFIX + userId;
    const s = readJSON(this.key, null);
    this.data = s || {
      chars: {},          // charId -> {seen, correct, mastery, streak, wrongStreak, mistakes, lastPracticeMs, lastConfidence}
      sessionNumber: 0,
      difficulty: 1,
      sessionIds: [],
      days: [],
    };
  }

  save() { writeJSON(this.key, this.data); }

  char(id) {
    if (!this.data.chars[id]) {
      this.data.chars[id] = {
        seen: 0, correct: 0, mastery: MASTERY_INITIAL, streak: 0,
        wrongStreak: 0, mistakes: 0, lastPracticeMs: null, lastConfidence: 1,
      };
    }
    return this.data.chars[id];
  }

  /** Seconds since this character was last practiced. First ever sighting
   *  reports the clamp max, not 0 -- "never seen" is maximally stale, and
   *  reporting 0 would look like "just practiced" to the rule engine. */
  timeSinceLastPractice(id, nowMs) {
    const c = this.char(id);
    if (c.lastPracticeMs == null) {
      return FEATURE_RANGES.find((r) => r.name === 'time_since_last_practice').max;
    }
    return Math.max(0, (nowMs - c.lastPracticeMs) / 1000);
  }

  startSession() {
    this.data.sessionNumber += 1;
    const today = new Date().toISOString().slice(0, 10);
    if (!this.data.days.includes(today)) this.data.days.push(today);
    this.save();
    return this.data.sessionNumber;
  }

  /** Apply the outcome of a scored attempt. Order matters: features are read
   *  BEFORE this runs (pre-attempt history), then this updates the history. */
  applyOutcome(id, correct, confidence, nowMs) {
    const c = this.char(id);
    c.seen += 1;
    if (correct) {
      c.correct += 1;
      c.streak += 1;
      c.wrongStreak = 0;
    } else {
      c.mistakes += 1;
      c.wrongStreak += 1;
      c.streak = 0;
    }
    c.mastery = Math.max(0, Math.min(1, updateMastery(c.mastery, correct)));
    c.lastPracticeMs = nowMs;
    c.lastConfidence = confidence;
    this.save();
  }

  accuracy(id) {
    const c = this.char(id);
    return c.seen === 0 ? 0 : c.correct / c.seen;
  }

  summary() {
    const chars = Object.values(this.data.chars);
    const seen = chars.reduce((a, c) => a + c.seen, 0);
    const correct = chars.reduce((a, c) => a + c.correct, 0);
    return {
      charsSeen: chars.filter((c) => c.seen > 0).length,
      attempts: seen,
      accuracy: seen ? correct / seen : null,
      sessions: this.data.sessionNumber,
      days: this.data.days.length,
      difficulty: this.data.difficulty,
    };
  }

  reset() {
    localStorage.removeItem(this.key);
    this.data = { chars: {}, sessionNumber: 0, difficulty: 1, sessionIds: [], days: [] };
  }

  rebuildFromRows(rows) {
    this.data = {
      chars: {},
      sessionNumber: 0,
      difficulty: 1,
      sessionIds: [],
      days: [],
    };
    const userRows = rows.filter((r) => r.user_id === this.userId || !r.user_id)
                         .sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));
    
    for (const r of userRows) {
      if (r.session_id && !this.data.sessionIds.includes(r.session_id)) {
        this.data.sessionIds.push(r.session_id);
        this.data.sessionNumber = this.data.sessionIds.length;
      }
      if (r.created_at) {
        const day = new Date(r.created_at).toISOString().slice(0, 10);
        if (!this.data.days.includes(day)) this.data.days.push(day);
      }
      const charId = Number(r.char_id);
      const isCorrect = Boolean(r.is_correct);
      const conf = Number(r.confidence_state || 1);
      const ms = r.created_at ? new Date(r.created_at).getTime() : Date.now();
      if (!isNaN(charId)) {
        this.applyOutcome(charId, isCorrect, conf, ms);
      }
    }
    this.save();
  }
}

// ---------------------------------------------------------------------------
// Attempt logging: local first, then Supabase, with a durable retry queue.
// ---------------------------------------------------------------------------

export class AttemptLogger {
  constructor(onStatus) {
    this.onStatus = onStatus || (() => {});
    this.queue = readJSON(QUEUE_KEY, []);
    this.rows = readJSON(ROWS_KEY, []);
    this.flushing = false;
    this.configured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
    addEventListener('online', () => this.flush());
  }

  get queueLength() { return this.queue.length; }
  get rowCount() { return this.rows.length; }
  allRows() { return this.rows; }

  /** Append a row. Always succeeds locally; network is best-effort. */
  log(row) {
    this.rows.push(row);
    writeJSON(ROWS_KEY, this.rows);
    if (!this.configured) {
      this.onStatus('local', `${this.rows.length} rows local (no backend configured)`);
      return;
    }
    this.queue.push(row);
    writeJSON(QUEUE_KEY, this.queue);
    this.flush();
  }

  async flush() {
    if (this.flushing || !this.configured || this.queue.length === 0) return;
    if (!navigator.onLine) {
      this.onStatus('pending', `${this.queue.length} queued (offline)`);
      return;
    }
    this.flushing = true;
    try {
      // Send as one batch; Supabase accepts an array insert.
      const batch = this.queue.slice(0, 100);
      const res = await fetch(`${SUPABASE_URL}/rest/v1/attempts`, {
        method: 'POST',
        headers: {
          'apikey': SUPABASE_ANON_KEY,
          'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
          'Content-Type': 'application/json',
          'Prefer': 'return=minimal,resolution=ignore-duplicates',
        },
        body: JSON.stringify(batch),
      });

      if (res.ok || res.status === 409) {
        // 409 = the dedupe index rejected a replay. The row is already stored,
        // so dropping it from the queue is correct, not data loss.
        this.queue = this.queue.slice(batch.length);
        writeJSON(QUEUE_KEY, this.queue);
        this.onStatus(this.queue.length ? 'pending' : 'ok',
          this.queue.length ? `${this.queue.length} queued` : `synced · ${this.rows.length} rows`);
        this.flushing = false;
        if (this.queue.length) return this.flush();
        return;
      }

      const body = await res.text();
      this.onStatus('error', `sync failed ${res.status} — ${this.queue.length} queued`);
      console.error('Supabase insert failed', res.status, body);
    } catch (err) {
      this.onStatus('error', `offline — ${this.queue.length} queued`);
      console.error('Supabase insert threw', err);
    } finally {
      this.flushing = false;
    }
  }

  async syncRemoteForUser(userId, learner) {
    if (!this.configured || !navigator.onLine) return;
    try {
      const res = await fetch(`${SUPABASE_URL}/rest/v1/attempts?user_id=eq.${encodeURIComponent(userId)}&select=*`, {
        headers: {
          'apikey': SUPABASE_ANON_KEY,
          'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
        },
      });
      if (!res.ok) return;
      const remoteRows = await res.json();
      if (Array.isArray(remoteRows) && remoteRows.length > 0) {
        if (learner && typeof learner.rebuildFromRows === 'function') {
          learner.rebuildFromRows(remoteRows);
        }
        const existingKeys = new Set(this.rows.map((r) => `${r.session_id}:${r.attempt_index}`));
        let added = 0;
        for (const row of remoteRows) {
          const key = `${row.session_id}:${row.attempt_index}`;
          if (!existingKeys.has(key)) {
            this.rows.push(row);
            existingKeys.add(key);
            added++;
          }
        }
        writeJSON(ROWS_KEY, this.rows);
        this.onStatus('ok', `synced · ${this.rows.length} rows`);
      }
    } catch (e) {
      console.warn('Could not sync remote user rows:', e);
    }
  }

  toCSV() {
    const esc = (v) => {
      if (v === null || v === undefined) return '';
      const s = String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const lines = [CSV_COLUMNS.join(',')];
    for (const r of this.rows) lines.push(CSV_COLUMNS.map((c) => esc(r[c])).join(','));
    return lines.join('\n');
  }

  downloadCSV(filename) {
    const blob = new Blob([this.toCSV()], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename || `braille_attempts_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  classCounts(field, n) {
    const counts = new Array(n).fill(0);
    for (const r of this.rows) {
      const v = r[field];
      if (v >= 0 && v < n) counts[v] += 1;
    }
    return counts;
  }

  distinctDays() {
    return new Set(this.rows.map((r) => String(r.created_at).slice(0, 10))).size;
  }
}
