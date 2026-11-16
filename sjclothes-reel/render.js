#!/usr/bin/env node
// Renders reel.html to an MP4 (1080x1920, 30fps) with the soundtrack.
//   node render.js                 -> out/sjclothes-reel.mp4
//   node render.js --stills 1,5,9  -> out/stills/t_<sec>.png (quick design check)
//   node render.js --notags        -> hide the "PLACEHOLDER" labels on empty slots
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
const ROOT = __dirname, FOOT = path.join(ROOT, 'footage'), OUT = path.join(ROOT, 'out');
const args = process.argv.slice(2);
const stillsArg = args.includes('--stills') ? args[args.indexOf('--stills') + 1] : null;
const notags = args.includes('--notags');
const WORKERS = Math.max(1, require('os').cpus().length - 1);
fs.mkdirSync(OUT, { recursive: true });

// 1. Build the footage manifest (videos -> 30fps frame sequences cropped to 9:16)
function manifest() {
  const m = {};
  if (!fs.existsSync(FOOT)) return m;
  for (const f of fs.readdirSync(FOOT)) {
    const ext = path.extname(f).toLowerCase(), slot = path.basename(f, ext), src = path.join(FOOT, f);
    if (['.jpg', '.jpeg', '.png', '.webp'].includes(ext)) m[slot] = { type: 'image', src: 'footage/' + f };
    if (['.mp4', '.mov', '.m4v', '.webm'].includes(ext)) {
      const dir = path.join(FOOT, '.frames', slot), stamp = path.join(dir, '.src');
      const sig = String(fs.statSync(src).mtimeMs);
      if (!fs.existsSync(stamp) || fs.readFileSync(stamp, 'utf8') !== sig) {
        fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
        console.log('extracting frames:', f);
        execFileSync('ffmpeg', ['-v', 'error', '-i', src, '-t', '12', '-vf',
          'fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920', '-q:v', '3', path.join(dir, 'f_%05d.jpg')]);
        fs.writeFileSync(stamp, sig);
      }
      const frames = fs.readdirSync(dir).filter(x => x.endsWith('.jpg')).length;
      m[slot] = { type: 'video', dir: 'footage/.frames/' + slot, frames, fps: 30 };
    }
  }
  return m;
}

(async () => {
  const FOOTAGE = manifest();
  console.log('footage slots filled:', Object.keys(FOOTAGE).join(', ') || '(none — using placeholders)');
  const browser = await chromium.launch({ args: ['--allow-file-access-from-files'] });
  const url = 'file://' + path.join(ROOT, 'reel.html') + '?render=1' + (notags ? '&notags=1' : '');
  async function newPage() {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
    await page.addInitScript(m => { window.FOOTAGE = m; }, FOOTAGE);
    await page.goto(url); await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => Promise.all([...document.fonts].map(f => f.load())));
    return page;
  }
  const shot = async (page, t, file, type) => {
    await page.evaluate(t => window.seek(t), t);
    await page.screenshot({ path: file, type, ...(type === 'jpeg' ? { quality: 93 } : {}), clip: { x: 0, y: 0, width: 1080, height: 1920 } });
  };

  if (stillsArg) {
    const dir = path.join(OUT, 'stills'); fs.mkdirSync(dir, { recursive: true });
    const page = await newPage();
    for (const s of stillsArg.split(',').map(Number)) await shot(page, s, path.join(dir, `t_${s.toFixed(2)}.png`), 'png');
    await browser.close(); console.log('stills ->', dir); return;
  }

  const DUR = 28.0, FPS = 30, N = Math.round(DUR * FPS);
  const fdir = path.join(OUT, 'frames'); fs.rmSync(fdir, { recursive: true, force: true }); fs.mkdirSync(fdir, { recursive: true });
  let done = 0; const t0 = Date.now();
  await Promise.all(Array.from({ length: WORKERS }, async (_, w) => {
    const page = await newPage();
    for (let i = w; i < N; i += WORKERS) {
      await shot(page, i / FPS, path.join(fdir, `f_${String(i).padStart(5, '0')}.jpg`), 'jpeg');
      if (++done % 60 === 0) console.log(`frame ${done}/${N}  (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
    }
  }));
  await browser.close();

  // 2. Soundtrack (music + voiceover) and encode
  const audio = path.join(OUT, 'soundtrack.wav');
  if (!fs.existsSync(audio)) execFileSync('python3', [path.join(ROOT, 'audio', 'make_audio.py')], { stdio: 'inherit' });
  const mp4 = path.join(OUT, 'sjclothes-reel.mp4');
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-framerate', String(FPS), '-i', path.join(fdir, 'f_%05d.jpg'), '-i', audio,
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-movflags', '+faststart',
    '-c:a', 'aac', '-b:a', '192k', '-shortest', mp4], { stdio: 'inherit' });
  console.log('done ->', mp4);
})();
