
document.addEventListener('DOMContentLoaded', function() {
    const mediaContainer = document.getElementById('media-container');
    const loadingSpinner = document.getElementById('loading-spinner');
    let page = 1; // Start loading from the next page
    let loading = false;
    let hasMoreMedia = true;
    const loadThreshold = 200; // Load more when within 200px of the bottom

    // Get the CSRF token once for later use
    let csrfToken = '';
    const csrfElement = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrfElement) {
        csrfToken = csrfElement.value;
    } else {
        // Alternative way to get CSRF token from cookie
        csrfToken = getCookie('csrftoken');
    }

    // Helper function to get cookies
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Initialize videos on page load
    function observeAutoplayVideos() {
        document.querySelectorAll('.autoplay-video:not([data-observed])').forEach(video => {
            videoObserver.observe(video);
            video.dataset.observed = 'true';
        });
    }

    //  ADD THIS RIGHT HERE — Initialize images on page load
    function observeMediaItems() {
        document.querySelectorAll('.media-item:not([data-observed])').forEach(el => {
            viewObserver.observe(el);
            el.dataset.observed = 'true';
        });
    }


    // --------------------------------------------------
    // Video Observer (3s Watch → View)
    // --------------------------------------------------

    const observerOptions = {
        root: null,
        threshold: 0.75
    };

    window.videoObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {

            const video = entry.target;
            const wrapper = video.closest('.video-wrapper');

            if (entry.isIntersecting) {

                if (wrapper) wrapper.classList.add('playing');

                video.muted = false; // required for autoplay

                document.querySelectorAll('video.autoplay-video').forEach(v => {
                    if (v !== video) v.pause();
                });

                video.play().catch(() => {});

                if (!video.dataset.viewLogged) {

                    video.dataset.viewLogged = "pending";

                    video._viewTimer = setTimeout(() => {

                        if (!video.paused && video.dataset.viewLogged === "pending") {

                            video.dataset.viewLogged = "true";

                            console.log(" Logging view for video:", video.dataset.mediaId);

                            fetch(`/media_engagement/${video.dataset.mediaId}/engagement/`, {
                                method: "POST",
                                headers: {
                                    "Content-Type": "application/json",
                                    "X-CSRFToken": getCookie('csrftoken'),
                                    "X-Requested-With": "XMLHttpRequest"
                                },
                                body: JSON.stringify({
                                    engagement_type: "view"
                                })
                            }).catch(err => console.log("View log failed:", err));
                        }

                    }, 3000);
                }

            } else {

                video.pause();
                if (wrapper) wrapper.classList.remove('playing');

                if (video._viewTimer) {
                    clearTimeout(video._viewTimer);
                    video._viewTimer = null;
                    video.dataset.viewLogged = "";
                }
            }

        });
    }, observerOptions);


    // --------------------------------------------------
    // Media Item Visibility Observer (4s Dwell → View)
    // --------------------------------------------------
    const viewObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            const el = entry.target;

            // 1. Skip if it's a video (handled by the videoObserver)
            if (el.querySelector('video')) return;

            if (entry.isIntersecting) {
                // 2. Only start a timer if we haven't logged this view yet
                if (!el.dataset.viewLogged) {
                    console.log("Image target reached 75% visibility. Starting 4s timer for ID:", el.dataset.id);
                
                    // Start a 3-second timer
                    el._dwellTimer = setTimeout(() => {
                        // Double check it's still visible and not already logged
                        if (el.dataset.viewLogged !== "true") {
                            el.dataset.viewLogged = "true";
                        
                            logImageEngagement(el.dataset.id);
                        
                            // 3. Stop observing this item once it's logged to save resources
                            observer.unobserve(el);
                        }
                    }, 3000); 
                }
            } else {
                // 4. If the user scrolls away before the s is up, cancel the timer
                if (el._dwellTimer) {
                    clearTimeout(el._dwellTimer);
                    el._dwellTimer = null;
                    console.log("User scrolled away. Timer cancelled for ID:", el.dataset.id);
                }
            }
        });
    }, {
        root: null,
        threshold: 0.75 // Image must be 75% visible
    });

    // Helper function to keep the observer code clean
    function logImageEngagement(mediaId) {
        console.log("Logging 3s dwell view for image:", mediaId);
        fetch(`/media_engagement/${mediaId}/engagement/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie('csrftoken'),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify({ engagement_type: "view" })
        })
        .catch(err => console.error("Image view log failed:", err));
    }



    // Initialize like links on page load
    initializeLikeLinks(document.querySelectorAll('.like-link'));

    // Function to handle like button clicks
    function handleLikeClick(event) {
        event.preventDefault();
        const likeLink = event.currentTarget;
        const url = likeLink.getAttribute('data-url');
        const mediaId = likeLink.getAttribute('data-media-id');

        // Ensure we have the CSRF token
        let tokenToUse = likeLink.getAttribute('data-csrf-token') || csrfToken;

        // Prevent multiple clicks
        if (likeLink.dataset.processing === 'true') {
            return;
        }
        likeLink.dataset.processing = 'true';

        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': tokenToUse,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ media_id: mediaId })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            const likeCountElement = likeLink.nextElementSibling;
            if (likeCountElement) {
                likeCountElement.textContent = data.like_count;
            }

            if (data.liked) {
                likeLink.classList.add('liked');
                likeLink.textContent = '❤️';
            } else {
                likeLink.classList.remove('liked');
                likeLink.textContent = '♡';
            }
        })
        .catch(error => {
            console.error('Error with like action:', error);
            // Optionally display an error message to the user
        })
        .finally(() => {
            likeLink.dataset.processing = 'false';
        });
    }

    // Function to initialize like links
    function initializeLikeLinks(likeLinks) {
        likeLinks.forEach(function(link) {
            if (!link.dataset.listener) {
                link.addEventListener('click', handleLikeClick);
                link.dataset.listener = 'true';
            }
        });
    }



    // Infinite scrolling functionality
    function loadMoreMedia() {
        if (loading || !hasMoreMedia) {
            return;
        }
        loading = true;
        if (loadingSpinner) loadingSpinner.style.display = 'block';

        //fetch(`?page=${page}`, {
        fetch(`/following_media/?page=${page}`, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.media && data.media.length > 0) {
                data.media.forEach(item => {
                    // Create new media item
                    const mediaDiv = document.createElement('div');
                    mediaDiv.classList.add('col', 'media-item');
                    mediaDiv.dataset.id = item.id;
                    mediaDiv.dataset.url = `/user_profile/media_detail_view/${item.id}/`; // Set a default


                    // Construct URLs using template-like string formatting
                    const profileUrl = item.profile_url; // Use profile_url from JSON
                    const profilePicUrl = item.profile_picture_url || '/static/images/default_profile.png';

                    const likeUrl = item.like_url; // Use like_url from JSON
                    const commentUrl = item.media_detail_url; // Use media_detail_url for comment link

                    // Assuming item.media_detail_url from your JSON corresponds to 'user_profile:explore_detail'
                    const exploreDetailUrl = item.explore_detail_url; // Assign to a clearer variable name

                    const isLiked = item.is_liked ? 'liked' : '';
                    const likeSymbol = item.is_liked ? '❤️' : '♡';

                    const viewCount = item.view_count;   //  new views count variable

                    const cleanDescription = DOMPurify.sanitize(item.description || '');


                    const shareBtnHTML = `
                    <button 
                        class="action-btn share-btn"
                        onclick="shareMedia(
                            ${item.id},
                            '${window.location.origin}/media/${item.id}/',
                            '${(item.user_username || "").replace(/'/g, "\\'")}'s post',
                            '${(item.description || "").replace(/'/g, "\\'")}',
                            '${window.location.origin}${item.media_url}',
                            '${item.media_type === "video" ? "video" : "image"}'
                        )"
                    >
                        <svg 
                            width="20" 
                            height="20" 
                            viewBox="0 0 24 24" 
                            fill="none" 
                            stroke="currentColor"
                        >
                            <circle cx="18" cy="5" r="3" stroke-width="2"/>
                            <circle cx="6" cy="12" r="3" stroke-width="2"/>
                            <circle cx="18" cy="19" r="3" stroke-width="2"/>
                            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" stroke-width="2"/>
                            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" stroke-width="2"/>
                        </svg>
                        Share
                    </button>
                    `;

                    //<!--for displaying follw button next to the username -->
                    let followButton = "";
                    if (item.show_follow) {
                        followButton = `
                            <!--<form method="post" action="${item.follow_url}">

                                <input type="hidden" name="csrfmiddlewaretoken" value="${csrfToken}">
                                <button type="submit" class="btn btn-sm btn-primary">Follow</button>
                            </form>-->
                            <button
                                class="btn btn-sm btn-primary follow-btn"
                                data-follow-url="${item.follow_url}">
                                Follow
                            </button>
                        `;
                    }

                    <!--for loading page content from infinite scrolling -->
                    let mediaContent = `
                        <a href="${profileUrl}" class="mention-with-avatar">
                            <img src="${profilePicUrl}" class="mention-avatar" alt="${item.user_username}'s profile picture" fetchpriority="high">
                            <h5>${item.user_username}</h5>
                        <!--</a>-->
                        ${followButton}   <!--  Inject follow form here -->
                        </a>

                        <br>
                        <a href="${exploreDetailUrl}" class="media-content-link">

                        <div class="media-content">
                            ${item.is_video ?
                                `<video muted autoplay playsinline preload="metadata" loading="lazy" class="img-fluid autoplay-video feed-video" data-media-id="${item.id}" style="cursor:pointer;">
                                    <source src="${item.file_url}" type="video/mp4">
                                    Your browser does not support the video tag.
                                </video>


                                <!-- Professional Play Button Overlay
                                <div class="play-overlay">
                                    <svg class="play-icon" viewBox="0 0 64 64">
                                        <circle cx="32" cy="32" r="30" fill="rgba(0,0,0,0.45)" />
                                        <polygon points="26,20 26,44 46,32" fill="#ffffff"/>
                                    </svg>
                                </div>-->

                                ` :
                                `<img src="${item.file_url}" alt="media" class="img-fluid" loading="lazy" style="cursor:pointer;">`
                            }
                            <div class="description">
                                <a href="${likeUrl}"
                                   class="like-link ${isLiked}"
                                   data-url="${likeUrl}"
                                   data-media-id="${item.id}"
                                   data-csrf-token="${csrfToken}">
                                    ${likeSymbol}
                                </a>
                                <span class="like-count">${item.likes_count || 0}</span> likes |

                                <!--  View Count -->
                                <span class="view-count mt-1 text-muted">
                                    👁️ : ${viewCount} |
                                </span>

                                <!--<a href="${commentUrl}">Comment | </a>-->
                                <span class="comment-link" onclick="location.href='${commentUrl}'">
                                    Comment |
                                </span>

                                <!--  View Count
                                <div class="view-count mt-1 text-muted">
                                    👁️ : ${viewCount}
                                </div>-->

                                <!--  Share Button Injected
                                ${shareBtnHTML}-->

                                <button
                                    class="share-btn"
                                    data-media-id="${item.id}"
                                    data-media-url="${exploreDetailUrl}"
                                    data-username="${item.user_username}">
                                    📤 Share
                                </button>

                                <div class="description-paragraph-container"></div>

                            </div>
                        </div>
                        </a>

                    `;

                    mediaDiv.innerHTML = mediaContent;

                    const descriptionDiv = mediaDiv.querySelector('.description-paragraph-container');
                    const descriptionParagraph = document.createElement('p');
                    descriptionParagraph.innerHTML = cleanDescription;
                    descriptionDiv.appendChild(descriptionParagraph);

                    mediaContainer.appendChild(mediaDiv);
                    observeAutoplayVideos();
                    initializeLikeLinks(mediaDiv.querySelectorAll('.like-link'));  //  Attach Like listeners

                });

                page++;
            } else {
                hasMoreMedia = false;
                const endMessage = document.createElement('div');
                endMessage.classList.add('col', 'text-center', 'my-4');
                endMessage.innerHTML = '<p>No more media to load</p>';
                mediaContainer.appendChild(endMessage);
            }
        })
        .catch(error => {
            console.error('Error loading more media:', error);
            const errorMsg = document.createElement('div');
            errorMsg.classList.add('col', 'text-center', 'my-4', 'text-danger');
            //errorMsg.innerHTML = '<p>Failed to load more content. Please try again later.</p>';
            errorMsg.innerHTML = '<p></p>';
            mediaContainer.appendChild(errorMsg);
        })
        .finally(() => {
            loading = false;



            //  Replace with these two lines
            observeAutoplayVideos();
            observeMediaItems();

            // Re-initialize event listeners for new like buttons
            initializeLikeLinks(mediaContainer.querySelectorAll('.like-link:not([data-listener])'));

            if (loadingSpinner) loadingSpinner.style.display = 'none';
        });
    }


    function checkScroll() {
        const scrollPosition = window.scrollY + window.innerHeight;
        const pageHeight = document.body.scrollHeight;

        if (scrollPosition >= pageHeight * 0.80) {
            loadMoreMedia();
        }
    }
    window.addEventListener('scroll', checkScroll);
    loadMoreMedia(); // Load first batch immediately

    //  ADD THESE — observe items already in DOM on initial load
    observeAutoplayVideos();
    observeMediaItems();
});

document.addEventListener('DOMContentLoaded', function () {
    // Function to protect an image or video
    function protectMediaElement(el) {
        if (el.dataset.protected) return; // Avoid duplicate bindings

        el.addEventListener('contextmenu', function (e) {
            e.preventDefault();
        });

        let pressTimer;

        el.addEventListener('touchstart', function (e) {
            pressTimer = setTimeout(() => {
                e.preventDefault();
            }, 600);
        });

        el.addEventListener('touchend', function () {
            clearTimeout(pressTimer);
        });

        el.addEventListener('touchmove', function () {
            clearTimeout(pressTimer);
        });

        el.dataset.protected = 'true'; // Mark as protected
    }

    // Protect initial media
    document.querySelectorAll('img, video').forEach(protectMediaElement);

    // Observe DOM changes for new images/videos
    const observer = new MutationObserver((mutationsList) => {
        mutationsList.forEach(mutation => {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType !== 1) return; // Only process element nodes
                if (node.matches('img, video')) {
                    protectMediaElement(node);
                }
                // Also check inside containers
                node.querySelectorAll?.('img, video').forEach(protectMediaElement);
            });
        });
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
});

<!--share script page link -->
document.addEventListener("DOMContentLoaded", function() {
    // Use event delegation so even AJAX-loaded buttons work
    document.addEventListener("click", async function(e) {
        // Check if the clicked element OR its parent is a share button
        let shareBtn = e.target.closest(".share-btn");
        if (!shareBtn) return;

        const mediaId = shareBtn.dataset.mediaId;
        const mediaUrl = shareBtn.dataset.mediaUrl;
        const username = shareBtn.dataset.username;

        const shareData = {
            title: `${username}'s post`,
            text: "Check out this upload on Socyfie!",
            url: mediaUrl   // Specific media detail URL
        };

        if (navigator.share) {
            try {
                await navigator.share(shareData);
                console.log("Share successful");
            } catch (err) {
                console.error("Share failed:", err);
            }
        } else {
            // Fallback: copy link to clipboard
            navigator.clipboard.writeText(mediaUrl)
                .then(() => alert("Link copied to clipboard!"))
                .catch(err => console.error("Could not copy link:", err));
        }
    });
});

<!--ajax follow hook-->
function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
}

document.addEventListener("click", function (e) {
    const btn = e.target.closest(".follow-btn");
    if (!btn) return;

    e.preventDefault();

    const url = btn.dataset.followUrl;
    const csrftoken = getCSRFToken();

    if (!csrftoken) {
        console.error("CSRF token not found");
        return;
    }

    fetch(url, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrftoken,
            <!--"Content-Type": "application/json"-->
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json"
        },
        credentials: "same-origin"
    })
    .then(res => {
        if (!res.ok) throw new Error("Request failed");
        return res.json();
    })
    .then(data => {
        if (data.success) {
            btn.textContent = data.following ? "Unfollow" : "Follow";
        }
    })
    .catch(err => console.error(err));
});


