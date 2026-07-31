// Build docs/BraillePresentation.pptx from the generated diagrams.
//
//   node tools/build_deck.js
//
// Design decisions worth knowing before editing this file:
//
//   * Each diagram in docs/diagrams/ is already a complete 16:9 slide with its
//     own title, subtitle and footnote. So diagram slides are FULL BLEED --
//     adding a second PowerPoint title on top would duplicate the one already
//     drawn inside the image.
//
//   * Slides that are talking points rather than structure (title, limitations,
//     next steps) are built from NATIVE pptxgenjs shapes and text, so they are
//     directly editable without any conversion step.
//
//   * Images are inserted as PNG here. A Python post-step then attaches the
//     matching SVG as an svgBlip with the PNG kept as fallback -- that is
//     exactly what PowerPoint itself writes when you insert an SVG, and it is
//     what enables right-click > Convert to Shape. pptxgenjs cannot emit that
//     structure on its own.
//
//   * Every slide background is set explicitly to FFFFFF. Pure white was a
//     hard requirement, and relying on the theme default would not guarantee it.
//
//   * Speaker notes carry the spoken version of each slide. They are plain
//     text and fully editable.

const path = require('path');
const fs = require('fs');
const pptxgen = require('pptxgenjs');

const ROOT = path.resolve(__dirname, '..');
const DIA = path.join(ROOT, 'docs', 'diagrams');
const OUT = path.join(ROOT, 'docs', 'BraillePresentation.pptx');

// Read the real numbers so a slide can never contradict the repo.
const M = JSON.parse(fs.readFileSync(path.join(ROOT, 'models', 'metrics.json'), 'utf8'));
const BMAP = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'braille_map.json'), 'utf8'));
const N_VERIFIED = BMAP.letters.filter((l) => l.verified).length;
const PARAMS = M.params.toLocaleString('en-US');
const TFLITE = M.tflite_bytes.toLocaleString('en-US');
const TEACH = (M.test.teaching_combined * 100).toFixed(1);
const CONF = (M.test.confidence_combined * 100).toFixed(1);

// palette -- matches the diagrams
const INK = '111827';
const MUTED = '6B7280';
const LINE = 'CBD5E1';
const SIM = '2563EB';
const DATA = '7C3AED';
const MODEL = '0D9488';
const HW = 'EA580C';
const APP = 'DB2777';
const OK = '059669';
const WARN = 'D97706';
const BAD = 'DC2626';

const W = 13.333;
const H = 7.5;

const SLIDES = [
  ['01_system_overview',
   'The whole system in one view. Five stages: a web simulation collects real learner data, ' +
   'Supabase stores it, a tiny model is trained on it, that model runs offline on an ESP32, ' +
   'and a mobile app shows teachers the results. Three stages are built and tested today; ' +
   'the device and the app are designed but not yet built.'],
  ['02_phase1_simulation',
   'Phase one is a measuring instrument, not a toy. It teaches Braille in the browser and records ' +
   '14 numbers for every single attempt. Because no hardware is needed, data collection can start ' +
   'weeks before any component arrives — and the same rule engine here is generated into the ' +
   'firmware, so the two can never disagree.'],
  ['03_features_and_labels',
   'The 14 inputs and the 2 outputs. The important design point is on the left: there is no ' +
   '"is correct" input. The two streaks are read after scoring, so correctness is already implied ' +
   'by them. That is what lets the network reproduce every rule the engine applies.'],
  ['04_data_pipeline',
   'How the training set is built. The order is deliberate: collect real data first, measure its ' +
   'timing distributions, then generate synthetic data fitted to those measurements. Generating ' +
   'synthetic data first would produce rows fitted to nothing.'],
  ['05_model_architecture',
   `The model itself. ${PARAMS} parameters, ${TFLITE} bytes after quantization. The amber band at the ` +
   'bottom is the honest framing: the labels come from a hand-written rule engine, so the network ' +
   `learns to reproduce that engine at ${TEACH} per cent. That is a real achievement in compression, ` +
   'not autonomous discovery of teaching strategy.'],
  ['06_esp32_fit',
   'Does it fit? Comfortably. 13.8 KB of 520 KB — under three per cent of the memory. Inference is ' +
   'under a millisecond. And it runs with the radio switched off, so the device needs no internet, ' +
   'costs nothing to run, and keeps every learner record local.'],
  ['07_training_to_deployment',
   'Five automated steps from CSV to a flashed microcontroller, with no hand-copied numbers. Two ' +
   'safeguards matter: golden test vectors are replayed on the device at boot, and the rules exist ' +
   'in one place then generate into three languages, proven equal across 3,000 test cases.'],
  ['08_hardware_architecture',
   'The hardware. An ESP32 with a speaker, six buttons, six vibration motors and an SD card. The two ' +
   'red and amber boxes are the failure modes that most often kill a build like this: an under-powered ' +
   'supply that reboots the board mid-session, and driving inductive motors without flyback protection.'],
  ['09_classroom_interaction',
   'What a student actually experiences. The device speaks a letter, they feel the raised reference, ' +
   'they press the dots they believe are right. If wrong, the correct dots buzz one at a time — that ' +
   'is the core teaching mechanism, letting a blind learner check their own answer by touch.'],
  ['10_teaching_actions',
   'The six decisions the system can make, and the exact rule that triggers each one. Note the two ' +
   'steps at the bottom: the rules are written first from teaching principles, and the network is ' +
   'then trained to reproduce them small enough to run on the microcontroller.'],
  ['11_teacher_mobile_app',
   'The planned teacher app. A teacher does not want raw rows — they want to know who is improving, ' +
   'which letters are failing, and what to do next. The data needs no new pipeline: it comes from the ' +
   'SD card or the same database the web app already writes to.'],
  ['12_status_and_roadmap',
   'Honest status. The software is built and tested. The Braille data is partly verified. Real learner ' +
   'data, the hardware and the app have not been started. The critical path is data collection, because ' +
   'it needs calendar time — learners must practise on different days — and no amount of effort compresses that.'],
];

function bg(slide) {
  slide.background = { color: 'FFFFFF' };
}

function build() {
  const pres = new pptxgen();
  pres.defineLayout({ name: 'DIA16x9', width: W, height: H });
  pres.layout = 'DIA16x9';
  pres.author = 'EEE 416 Project';
  pres.title = 'AI-Assisted Bangla Braille Tutor';

  // ---------------------------------------------------------------- title
  const t = pres.addSlide();
  bg(t);
  t.addText('AI-Assisted', {
    x: 0.9, y: 1.55, w: 11.5, h: 0.66, fontSize: 40, color: MUTED,
    fontFace: 'Arial', margin: 0,
  });
  t.addText('Bangla Braille Tutor', {
    x: 0.9, y: 2.25, w: 11.5, h: 0.95, fontSize: 54, bold: true, color: INK,
    fontFace: 'Arial', margin: 0,
  });
  t.addText('A TinyML system that teaches Braille and runs completely offline on a microcontroller', {
    x: 0.9, y: 3.35, w: 11.5, h: 0.5, fontSize: 18, color: MUTED,
    fontFace: 'Arial', margin: 0,
  });

  const stats = [
    [PARAMS, 'model parameters', MODEL],
    [`${TFLITE} B`, 'quantized size', MODEL],
    ['2.7%', 'of ESP32 memory', HW],
    ['< 1 ms', 'inference, offline', OK],
  ];
  stats.forEach(([big, small, color], i) => {
    const x = 0.9 + i * 2.95;
    t.addShape(pres.ShapeType.roundRect, {
      x, y: 4.3, w: 2.7, h: 1.35, fill: { color: 'FFFFFF' },
      line: { color, width: 1.5 }, rectRadius: 0.1,
    });
    t.addText(big, {
      x: x + 0.15, y: 4.5, w: 2.4, h: 0.5, fontSize: 24, bold: true,
      color: INK, fontFace: 'Arial', margin: 0,
    });
    t.addText(small, {
      x: x + 0.15, y: 5.02, w: 2.4, h: 0.35, fontSize: 12, color: MUTED,
      fontFace: 'Arial', margin: 0,
    });
  });

  t.addText('EEE 416  ·  Department of Electrical and Electronic Engineering', {
    x: 0.9, y: 6.35, w: 11.5, h: 0.4, fontSize: 13, color: MUTED,
    fontFace: 'Arial', margin: 0,
  });
  t.addNotes(
    'This project teaches Bangla Braille using a small neural network that runs entirely offline ' +
    'on a four-dollar microcontroller. The whole pipeline is built: a simulation that collects real ' +
    'learner data, a training pipeline, and firmware. What remains is collecting data from real ' +
    'learners and assembling the hardware.');

  // ------------------------------------------------------- diagram slides
  SLIDES.forEach(([name, notes]) => {
    const png = path.join(DIA, `${name}.png`);
    if (!fs.existsSync(png)) throw new Error(`missing diagram: ${png}`);
    const s = pres.addSlide();
    bg(s);
    // full bleed -- the diagram already contains its own title and footnote
    s.addImage({ path: png, x: 0, y: 0, w: W, h: H });
    s.addNotes(notes);
  });

  // ---------------------------------------------------------- limitations
  const lim = pres.addSlide();
  bg(lim);
  lim.addText('What this project has NOT yet shown', {
    x: 0.7, y: 0.5, w: 12, h: 0.55, fontSize: 34, bold: true, color: INK,
    fontFace: 'Arial', margin: 0,
  });
  lim.addText('Stating these plainly is stronger than being asked about them', {
    x: 0.7, y: 1.08, w: 12, h: 0.4, fontSize: 16, color: MUTED,
    fontFace: 'Arial', margin: 0,
  });

  const limits = [
    ['No real learner data yet',
     'Every accuracy figure comes from a synthetic pipeline test. Those rows were simulated and ' +
     'labelled by the same rule engine the model reproduces, so the numbers are circular.', BAD],
    [`Only ${N_VERIFIED} of 50 characters verified`,
     'The 11 vowels were read from reference images. The 39 consonants are still placeholder ' +
     'patterns. Of 11 vowel guesses, one was wrong — so roughly 3 or 4 consonants are likely wrong too.', WARN],
    ['The model imitates a rule engine',
     `It reproduces hand-written rules at ${TEACH} per cent. That is compression of an explicit policy ` +
     'into 1,161 parameters — a genuine TinyML result, but not autonomous discovery of teaching strategy.', WARN],
    ['The hardware has never been assembled',
     'The firmware is written and its generated headers compile and self-check, but no physical device ' +
     'exists. Nothing has run on real silicon.', BAD],
  ];
  limits.forEach(([title, body, color], i) => {
    const y = 1.72 + i * 1.35;
    lim.addShape(pres.ShapeType.roundRect, {
      x: 0.7, y, w: 12, h: 1.15, fill: { color: 'FFFFFF' },
      line: { color, width: 1.75 }, rectRadius: 0.08,
    });
    lim.addText(title, {
      x: 0.95, y: y + 0.13, w: 11.5, h: 0.35, fontSize: 17, bold: true,
      color: INK, fontFace: 'Arial', margin: 0,
    });
    lim.addText(body, {
      x: 0.95, y: y + 0.5, w: 11.5, h: 0.6, fontSize: 13, color: MUTED,
      fontFace: 'Arial', margin: 0,
    });
  });
  lim.addNotes(
    'These four limitations belong in the presentation, not hidden in an appendix. An examiner who ' +
    'finds them missing will assume they were concealed. Stated up front, they show the project is ' +
    'understood rather than oversold. Each one has a clear route to being resolved.');

  // ----------------------------------------------------------- next steps
  const nx = pres.addSlide();
  bg(nx);
  nx.addText('What happens next', {
    x: 0.7, y: 0.5, w: 12, h: 0.55, fontSize: 34, bold: true, color: INK,
    fontFace: 'Arial', margin: 0,
  });
  nx.addText('One task is on the critical path. Everything else runs in parallel.', {
    x: 0.7, y: 1.08, w: 12, h: 0.4, fontSize: 16, color: MUTED,
    fontFace: 'Arial', margin: 0,
  });

  // critical path callout
  nx.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y: 1.7, w: 12, h: 1.5, fill: { color: 'FFFFFF' },
    line: { color: BAD, width: 2.5 }, rectRadius: 0.1,
  });
  nx.addText('CRITICAL PATH  ·  start today', {
    x: 0.95, y: 1.85, w: 11.5, h: 0.30, fontSize: 13, bold: true, color: BAD,
    fontFace: 'Arial', margin: 0,
  });
  nx.addText('Collect real learner data', {
    x: 0.95, y: 2.17, w: 11.5, h: 0.42, fontSize: 22, bold: true, color: INK,
    fontFace: 'Arial', margin: 0,
  });
  nx.addText('Each learner must practise on DIFFERENT DAYS. Two of the 14 features — session number and ' +
             'time since last practice — carry no signal at all if every session happens in one sitting. ' +
             'This is calendar time, and no amount of effort compresses it.', {
    x: 0.95, y: 2.62, w: 11.5, h: 0.5, fontSize: 13, color: MUTED,
    fontFace: 'Arial', margin: 0,
  });

  const parallel = [
    ['Supply 39 consonant images', 'Drop them in, run one command. Fixes the remaining Braille patterns.', DATA],
    ['Order and assemble hardware', 'Work through the six bring-up sketches, one peripheral at a time.', HW],
    ['Re-record the audio', 'Replace synthetic speech with a human voice. Same filenames, drop-in.', APP],
    ['Retrain on real data', 'One day of work once the sessions exist. Then reflash the device.', MODEL],
  ];
  nx.addText('IN PARALLEL', {
    x: 0.7, y: 3.45, w: 12, h: 0.3, fontSize: 13, bold: true, color: MUTED,
    fontFace: 'Arial', margin: 0,
  });
  parallel.forEach(([title, body, color], i) => {
    const x = 0.7 + (i % 2) * 6.15;
    const y = 3.85 + Math.floor(i / 2) * 1.35;
    nx.addShape(pres.ShapeType.roundRect, {
      x, y, w: 5.85, h: 1.15, fill: { color: 'FFFFFF' },
      line: { color, width: 1.75 }, rectRadius: 0.08,
    });
    nx.addText(title, {
      x: x + 0.25, y: y + 0.14, w: 5.35, h: 0.35, fontSize: 16, bold: true,
      color: INK, fontFace: 'Arial', margin: 0,
    });
    nx.addText(body, {
      x: x + 0.25, y: y + 0.52, w: 5.35, h: 0.55, fontSize: 12.5, color: MUTED,
      fontFace: 'Arial', margin: 0,
    });
  });
  nx.addNotes(
    'The single most important point: data collection cannot be rushed at the end. It needs learners ' +
    'practising across multiple days, so it must start immediately and run while the hardware is being ' +
    'built. Everything in the lower half can happen at the same time.');

  return pres.writeFile({ fileName: OUT });
}

build()
  .then(() => {
    const kb = (fs.statSync(OUT).size / 1024).toFixed(0);
    console.log(`wrote ${path.relative(ROOT, OUT)}  (${SLIDES.length + 3} slides, ${kb} KB)`);
    console.log('next: python3 tools/embed_svg_in_pptx.py   # makes the diagrams editable');
  })
  .catch((e) => { console.error(e); process.exit(1); });
