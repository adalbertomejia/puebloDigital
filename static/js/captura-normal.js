(() => {
  'use strict';
  const form = document.querySelector('[data-captura-normal]');
  if (!form) return;
  const rows = [...form.querySelectorAll('[data-registro]')];
  const message = document.getElementById('captura-mensaje');
  let saving = false;
  const dirty = new Set();
  form.addEventListener('input', event => {
    const row = event.target.closest('[data-registro]');
    if (!row) return;
    dirty.add(row);
    row.querySelector('[data-estado-fila]').textContent = 'Sin guardar';
  });
  document.getElementById('captura-buscar').addEventListener('input', event => {
    const tokens = event.target.value.trim().toLocaleLowerCase().split(/\s+/);
    rows.forEach(row => { row.hidden = !tokens.every(token => row.dataset.busqueda.toLocaleLowerCase().includes(token)); });
  });
  if (!window.fetch) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (saving) return;
    const row = event.submitter?.closest('[data-registro]');
    const selected = row ? [row] : rows;
    const fields = selected.flatMap(item => [...item.querySelectorAll('[name]')]);
    if (fields.some(field => !field.reportValidity())) return;
    const data = new FormData();
    data.set('csrfmiddlewaretoken', form.elements.csrfmiddlewaretoken.value);
    fields.forEach(field => data.set(field.name, field.value));
    saving = true;
    // Freeze edited rows so the acknowledgement cannot mask newer changes.
    const buttons = [...form.querySelectorAll('button')];
    const inputs = rows.flatMap(item => [...item.querySelectorAll('input, select')]);
    [...buttons, ...inputs].forEach(field => { field.disabled = true; });
    message.textContent = 'Guardando asistencia y adeudos…';
    try {
      const response = await fetch(form.action || location.href, {method: 'POST', body: data, headers: {'X-Requested-With': 'XMLHttpRequest'}});
      if (response.redirected) { location.assign(response.url); return; }
      if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('No se pudo confirmar el guardado. Revisa los datos antes de volver a guardar.');
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || 'No se pudieron guardar los cambios.');
      selected.forEach(item => { dirty.delete(item); item.querySelector('[data-estado-fila]').textContent = 'Guardado'; });
      Object.entries(result.metrics).forEach(([key, value]) => {
        document.querySelectorAll(`[data-metric="${key}"]`).forEach(node => { node.textContent = value; });
      });
      message.textContent = 'Guardado. Adeudos sincronizados con Tesorería.';
    } catch (error) {
      message.textContent = error.message;
    } finally {
      saving = false;
      [...buttons, ...inputs].forEach(field => { field.disabled = false; });
    }
  });
  window.addEventListener('beforeunload', event => { if (dirty.size || saving) { event.preventDefault(); event.returnValue = ''; } });
})();
