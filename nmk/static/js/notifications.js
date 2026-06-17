// nmk/static/js/notifications.js
// WebSocket-based notification system - NO Firebase needed

(function() {

    'use strict';

    // ========================================
    // STOP FOR GUEST USERS
    // ========================================

    const isAuthenticated =
        document.body.dataset.authenticated === "true";

    if (!isAuthenticated) {

        console.log(
            "Guest user detected - websocket disabled"
        );

        return;
    }

    console.log('🔔 Notification system initializing...');

    let notificationSocket = null;
    let reconnectAttempts = 0;

    const MAX_RECONNECT_ATTEMPTS = 10;

    let unreadCount = 0;

    const originalPageTitle = document.title;

    // ========================================
    // NOTIFICATION POPUP DISPLAY
    // ========================================

    function showNotificationPopup(notification) {

        console.log('📢 Showing notification popup:', notification);

        const popup = createNotificationPopup(notification);

        document.body.appendChild(popup);

        // Animate in
        setTimeout(() => {
            popup.classList.add('show');
        }, 10);

        // Auto-hide after 5 seconds
        setTimeout(() => {
            hideNotificationPopup(popup);
        }, 5000);

        // Play sound
        playNotificationSound();
    }

    function createNotificationPopup(notification) {

        const popup = document.createElement('div');

        popup.className = 'notification-popup';

        popup.dataset.notificationId = notification.id || '';

        const iconMap = {
            'new_message': '💬',
            'typing_indicator': '⌨️',
            'system': '🔔'
        };

        const icon = iconMap[notification.type] || '🔔';

        popup.innerHTML = `
            <div class="notification-icon">${icon}</div>

            <div class="notification-content">

                <div class="notification-title">
                    <strong>${escapeHtml(notification.sender || 'System')}</strong>
                </div>

                <div class="notification-message">
                    ${escapeHtml(notification.message || 'New notification')}
                </div>

                <div class="notification-time">
                    ${formatTimestamp(notification.timestamp)}
                </div>

            </div>

            <button class="notification-close">
                ×
            </button>
        `;

        // Close button
        const closeBtn = popup.querySelector('.notification-close');

        if (closeBtn) {

            closeBtn.addEventListener('click', function(e) {

                e.stopPropagation();

                popup.remove();
            });
        }

        // ========================================
        // SAFE URL HANDLING
        // ========================================

        if (
            notification.url &&
            typeof notification.url === 'string'
        ) {

            popup.style.cursor = 'pointer';

            popup.addEventListener('click', function(e) {

                if (
                    !e.target.classList.contains('notification-close')
                ) {

                    try {

                        // Validate URL safely
                        const targetUrl = new URL(
                            notification.url,
                            window.location.origin
                        );

                        console.log(
                            'Navigating to:',
                            targetUrl.href
                        );

                        window.location.href = targetUrl.href;

                    } catch (error) {

                        console.error(
                            '❌ Invalid notification URL:',
                            notification.url,
                            error
                        );
                    }
                }
            });
        }

        return popup;
    }

    function hideNotificationPopup(popup) {

        popup.classList.remove('show');

        setTimeout(() => {

            if (popup.parentElement) {

                popup.parentElement.removeChild(popup);
            }

        }, 300);
    }

    function playNotificationSound() {

        try {

            const audioContext = new (
                window.AudioContext ||
                window.webkitAudioContext
            )();

            const oscillator = audioContext.createOscillator();

            const gainNode = audioContext.createGain();

            oscillator.connect(gainNode);

            gainNode.connect(audioContext.destination);

            oscillator.frequency.value = 800;

            oscillator.type = 'sine';

            gainNode.gain.setValueAtTime(
                0.3,
                audioContext.currentTime
            );

            gainNode.gain.exponentialRampToValueAtTime(
                0.01,
                audioContext.currentTime + 0.2
            );

            oscillator.start(audioContext.currentTime);

            oscillator.stop(audioContext.currentTime + 0.2);

            console.log('🔊 Notification sound played');

        } catch (error) {

            console.warn(
                'Could not play notification sound:',
                error
            );
        }
    }

    // ========================================
    // NOTIFICATION BADGE
    // ========================================

    function updateNotificationBadge(count) {

        unreadCount = count || 0;

        console.log(
            '📊 Updating notification badge:',
            unreadCount
        );

        const badge = document.getElementById(
            'notification-badge'
        );

        if (badge) {

            if (unreadCount > 0) {

                badge.textContent =
                    unreadCount > 99
                        ? '99+'
                        : unreadCount;

                badge.style.display = 'inline-block';

            } else {

                badge.style.display = 'none';
            }
        }

        // Update title
        if (unreadCount > 0) {

            document.title =
                `(${unreadCount}) ${originalPageTitle}`;

        } else {

            document.title = originalPageTitle;
        }
    }

    // ========================================
    // WEBSOCKET CONNECTION
    // ========================================

    function connectNotificationWebSocket() {

        console.log(
            '🔌 Connecting to notification WebSocket...'
        );

        const protocol =
            window.location.protocol === 'https:'
                ? 'wss'
                : 'ws';

        const wsUrl =
            `${protocol}://${window.location.host}/ws/notifications/`;

        console.log('WebSocket URL:', wsUrl);

        try {

            console.trace("notifications.js creating websocket");
            notificationSocket = new WebSocket(wsUrl);

            notificationSocket.onopen = function(e) {

                console.log(
                    '✅ Notification WebSocket CONNECTED'
                );

                reconnectAttempts = 0;

                updateConnectionStatus(true);
            };

            notificationSocket.onmessage = function(e) {

                console.log(
                    '📨 Notification WebSocket message received'
                );

                try {

                    const data = JSON.parse(e.data);

                    console.log('Message data:', data);

                    handleNotificationMessage(data);

                } catch (error) {

                    console.error(
                        '❌ Error parsing notification message:',
                        error
                    );
                }
            };

            notificationSocket.onerror = function(e) {

                console.error(
                    '❌ Notification WebSocket error:'
                );

                updateConnectionStatus(false);
            };

            notificationSocket.onclose = function(e) {

                console.warn(
                    '🔌 Notification WebSocket closed:'
                );

                updateConnectionStatus(false);

                // Reconnect logic
                if (
                    isAuthenticated &&
                    reconnectAttempts <
                    MAX_RECONNECT_ATTEMPTS
                ) {

                    reconnectAttempts++;

                    const delay = Math.min(
                        1000 * reconnectAttempts,
                        10000
                    );

                    console.log(
                        `Reconnecting in ${delay}ms `
                        + `(attempt ${reconnectAttempts})`
                    );

                    setTimeout(
                        connectNotificationWebSocket,
                        delay
                    );
                }
            };

        } catch (error) {

            console.error(
                '❌ Error creating notification WebSocket:',
                error
            );
        }
    }

    // ========================================
    // HANDLE NOTIFICATION MESSAGE
    // ========================================

    function handleNotificationMessage(data) {

        const messageType = data.type;

        console.log(
            '📬 Handling notification type:',
            messageType
        );

        switch (messageType) {

            case 'connection_established':

                console.log(
                    '✅ Connection confirmed:',
                    data.message
                );

                console.log(
                    'User:',
                    data.username,
                    'ID:',
                    data.user_id
                );

                break;

            case 'notification':

                const notification = data.notification || {};

                // ========================================
                // DEBUG FULL PAYLOAD
                // ========================================

                console.log(
                    'FULL NOTIFICATION PAYLOAD:',
                    JSON.stringify(
                        notification,
                        null,
                        2
                    )
                );

                console.log(
                    '🔔 New notification:',
                    notification
                );

                // Show popup
                showNotificationPopup(notification);

                // Update badge
                if (
                    notification.unread_count !== undefined
                ) {

                    updateNotificationBadge(
                        notification.unread_count
                    );
                }

                // Dispatch custom event
                window.dispatchEvent(
                    new CustomEvent(
                        'newNotification',
                        {
                            detail: notification
                        }
                    )
                );

                break;

            case 'marked_read':

                console.log(
                    '✅ Notifications marked as read'
                );

                updateNotificationBadge(0);

                break;

            case 'pong':

                console.log('🏓 Pong received');

                break;

            default:

                console.log(
                    'Unknown message type:',
                    messageType
                );
        }
    }

    // ========================================
    // CONNECTION STATUS
    // ========================================

    function updateConnectionStatus(connected) {

        const statusIndicator =
            document.getElementById(
                'notification-connection-status'
            );

        if (statusIndicator) {

            if (connected) {

                statusIndicator.textContent =
                    '🟢 Connected';

                statusIndicator.style.color =
                    'green';

            } else {

                statusIndicator.textContent =
                    '🔴 Disconnected';

                statusIndicator.style.color =
                    'red';
            }
        }
    }

    // ========================================
    // UTILITIES
    // ========================================

    function escapeHtml(text) {

        const div = document.createElement('div');

        div.textContent = text || '';

        return div.innerHTML;
    }

    function formatTimestamp(timestamp) {

        if (!timestamp) {
            return '';
        }

        const ts = Number(timestamp);

        if (isNaN(ts)) {

            console.warn(
                'Invalid timestamp:',
                timestamp
            );

            return '';
        }

        const date = new Date(ts * 1000);

        if (isNaN(date.getTime())) {

            console.warn(
                'Invalid date generated:',
                timestamp
            );

            return '';
        }

        const now = new Date();

        const diffSeconds = Math.floor(
            (now - date) / 1000
        );

        if (diffSeconds < 60) {
            return 'Just now';
        }

        if (diffSeconds < 3600) {
            return `${Math.floor(diffSeconds / 60)}m ago`;
        }

        if (diffSeconds < 86400) {
            return `${Math.floor(diffSeconds / 3600)}h ago`;
        }

        return date.toLocaleDateString();
    }

    // ========================================
    // PUBLIC API
    // ========================================

    window.NotificationSystem = {

        connect: connectNotificationWebSocket,

        disconnect: function() {

            if (notificationSocket) {

                notificationSocket.close();
            }
        },

        sendPing: function() {

            if (
                notificationSocket &&
                notificationSocket.readyState ===
                    WebSocket.OPEN
            ) {

                notificationSocket.send(
                    JSON.stringify({
                        type: 'ping'
                    })
                );
            }
        },

        markAsRead: function() {

            if (
                notificationSocket &&
                notificationSocket.readyState ===
                    WebSocket.OPEN
            ) {

                notificationSocket.send(
                    JSON.stringify({
                        type: 'mark_read'
                    })
                );
            }
        },

        getUnreadCount: function() {

            return unreadCount;
        }
    };

    // ========================================
    // VISIBILITY RECONNECT
    // ========================================

    document.addEventListener(
        'visibilitychange',
        function() {

            if (
                document.visibilityState === 'visible'
            ) {

                if (
                    !notificationSocket ||
                    notificationSocket.readyState ===
                        WebSocket.CLOSED
                ) {

                    console.log(
                        '🔄 Reconnecting after visibility restore'
                    );

                    connectNotificationWebSocket();
                }
            }
        }
    );

    // ========================================
    // AUTO INIT
    // ========================================

    if (document.readyState === 'loading') {

        document.addEventListener(
            'DOMContentLoaded',
            function() {

                console.log(
                    '📱 DOM ready, connecting notification WebSocket'
                );

                connectNotificationWebSocket();
            }
        );

    } else {

        console.log(
            '📱 DOM already ready, connecting notification WebSocket'
        );

        connectNotificationWebSocket();
    }

    // ========================================
    // KEEPALIVE PING
    // ========================================

    setInterval(function() {

        if (
            notificationSocket &&
            notificationSocket.readyState ===
                WebSocket.OPEN
        ) {

            window.NotificationSystem.sendPing();
        }

    }, 30000);

    console.log('✅ Notification system initialized');

})();
