let birthdaySliderTimer;
const BIRTHDAY_SLIDER_DELAY = 5000;

function showBirthdaySlide(index) {
  const slides = $("#birthdayDots .birthday-events-nav-item");
  const sliderReel = $("#birthdayContainer");
  if (!slides.length || !sliderReel.length) return;

  const target = ((index % slides.length) + slides.length) % slides.length;
  sliderReel.css("transform", `translateX(-${target * 100}%)`);
  slides.removeClass("birthday-events-nav-item--active");
  slides.filter(`[data-target="${target}"]`).addClass("birthday-events-nav-item--active");
}

function autoSlider() {
  const slides = $("#birthdayDots .birthday-events-nav-item");
  clearInterval(birthdaySliderTimer);

  if (slides.length < 2) return;

  birthdaySliderTimer = setInterval(function () {
    const current = Number(
      slides.filter(".birthday-events-nav-item--active").data("target")
    );
    showBirthdaySlide((Number.isFinite(current) ? current : 0) + 1);
  }, BIRTHDAY_SLIDER_DELAY);
}

function moveSlider(e) {
  const clickedEl = $(e.target).closest(".birthday-events-nav-item");
  const targetSlideNumber = Number(clickedEl.data("target"));

  if (Number.isFinite(targetSlideNumber)) {
    showBirthdaySlide(targetSlideNumber);
    // A manual selection should remain visible for a full interval.
    autoSlider();
  }
}
