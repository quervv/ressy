document.documentElement.classList.add("motion");
if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  document.documentElement.classList.add("calm");
}
