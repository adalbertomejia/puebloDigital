(() => {
  'use strict';

  const root = document.querySelector('[data-contributions-workspace]');
  const dataElement = document.getElementById('contributions-chart-data');
  if (!root || !dataElement) return;

  const data = JSON.parse(dataElement.textContent);
  const tabs = [...root.querySelectorAll('[data-summary-tab]')];
  const panels = [...root.querySelectorAll('[data-summary-panel]')];
  const canvas = root.querySelector('[data-contributions-chart]');
  const empty = root.querySelector('[data-chart-empty]');
  const title = root.querySelector('[data-chart-title]');
  const description = root.querySelector('[data-chart-description]');
  const currency = new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' });
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let chart = null;
  let currentConcept = 0;

  const copy = {
    conceptos: ['Avance del concepto', 'Distribución del monto aportado frente al objetivo del concepto.'],
    manzanas: ['Comparación por manzana', 'Comparación de las aportaciones registradas por manzana.'],
    ciudadanos: ['Aportaciones por ciudadano', 'Aportaciones de los ciudadanos mostrados actualmente.'],
  };
  const remember = (name, value) => {
    const url = new URL(window.location.href);
    url.searchParams.set(name, value);
    history.replaceState({}, '', url);
    document.querySelectorAll(`input[name="${name}"]`).forEach(input => { input.value = value; });
  };
  const clearChart = () => {
    if (chart) chart.destroy();
    chart = null;
  };
  const showEmpty = message => {
    clearChart();
    canvas.hidden = true;
    empty.hidden = false;
    empty.textContent = message;
  };
  const moneyTooltip = context => `${context.dataset.label || context.label}: ${currency.format(context.raw)}`;
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: reducedMotion ? false : { duration: 250 },
    plugins: { tooltip: { callbacks: { label: moneyTooltip } } },
  };

  const render = name => {
    [title.textContent, description.textContent] = copy[name];
    if (!window.Chart) {
      showEmpty('No fue posible inicializar la gráfica. Los datos permanecen disponibles en el resumen.');
      return;
    }
    clearChart();
    canvas.hidden = false;
    empty.hidden = true;
    let config;
    if (name === 'conceptos') {
      const concept = data.conceptos[currentConcept];
      if (!concept) return showEmpty('No hay conceptos disponibles para los filtros seleccionados.');
      if (concept.objetivo === null) return showEmpty('Este concepto no tiene un objetivo financiero definido.');
      config = {
        type: 'doughnut',
        data: { labels: ['Aportado', 'Restante'], datasets: [{ data: [concept.aportado, concept.restante], backgroundColor: ['#6fcf97', '#f59e91'], borderColor: '#ffffff', borderWidth: 3 }] },
        options: { ...commonOptions, cutout: '66%', plugins: { ...commonOptions.plugins, legend: { position: 'bottom', labels: { usePointStyle: true, padding: 18 } }, tooltip: { callbacks: { label: context => `${context.label}: ${currency.format(context.raw)} (${concept.porcentaje.toFixed(1)}% alcanzado)` } } } },
      };
      canvas.setAttribute('aria-label', `Avance de ${concept.nombre}: ${currency.format(concept.aportado)} aportado y ${currency.format(concept.restante)} restante.${concept.superado ? ' Objetivo superado.' : ''}`);
    } else {
      const rows = data[name].filter(row => row.total > 0);
      if (!rows.length) return showEmpty(name === 'manzanas' ? 'No hay manzanas con movimientos para los filtros seleccionados.' : 'No hay ciudadanos con aportaciones en la página actual.');
      config = {
        type: 'bar',
        data: { labels: rows.map(row => row.nombre), datasets: [{ label: 'Total aportado', data: rows.map(row => row.total), backgroundColor: '#68a9cf', borderColor: '#397da7', borderWidth: 1, borderRadius: 6 }] },
        options: { ...commonOptions, indexAxis: 'y', plugins: { ...commonOptions.plugins, legend: { display: false } }, scales: { x: { beginAtZero: true, grid: { color: '#e2e8f0' }, ticks: { callback: value => currency.format(value) } }, y: { grid: { display: false } } } },
      };
      canvas.setAttribute('aria-label', `${copy[name][0]}. ${rows.length} barras; los datos exactos están disponibles en la tarjeta contigua.`);
    }
    chart = new window.Chart(canvas, config);
  };

  const selectSummary = (name, focus = false) => {
    tabs.forEach(tab => { const active = tab.dataset.summaryTab === name; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; if (focus && active) tab.focus(); });
    panels.forEach(panel => { panel.hidden = panel.dataset.summaryPanel !== name; });
    remember('resumen', name);
    render(name);
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectSummary(tab.dataset.summaryTab));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      selectSummary(tabs[next].dataset.summaryTab, true);
    });
  });

  const carousel = root.querySelector('[data-concept-carousel]');
  if (carousel) {
    const slides = [...carousel.querySelectorAll('[data-concept-slide]')];
    const previous = carousel.querySelector('[data-concept-previous]');
    const next = carousel.querySelector('[data-concept-next]');
    const status = carousel.querySelector('[data-concept-status]');
    currentConcept = Math.max(0, slides.findIndex(slide => !slide.hidden));
    const show = index => {
      currentConcept = Math.min(Math.max(index, 0), slides.length - 1);
      slides.forEach((slide, position) => { slide.hidden = position !== currentConcept; });
      previous.disabled = currentConcept === 0;
      next.disabled = currentConcept === slides.length - 1;
      status.textContent = `Concepto ${currentConcept + 1} de ${slides.length}`;
      remember('concepto_indice', currentConcept + 1);
      if (root.querySelector('[data-summary-tab="conceptos"]').getAttribute('aria-selected') === 'true') render('conceptos');
    };
    previous.addEventListener('click', () => show(currentConcept - 1));
    next.addEventListener('click', () => show(currentConcept + 1));
    show(currentConcept);
  }
  const active = tabs.find(tab => tab.getAttribute('aria-selected') === 'true') || tabs[0];
  selectSummary(active.dataset.summaryTab);
})();
