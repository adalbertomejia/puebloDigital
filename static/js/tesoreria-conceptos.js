(() => {
  const container = document.querySelector('#conceptos-paginados');
  if (!container || !window.fetch || !window.history?.pushState) return;

  let controller;
  let requestNumber = 0;

  async function load(url, { push = true, direction = 1, fallback = false } = {}) {
    controller?.abort();
    controller = new AbortController();
    const currentRequest = ++requestNumber;
    const content = container.querySelector('[data-concepts-content]');
    content?.setAttribute('aria-busy', 'true');
    container.classList.toggle('is-moving-back', direction < 0);
    container.classList.add('is-loading');

    try {
      const response = await fetch(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const html = await response.text();
      if (currentRequest !== requestNumber) return;
      container.innerHTML = html;
      container.classList.add('is-entering');
      requestAnimationFrame(() => container.classList.remove('is-entering'));
      if (push) history.pushState({ concepts: true }, '', url);
    } catch (error) {
      if (error.name !== 'AbortError' && fallback) window.location.assign(url);
    } finally {
      if (currentRequest === requestNumber) {
        container.classList.remove('is-loading', 'is-moving-back');
        container.querySelector('[data-concepts-content]')?.setAttribute('aria-busy', 'false');
      }
    }
  }

  container.addEventListener('click', (event) => {
    const link = event.target.closest('a[data-concepts-page]');
    if (!link) return;
    event.preventDefault();
    const current = new URL(window.location.href);
    const destination = new URL(link.href);
    const changedParameter = destination.searchParams.get('pagina_cooperaciones') !== current.searchParams.get('pagina_cooperaciones')
      ? 'pagina_cooperaciones' : 'pagina_conceptos';
    const direction = Number(destination.searchParams.get(changedParameter) || 1) >= Number(current.searchParams.get(changedParameter) || 1) ? 1 : -1;
    load(destination.href, { direction, fallback: true });
  });

  window.addEventListener('popstate', () => load(window.location.href, { push: false }));
})();
