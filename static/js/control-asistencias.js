(() => {
  'use strict';

  document.querySelectorAll('[data-attendance-carousel]').forEach(carousel => {
    const slides = [...carousel.querySelectorAll('[data-attendance-slide]')];
    const previous = carousel.querySelector('[data-attendance-previous]');
    const next = carousel.querySelector('[data-attendance-next]');
    const status = carousel.querySelector('[data-attendance-status]');
    if (slides.length < 2 || !previous || !next || !status) return;

    const label = carousel.dataset.carouselLabel;
    let current = Math.max(0, slides.findIndex(slide => !slide.hidden));
    const show = index => {
      current = Math.min(Math.max(index, 0), slides.length - 1);
      slides.forEach((slide, position) => { slide.hidden = position !== current; });
      previous.disabled = current === 0;
      next.disabled = current === slides.length - 1;
      status.textContent = `${label.charAt(0).toUpperCase()}${label.slice(1, -1)} ${current + 1} de ${slides.length}`;
    };

    previous.addEventListener('click', () => show(current - 1));
    next.addEventListener('click', () => show(current + 1));
    show(current);
  });
})();
