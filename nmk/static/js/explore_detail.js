/* ============================================================================
   explore_detail.js — TikTok-style full-screen reel engine
   Replaces the old thumbnail-grid infinite-scroll script.

   Contract with the backend (service_auth/user_profile/views.py::explore_detail):
     - Same URL serves both the initial page AND ?ajax=1&cursor=<id> batches.
     - Each post JSON object has: id, media_type, file_url, thumbnail_url,
       description_html, likes_count, is_liked, comments_count, view_count,
       is_own, show_follow, user{id,username,profile_picture_url}, urls{...}
     - View counting only fires client-side after a slide is >=95% visible
       for 4 continuous seconds (see VIEW_VISIBILITY_THRESHOLD / VIEW_DWELL_MS).
   ============================================================================ */

(function () {
    'use strict';

    const VIEW_VISIBILITY_THRESHOLD = 0.95;
    const VIEW_DWELL_MS = 4000;
    const AUTOPLAY_THRESHOLD = 0.6;
    const PREFETCH_LOOKAHEAD = 2;      // start fetching next batch when this many slides from the end

    const reelRoot = document.getElementById('reel-root');
    const closeBtn = document.getElementById('reel-close-btn');
    const loadingHint = document.getElementById('reel-loading-hint');
    const slideTemplate = document.getElementById('reel-slide-template');
    const toastEl = document.getElementById('reel-toast');

    if (!reelRoot || !slideTemplate) return;

    document.body.classList.add('reel-open');

    const ENDPOINT = window.location.pathname; // explore_detail/<id>/ — reused for pagination
    let nextCursor = null;
    let hasMore = true;
    let loadingMore = false;
    let postsById = {};   // id -> post data (for quick lookup on interactions)

    function csrfToken() {
        if (window.__CSRF_TOKEN__) return window.__CSRF_TOKEN__;
        const m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    function toast(msg) {
        toastEl.textContent = msg;
        toastEl.classList.add('show');
        clearTimeout(toastEl._t);
        toastEl._t = setTimeout(() => toastEl.classList.remove('show'), 2400);
    }

    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    function fmtTime(iso) {
        try {
            const d = new Date(iso);
            return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        } catch (_) { return ''; }
    }

    /* ------------------------------------------------------------------
       BUILD / FILL A SLIDE
       ------------------------------------------------------------------ */
    function fillMediaWrap(wrapEl, post) {
        wrapEl.innerHTML = '';
        if (post.media_type === 'video') {
            const video = document.createElement('video');
            video.className = 'reel-video';
            video.playsInline = true;
            video.loop = true;
            video.muted = true;
            video.preload = 'metadata';
            if (post.thumbnail_url) video.poster = post.thumbnail_url;
            const source = document.createElement('source');
            source.src = post.file_url;
            source.type = 'video/mp4';
            video.appendChild(source);
            wrapEl.appendChild(video);
        } else {
            const img = document.createElement('img');
            img.className = 'reel-image';
            img.src = post.file_url;
            img.loading = 'lazy';
            img.alt = 'media';
            wrapEl.appendChild(img);
        }
        const hint = document.createElement('div');
        hint.className = 'reel-muted-hint';
        hint.textContent = '🔇';
        wrapEl.appendChild(hint);
    }

    function fillSlideChrome(slideEl, post) {
        slideEl.dataset.mediaId = post.id;
        slideEl.dataset.viewLogged = 'false';

        const likeBtn = slideEl.querySelector('[data-action="like"]');
        const likeIcon = likeBtn.querySelector('.icon');
        const likeCount = likeBtn.querySelector('.reel-like-count');
        likeIcon.textContent = post.is_liked ? '❤️' : '♡';
        likeBtn.classList.toggle('liked', !!post.is_liked);
        likeCount.textContent = post.likes_count;

        slideEl.querySelector('.reel-comment-count').textContent = post.comments_count;

        const avatarImg = slideEl.querySelector('.avatar-icon');
        avatarImg.src = post.user.profile_picture_url;

        const userPic = slideEl.querySelector('.reel-user-pic');
        userPic.src = post.user.profile_picture_url;
        slideEl.querySelector('.reel-username').textContent = post.user.username;

        const followBtn = slideEl.querySelector('[data-action="follow"]');
        if (post.show_follow && post.urls.follow) {
            followBtn.style.display = 'inline-block';
            followBtn.textContent = 'Follow';
            followBtn.classList.remove('following');
        } else {
            followBtn.style.display = 'none';
        }

        const descEl = slideEl.querySelector('.reel-description');
        descEl.innerHTML = post.description_html || '';
        descEl.addEventListener('click', function () {
            descEl.classList.toggle('expanded');
        }, { once: true });

        const menuDeleteBtn = document.getElementById('reel-menu-delete');
        // delete visibility is set contextually when the menu opens (per active slide)
    }

    function buildSlide(post, reuseMediaWrap) {
        let slideEl;
        let mediaWrap;

        if (reuseMediaWrap) {
            slideEl = reuseMediaWrap.closest('.reel-slide');
            const frag = slideTemplate.content.cloneNode(true);
            const templateSlide = frag.querySelector('.reel-slide');
            // move the action rail / bottom overlay from the template into the existing anchor slide
            slideEl.appendChild(templateSlide.querySelector('.reel-actions'));
            slideEl.appendChild(templateSlide.querySelector('.reel-bottom-overlay'));
            mediaWrap = reuseMediaWrap;
        } else {
            const frag = slideTemplate.content.cloneNode(true);
            slideEl = frag.querySelector('.reel-slide');
            mediaWrap = slideEl.querySelector('.reel-media-wrap');
            fillMediaWrap(mediaWrap, post);
        }

        fillSlideChrome(slideEl, post);
        wireSlideInteractions(slideEl, post);
        return slideEl;
    }

    /* ------------------------------------------------------------------
       INTERACTIONS: like / follow / comment / share / menu / mute-toggle
       ------------------------------------------------------------------ */
    function wireSlideInteractions(slideEl, post) {
        const mediaWrap = slideEl.querySelector('.reel-media-wrap');
        const video = mediaWrap.querySelector('video');
        const mutedHint = mediaWrap.querySelector('.reel-muted-hint');

        // tap to mute/unmute video
        if (video) {
            mediaWrap.addEventListener('click', function (e) {
                if (e.target.closest('.reel-actions') || e.target.closest('.reel-bottom-overlay')) return;
                video.muted = !video.muted;
                mutedHint.textContent = video.muted ? '🔇' : '🔊';
                mutedHint.classList.add('show');
                setTimeout(() => mutedHint.classList.remove('show'), 500);
            });
        }

        // like
        const likeBtn = slideEl.querySelector('[data-action="like"]');
        likeBtn.addEventListener('click', function () {
            if (likeBtn.dataset.busy === 'true') return;
            likeBtn.dataset.busy = 'true';
            fetch(post.urls.like, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
            })
            .then(r => r.json())
            .then(data => {
                post.is_liked = data.liked;
                post.likes_count = data.like_count;
                likeBtn.querySelector('.icon').textContent = data.liked ? '❤️' : '♡';
                likeBtn.classList.toggle('liked', data.liked);
                likeBtn.querySelector('.reel-like-count').textContent = data.like_count;
            })
            .catch(() => toast('Could not update like'))
            .finally(() => { likeBtn.dataset.busy = 'false'; });
        });

        // follow
        const followBtn = slideEl.querySelector('[data-action="follow"]');
        followBtn.addEventListener('click', function () {
            if (!post.urls.follow) return;
            fetch(post.urls.follow, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    followBtn.textContent = data.following ? 'Following' : 'Follow';
                    followBtn.classList.toggle('following', data.following);
                }
            })
            .catch(() => toast('Could not update follow'));
        });

        // profile
        slideEl.querySelector('[data-action="profile"]').addEventListener('click', function () {
            window.location.href = post.urls.profile;
        });

        // comment
        slideEl.querySelector('[data-action="comment"]').addEventListener('click', function () {
            openCommentDrawer(post, slideEl);
        });

        // share
        slideEl.querySelector('[data-action="share"]').addEventListener('click', function () {
            const shareUrl = window.location.origin + post.urls.share;
            const shareData = {
                title: `${post.user.username}'s post on Socyfie`,
                text: 'Check this out!',
                url: shareUrl,
            };
            if (navigator.share) {
                navigator.share(shareData).catch(() => {});
            } else {
                navigator.clipboard.writeText(shareUrl)
                    .then(() => toast('Link copied to clipboard'))
                    .catch(() => toast('Could not copy link'));
            }
        });

        // menu (not interested / report / delete)
        slideEl.querySelector('[data-action="menu"]').addEventListener('click', function () {
            openMenuSheet(post, slideEl);
        });
    }

    /* ------------------------------------------------------------------
       COMMENT DRAWER
       ------------------------------------------------------------------ */
    const drawerBackdrop = document.getElementById('reel-drawer-backdrop');
    const commentDrawer = document.getElementById('reel-comment-drawer');
    const rcdBody = document.getElementById('rcd-body');
    const rcdTitle = document.getElementById('rcd-title');
    const rcdComposer = document.getElementById('rcd-composer');
    const rcdInput = document.getElementById('rcd-input');
    let activeCommentPost = null;
    let activeCommentSlide = null;

    function openCommentDrawer(post, slideEl) {
        activeCommentPost = post;
        activeCommentSlide = slideEl;
        rcdTitle.textContent = `${post.comments_count} Comments`;
        rcdBody.innerHTML = '<div class="rcd-empty">Loading…</div>';
        drawerBackdrop.classList.add('show');
        commentDrawer.classList.add('open');
        pauseAllVideos();

        fetch(post.urls.comments)
            .then(r => r.json())
            .then(data => {
                if (!data.comments.length) {
                    rcdBody.innerHTML = '<div class="rcd-empty">No comments yet. Be the first!</div>';
                    return;
                }
                rcdBody.innerHTML = data.comments.map(renderCommentRow).join('');
            })
            .catch(() => { rcdBody.innerHTML = '<div class="rcd-empty">Could not load comments.</div>'; });
    }

    function renderCommentRow(c) {
        return `
            <div class="rcd-comment" data-comment-id="${c.id}">
                <img src="${c.user.profile_picture_url}" alt="">
                <div>
                    <span class="name">${esc(c.user.username)}</span>
                    <span class="content">${c.content}</span>
                    <div class="time">${fmtTime(c.created_at)}</div>
                </div>
            </div>`;
    }

    function closeCommentDrawer() {
        drawerBackdrop.classList.remove('show');
        commentDrawer.classList.remove('open');
        activeCommentPost = null;
        activeCommentSlide = null;
    }

    document.getElementById('rcd-close-btn').addEventListener('click', closeCommentDrawer);
    drawerBackdrop.addEventListener('click', function () {
        closeCommentDrawer();
        closeMenuSheet();
    });

    rcdComposer.addEventListener('submit', function (e) {
        e.preventDefault();
        const content = rcdInput.value.trim();
        if (!content || !activeCommentPost) return;

        fetch(activeCommentPost.urls.post_comment, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ content }),
        })
        .then(r => r.json())
        .then(data => {
            if (data.error) { toast(data.error); return; }
            const emptyEl = rcdBody.querySelector('.rcd-empty');
            if (emptyEl) emptyEl.remove();
            rcdBody.insertAdjacentHTML('afterbegin', renderCommentRow(data));
            rcdInput.value = '';

            activeCommentPost.comments_count = data.comments_count;
            rcdTitle.textContent = `${data.comments_count} Comments`;
            if (activeCommentSlide) {
                activeCommentSlide.querySelector('.reel-comment-count').textContent = data.comments_count;
            }
        })
        .catch(() => toast('Could not post comment'));
    });

    /* ------------------------------------------------------------------
       MENU SHEET (not interested / report / delete)
       ------------------------------------------------------------------ */
    const menuBackdrop = document.getElementById('reel-menu-backdrop');
    const menuSheet = document.getElementById('reel-menu-sheet');
    const menuDeleteBtn = document.getElementById('reel-menu-delete');
    let activeMenuPost = null;
    let activeMenuSlide = null;

    function openMenuSheet(post, slideEl) {
        activeMenuPost = post;
        activeMenuSlide = slideEl;
        menuDeleteBtn.style.display = (post.is_own && post.urls.delete) ? 'block' : 'none';
        menuBackdrop.classList.add('show');
        menuSheet.classList.add('open');
    }

    function closeMenuSheet() {
        menuBackdrop.classList.remove('show');
        menuSheet.classList.remove('open');
        activeMenuPost = null;
        activeMenuSlide = null;
    }

    menuBackdrop.addEventListener('click', closeMenuSheet);

    menuSheet.addEventListener('click', function (e) {
        const btn = e.target.closest('[data-menu-action]');
        if (!btn || !activeMenuPost) { closeMenuSheet(); return; }
        const action = btn.dataset.menuAction;

        if (action === 'cancel') { closeMenuSheet(); return; }

        if (action === 'not_interested') {
            fetch(activeMenuPost.urls.not_interested, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
            })
            .then(() => {
                toast('Got it — you\u2019ll see less like this');
                removeSlide(activeMenuSlide);
            })
            .catch(() => toast('Could not update preference'))
            .finally(closeMenuSheet);
            return;
        }

        if (action === 'report') {
            fetch(activeMenuPost.urls.report, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
            })
            .then(() => toast('Reported. Thanks for letting us know.'))
            .catch(() => toast('Could not submit report'))
            .finally(closeMenuSheet);
            return;
        }

        if (action === 'delete') {
            if (!confirm('Delete this post? This cannot be undone.')) { closeMenuSheet(); return; }
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = activeMenuPost.urls.delete;
            const csrf = document.createElement('input');
            csrf.type = 'hidden'; csrf.name = 'csrfmiddlewaretoken'; csrf.value = csrfToken();
            form.appendChild(csrf);
            document.body.appendChild(form);
            form.submit();
            return;
        }
    });

    function removeSlide(slideEl) {
        if (!slideEl) return;
        const video = slideEl.querySelector('video');
        if (video) video.pause();
        slideEl.style.transition = 'opacity .2s';
        slideEl.style.opacity = '0';
        setTimeout(() => slideEl.remove(), 200);
    }

    /* ------------------------------------------------------------------
       AUTOPLAY (video) + VIEW-TRACKING (image & video, 4s / 95% dwell)
       ------------------------------------------------------------------ */
    function pauseAllVideos() {
        reelRoot.querySelectorAll('video').forEach(v => v.pause());
    }

    const autoplayObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target.querySelector ? entry.target.querySelector('video') : null;
            const vid = entry.target.tagName === 'VIDEO' ? entry.target : video;
            if (!vid) return;
            if (entry.isIntersecting) {
                vid.play().catch(() => {});
            } else {
                vid.pause();
            }
        });
    }, { threshold: AUTOPLAY_THRESHOLD });

    const viewObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const slideEl = entry.target;
            if (entry.isIntersecting) {
                if (slideEl.dataset.viewLogged === 'true') return;
                slideEl._viewTimer = setTimeout(() => {
                    logView(slideEl);
                }, VIEW_DWELL_MS);
            } else {
                if (slideEl._viewTimer) {
                    clearTimeout(slideEl._viewTimer);
                    slideEl._viewTimer = null;
                }
            }
        });
    }, { threshold: VIEW_VISIBILITY_THRESHOLD });

    function logView(slideEl) {
        if (slideEl.dataset.viewLogged === 'true') return;
        const mediaId = slideEl.dataset.mediaId;
        const post = postsById[mediaId];
        if (!post) return;
        slideEl.dataset.viewLogged = 'true';

        fetch(post.urls.view_engagement, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ engagement_type: 'view' }),
        }).catch(() => { /* non-fatal */ });
    }

    /* ------------------------------------------------------------------
       INFINITE SCROLL — prefetch next batch when near the end
       ------------------------------------------------------------------ */
    const prefetchObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                loadMore();
            }
        });
    }, { threshold: 0.1 });

    function attachPrefetchSentinel() {
        const slides = reelRoot.querySelectorAll('.reel-slide');
        // remove previous sentinel flags, mark the Nth-from-end slide
        slides.forEach(s => prefetchObserver.unobserve(s));
        const idx = Math.max(0, slides.length - 1 - PREFETCH_LOOKAHEAD);
        if (slides[idx]) prefetchObserver.observe(slides[idx]);
    }

    function loadMore() {
        if (loadingMore || !hasMore) return;
        loadingMore = true;
        loadingHint.style.display = 'block';

        const url = `${ENDPOINT}?ajax=1${nextCursor ? `&cursor=${nextCursor}` : ''}`;
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(r => r.json())
            .then(data => {
                (data.posts || []).forEach(post => {
                    postsById[post.id] = post;
                    const slideEl = buildSlide(post, null);
                    reelRoot.appendChild(slideEl);

                    autoplayObserver.observe(slideEl);
                    viewObserver.observe(slideEl);

                    const video = slideEl.querySelector('video');
                    if (video) autoplayObserver.observe(video);
                });

                nextCursor = data.next_cursor;
                hasMore = data.has_more;

                attachPrefetchSentinel();
            })
            .catch(() => toast('Could not load more posts'))
            .finally(() => {
                loadingMore = false;
                loadingHint.style.display = 'none';
            });
    }

    /* ------------------------------------------------------------------
       INIT — enrich the server-rendered anchor slide, then start the feed
       ------------------------------------------------------------------ */
    function init() {
        const anchorPost = window.__REEL_ANCHOR_POST__;
        if (!anchorPost) return;

        postsById[anchorPost.id] = anchorPost;

        const anchorSlideEl = reelRoot.querySelector('.reel-slide[data-slide-anchor]');
        const anchorMediaWrap = anchorSlideEl.querySelector('.reel-media-wrap');
        buildSlide(anchorPost, anchorMediaWrap);
        anchorSlideEl.removeAttribute('data-slide-anchor');

        autoplayObserver.observe(anchorSlideEl);
        viewObserver.observe(anchorSlideEl);
        const anchorVideo = anchorSlideEl.querySelector('video');
        if (anchorVideo) {
            autoplayObserver.observe(anchorVideo);
            anchorVideo.muted = false;
            anchorVideo.play().catch(() => { anchorVideo.muted = true; anchorVideo.play().catch(() => {}); });
        }

        attachPrefetchSentinel();
        loadMore();   // warm the next batch immediately
    }

    closeBtn.addEventListener('click', function () {
        pauseAllVideos();
        if (window.history.length > 1) {
            window.history.back();
        } else {
            // Fallback exit target when there's no history (e.g. deep link / new tab).
            // Set from the template so this file stays a plain static asset.
            window.location.href = window.__REEL_EXIT_URL__ || '/explore_me/';
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
