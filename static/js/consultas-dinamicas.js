(() => {
  'use strict';
  const enabled = () => document.querySelector('.pd-main[data-live-page]');
  if (!enabled() || !window.fetch || !window.AbortController) return;
  let controller, timer, generation = 0;
  const initialPath = location.pathname;
  const cancel = () => { clearTimeout(timer); controller?.abort(); generation++; };
  const formUrl = (form, submitter) => {
    const url = new URL(form.action || location.href, location.origin);
    const data = new FormData(form);
    if (submitter?.name) data.set(submitter.name, submitter.value);
    url.search = new URLSearchParams(data).toString();
    return url;
  };
  async function update(destination, mode = 'push') {
    const url = new URL(destination, location.href);
    if (url.origin !== location.origin || url.pathname !== initialPath) return location.assign(url);
    cancel();
    const current = generation;
    controller = new AbortController();
    const main = enabled();
    if (!main) return location.assign(url);
    main.setAttribute('aria-busy', 'true');
    const active = document.activeElement;
    const focus = main.contains(active) ? {id: active.id, name: active.name, form: [...main.querySelectorAll('form')].indexOf(active.form), start: active.selectionStart, end: active.selectionEnd} : null;
    const opened = [...main.querySelectorAll('details[id][open]')].map(node => node.id);
    try {
      const response = await fetch(url, {signal: controller.signal, headers: {'X-PD-Consultation': 'true'}});
      if (current !== generation) return;
      if (response.redirected) return location.assign(response.url);
      if (!response.ok) return location.assign(url);
      const html = await response.text();
      if (current !== generation) return;
      const next = new DOMParser().parseFromString(html, 'text/html');
      const content = next.querySelector('.pd-main[data-live-page]');
      if (!content) return location.assign(url);
      document.dispatchEvent(new CustomEvent('pd:before-update'));
      main.innerHTML = content.innerHTML;
      document.title = next.title;
      opened.forEach(id => { const node = document.getElementById(id); if (node) node.open = true; });
      if (mode === 'push') history.pushState({pdLive: true}, '', url);
      if (mode === 'replace') history.replaceState({pdLive: true}, '', url);
      document.dispatchEvent(new CustomEvent('pd:updated'));
      if (focus) {
        const field = focus.id ? document.getElementById(focus.id) : main.querySelectorAll('form')[focus.form]?.elements.namedItem(focus.name);
        if (field?.focus) {
          field.focus({preventScroll: true});
          if (focus.start !== null && field.setSelectionRange) {
            try { field.setSelectionRange(focus.start, focus.end); } catch (_) { /* Non-text fields. */ }
          }
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError' && current === generation) {
        main.querySelector('[data-live-error]')?.remove();
        const alert = document.createElement('p');
        alert.dataset.liveError = ''; alert.className = 'pd-alert pd-alert--danger'; alert.setAttribute('role', 'alert');
        alert.textContent = 'No se pudo actualizar la consulta. ';
        const link = document.createElement('a'); link.href = url; link.dataset.fullNavigation = ''; link.textContent = 'Abrir los resultados';
        alert.append(link); main.prepend(alert);
      }
    } finally {
      if (current === generation) main.setAttribute('aria-busy', 'false');
    }
  }
  const getForm = target => {
    const form = target.closest('form');
    return form && (form.getAttribute('method') || 'get').toLowerCase() === 'get' && enabled()?.contains(form) ? form : null;
  };
  document.addEventListener('submit', event => {
    const form = getForm(event.target);
    if (!form) return;
    event.preventDefault(); update(formUrl(form, event.submitter));
  });
  document.addEventListener('change', event => {
    const form = getForm(event.target);
    if (form && !['search', 'text'].includes(event.target.type)) update(formUrl(form));
  });
  document.addEventListener('input', event => {
    const form = getForm(event.target);
    if (!form || !['search', 'text'].includes(event.target.type)) return;
    cancel();
    timer = setTimeout(() => update(formUrl(form), 'replace'), 400);
  });
  document.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!link || !enabled()?.contains(link) || link.hasAttribute('data-full-navigation') || link.target || link.download || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.getAttribute('href')?.startsWith('#')) return;
    const url = new URL(link.href);
    if (url.origin !== location.origin || url.pathname !== initialPath) return;
    event.preventDefault(); update(url);
  });
  window.addEventListener('popstate', () => update(location.href, 'none'));
})();
