  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('img').forEach(function (img) {
      // Disable right-click context menu
      img.addEventListener('contextmenu', function (e) {
        e.preventDefault();
      });

      // Prevent long-press menu on mobile (without blocking scrolling)
      let pressTimer;

      img.addEventListener('touchstart', function (e) {
        // Start a timer on touchstart
        pressTimer = setTimeout(() => {
          e.preventDefault(); // Only prevent default if held long enough
        }, 600); // Adjust delay as needed (600ms is common)
      });

      img.addEventListener('touchend', function () {
        clearTimeout(pressTimer);
      });

      img.addEventListener('touchmove', function () {
        clearTimeout(pressTimer); // Cancel if user scrolls
      });
    });
  });
