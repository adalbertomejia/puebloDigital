(() => {
  const $ = window.django?.jQuery;
  if (!$) return;
  $(document).on('change', '#id_ciudadano', () => {
    $('#id_obligacion').val(null).trigger('change');
  });
})();
