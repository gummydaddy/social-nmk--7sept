document.addEventListener("DOMContentLoaded", function () {
    const images = document.querySelectorAll("img.lazyload");

    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;

                img.src = img.dataset.src;
                img.classList.remove("lazyload");

                observer.unobserve(img);
            }
        });
    });

    images.forEach(img => observer.observe(img));
});
