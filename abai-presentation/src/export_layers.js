// Render every slide of the HTML show into layers for the PowerPoint builder.
// Usage: node export_layers.js <show.html> <out_dir>
// Writes <out_dir>/manifest.json plus one JPEG background per slide and one image per element.
// Text is rendered here with the embedded fonts, so Kazakh letters look the same on every computer.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const [file, outDir] = process.argv.slice(2);
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  page.on('pageerror', e => console.error('page error:', e.message));
  await page.goto('file://' + path.resolve(file) + '?export=1');
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  const n = await page.evaluate(() => window.__exp.count);
  const W = 1920, H = 1080;
  const clamp = b => {
    const x0 = Math.max(0, Math.floor(b.x)), y0 = Math.max(0, Math.floor(b.y));
    const x1 = Math.min(W, Math.ceil(b.x + b.w)), y1 = Math.min(H, Math.ceil(b.y + b.h));
    return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
  };
  const shared = {};
  const manifest = [];
  for (let i = 0; i < n; i++) {
    const info = await page.evaluate(i => window.__exp.slide(i), i);
    await page.evaluate(i => window.__exp.isolate(i, -1), i);
    await page.waitForTimeout(80);
    const bg = `s${i + 1}_bg.jpg`;
    await page.screenshot({ path: path.join(outDir, bg), type: 'jpeg', quality: 92, clip: { x: 0, y: 0, width: W, height: H } });
    const slide = { title: info.title, tr: info.tr, notes: info.notes.trim(), bg, els: [] };
    for (const el of info.els) {
      const rec = { k: el.k, anim: el.anim, t: el.t, du: el.du, name: el.name, loop: el.loop, alt: el.alt, parts: [] };
      if (el.shared) {
        // shared art (medallion, portrait frames) is captured once with padding proportional to its size
        const p = el.box.w * 0.12;
        const outer = { x: el.box.x - p, y: el.box.y - p, w: el.box.w + 2 * p, h: el.box.h + 2 * p };
        if (!shared[el.shared]) {
          await page.evaluate(([i, k]) => window.__exp.isolate(i, k), [i, el.k]);
          const fn = `shared_${el.shared}.png`;
          await page.screenshot({ path: path.join(outDir, fn), omitBackground: true, clip: { x: outer.x, y: outer.y, width: outer.w, height: outer.h } });
          shared[el.shared] = fn;
        }
        rec.parts.push({ file: shared[el.shared], box: outer, shared: true });
      } else if (el.split) {
        // framed photo: the photo itself as JPEG, the frame, shadow and caption as PNG on top
        const pad = 60;
        const fb = clamp({ x: el.box.x - pad, y: el.box.y - pad, w: el.box.w + 2 * pad, h: el.box.h + 2 * pad });
        const pb = clamp(el.pbox);
        await page.evaluate(([i, k]) => window.__exp.isolate(i, k, 'photo'), [i, el.k]);
        const pf = `s${i + 1}_e${el.k}_photo.jpg`;
        await page.screenshot({ path: path.join(outDir, pf), type: 'jpeg', quality: 88, clip: pb });
        await page.evaluate(([i, k]) => window.__exp.isolate(i, k, 'frame'), [i, el.k]);
        const ff = `s${i + 1}_e${el.k}_frame.png`;
        await page.screenshot({ path: path.join(outDir, ff), omitBackground: true, clip: fb });
        rec.parts.push({ file: pf, box: { x: pb.x, y: pb.y, w: pb.width, h: pb.height } });
        rec.parts.push({ file: ff, box: { x: fb.x, y: fb.y, w: fb.width, h: fb.height }, trim: true });
      } else {
        await page.evaluate(([i, k]) => window.__exp.isolate(i, k), [i, el.k]);
        if (el.fmt === 'jpg') {
          const b = clamp(el.box);
          const f = `s${i + 1}_e${el.k}.jpg`;
          await page.screenshot({ path: path.join(outDir, f), type: 'jpeg', quality: 88, clip: b });
          rec.parts.push({ file: f, box: { x: b.x, y: b.y, w: b.width, h: b.height }, photo: true });
        } else {
          const pad = 70;
          const b = clamp({ x: el.box.x - pad, y: el.box.y - pad, w: el.box.w + 2 * pad, h: el.box.h + 2 * pad });
          const f = `s${i + 1}_e${el.k}.png`;
          await page.screenshot({ path: path.join(outDir, f), omitBackground: true, clip: b });
          rec.parts.push({ file: f, box: { x: b.x, y: b.y, w: b.width, h: b.height }, trim: true });
        }
      }
      slide.els.push(rec);
    }
    manifest.push(slide);
    process.stdout.write(`slide ${i + 1}: ${slide.els.length} layers\n`);
  }
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 1));
  await browser.close();
})();
