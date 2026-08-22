document.addEventListener('DOMContentLoaded', () => {
  // Disable drag behavior on all images
  document.querySelectorAll('img').forEach(img => {
    img.setAttribute('draggable', 'false');
    img.addEventListener('dragstart', e => e.preventDefault());
    img.addEventListener('contextmenu', e => e.preventDefault()); // disables right-click
  });

  // Optional: Block text/image selection
  document.body.addEventListener('selectstart', e => e.preventDefault());
});
