/*
  search.js - type-ahead suggestions under the search box.

  Typing "s" shows matching artists and songs (prefix matches first, then any
  substring). Arrow keys move, Enter opens, Escape closes; submitting the form
  still runs the full search page.
*/
(function () {
  const form = document.querySelector('form.search');
  const input = form && form.querySelector('input[name="q"]');
  const panel = document.getElementById('search-suggest');
  if (!form || !input || !panel) return;

  let items = [];          // { el, href }
  let active = -1;         // index in items
  let timer = 0;
  let lastQuery = '';
  let controller = null;

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function highlight(text, query) {
    const safe = escapeHtml(text);
    if (!query) return safe;
    const index = safe.toLowerCase().indexOf(query.toLowerCase());
    if (index < 0) return safe;
    return safe.slice(0, index) + '<mark>' + safe.slice(index, index + query.length) +
           '</mark>' + safe.slice(index + query.length);
  }

  function close() {
    panel.hidden = true;
    panel.innerHTML = '';
    items = [];
    active = -1;
    input.setAttribute('aria-expanded', 'false');
  }

  function setActive(index) {
    if (!items.length) return;
    active = (index + items.length) % items.length;
    items.forEach(function (item, i) {
      item.el.classList.toggle('is-active', i === active);
    });
    items[active].el.scrollIntoView({ block: 'nearest' });
    input.setAttribute('aria-activedescendant', 'sg-' + active);
  }

  function render(data) {
    const query = data.q || '';
    const parts = [];

    if (data.artists.length) {
      parts.push('<div class="sg-label">ศิลปิน</div>');
      data.artists.forEach(function (artist) {
        const face = artist.photo
          ? '<span class="sg-ico is-photo is-round"><img src="' + artist.photo + '" alt="" loading="lazy"></span>'
          : '<span class="sg-ico">👤</span>';
        parts.push(
          '<a class="sg-item" role="option" href="/artist/' + artist.id + '">' +
            face +
            '<span class="sg-text"><span class="sg-title">' + highlight(artist.name, query) + '</span>' +
            '<span class="sg-sub">ศิลปิน</span></span>' +
          '</a>');
      });
    }

    if (data.songs.length) {
      parts.push('<div class="sg-label">เพลง</div>');
      data.songs.forEach(function (song) {
        const art = song.cover
          ? '<span class="sg-ico is-photo"><img src="' + song.cover + '" alt="" loading="lazy"></span>'
          : '<span class="sg-ico">♪</span>';
        parts.push(
          '<a class="sg-item" role="option" href="/song/' + song.id + '">' +
            art +
            '<span class="sg-text"><span class="sg-title">' + highlight(song.title, query) + '</span>' +
            '<span class="sg-sub">' + escapeHtml(song.artist || '') + '</span></span>' +
          '</a>');
      });
    }

    if (!parts.length) {
      panel.innerHTML = '<div class="sg-empty">ไม่พบ "' + escapeHtml(query) + '"</div>';
      panel.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      items = [];
      active = -1;
      return;
    }

    parts.push('<a class="sg-all" href="/search?q=' + encodeURIComponent(query) + '">' +
               'ดูผลลัพธ์ทั้งหมดของ "' + escapeHtml(query) + '" →</a>');
    panel.innerHTML = parts.join('');
    panel.hidden = false;
    input.setAttribute('aria-expanded', 'true');

    items = Array.from(panel.querySelectorAll('.sg-item')).map(function (el, i) {
      el.id = 'sg-' + i;
      return { el: el, href: el.getAttribute('href') };
    });
    active = -1;
    input.removeAttribute('aria-activedescendant');
  }

  async function load(query) {
    lastQuery = query;
    if (controller) controller.abort();
    controller = new AbortController();
    try {
      const response = await fetch('/api/suggest?q=' + encodeURIComponent(query),
                                   { signal: controller.signal });
      if (!response.ok) return;
      const data = await response.json();
      if (query !== lastQuery) return;          // a newer keystroke already won
      render(data);
    } catch (error) {
      if (error.name !== 'AbortError') close();
    }
  }

  input.addEventListener('input', function () {
    const query = input.value.trim();
    window.clearTimeout(timer);
    if (!query) { close(); return; }
    timer = window.setTimeout(function () { load(query); }, 170);
  });

  input.addEventListener('keydown', function (event) {
    if (panel.hidden) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive(active + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive(active - 1);
    } else if (event.key === 'Enter') {
      if (active >= 0 && items[active]) {
        event.preventDefault();
        window.location.href = items[active].href;
      }
    } else if (event.key === 'Escape') {
      close();
    }
  });

  input.addEventListener('focus', function () {
    if (input.value.trim() && panel.innerHTML) panel.hidden = false;
  });

  document.addEventListener('click', function (event) {
    if (!form.contains(event.target)) close();
  });

  form.addEventListener('submit', function () { close(); });
})();
