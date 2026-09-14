let deferredPrompt = null;

document.addEventListener("DOMContentLoaded", () => {
    const installButton = document.getElementById("install-button");

    if (!installButton) {
        console.warn("Socyfie: #install-button not found");
        return;
    }

    console.log("Socyfie PWA install script loaded");

    // Keep hidden until browser tells us installation is available
    installButton.style.display = "none";

    // Install button click
    installButton.addEventListener("click", async () => {
        console.log("Socyfie: Install button clicked");

        if (!deferredPrompt) {
            console.log("Socyfie: No install prompt currently available");
            return;
        }

        // Show browser's installation prompt
        deferredPrompt.prompt();

        const { outcome } = await deferredPrompt.userChoice;

        console.log(
            `Socyfie: User response to install prompt: ${outcome}`
        );

        // The prompt can only be used once
        deferredPrompt = null;

        // Hide button
        installButton.style.display = "none";
    });
});


// Browser says PWA can be installed
window.addEventListener("beforeinstallprompt", (e) => {

    console.log("Socyfie: beforeinstallprompt fired");

    // Stop automatic browser prompt
    e.preventDefault();

    // Save event
    deferredPrompt = e;

    const installButton = document.getElementById("install-button");

    if (installButton) {
        installButton.style.display = "block";

        console.log("Socyfie: Install button shown");
    }
});


// PWA successfully installed
window.addEventListener("appinstalled", () => {

    console.log("Socyfie: App installed");

    deferredPrompt = null;

    const installButton = document.getElementById("install-button");

    if (installButton) {
        installButton.style.display = "none";
    }
});

