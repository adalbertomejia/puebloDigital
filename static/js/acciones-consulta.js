(function () {
  'use strict';
  document.addEventListener('click', async function (event) {
    const print = event.target.closest('[data-imprimir-consulta]');
    if (print) {
      document.body.classList.add('pd-consulta-imprimible');
      window.print();
      return;
    }
    const share = event.target.closest('[data-compartir-consulta]');
    if (!share) return;
    const status = share.closest('[data-acciones-consulta]').querySelector('[data-estado-compartir]');
    share.disabled = true;
    try {
      if (navigator.share) {
        await navigator.share({title: document.title, url: window.location.href});
        status.textContent = 'Consulta compartida.';
      } else if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(window.location.href);
        status.textContent = 'Enlace copiado. Requiere una cuenta autorizada.';
      } else {
        status.textContent = 'Copia la dirección del navegador para compartir esta consulta.';
      }
    } catch (error) {
      status.textContent = error.name === 'AbortError' ? '' : 'No se pudo compartir. Puedes copiar la dirección del navegador.';
    } finally {
      share.disabled = false;
    }
  });
}());
