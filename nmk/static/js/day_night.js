document.addEventListener('DOMContentLoaded', function () {
    // Check the saved mode in localStorage
    var currentMode = localStorage.getItem('mode');

    var container = document.querySelector('.content-container');
    var classMain = document.querySelector('.class-main');

    var mediaWrappers = document.querySelectorAll('.media-wrapper');
    var mediaContents = document.querySelectorAll('.media-content');

    var button = document.getElementById('toggleButton');

    function enableNightMode() {
        if (container) container.classList.add('night-mode');
        if (classMain) classMain.classList.add('night-mode');

        mediaWrappers.forEach(el => el.classList.add('night-mode'));
        mediaContents.forEach(el => el.classList.add('night-mode'));

        document.body.classList.add('socyfie-night-mode');

        if (button) {
            button.textContent = 'Switch to Day Mode🌒';
        }
    }

    function enableDayMode() {
        if (container) container.classList.remove('night-mode');
        if (classMain) classMain.classList.remove('night-mode');

        mediaWrappers.forEach(el => el.classList.remove('night-mode'));
        mediaContents.forEach(el => el.classList.remove('night-mode'));

        document.body.classList.remove('socyfie-night-mode');

        if (button) {
            button.textContent = 'Switch to Night Mode🌒';
        }
    }

    // Apply saved mode
    if (currentMode === 'night') {
        enableNightMode();
    } else {
        enableDayMode();
    }

    // Toggle background mode and save to localStorage
    window.toggleBackground = function () {
        if (container && container.classList.contains('night-mode')) {
            enableDayMode();
            localStorage.setItem('mode', 'day');
        } else {
            enableNightMode();
            localStorage.setItem('mode', 'night');
        }
    };
});
