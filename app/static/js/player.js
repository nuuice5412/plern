/* =====================================================================
   player.js — ตัวเล่นเพลง (frontend ล้วน ไม่ต้องใช้ library)

   หลักการทำงาน
   1) ทุกแถวเพลงในหน้าเป็น <tr class="track"> ที่มี data-id / data-title / ...
   2) กดเล่น -> เก็บ "queue" = ทุกแถวในตารางเดียวกัน แล้วเล่นตามลำดับ
   3) ทุกครั้งที่เริ่มเล่น จะยิง POST /api/play/<SongID> เพื่อบันทึกการฟัง
      ลงตาราง HISTORY (แล้ว trigger ในฐานข้อมูลจะบวก PlayCount ให้)
   4) มีสองหน้าจอที่ต้องอัปเดตพร้อมกัน: แถบล่าง (mini) และหน้าจอเต็ม (full)
      -> รวมไว้ที่ syncUI() ที่เดียว
   ===================================================================== */
(function () {
  'use strict';

  const audio = document.getElementById('audio');
  const playerEl = document.getElementById('player');
  if (!audio || !playerEl) return;

  const AUDIO_BASE = playerEl.dataset.audioBase || '/static/audio/';
  const PLAY_URL = playerEl.dataset.playUrl || '/api/play/';
  const byId = (id) => document.getElementById(id);

  // ---- แถบเล่นเพลงด้านล่าง ----
  const mini = {
    play: byId('btn-play'), prev: byId('btn-prev'), next: byId('btn-next'),
    shuffle: byId('btn-shuffle'), repeat: byId('btn-repeat'),
    seek: byId('seek'), vol: byId('vol'), cur: byId('cur'), total: byId('total'),
    cover: byId('np-cover'), title: byId('np-title'), artist: byId('np-artist'),
    plays: byId('np-plays'), tag: byId('np-tag'),
    expand: byId('btn-expand'), expandCover: byId('np-expand-cover'),
  };

  // ---- หน้าจอเต็ม ----
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
  let toastTimer = null;

  // ---- manifest (บอกว่าเพลงไหนใช้ไฟล์เสียงอะไร) ----
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
    // รองรับทั้งตารางเพลง (tr.track) และแถวการ์ดบนหน้าแรก (.rail-card)
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
      if (btn) btn.classList.remove('eq-active');   // คืนไอคอน ▶ ให้แถวเก่า
    });
    if (row) row.classList.add('is-playing');
  }

  // ไอคอนในปุ่มเล่น: ▶ / ⏸ (SVG คมชัด ปรับความหนาได้) + แท่งเสียง 4 แท่ง animated
  const PLAY_SVG = '<span class="ico ico-play" aria-hidden="true"><svg viewBox="0 0 24 24">'
    + '<path d="M8.6 4.3v15.4c0 .9 1 1.4 1.7 1l12-7.7c.7-.4.7-1.4 0-1.8l-12-7.7c-.7-.5-1.7 0-1.7 .8z"/></svg></span>';
  const PAUSE_SVG = '<span class="ico ico-pause" aria-hidden="true"><svg viewBox="0 0 24 24">'
    + '<rect x="7" y="4.5" width="3.8" height="15" rx="1.3"/>'
    + '<rect x="13.2" y="4.5" width="3.8" height="15" rx="1.3"/></svg></span>';
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

  // ------------------------------------------------------------------ เล่นเพลง
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
      .catch(function () { /* บันทึกประวัติไม่ควรทำให้การฟังสะดุด */ });
  }

  async function playAt(index) {
    if (index < 0 || index >= queue.length) return;
    cursor = index;
    const track = queue[index];

    await manifestReady;          // ต้องรู้ชื่อไฟล์จริงก่อนตั้ง src

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

  // ------------------------------------------------------------------ หน้าจอเต็ม
  function openFull() {
    if (cursor < 0) { toast('เลือกเพลงก่อนแล้วค่อยขยาย'); return; }
    full.root.hidden = false;
    full.root.setAttribute('aria-hidden', 'false');
    document.body.classList.add('np-open');
  }

  function closeFull() {
    setCreditsView(false);            // กลับไปหน้าปกเมื่อปิด
    full.root.hidden = true;
    full.root.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('np-open');
  }

  // ------------------------------------------------------------------ wiring
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
      event.preventDefault();      // การ์ดเพลงอยู่ใน <a> — อย่าให้พาไปหน้าใหม่
      queue = [trackFromRow(singleButton)];
      playAt(0);
    }
  });

  // ปุ่มควบคุม (มีทั้งแถบล่างและหน้าจอเต็ม)
  [[mini.play, togglePlay], [full.play, togglePlay],
   [mini.next, goNext], [full.next, goNext],
   [mini.prev, goPrev], [full.prev, goPrev],
   [mini.expand, openFull], [mini.expandCover, openFull],
   [full.minimize, closeFull]].forEach(function (pair) {
    if (pair[0]) pair[0].addEventListener('click', pair[1]);
  });

  // สุ่มเพลง
  function toggleShuffle() {
    shuffleOn = !shuffleOn;
    setActive(mini.shuffle, shuffleOn);
    setActive(full.shuffle, shuffleOn);
    toast(shuffleOn ? 'สุ่มเพลง: เปิด' : 'สุ่มเพลง: ปิด');
  }
  if (mini.shuffle) mini.shuffle.addEventListener('click', toggleShuffle);
  if (full.shuffle) full.shuffle.addEventListener('click', toggleShuffle);

  // เล่นซ้ำ: ปิด -> ทั้งหมด -> เพลงเดียว
  function cycleRepeat() {
    repeatMode = repeatMode === 'off' ? 'all' : repeatMode === 'all' ? 'one' : 'off';
    setActive(mini.repeat, repeatMode !== 'off');
    setActive(full.repeat, repeatMode !== 'off');
    if (mini.repeat) mini.repeat.textContent = repeatMode === 'one' ? '↻1' : '↻';
    if (full.repeat) full.repeat.textContent = repeatMode === 'one' ? '↻1' : '↻';
    toast(repeatMode === 'off' ? 'เล่นซ้ำ: ปิด'
        : repeatMode === 'all' ? 'เล่นซ้ำ: ทั้งอัลบั้ม/ทั้งคิว' : 'เล่นซ้ำ: เพลงนี้เพลงเดียว');
  }
  if (mini.repeat) mini.repeat.addEventListener('click', cycleRepeat);
  if (full.repeat) full.repeat.addEventListener('click', cycleRepeat);

  // เต็มหน้าจอของเบราว์เซอร์ (ปุ่ม ⛶)
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

  // ---------- แท็บเครดิต (แสดงในหน้าจอเต็ม ไม่ต้องไปหน้าเพลง) ----------
  let creditsOpen = false;
  const creditsCache = new Map();
  // ลำดับการแสดงผลแบบ Apple Music / Tidal: ฝ่ายผลิต -> ผู้แต่ง -> นักร้อง
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
    if (!creditsOpen) return;          // ผู้ใช้อาจปิดแท็บไปแล้วระหว่างรอ
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

  // ---------- คิวเพลง ----------
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

  // ความคืบหน้า
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
    if (mini.play) mini.play.textContent = '⏸';
    if (full.play) full.play.textContent = '⏸';
    setRowPlayState(true);
  });

  audio.addEventListener('pause', function () {
    if (mini.play) mini.play.textContent = '▶';
    if (full.play) full.play.textContent = '▶';
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
      if (mini.play) mini.play.textContent = '▶';
      if (full.play) full.play.textContent = '▶';
    }
  });

  audio.addEventListener('error', function () {
    if (audio.src) toast('ไม่พบไฟล์เสียงของเพลงนี้');
  });

  // เลื่อนตำแหน่ง + ระดับเสียง (ซิงก์กันทั้งสองหน้าจอ)
  [mini.seek, full.seek].forEach(function (el) {
    if (!el) return;
    el.addEventListener('input', function () {
      if (audio.duration) {
        audio.currentTime = (Number(el.value) / 100) * audio.duration;
      }
    });
  });

  // ระดับเสียง: จำค่าไว้ใน localStorage เพื่อให้คงอยู่แม้รีเฟรชหน้า
  const VOLUME_KEY = 'spi-music:volume';

  function readSavedVolume() {
    try {
      const raw = window.localStorage.getItem(VOLUME_KEY);
      if (raw === null) return null;
      const value = Number(raw);
      return Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
    } catch (error) {
      return null;                 // โหมดส่วนตัวบางเบราว์เซอร์ปิด localStorage
    }
  }

  function saveVolume(value) {
    try {
      window.localStorage.setItem(VOLUME_KEY, String(value));
    } catch (error) {
      /* เก็บไม่ได้ก็ไม่เป็นไร แค่ไม่จำค่า */
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

  // คีย์บอร์ด: Space = เล่น/หยุด, Esc = ย่อหน้าจอเต็ม
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && full.root && !full.root.hidden) {
      if (creditsOpen) setCreditsView(false);   // ปิดแท็บเครดิตก่อน
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






