/* =====================================================================
   player.js — music player (pure frontend, no library needed)

   How it works
   1) Every song row on the page is a <tr class="track"> with data-id / data-title / ...
   2) Press play -> build "queue" = all rows in the same table, then play in order
   3) On every play start, POST /api/play/<SongID> to record the listen
      into the HISTORY table (the database trigger then increments PlayCount)
   4) Two screens must update together: the bottom bar (mini) and the full screen (full)
      -> both are handled in a single place, syncUI()
   ===================================================================== */
(function () {
  'use strict';

  const audio = document.getElementById('audio');
  const playerEl = document.getElementById('player');
  if (!audio || !playerEl) return;

  const AUDIO_BASE = playerEl.dataset.audioBase || '/static/audio/';
  const PLAY_URL = playerEl.dataset.playUrl || '/api/play/';
  const byId = (id) => document.getElementById(id);

  // ---- bottom player bar ----
  const mini = {
    play: byId('btn-play'), prev: byId('btn-prev'), next: byId('btn-next'),
    shuffle: byId('btn-shuffle'), repeat: byId('btn-repeat'),
    seek: byId('seek'), vol: byId('vol'), cur: byId('cur'), total: byId('total'),
    cover: byId('np-cover'), title: byId('np-title'), artist: byId('np-artist'),
    plays: byId('np-plays'), tag: byId('np-tag'),
    expand: byId('btn-expand'), expandCover: byId('np-expand-cover'),
  };

  // ---- full screen ----
  const full = {
    root: byId('nowplaying'), bg: byId('np-bg'), cover: byId('npf-cover'),
    title: byId('npf-title'), artist: byId('npf-artist'), tag: byId('npf-tag'),
    play: byId('npf-play'), prev: byId('npf-prev'), next: byId('npf-next'),
    shuffle: byId('npf-shuffle'), repeat: byId('npf-repeat'),
    seek: byId('npf-seek'), vol: byId('npf-vol'),
    cur: byId('npf-cur'), total: byId('npf-total'),
    songLink: byId('npf-song-link'), minimize: byId('npf-minimize'),
    creditsBtn: byId('npf-credits-btn'), creditsPanel: byId('np-credits'),
    creditsList: byId('npc-list'), creditsArt: byId('npc-art'),
    fullscreen: byId('npf-fullscreen'), source: byId('npf-source'),
    pill: byId('npf-pill'), queueBtn: byId('npf-queue-btn'),
    queuePanel: byId('np-queue'), queueList: byId('np-queue-list'),
    queueClose: byId('np-queue-close'),
  };

  /** @type {Array<{id:number,title:string,artist:string,duration:number,el:HTMLElement,cover:string|null,href:string|null}>} */
  let queue = [];
  let cursor = -1;
  let shuffleOn = false;
  let repeatMode = 'off';           // off | all | one

  // playback modes are remembered across reloads (localStorage)
  const SHUFFLE_KEY = 'plern:shuffle';
  const REPEAT_KEY = 'plern:repeat';

  function readFlag(key) {
    try {
      return window.localStorage.getItem(key) === '1';
    } catch (error) {
      return false;
    }
  }

  function readMode() {
    try {
      const value = window.localStorage.getItem(REPEAT_KEY);
      return ['off', 'all', 'one'].includes(value) ? value : 'off';
    } catch (error) {
      return 'off';
    }
  }

  function writeState(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) { /* private mode */ }
  }
  let toastTimer = null;

  // ---- manifest (tells which song uses which audio file) ----
  let manifest = {};
  const manifestReady = fetch(AUDIO_BASE + 'manifest.json', { cache: 'no-cache' })
    .then(function (res) { return res.ok ? res.json() : { tracks: {} }; })
    .then(function (data) { manifest = (data && data.tracks) || {}; return manifest; })
    .catch(function () { return {}; });

  function entryFor(songId) { return manifest[String(songId)] || null; }

  function sourceFor(songId) {
    const entry = entryFor(songId);
    return AUDIO_BASE + ((entry && entry.file) || ('song_' + songId + '.wav'));
  }

  // ------------------------------------------------------------------ utils
  function fmt(seconds) {
    const s = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  function toast(message) {
    const el = byId('toast');
    if (!el) return;
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('show'); }, 3200);
  }

  function trackFromRow(row) {
    const img = row.querySelector('.cover img');
    const link = row.querySelector('a.title-link');
    return {
      id: Number(row.dataset.id),
      title: row.dataset.title || 'ไม่ทราบชื่อเพลง',
      artist: row.dataset.artist || '',
      duration: Number(row.dataset.duration) || 0,
      cover: img ? img.getAttribute('src') : (row.dataset.cover || null),
      href: link ? link.getAttribute('href') : (row.dataset.href || null),
      el: row,
    };
  }

  function rowsIn(container) {
    // supports both song tables (tr.track) and home-page card rows (.rail-card)
    let items = container.querySelectorAll('tr.track');
    if (!items.length) {
      items = container.querySelectorAll('.rail-card[data-id]');
    }
    return Array.prototype.map.call(items, trackFromRow);
  }

  function highlight(row) {
    document.querySelectorAll('tr.track.is-playing').forEach(function (el) {
      el.classList.remove('is-playing');
      const btn = el.querySelector('.play-toggle');
      if (btn) btn.classList.remove('eq-active');   // restore the ▶ icon on the previous row
    });
    if (row) row.classList.add('is-playing');
  }

  // icons inside the play button: ▶ / ⏸ (crisp SVG, adjustable stroke weight) + 4 animated sound bars
  const PLAY_SVG = '<span class="ico ico-play" aria-hidden="true"><svg viewBox="0 0 24 24">'
    + '<path d="M8.6 4.3v15.4c0 .9 1 1.4 1.7 1l12-7.7c.7-.4.7-1.4 0-1.8l-12-7.7c-.7-.5-1.7 0-1.7 .8z"/></svg></span>';
  const PAUSE_SVG = '<span class="ico ico-pause" aria-hidden="true"><svg viewBox="0 0 24 24">'
    + '<rect x="7" y="4.5" width="3.8" height="15" rx="1.3"/>'
    + '<rect x="13.2" y="4.5" width="3.8" height="15" rx="1.3"/></svg></span>';
  const ICON_PLAY = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
    + '<polygon points="8,5 21.5,12 8,19"/></svg>';
  const ICON_PAUSE = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
    + '<rect x="7" y="5" width="4" height="14" rx="1.4"/>'
    + '<rect x="13.5" y="5" width="4" height="14" rx="1.4"/></svg>';

  const EQ_ICON = '<span class="eq" aria-hidden="true"><i></i><i></i><i></i><i></i></span>';

  function decoratePlayButtons() {
    document.querySelectorAll('.play-toggle').forEach(function (btn) {
      if (btn.dataset.decorated) return;
      btn.innerHTML = PLAY_SVG + PAUSE_SVG + EQ_ICON;
      btn.dataset.decorated = '1';
    });
  }
  decoratePlayButtons();

  function setRowPlayState(playing) {
    if (cursor < 0) return;
    const row = queue[cursor] && queue[cursor].el;
    const btn = row && row.querySelector('.play-toggle');
    if (btn) btn.classList.toggle('eq-active', playing);
  }

  function paintCover(el, src, songId) {
    if (!el) return;
    el.style.setProperty('--h', (Number(songId) * 47) % 360);
    el.innerHTML = src ? '<img src="' + src + '" alt="">' : '<span>♪</span>';
  }

  // ------------------------------------------------------------------ UI
  function setActive(button, active) {
    if (!button) return;
    button.classList.toggle('is-active', !!active);
  }

  function syncUI(track) {
    const src = track.cover || null;
    const preview = !!(entryFor(track.id) && entryFor(track.id).source === 'itunes');

    paintCover(mini.cover, src, track.id);
    paintCover(full.cover, src, track.id);
    if (full.bg) {
      full.bg.style.backgroundImage = src ? 'url("' + src + '")' : 'none';
    }

    if (mini.title) mini.title.textContent = track.title;
    if (mini.artist) mini.artist.textContent = track.artist || '—';
    if (full.title) full.title.textContent = track.title;
    if (full.artist) full.artist.textContent = track.artist || '—';

    if (mini.tag) mini.tag.hidden = !preview;
    if (full.pill) full.pill.hidden = !preview;
    if (full.source) full.source.hidden = !preview;

    if (full.songLink) {
      if (track.href) {
        full.songLink.href = track.href;
        full.songLink.hidden = false;
      } else {
        full.songLink.hidden = true;
      }
    }
    if (creditsOpen) loadCredits(track.id);
    if (full.title && track.href) full.title.setAttribute('href', track.href);

    playerEl.dataset.idle = 'false';
    [mini.play, mini.prev, mini.next, mini.seek].forEach(function (el) {
      if (el) el.disabled = false;
    });

    const cell = track.el && track.el.querySelector('.plays');
    if (mini.plays && cell) mini.plays.textContent = cell.textContent.trim() + ' ครั้ง';
  }

  // ------------------------------------------------------------------ playback
  function recordPlay(songId) {
    fetch(PLAY_URL + songId, { method: 'POST' })
      .then(function (res) {
        return res.json().then(function (body) { return { ok: res.ok, body: body }; });
      })
      .then(function (result) {
        if (result.ok && result.body.ok) {
          const count = result.body.playCount;
          if (mini.plays) mini.plays.textContent = count + ' ครั้ง';
          const cell = document.querySelector('tr.track[data-id="' + songId + '"] .plays');
          if (cell) cell.textContent = count;
        } else if (result.body && result.body.reason) {
          toast(result.body.reason);
        }
      })
      .catch(function () { /* failing to log plays should never interrupt listening */ });
  }

  async function playAt(index) {
    if (index < 0 || index >= queue.length) return;
    cursor = index;
    const track = queue[index];

    await manifestReady;          // the real file name must be known before setting src

    audio.src = sourceFor(track.id);
    audio.play().catch(function () {
      toast('เล่นไฟล์เสียงไม่สำเร็จ (อาจยังไม่ได้สร้างไฟล์เสียง)');
    });

    syncUI(track);
    highlight(track.el);
    recordPlay(track.id);
  }

  function nextIndex() {
    if (!queue.length) return -1;
    if (repeatMode === 'one') return cursor;
    if (shuffleOn && queue.length > 1) {
      let idx;
      do { idx = Math.floor(Math.random() * queue.length); } while (idx === cursor);
      return idx;
    }
    if (cursor + 1 < queue.length) return cursor + 1;
    return repeatMode === 'all' ? 0 : -1;
  }

  function goNext() {
    const idx = nextIndex();
    if (idx >= 0) playAt(idx);
  }

  function goPrev() {
    if (cursor > 0) playAt(cursor - 1);
    else if (queue.length) playAt(0);
  }

  function togglePlay() {
    if (cursor < 0) {
      if (queue.length) playAt(0);
      return;
    }
    if (audio.paused) audio.play().catch(function () {});
    else audio.pause();
  }

  // ------------------------------------------------------------------ full screen
  function openFull() {
    if (cursor < 0) { toast('เลือกเพลงก่อนแล้วค่อยขยาย'); return; }
    full.root.hidden = false;
    full.root.setAttribute('aria-hidden', 'false');
    document.body.classList.add('np-open');
  }

  function closeFull() {
    setCreditsView(false);            // go back to the cover when closing
    full.root.hidden = true;
    full.root.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('np-open');
  }

  // ------------------------------------------------------------------ wiring
  // profile dropdown (topbar)
  (function () {
    const wrap = byId('profile-menu');
    const button = byId('profile-btn');
    const drop = byId('profile-drop');
    if (!wrap || !button || !drop) return;

    function close() {
      drop.hidden = true;
      button.setAttribute('aria-expanded', 'false');
    }
    function open() {
      drop.hidden = false;
      button.setAttribute('aria-expanded', 'true');
    }

    button.addEventListener('click', function (event) {
      event.stopPropagation();
      drop.hidden ? open() : close();
    });
    document.addEventListener('click', function (event) {
      if (!wrap.contains(event.target)) close();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') close();
    });
  })();

  document.addEventListener('click', function (event) {
    const toggle = event.target.closest('.play-toggle');
    if (toggle) {
      const row = toggle.closest('tr.track');
      const table = row && row.closest('table');
      if (!row || !table) return;
      const rows = rowsIn(table);
      const index = rows.findIndex(function (t) { return t.el === row; });
      if (index < 0) return;

      if (queue.length && queue[cursor] && queue[cursor].el === row) {
        togglePlay();
        return;
      }
      queue = rows;
      playAt(index);
      return;
    }

    const listButton = event.target.closest('[data-play-list]');
    if (listButton) {
      const container = document.querySelector(listButton.dataset.playList);
      if (!container) return;
      const rows = rowsIn(container);
      if (!rows.length) { toast('ไม่มีเพลงให้เล่นในรายการนี้'); return; }
      queue = rows;
      playAt(0);
      return;
    }

    const singleButton = event.target.closest('[data-play-song]');
    if (singleButton) {
      event.preventDefault();      // the song card is inside an <a> — don't navigate away
      const clickedId = Number(singleButton.dataset.id);

      // Build the queue from the surrounding collection so prev/next work,
      // instead of a one-track queue that makes those buttons look broken.
      const collection = singleButton.closest('.rail-track, tbody, ol, ul');
      if (collection) {
        const items = rowsIn(collection);
        const position = items.findIndex(function (t) { return t.id === clickedId; });
        if (items.length > 1 && position >= 0) {
          queue = items;
          playAt(position);
          return;
        }
      }

      queue = [trackFromRow(singleButton)];
      playAt(0);
    }
  });

  // control buttons (exist in both the bottom bar and the full screen)
  [[mini.play, togglePlay], [full.play, togglePlay],
   [mini.next, goNext], [full.next, goNext],
   [mini.prev, goPrev], [full.prev, goPrev],
   [mini.expand, openFull], [mini.expandCover, openFull],
   [full.minimize, closeFull]].forEach(function (pair) {
    if (pair[0]) pair[0].addEventListener('click', pair[1]);
  });

  // shuffle
  function toggleShuffle() {
    shuffleOn = !shuffleOn;
    writeState(SHUFFLE_KEY, shuffleOn ? '1' : '0');
    setActive(mini.shuffle, shuffleOn);
    setActive(full.shuffle, shuffleOn);
    toast(shuffleOn ? 'สุ่มเพลง: เปิด' : 'สุ่มเพลง: ปิด');
  }
  if (mini.shuffle) mini.shuffle.addEventListener('click', toggleShuffle);
  if (full.shuffle) full.shuffle.addEventListener('click', toggleShuffle);

  // restore the saved shuffle / repeat state on load
  shuffleOn = readFlag(SHUFFLE_KEY);
  setActive(mini.shuffle, shuffleOn);
  setActive(full.shuffle, shuffleOn);
  repeatMode = readMode();
  setActive(mini.repeat, repeatMode !== 'off');
  setActive(full.repeat, repeatMode !== 'off');
  [mini.repeat, full.repeat].forEach(function (btn) {
    if (btn) btn.dataset.mode = repeatMode;
  });

  // repeat: off -> all -> one
  function cycleRepeat() {
    repeatMode = repeatMode === 'off' ? 'all' : repeatMode === 'all' ? 'one' : 'off';
    writeState(REPEAT_KEY, repeatMode);
    setActive(mini.repeat, repeatMode !== 'off');
    setActive(full.repeat, repeatMode !== 'off');
    [mini.repeat, full.repeat].forEach(function (btn) {
      if (btn) btn.dataset.mode = repeatMode;
    });
    toast(repeatMode === 'off' ? 'เล่นซ้ำ: ปิด'
        : repeatMode === 'all' ? 'เล่นซ้ำ: ทั้งอัลบั้ม/ทั้งคิว' : 'เล่นซ้ำ: เพลงนี้เพลงเดียว');
  }
  if (mini.repeat) mini.repeat.addEventListener('click', cycleRepeat);
  if (full.repeat) full.repeat.addEventListener('click', cycleRepeat);

  // browser fullscreen (⛶ button)
  if (full.fullscreen) {
    full.fullscreen.addEventListener('click', function () {
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(function () {});
      } else {
        document.documentElement.requestFullscreen().catch(function () {
          toast('เบราว์เซอร์ไม่อนุญาตให้เต็มหน้าจอ');
        });
      }
    });
  }

  // ---------- credits tab (shown in the full screen, no need to visit the song page) ----------
  let creditsOpen = false;
  const creditsCache = new Map();
  // display order matching Apple Music / Tidal: producer -> composer -> singer
  const ROLE_ORDER = { Producer: 1, Composer: 2, Lyricist: 3, Featured: 4, Singer: 5 };

  function setCreditsView(open) {
    creditsOpen = open;
    if (full.creditsBtn) full.creditsBtn.classList.toggle('is-active', open);
    if (full.creditsPanel) full.creditsPanel.hidden = !open;
    if (full.cover) full.cover.hidden = open;
    if (open && cursor >= 0) loadCredits(queue[cursor].id);
  }

  async function loadCredits(songId) {
    if (!full.creditsList) return;

    let data = creditsCache.get(songId);
    if (!data) {
      full.creditsList.innerHTML = '<div class="np-credit-value">กำลังโหลด…</div>';
      try {
        const res = await fetch('/api/song/' + songId);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        data = await res.json();
        creditsCache.set(songId, data);
      } catch (error) {
        full.creditsList.innerHTML = '<div class="np-credit-value">โหลดเครดิตไม่สำเร็จ</div>';
        return;
      }
    }
    if (!creditsOpen) return;          // the user may have closed the tab while waiting
    renderCredits(data);
  }

  function renderCredits(data) {
    const track = queue[cursor];
    if (full.creditsArt && track) paintCover(full.creditsArt, track.cover, track.id);

    const groups = new Map();
    (data.credits || []).forEach(function (item) {
      const key = item.Role || item.Label;
      if (!groups.has(key)) groups.set(key, { label: item.ShortLabel || item.Label || item.Role, names: [] });
      const bucket = groups.get(key);
      if (bucket.names.indexOf(item.ArtistName) === -1) bucket.names.push(item.ArtistName);
    });

    const ordered = [...groups.entries()].sort(function (a, b) {
      return (ROLE_ORDER[a[0]] || 9) - (ROLE_ORDER[b[0]] || 9);
    });

    let html = '';
    ordered.forEach(function (entry) {
      html += '<div class="np-credit-group">' +
              '<div class="np-credit-label">' + entry[1].label + '</div>' +
              '<div class="np-credit-value">' + entry[1].names.join(', ') + '</div></div>';
    });
    if (data.releasedYearBE) {
      html += '<div class="np-credit-group"><div class="np-credit-label">ออกเมื่อ</div>' +
              '<div class="np-credit-value">' + data.releasedYearBE + '</div></div>';
    }
    html += '<div class="np-credit-group"><div class="np-credit-label">จำนวนครั้งที่เล่น</div>' +
            '<div class="np-credit-value">' + data.plays + '</div></div>';

    full.creditsList.innerHTML = html;
  }

  if (full.creditsBtn) {
    full.creditsBtn.addEventListener('click', function () { setCreditsView(!creditsOpen); });
  }

  // ---------- queue ----------
  function renderQueue() {
    if (!full.queueList) return;
    full.queueList.innerHTML = queue.map(function (track, index) {
      const active = index === cursor ? ' class="active"' : '';
      const cover = track.cover
        ? '<img src="' + track.cover + '" alt="">'
        : '<span>♪</span>';
      return '<li' + active + ' data-index="' + index + '">' +
             '<span class="q-cover cover">' + cover + '</span>' +
             '<span class="q-title">' + track.title + '</span>' +
             '<span class="q-artist">' + (track.artist || '') + '</span>' +
             '</li>';
    }).join('');
  }

  function toggleQueue(force) {
    if (!full.queuePanel) return;
    const show = typeof force === 'boolean' ? force : full.queuePanel.hidden;
    if (show) renderQueue();
    full.queuePanel.hidden = !show;
  }

  if (full.queueBtn) {
    full.queueBtn.addEventListener('click', function () { toggleQueue(); });
  }
  if (full.queueClose) {
    full.queueClose.addEventListener('click', function () { toggleQueue(false); });
  }
  if (full.queueList) {
    full.queueList.addEventListener('click', function (event) {
      const item = event.target.closest('li[data-index]');
      if (!item) return;
      playAt(Number(item.dataset.index));
      renderQueue();
    });
  }

  // progress
  audio.addEventListener('timeupdate', function () {
    const duration = audio.duration || 0;
    const percent = duration > 0 ? (audio.currentTime / duration) * 100 : 0;
    [mini.cur, full.cur].forEach(function (el) { if (el) el.textContent = fmt(audio.currentTime); });
    [mini.total, full.total].forEach(function (el) { if (el) el.textContent = fmt(duration); });
    [mini.seek, full.seek].forEach(function (el) { if (el) el.value = String(percent); });
  });

  audio.addEventListener('loadedmetadata', function () {
    [mini.total, full.total].forEach(function (el) {
      if (el) el.textContent = fmt(audio.duration);
    });
  });

  audio.addEventListener('play', function () {
    if (mini.play) mini.play.innerHTML = ICON_PAUSE;
    if (full.play) full.play.innerHTML = ICON_PAUSE;
    setRowPlayState(true);
  });

  audio.addEventListener('pause', function () {
    if (mini.play) mini.play.innerHTML = ICON_PLAY;
    if (full.play) full.play.innerHTML = ICON_PLAY;
    setRowPlayState(false);
  });

  audio.addEventListener('ended', function () {
    if (repeatMode === 'one') {
      audio.currentTime = 0;
      audio.play().catch(function () {});
      return;
    }
    const idx = nextIndex();
    if (idx >= 0 && idx !== cursor) {
      playAt(idx);
    } else if (idx >= 0 && repeatMode === 'all') {
      playAt(idx);
    } else {
      if (mini.play) mini.play.innerHTML = ICON_PLAY;
      if (full.play) full.play.innerHTML = ICON_PLAY;
    }
  });

  audio.addEventListener('error', function () {
    if (audio.src) toast('ไม่พบไฟล์เสียงของเพลงนี้');
  });

  // seek position + volume (kept in sync across both screens)
  [mini.seek, full.seek].forEach(function (el) {
    if (!el) return;
    el.addEventListener('input', function () {
      if (audio.duration) {
        audio.currentTime = (Number(el.value) / 100) * audio.duration;
      }
    });
  });

  // volume + playback modes: remember them in localStorage across refreshes
  const VOLUME_KEY = 'plern:volume';


  function readSavedVolume() {
    try {
      const raw = window.localStorage.getItem(VOLUME_KEY);
      if (raw === null) return null;
      const value = Number(raw);
      return Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
    } catch (error) {
      return null;                 // some browsers disable localStorage in private mode
    }
  }

  function saveVolume(value) {
    try {
      window.localStorage.setItem(VOLUME_KEY, String(value));
    } catch (error) {
      /* if it can't be stored, that's fine — the value just isn't remembered */
    }
  }

  function applyVolume(value) {
    audio.volume = value;
    if (mini.vol) mini.vol.value = String(value);
    if (full.vol) full.vol.value = String(value);
  }

  [mini.vol, full.vol].forEach(function (el) {
    if (!el) return;
    el.addEventListener('input', function () {
      const value = Number(el.value);
      applyVolume(value);
      saveVolume(value);
    });
  });

  const savedVolume = readSavedVolume();
  applyVolume(savedVolume === null ? (mini.vol ? Number(mini.vol.value) : 0.8) : savedVolume);

  // keyboard: Space = play/pause, Esc = collapse the full screen
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && full.root && !full.root.hidden) {
      if (creditsOpen) setCreditsView(false);   // close the credits tab first
      else closeFull();
      return;
    }
    if (event.code !== 'Space') return;
    const tag = (event.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button') return;
    event.preventDefault();
    togglePlay();
  });
})();






