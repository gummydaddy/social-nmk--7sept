(function () {
    'use strict';

    console.log("========== OneSignal Login Debug ==========");
    console.log("Landing page OneSignal script loaded");
    console.log("User Agent:", navigator.userAgent);

    var isAuthenticated = document.body.dataset.authenticated === 'true';
    var currentUserId = document.body.dataset.userId;

    console.log("Authenticated:", isAuthenticated);
    console.log("Current User ID:", currentUserId);

    if (!isAuthenticated || !currentUserId) {
        console.log("User is anonymous. Skipping OneSignal login.");
        return;
    }

    var loggedIn = false;

    function attemptOneSignalLogin() {

        console.log("attemptOneSignalLogin() called");

        console.log({
            medianExists: !!window.median,
            onesignalExists: !!(window.median && window.median.onesignal),
            loginExists: !!(
                window.median &&
                window.median.onesignal &&
                typeof window.median.onesignal.login === "function"
            )
        });

        if (loggedIn) {
            console.log("Already logged into OneSignal.");
            return true;
        }

        if (
            window.median &&
            window.median.onesignal &&
            typeof window.median.onesignal.login === "function"
        ) {

            console.log("Calling median.onesignal.login() for user:", currentUserId);

            window.median.onesignal.login(String(currentUserId))
                .then(function (result) {

                    console.log("login() promise resolved:", result);

                    if (result && result.success) {

                        loggedIn = true;

                        console.log("✅ OneSignal external ID set for user:", currentUserId);

                        if (typeof window.median.onesignal.onesignalInfo === "function") {

                            window.median.onesignal.onesignalInfo()
                                .then(function (info) {

                                    console.log("========== OneSignal Info ==========");
                                    console.log(info);
                                    console.log("Subscribed:", info.oneSignalSubscribed);
                                    console.log("Player ID:", info.playerId);
                                    console.log("External ID:", info.externalId);

                                })
                                .catch(function (err) {
                                    console.warn("onesignalInfo() failed:", err);
                                });

                        } else {
                            console.warn("onesignalInfo() is not available.");
                        }

                    } else {

                        console.warn(
                            "median.onesignal.login() returned unsuccessful:",
                            result
                        );

                    }

                })
                .catch(function (err) {

                    console.error("OneSignal login promise rejected:", err);

                });

            return true;
        }

        console.log("Median bridge not available yet.");

        return false;
    }

    // Try immediately.
    if (!attemptOneSignalLogin()) {

        console.log("Starting bridge polling...");

        var attempts = 0;
        var maxAttempts = 5;

        var pollId = setInterval(function () {

            attempts++;

            console.log(
                "Poll #" + attempts,
                {
                    medianExists: !!window.median,
                    onesignalExists: !!(
                        window.median &&
                        window.median.onesignal
                    ),
                    loginExists: !!(
                        window.median &&
                        window.median.onesignal &&
                        typeof window.median.onesignal.login === "function"
                    )
                }
            );

            if (attemptOneSignalLogin() || attempts >= maxAttempts) {

                clearInterval(pollId);

                if (attempts >= maxAttempts && !loggedIn) {

                    console.warn(
                        "Median bridge never became available after " +
                        maxAttempts +
                        " attempts."
                    );

                } else {

                    console.log("Stopped polling.");

                }
            }

        }, 500);
    }

    // Listen for the Median ready event.
    window.addEventListener("median.library.ready", function () {

        console.log("====================================");
        console.log("✅ median.library.ready event fired");
        console.log("window.median =", window.median);
        console.log("====================================");

        attemptOneSignalLogin();

    });

})();
