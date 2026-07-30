// Braille cell rendering + the 6-key input surface.
//
// The cell is drawn from the dot array in data/braille_map.json, so correcting
// the Braille chart corrects the display with no code change. The glow and
// pulse stand in for the coin vibration motors on the hardware build -- one
// visual dot per physical motor, same indices.

export const DOTS = [1, 2, 3, 4, 5, 6];

/** [1,3] -> 0b000101. Matches BRAILLE_PATTERN in firmware/braille_map.h. */
export function dotsToMask(dots) {
  return dots.reduce((m, d) => m | (1 << (d - 1)), 0);
}

export function maskToDots(mask) {
  return DOTS.filter((d) => mask & (1 << (d - 1)));
}

export class BrailleCell {
  constructor(root) {
    this.root = root;
    this.els = new Map();
    for (const el of root.querySelectorAll('.dot')) {
      this.els.set(Number(el.dataset.dot), el);
    }
  }

  clear() {
    for (const el of this.els.values()) {
      el.classList.remove('on', 'correct', 'wrong', 'pulse');
    }
  }

  setMask(mask, { pulse = false } = {}) {
    for (const d of DOTS) {
      const el = this.els.get(d);
      const on = Boolean(mask & (1 << (d - 1)));
      el.classList.toggle('on', on);
      if (on && pulse) {
        el.classList.remove('pulse');
        void el.offsetWidth;          // restart the animation
        el.classList.add('pulse');
      }
    }
  }

  toggle(dot, on) {
    const el = this.els.get(dot);
    if (!el) return;
    el.classList.toggle('on', on);
    if (on) {
      el.classList.remove('pulse');
      void el.offsetWidth;
      el.classList.add('pulse');
    }
  }

  /** Show which dots were right and which were wrong after a submission. */
  showComparison(expectedMask, enteredMask) {
    for (const d of DOTS) {
      const el = this.els.get(d);
      const exp = Boolean(expectedMask & (1 << (d - 1)));
      const got = Boolean(enteredMask & (1 << (d - 1)));
      el.classList.remove('on', 'correct', 'wrong');
      if (exp && got) el.classList.add('correct');       // right dot, pressed
      else if (exp && !got) el.classList.add('wrong');   // missed a dot
      else if (!exp && got) el.classList.add('wrong');   // pressed a wrong dot
    }
  }
}

/**
 * 6-key input with per-dot press/release timing.
 *
 * Timing is what feeds response_time and press_duration, so it uses
 * performance.now() (monotonic) rather than Date.now(), which can jump if the
 * system clock is adjusted mid-session.
 */
export class KeyPad {
  constructor(container, { onChange } = {}) {
    this.container = container;
    this.onChange = onChange || (() => {});
    this.reset();

    this.keyEls = new Map();
    for (const el of container.querySelectorAll('.key')) {
      const dot = Number(el.dataset.dot);
      this.keyEls.set(dot, el);
      el.addEventListener('mousedown', (e) => { e.preventDefault(); this.press(dot); });
      el.addEventListener('mouseup', () => this.release(dot));
      el.addEventListener('mouseleave', () => { if (this.held.has(dot)) this.release(dot); });
      el.addEventListener('touchstart', (e) => { e.preventDefault(); this.press(dot); }, { passive: false });
      el.addEventListener('touchend', (e) => { e.preventDefault(); this.release(dot); }, { passive: false });
    }

    // Perkins brailler layout: S D F = dots 3 2 1, J K L = dots 4 5 6
    // Numpad 3x2 grid: 7 4 1 = dots 1 2 3 (Left), 8 5 2 = dots 4 5 6 (Right)
    this.keymap = {
      f: 1, d: 2, s: 3, j: 4, k: 5, l: 6,
      '7': 1, '4': 2, '1': 3,
      '8': 4, '5': 5, '2': 6,
      numpad7: 1, numpad4: 2, numpad1: 3,
      numpad8: 4, numpad5: 5, numpad2: 6,
    };
    this._down = (e) => {
      const k = e.key.toLowerCase();
      const c = e.code.toLowerCase();
      const dot = this.keymap[k] || this.keymap[c];
      if (dot && !e.repeat) { e.preventDefault(); this.press(dot); }
    };
    this._up = (e) => {
      const k = e.key.toLowerCase();
      const c = e.code.toLowerCase();
      const dot = this.keymap[k] || this.keymap[c];
      if (dot) { e.preventDefault(); this.release(dot); }
    };
    this.enabled = false;
  }

  enable() {
    if (this.enabled) return;
    addEventListener('keydown', this._down);
    addEventListener('keyup', this._up);
    this.enabled = true;
  }

  disable() {
    removeEventListener('keydown', this._down);
    removeEventListener('keyup', this._up);
    this.enabled = false;
  }

  reset() {
    this.mask = 0;
    this.held = new Map();     // dot -> press timestamp
    this.events = [];          // {dot, downMs, upMs}
    this.pressOrder = [];
    this.firstPressMs = null;
    if (this.keyEls) for (const el of this.keyEls.values()) el.classList.remove('active');
  }

  press(dot) {
    if (this.held.has(dot)) return;
    const now = performance.now();
    if (this.firstPressMs === null) this.firstPressMs = now;
    this.held.set(dot, now);
    this.keyEls.get(dot)?.classList.add('active');
    if (!this.pressOrder.includes(dot)) this.pressOrder.push(dot);
    this.mask |= (1 << (dot - 1));
    this.onChange(this.mask, dot, true);
  }

  release(dot) {
    const downMs = this.held.get(dot);
    if (downMs === undefined) return;
    this.held.delete(dot);
    this.keyEls.get(dot)?.classList.remove('active');
    this.events.push({ dot, downMs, upMs: performance.now() });
    this.onChange(this.mask, dot, false);
  }

  /** Mean press->release duration across the keys used this attempt, in ms.
   *  Keys still held at submit time are closed out at `now`. */
  meanPressDuration(now = performance.now()) {
    const durations = this.events.map((e) => e.upMs - e.downMs);
    for (const downMs of this.held.values()) durations.push(now - downMs);
    if (durations.length === 0) return 0;
    return durations.reduce((a, b) => a + b, 0) / durations.length;
  }
}
