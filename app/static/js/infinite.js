/*
  infinite.js - /songs loads 50 rows at a time and appends more as you scroll.

  The table carries data-next-page / data-pages; the server renders plain <tr>
  fragments for ?partial=1, so the markup is identical to the first page and the
  existing delegated click handlers in player.js keep working.
*/
(function () {
  const table = document.getElementById('all-tracks');
  const footer = document.getElementById('load-more');
  if (!table || !footer) return;

  const body = document.getElementById('all-tracks-body');
  const sentinel = footer.querySelector('.load-more-text');
  let nextPage = Number(table.dataset.nextPage);
  const lastPage = Number(table.dataset.pages);
  const sort = table.dataset.sort || 'top';
  let loading = false;
  let done = footer.dataset.end === 'true';

  function setFooter(state) {
    footer.classList.toggle('is-loading', state === 'loading');
    footer.classList.toggle('is-done', state === 'done');
    if (state === 'loading') sentinel.textContent = 'กำลังโหลด…';
    if (state === 'done') sentinel.textContent = 'ครบทั้งหมดแล้ว';
  }

  if (done) setFooter('done');

  async function loadNext() {
    if (loading || done) return;
    loading = true;
    setFooter('loading');

    const params = new URLSearchParams({ page: nextPage, partial: '1' });
    if (sort === 'new') params.set('sort', 'new');

    try {
      const response = await fetch('/songs?' + params.toString(), {
        headers: { 'X-Requested-With': 'fetch' },
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);

      const html = (await response.text()).trim();
      if (html) {
        const holder = document.createElement('tbody');
        holder.innerHTML = html;
        const rows = Array.from(holder.children);
        const fragment = document.createDocumentFragment();
        rows.forEach(function (row) { fragment.appendChild(row); });
        body.appendChild(fragment);
      }

      nextPage += 1;
      table.dataset.nextPage = String(nextPage);
      if (nextPage > lastPage) {
        done = true;
        setFooter('done');
      } else {
        setFooter('ready');
      }
    } catch (error) {
      setFooter('ready');
      sentinel.textContent = 'โหลดไม่สำเร็จ — เลื่อนอีกครั้งเพื่อลองใหม่';
      await new Promise(function (resolve) { setTimeout(resolve, 1200); });
    } finally {
      loading = false;
    }
  }

  // preload a little before the footer becomes visible
  const observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) loadNext();
    });
  }, { rootMargin: '400px 0px' });

  observer.observe(footer);

  // keyboard/page-end fallback
  window.addEventListener('scroll', function () {
    if (done || loading) return;
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) loadNext();
  }, { passive: true });
})();
