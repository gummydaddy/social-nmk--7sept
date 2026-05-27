<!--for pull-to-refresh gesture-->

document.addEventListener('DOMContentLoaded', function () {
    const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent);
    const isInStandaloneMode = () => ('standalone' in window.navigator) && window.navigator.standalone;

    if (!(isIos() && isInStandaloneMode())) return;

    let startY = 0;
    let pulling = false;
    const threshold = 80;

    const refreshEl = document.createElement('div');
    refreshEl.id = 'pull-to-refresh';
    refreshEl.innerHTML = `
        <div class="spinner"></div>
        <div class="message">↓ Pull to refresh</div>
    `;
    document.body.prepend(refreshEl);

    const messageEl = refreshEl.querySelector('.message');
    const spinnerEl = refreshEl.querySelector('.spinner');

    document.addEventListener('touchstart', function (e) {
        if (window.scrollY === 0) {
            startY = e.touches[0].clientY;
            pulling = true;
        }
    });

    document.addEventListener('touchmove', function (e) {
        if (!pulling) return;

        const distance = e.touches[0].clientY - startY;
        if (distance > 0) {
            e.preventDefault();
            refreshEl.style.height = Math.min(distance, threshold) + 'px';
            messageEl.textContent = distance > threshold ? '↻ Release to refresh' : '↓ Pull to refresh';
        }
    }, { passive: false });

    document.addEventListener('touchend', function (e) {
        if (!pulling) return;

        const distance = e.changedTouches[0].clientY - startY;
        pulling = false;

        if (distance > threshold) {
            refreshEl.style.height = '60px';
            refreshEl.classList.add('show-spinner');
            messageEl.textContent = 'Refreshing...';
            setTimeout(() => location.reload(), 800);
        } else {
            refreshEl.style.height = '0';
        }
    });
});
