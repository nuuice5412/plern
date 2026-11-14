/*
  ambient.js - a soft light that takes the colour of the cover you are hovering.

  How it works
    - every hover target (cards, table rows, hero covers) is scanned for an <img>
    - the image is drawn to a tiny canvas and its average mid-tone colour is cached
    - that colour drives the CSS variables of #ambient, positioned at the element

  Same-origin images only (everything is served by this Flask app), so the canvas
  is never tainted and no CORS setup is needed.
*/
(function () {
  const layer = document.getElementById('ambient');
  if (!layer) return;

  const HOVER_SELECTOR = '.rail-card, tr.track, .coll-card, .song-hero, .detail-head, .np-full';
  const cache = new Map();
  let current = null;

  function sample(img) {
    const src = img.currentSrc || img.src;
    if (!src) return null;
    if (cache.has(src)) return cache.get(src);

    let colour = null;
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 12;
      canvas.height = 12;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(img, 0, 0, 12, 12);
      const { data } = ctx.getImageData(0, 0, 12, 12);

      let r = 0, g = 0, b = 0, n = 0;
      for (let i = 0; i < data.length; i += 4) {
        const rr = data[i], gg = data[i + 1], bb = data[i + 2];
        const max = Math.max(rr, gg, bb), min = Math.min(rr, gg, bb);
        const light = (rr + gg + bb) / 3;
        // skip near-black and blown-out pixels, and dull greys
        if (light < 24 || light > 236) continue;
        if (max - min < 12) continue;
        r += rr; g += gg; b += bb; n += 1;
      }
      if (n > 0) {
        r = Math.round(r / n); g = Math.round(g / n); b = Math.round(b / n);
        // push saturation a little so the glow reads as a colour
        const grey = (r + g + b) / 3;
        const boost = 1.28;
        r = Math.min(255, Math.round(grey + (r - grey) * boost));
        g = Math.min(255, Math.round(grey + (g - grey) * boost));
        b = Math.min(255, Math.round(grey + (b - grey) * boost));
        colour = `rgb(${r} ${g} ${b})`;
      }
    } catch (err) {
      colour = null;
    }

    cache.set(src, colour);
    return colour;
  }

  function show(target) {
    const img = target.querySelector('img');
    if (!img) return;
    const colour = sample(img);
    if (!colour) return;

    const rect = target.getBoundingClientRect();
    // fall back to the card centre until the pointer actually moves
    const x = (rect.left + rect.width / 2) / window.innerWidth * 100;
    const y = (rect.top + Math.min(rect.height, 280) / 2) / window.innerHeight * 100;

    layer.style.setProperty('--ambient-color', colour);
    layer.style.setProperty('--ambient-x', `${x.toFixed(1)}%`);
    layer.style.setProperty('--ambient-y', `${y.toFixed(1)}%`);
    layer.classList.add('is-on');
  }

  document.addEventListener('mouseover', (event) => {
    const target = event.target.closest(HOVER_SELECTOR);
    if (!target || target === current) return;
    current = target;
    show(target);
  });

  // the glow chases the pointer instead of sitting on the element centre
  let frame = 0;
  let pointer = { x: 0, y: 0 };

  document.addEventListener('mousemove', (event) => {
    pointer.x = event.clientX / window.innerWidth * 100;
    pointer.y = event.clientY / window.innerHeight * 100;
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (!layer.classList.contains('is-on')) return;
      layer.style.setProperty('--ambient-x', `${pointer.x.toFixed(1)}%`);
      layer.style.setProperty('--ambient-y', `${pointer.y.toFixed(1)}%`);
    });
  }, { passive: true });

  document.addEventListener('mouseout', (event) => {
    const target = event.target.closest(HOVER_SELECTOR);
    if (!target) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    current = null;
    layer.classList.remove('is-on');
  });
})();
