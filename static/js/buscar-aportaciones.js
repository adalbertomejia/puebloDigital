(() => {
  const form = document.querySelector('[data-dynamic-search]');
  const results = document.getElementById('search-results');
  if (!form || !results || !window.fetch || !window.AbortController) return;

  let timer;
  let controller;
  const update = async (url, push = true) => {
    if (controller) controller.abort();
    controller = new AbortController();
    results.setAttribute('aria-busy', 'true');
    form.classList.add('is-loading');
    try {
      const response = await fetch(url, {headers: {'HX-Request': 'true'}, signal: controller.signal});
      if (!response.ok) throw new Error('No fue posible actualizar la búsqueda');
      results.innerHTML = await response.text();
      if (push) history.pushState({}, '', url);
    } catch (error) {
      if (error.name !== 'AbortError') {
        results.insertAdjacentHTML('afterbegin', '<p class="search-dynamic-error" role="alert">No se pudo actualizar. Puedes usar el botón Buscar para continuar.</p>');
      }
    } finally {
      results.setAttribute('aria-busy', 'false');
      form.classList.remove('is-loading');
    }
  };
  const formUrl = () => `${form.action || location.pathname}?${new URLSearchParams(new FormData(form))}`;
  form.addEventListener('submit', event => { event.preventDefault(); update(formUrl()); });
  form.addEventListener('change', () => update(formUrl()));
  form.q.addEventListener('input', () => {
    clearTimeout(timer);
    const value = form.q.value.trim();
    if (value.length === 1) return;
    timer = setTimeout(() => update(formUrl()), 400);
  });
  results.addEventListener('click', event => {
    const link = event.target.closest('[data-results-page]');
    if (!link) return;
    event.preventDefault(); update(link.href);
  });
  addEventListener('popstate', () => location.reload());
})();
