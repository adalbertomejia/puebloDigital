(() => {
  const jq = window.django?.jQuery;
  if (!jq) return;
  jq(document).on('change', '#id_ciudadano, #id_comite', () => {
    jq('#id_responsable').val(null).trigger('change');
  });
})();
