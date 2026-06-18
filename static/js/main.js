// Navbar scroll effect
document.addEventListener('DOMContentLoaded', () => {
  const nav = document.querySelector('.pe-navbar');
  if (nav) {
    window.addEventListener('scroll', () => {
      nav.classList.toggle('scrolled', window.scrollY > 50);
    });
  }
});
