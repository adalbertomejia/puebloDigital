(() => {
  'use strict';

  const form = document.querySelector('[data-dynamic-citizen-search]');
  const results = document.getElementById('citizen-search-results');
  if (!form || !results || !window.fetch || !window.AbortController) return;

  const query = form.querySelector('input[name="q"]');
  let timer;
  let controller;
  let requestSequence = 0;

  const formUrl = () => {
    const url = new URL(form.getAttribute('action') || location.pathname, location.origin);
    url.search = new URLSearchParams(new FormData(form)).toString();
    return url.toString();
  };

  const update = async (url, push = true) => {
    clearTimeout(timer);
    const requestId = ++requestSequence;
    if (controller) controller.abort();
    controller = new AbortController();
    results.setAttribute('aria-busy', 'true');
    form.classList.add('is-loading');

    try {
      const response = await fetch(url, {
        headers: {'HX-Request': 'true'},
        signal: controller.signal,
      });
      if (!response.ok) throw new Error('No fue posible actualizar la búsqueda');
      const html = await response.text();
      if (requestId !== requestSequence) return;
      results.innerHTML = html;
      if (push) history.pushState({}, '', url);
    } catch (error) {
      if (error.name !== 'AbortError' && requestId === requestSequence) {
        results.insertAdjacentHTML('afterbegin', '<p class="search-dynamic-error" role="alert">No se pudo actualizar. Puedes usar el botón de búsqueda para continuar.</p>');
      }
    } finally {
      if (requestId === requestSequence) {
        results.setAttribute('aria-busy', 'false');
        form.classList.remove('is-loading');
        controller = null;
      }
    }
  };

  form.addEventListener('submit', event => {
    event.preventDefault();
    update(formUrl());
  });
  form.addEventListener('change', event => {
    if (event.target !== query) update(formUrl());
  });
  if (query) {
    query.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => update(formUrl()), 400);
    });
  }
  results.addEventListener('click', event => {
    const link = event.target.closest('[data-results-page]');
    if (!link) return;
    event.preventDefault();
    update(link.href);
  });
  addEventListener('popstate', () => location.reload());
})();
