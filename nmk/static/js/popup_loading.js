document.addEventListener("DOMContentLoaded", function () {

    // ========================================
    // STOP FOR GUEST USERS
    // ========================================

    const isAuthenticated =
        document.body.dataset.authenticated === "true";

    if (!isAuthenticated) {

        console.log(
            "Guest user detected - notification polling disabled"
        );

        return;
    }

    // ========================================
    // CSRF HELPER
    // ========================================

    function getCookie(name) {

        let cookieValue = null;

        if (document.cookie && document.cookie !== "") {

            const cookies = document.cookie.split(";");

            for (let cookie of cookies) {

                cookie = cookie.trim();

                if (cookie.startsWith(name + "=")) {

                    cookieValue = decodeURIComponent(
                        cookie.substring(name.length + 1)
                    );

                    break;
                }
            }
        }

        return cookieValue;
    }

    const csrftoken = getCookie("csrftoken");

    const popupContainer = document.getElementById(
        "popup-notification-container"
    );

    // Prevent duplicate popups
    let shownNotifications = new Set();

    // ========================================
    // ESCAPE HTML
    // ========================================

    function escapeHtml(text) {

        if (text === null || text === undefined) {
            return "";
        }

        const div = document.createElement("div");

        div.textContent = String(text);

        return div.innerHTML;
    }

    // ========================================
    // CREATE POPUP
    // ========================================

    function showPopup(notification) {

        try {

            // Prevent duplicates
            if (
                notification.id &&
                shownNotifications.has(notification.id)
            ) {
                return;
            }

            if (notification.id) {
                shownNotifications.add(notification.id);
            }

            // Debug full notification
            console.log(
                "FULL NOTIFICATION:",
                JSON.stringify(notification, null, 2)
            );

            const popup = document.createElement("div");

            popup.className = "popup-notification";

            // ========================================
            // SAFE TITLE/MESSAGE
            // ========================================

            const safeTitle = escapeHtml(
                notification.title || "Notification"
            );

            const safeMessage = escapeHtml(
                notification.message || ""
            );

            // ========================================
            // SAFE DOM CREATION
            // ========================================

            const popupContent = document.createElement("div");

            popupContent.className = "popup-content";

            const strong = document.createElement("strong");

            strong.textContent = safeTitle;

            const p = document.createElement("p");

            p.textContent = safeMessage;

            popupContent.appendChild(strong);

            popupContent.appendChild(p);

            popup.appendChild(popupContent);

            popupContainer.appendChild(popup);

            // Animate in
            setTimeout(() => {

                popup.classList.add("show");

            }, 100);

            // Auto remove
            setTimeout(() => {

                popup.classList.remove("show");

                setTimeout(() => {

                    if (popup.parentNode) {
                        popup.remove();
                    }

                }, 300);

            }, 5000);

        } catch (error) {

            console.error(
                "❌ Popup creation error:",
                error
            );

            console.error(
                "Notification payload:",
                notification
            );
        }
    }

    // ========================================
    // FETCH NOTIFICATIONS
    // ========================================

    async function checkNotifications() {

        try {

            const response = await fetch(
                "/api/notifications/",
                {
                    method: "GET",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                        "X-CSRFToken": csrftoken,
                    },
                    credentials: "same-origin",
                }
            );

            // ========================================
            // CHECK RESPONSE STATUS
            // ========================================

            if (!response.ok) {

                throw new Error(
                    `HTTP error ${response.status}`
                );
            }

            // ========================================
            // SAFELY READ RESPONSE
            // ========================================

            const contentType = response.headers.get("content-type");

            if (
                !contentType ||
                !contentType.includes("application/json")
            ) {

                console.warn(
                    "Non-JSON notification response skipped"
                );

                return;
            }

            const text = await response.text();

            if (!text) {

                console.warn(
                    "Empty notification response"
                );

                return;
            }

            let data;

            try {

                data = JSON.parse(text);

            } catch (jsonError) {

                console.error(
                    "❌ Invalid JSON response:",
                    text
                );

                throw jsonError;
            }

            console.log(
                "Notification API response:",
                data
            );

            // ========================================
            // VALIDATE DATA
            // ========================================

            if (
                data &&
                data.success &&
                Array.isArray(data.notifications)
            ) {

                data.notifications.forEach(notification => {

                    try {

                        if (
                            notification &&
                            !notification.is_read
                        ) {

                            showPopup(notification);
                        }

                    } catch (notificationError) {

                        console.error(
                            "❌ Notification render error:",
                            notificationError
                        );

                        console.error(
                            "Problem notification:",
                            notification
                        );
                    }
                });
            }

        } catch (error) {

            console.error(
                "❌ Notification fetch error:",
                error
            );
        }
    }


    if (isAuthenticated) {

    // ========================================
    // INITIAL FETCH
    // ========================================
        checkNotifications();

    // ========================================
    // AUTO CHECK EVERY 10 SEC
    // ========================================
        setInterval(checkNotifications, 10000);
    }


});
