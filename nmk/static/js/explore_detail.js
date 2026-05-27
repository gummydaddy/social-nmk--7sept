document.addEventListener('DOMContentLoaded', function () {

    const relatedContainer = document.getElementById('related-media-container');
    const loadingSpinner = document.getElementById('loading-spinner');

    let nextCursor = relatedContainer?.dataset.nextCursor || null;
    let hasMoreMedia = relatedContainer?.dataset.hasMore === "true";
    let loading = false;

    const loadThreshold = 200;

    /* -----------------------------------
        CSRF HELPER
    ----------------------------------- */
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            document.cookie.split(';').forEach(cookie => {
                cookie = cookie.trim();
                if (cookie.startsWith(name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                }
            });
        }
        return cookieValue;
    }

    const csrfToken =
        document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || getCookie('csrftoken');


    /* -----------------------------------
        AUTOPLAY OBSERVER
    ----------------------------------- */
    const observerOptions = { root: null, threshold: 0.75 };

    const videoObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target;

            if (entry.isIntersecting) {

                document.querySelectorAll('video.autoplay-video')
                    .forEach(v => { if (v !== video) v.pause(); });

                if (video.readyState >= 2) {
                    video.play().catch(() => {});
                } else {
                    video.addEventListener('loadeddata', () => {
                        video.play().catch(() => {});
                    }, { once: true });
                }

                /* 3-sec view validation */
                if (!video.dataset.viewLogged) {
                    video.dataset.viewLogged = "pending";

                    setTimeout(() => {
                        if (!video.paused && video.dataset.viewLogged === "pending") {
                            video.dataset.viewLogged = "true";

                            fetch("/user_profile/media_engagement/", {
                                method: "POST",
                                headers: {
                                    "Content-Type": "application/json",
                                    "X-CSRFToken": csrfToken,
                                    "X-Requested-With": "XMLHttpRequest"
                                },
                                body: JSON.stringify({
                                    media_id: video.dataset.mediaId,
                                    engagement_type: "view"
                                })
                            }).catch(() => {});
                        }
                    }, 3000);
                }

            } else {
                video.pause();
            }
        });
    }, observerOptions);

    function observeVideos() {
        document.querySelectorAll('.autoplay-video:not([data-observed])')
            .forEach(video => {
                videoObserver.observe(video);
                video.dataset.observed = "true";
            });
    }

    observeVideos();


    /* -----------------------------------
        LIKE SYSTEM
    ----------------------------------- */
    function initializeLikeLinks(scope = document) {
        scope.querySelectorAll('.like-link:not([data-listener])')
            .forEach(link => {
                link.addEventListener('click', handleLikeClick);
                link.dataset.listener = "true";
            });
    }

    function handleLikeClick(e) {
        e.preventDefault();
        const link = e.currentTarget;

        if (link.dataset.processing === "true") return;
        link.dataset.processing = "true";

        fetch(link.dataset.url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest"
            }
        })
        .then(res => res.json())
        .then(data => {
            link.textContent = data.liked ? "❤️" : "♡";
            link.classList.toggle("liked", data.liked);
            link.nextElementSibling.textContent = data.like_count;
        })
        .finally(() => link.dataset.processing = "false");
    }

    initializeLikeLinks();


    /* -----------------------------------
        INFINITE SCROLL (CURSOR)
    ----------------------------------- */
    function loadMoreMedia() {

        if (loading || !hasMoreMedia || !nextCursor) return;

        loading = true;
        if (loadingSpinner) loadingSpinner.style.display = "block";

        fetch(`${window.location.pathname}?cursor=${nextCursor}`, {
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
        .then(res => res.json())
        .then(data => {

            if (!data.related_media || data.related_media.length === 0) {
                hasMoreMedia = false;
                return;
            }

            data.related_media.forEach(item => {

                const col = document.createElement('div');
                col.className = "col related-media-item";

                const exploreUrl = `${item.explore_detail_url}?cursor=${item.id}`;
                
                // Determine which URL to use for the thumbnail
                const thumbUrl = item.thumbnail_url ? item.thumbnail_url : item.file_url;

                col.innerHTML = `
                    <a href="${exploreUrl}" class="media-content">
                        <div class="position-relative media-thumb-square">
                            <img src="${thumbUrl}" 
                                 alt="Thumbnail" 
                                 class="img-fluid object-cover" 
                                 loading="lazy"
                                 ${item.is_video ? `data-video="${item.file_url}"` : ''}>
                            
                            ${item.is_video ? `
                                <span class="position-absolute top-50 start-50 translate-middle text-white fs-3">
                                    ▶
                                </span>
                            ` : ''}
                        </div>
                    </a>

                    <div class="actions mt-1">
                        <a href="${item.like_url}"
                           class="like-link ${item.is_liked_by_user ? "liked" : ""}"
                           data-url="/like_media/${item.id}/"
                           data-media-id="${item.id}">
                           ${item.is_liked_by_user ? "❤️" : "♡"}
                        </a>
                        <span class="like-count">${item.likes_count}</span>
                    </div>
                `;

                relatedContainer.appendChild(col);
            });

            nextCursor = data.next_cursor;
            hasMoreMedia = data.has_more;

            observeVideos();
            initializeLikeLinks(relatedContainer);

        })
        .catch(() => {})
        .finally(() => {
            loading = false;
            if (loadingSpinner) loadingSpinner.style.display = "none";
        });
    }

    function checkScroll() {
        const scrollPosition = window.scrollY + window.innerHeight;
        const pageHeight = document.body.scrollHeight;

        if (scrollPosition >= pageHeight - loadThreshold) {
            loadMoreMedia();
        }
    }

    window.addEventListener("scroll", checkScroll);


    /* -----------------------------------
        MEDIA PROTECTION
    ----------------------------------- */
    function protectMedia(el) {
        if (el.dataset.protected) return;

        el.addEventListener("contextmenu", e => e.preventDefault());
        el.dataset.protected = "true";
    }

    document.querySelectorAll("img, video").forEach(protectMedia);

    const protectObserver = new MutationObserver(mutations => {
        mutations.forEach(m => {
            m.addedNodes.forEach(node => {
                if (node.nodeType !== 1) return;
                if (node.matches("img, video")) protectMedia(node);
                node.querySelectorAll?.("img, video").forEach(protectMedia);
            });
        });
    });

    protectObserver.observe(document.body, {
        childList: true,
        subtree: true
    });


    /* -----------------------------------
        SHARE BUTTON (DELEGATED)
    -----------------------------------
    document.addEventListener("click", async function (e) {
        const shareBtn = e.target.closest(".share-btn");
        if (!shareBtn) return;

        const mediaUrl = shareBtn.dataset.mediaUrl;
        const username = shareBtn.dataset.username;

        const shareData = {
            title: `${username}'s post`,
            text: "Check out this upload on Socyfie!",
            url: mediaUrl
        };

        if (navigator.share) {
            try { await navigator.share(shareData); } catch {}
        } else {
            navigator.clipboard.writeText(mediaUrl);
        }
    });*/


    /* -----------------------------------
        FOLLOW AJAX
    ----------------------------------- */
    document.addEventListener("click", function (e) {
        const btn = e.target.closest(".follow-btn");
        if (!btn) return;

        e.preventDefault();

        fetch(btn.dataset.followUrl, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest"
            }
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                btn.textContent = data.following ? "Unfollow" : "Follow";
            }
        })
        .catch(() => {});
    });

});












