document.addEventListener("DOMContentLoaded", function () {

    /*
     * ============================================================
     * SOCYFIE GLOBAL THEME
     * Based on the pink/coral/orange design shown in the reference
     * ============================================================
     */

    const THEME_NAME = "socyfie";

    /*
     * ------------------------------------------------------------
     * Inject global theme CSS
     * ------------------------------------------------------------
     */

    if (!document.getElementById("socyfie-theme-css")) {

        const style = document.createElement("style");

        style.id = "socyfie-theme-css";

        style.textContent = `

        /* ========================================================
           ROOT COLORS
           ======================================================== */

        :root {

            --socyfie-primary: #FF4F6D;
            --socyfie-primary-dark: #F23F60;

            --socyfie-secondary: #FF6B6B;

            --socyfie-orange: #FF8A3D;

            --socyfie-gradient:
                linear-gradient(
                    135deg,
                    #FF4F6D 0%,
                    #FF6B6B 55%,
                    #FF8A3D 100%
                );

            --socyfie-gradient-soft:
                linear-gradient(
                    135deg,
                    #FFF0F2 0%,
                    #FFF6F1 100%
                );

            --socyfie-background: #FFF9F8;

            --socyfie-card: #FFFFFF;

            --socyfie-text: #222222;

            --socyfie-text-secondary: #666666;

            --socyfie-text-muted: #888888;

            --socyfie-border: #F3D8D5;

            --socyfie-border-light: #F8E9E6;

            --socyfie-shadow:
                0 4px 18px rgba(255, 91, 111, 0.08);

            --socyfie-shadow-hover:
                0 8px 25px rgba(255, 91, 111, 0.16);

            --socyfie-radius: 16px;

            --socyfie-radius-small: 10px;

        }


        /* ========================================================
           BODY / PAGE
           ======================================================== */

        body.socyfie-theme {

            background:
                linear-gradient(
                    180deg,
                    #FFFDFC 0%,
                    #FFF9F8 45%,
                    #FFF7F6 100%
                ) !important;

            color: var(--socyfie-text) !important;

        }


        /* ========================================================
           MAIN CONTAINERS
           ======================================================== */

        body.socyfie-theme .content-container,
        body.socyfie-theme .class-main,
        body.socyfie-theme main {

            color: var(--socyfie-text);

        }


        /* ========================================================
           HEADINGS
           ======================================================== */

        body.socyfie-theme h1,
        body.socyfie-theme h2,
        body.socyfie-theme h3,
        body.socyfie-theme h4,
        body.socyfie-theme h5,
        body.socyfie-theme h6 {

            color: var(--socyfie-text);

        }


        /* ========================================================
           LINKS
           ======================================================== */

        body.socyfie-theme a {

            color: var(--socyfie-primary);

        }

        body.socyfie-theme a:hover {

            color: var(--socyfie-primary-dark);

        }


        /* ========================================================
           PRIMARY BUTTONS
           ======================================================== */

        body.socyfie-theme .btn-primary,
        body.socyfie-theme button.primary,
        body.socyfie-theme .primary-button,
        body.socyfie-theme .create-button,
        body.socyfie-theme .submit-button {

            background: var(--socyfie-gradient) !important;

            border: none !important;

            color: #FFFFFF !important;

            border-radius: 12px !important;

            box-shadow:
                0 4px 12px rgba(255, 79, 109, 0.20);

            transition:
                transform 0.2s ease,
                box-shadow 0.2s ease;

        }


        body.socyfie-theme .btn-primary:hover,
        body.socyfie-theme button.primary:hover,
        body.socyfie-theme .primary-button:hover,
        body.socyfie-theme .create-button:hover,
        body.socyfie-theme .submit-button:hover {

            transform: translateY(-1px);

            box-shadow:
                0 7px 18px rgba(255, 79, 109, 0.28);

        }


        /* ========================================================
           BOOTSTRAP BUTTONS
           ======================================================== */

        body.socyfie-theme .btn-danger,
        body.socyfie-theme .btn-success,
        body.socyfie-theme .btn-warning {

            background: var(--socyfie-gradient) !important;

            border-color: transparent !important;

            color: #FFFFFF !important;

        }


        body.socyfie-theme .btn-info {

            background: #FF8A6B !important;

            border-color: #FF8A6B !important;

            color: white !important;

        }


        /* ========================================================
           OUTLINE BUTTONS
           ======================================================== */

        body.socyfie-theme .btn-outline-primary {

            color: var(--socyfie-primary) !important;

            border-color: var(--socyfie-primary) !important;

            background: transparent !important;

        }


        body.socyfie-theme .btn-outline-primary:hover {

            background: var(--socyfie-gradient) !important;

            color: white !important;

            border-color: transparent !important;

        }


        /* ========================================================
           GENERIC BUTTONS
           ======================================================== */

        body.socyfie-theme button {

            border-radius: 10px;

        }


        /* ========================================================
           CARDS
           ======================================================== */

        body.socyfie-theme .card,
        body.socyfie-theme .media-wrapper,
        body.socyfie-theme .media-content,
        body.socyfie-theme .post,
        body.socyfie-theme .post-card,
        body.socyfie-theme .media-card,
        body.socyfie-theme .content-card {

            border-color: var(--socyfie-border-light);
        }


        body.socyfie-theme .col.media-item {

            border-radius: var(--socyfie-radius);

            box-shadow: var(--socyfie-shadow);

        }


        /* ========================================================
           CARD HOVER
           ======================================================== */

        body.socyfie-theme .card:hover,
        body.socyfie-theme .media-wrapper:hover,
        body.socyfie-theme .media-card:hover {

            box-shadow: var(--socyfie-shadow-hover);

        }


        /* ========================================================
           INPUTS
           ======================================================== */

        body.socyfie-theme input,
        body.socyfie-theme textarea,
        body.socyfie-theme select {

            background-color: #FFFFFF !important;

            color: var(--socyfie-text) !important;

            border: 1px solid var(--socyfie-border) !important;

            border-radius: 12px !important;

        }


        body.socyfie-theme input:focus,
        body.socyfie-theme textarea:focus,
        body.socyfie-theme select:focus {

            border-color: var(--socyfie-primary) !important;

            box-shadow:
                0 0 0 3px rgba(255, 79, 109, 0.10) !important;

            outline: none !important;

        }


        /* ========================================================
           SEARCH BOX
           ======================================================== */

        body.socyfie-theme .search-box,
        body.socyfie-theme .search-container,
        body.socyfie-theme .search-input {

            background: #FFFFFF !important;

            border: 1px solid #F2D7D4 !important;

            border-radius: 24px !important;

        }


        /* ========================================================
           NAVIGATION
           ======================================================== */

        body.socyfie-theme nav,
        body.socyfie-theme .navbar,
        body.socyfie-theme .bottom-nav,
        body.socyfie-theme .bottom-navigation {

            background: rgba(255,255,255,0.96) !important;

            border-color: var(--socyfie-border-light) !important;

        }


        body.socyfie-theme .nav-link.active,
        body.socyfie-theme .bottom-nav .active,
        body.socyfie-theme .bottom-navigation .active {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           ICONS
           ======================================================== */

        body.socyfie-theme .text-primary,
        body.socyfie-theme .icon-primary,
        body.socyfie-theme .primary-icon {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           BADGES
           ======================================================== */

        body.socyfie-theme .badge,
        body.socyfie-theme .notification-badge {

            background: var(--socyfie-gradient) !important;

            color: #FFFFFF !important;

            border: none !important;

        }


        /* ========================================================
           ACTIVE / SELECTED ELEMENTS
           ======================================================== */

        body.socyfie-theme .active,
        body.socyfie-theme .selected {

            --active-color: var(--socyfie-primary);

        }


        body.socyfie-theme .active-tab,
        body.socyfie-theme .selected-tab {

            background: var(--socyfie-gradient) !important;

            color: #FFFFFF !important;

        }


        /* ========================================================
           TABS
           ======================================================== */

        body.socyfie-theme .nav-tabs .nav-link.active {

            color: #FFFFFF !important;

            background: var(--socyfie-gradient) !important;

            border-color: transparent !important;

            border-radius: 10px !important;

        }


        /* ========================================================
           PROGRESS BARS
           ======================================================== */

        body.socyfie-theme .progress-bar {

            background: var(--socyfie-gradient) !important;

        }


        /* ========================================================
           CHECKBOX / RADIO
           ======================================================== */

        body.socyfie-theme input[type="checkbox"],
        body.socyfie-theme input[type="radio"] {

            accent-color: var(--socyfie-primary);

        }


        /* ========================================================
           DROPDOWNS
           ======================================================== */

        body.socyfie-theme .dropdown-menu {

            background: #FFFFFF !important;

            border: 1px solid var(--socyfie-border-light) !important;

            border-radius: 14px !important;

            box-shadow:
                0 10px 30px rgba(255, 79, 109, 0.12);

        }


        body.socyfie-theme .dropdown-item:hover,
        body.socyfie-theme .dropdown-item:focus {

            background: #FFF0F2 !important;

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           MODALS
           ======================================================== */

        body.socyfie-theme .modal-content {

            background: #FFFFFF !important;

            border: 1px solid var(--socyfie-border-light) !important;

            border-radius: 18px !important;

            box-shadow:
                0 15px 45px rgba(255, 79, 109, 0.15);

        }


        /* ========================================================
           ALERTS
           ======================================================== */

        body.socyfie-theme .alert {

            border-radius: 12px;

            border: 1px solid var(--socyfie-border-light);

        }


        body.socyfie-theme .alert-danger,
        body.socyfie-theme .alert-warning {

            background: #FFF0F2 !important;

            color: #C93652 !important;

            border-color: #FFD1D8 !important;

        }


        body.socyfie-theme .alert-success {

            background: #FFF5F1 !important;

            color: #C65D36 !important;

            border-color: #FFDCCF !important;

        }


        /* ========================================================
           TABLES
           ======================================================== */

        body.socyfie-theme table {

            background: #FFFFFF;

            color: var(--socyfie-text);

        }


        body.socyfie-theme th {

            color: var(--socyfie-primary);

        }


        body.socyfie-theme tr {

            border-color: var(--socyfie-border-light);

        }


        /* ========================================================
           PAGINATION
           ======================================================== */

        body.socyfie-theme .page-item.active .page-link {

            background: var(--socyfie-gradient) !important;

            border-color: transparent !important;

        }


        body.socyfie-theme .page-link {

            color: var(--socyfie-primary);

        }


        /* ========================================================
           LINKS / HASHTAGS
           ======================================================== */

        body.socyfie-theme .hashtag,
        body.socyfie-theme .hashtag-link {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           LIKE / HEART / SOCIAL ACTIONS
           ======================================================== */

        body.socyfie-theme .like.active,
        body.socyfie-theme .liked,
        body.socyfie-theme .heart.active {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           FLOATING CREATE BUTTON
           ======================================================== */

        body.socyfie-theme .floating-button,
        body.socyfie-theme .fab,
        body.socyfie-theme .create-fab {

            background: var(--socyfie-gradient) !important;

            color: #FFFFFF !important;

            border: none !important;

            box-shadow:
                0 8px 20px rgba(255, 79, 109, 0.30);

        }


        /* ========================================================
           PRIMARY CREATE / CTA AREAS
           ======================================================== */

        body.socyfie-theme .cta,
        body.socyfie-theme .create-banner,
        body.socyfie-theme .promo-banner {

            background: var(--socyfie-gradient) !important;

            color: #FFFFFF !important;

            border: none !important;

        }


        /* ========================================================
           TOASTS
           ======================================================== */

        body.socyfie-theme .toast {

            background: #FFFFFF !important;

            border: 1px solid var(--socyfie-border-light) !important;

            box-shadow:
                0 8px 25px rgba(255, 79, 109, 0.15);

        }


        /* ========================================================
           SCROLLBAR
           ======================================================== */

        body.socyfie-theme ::-webkit-scrollbar {

            width: 7px;

            height: 7px;

        }


        body.socyfie-theme ::-webkit-scrollbar-track {

            background: #FFF5F4;

        }


        body.socyfie-theme ::-webkit-scrollbar-thumb {

            background: #FFB2B8;

            border-radius: 10px;

        }


        body.socyfie-theme ::-webkit-scrollbar-thumb:hover {

            background: var(--socyfie-primary);

        }


        /* ========================================================
           SELECTION
           ======================================================== */

        body.socyfie-theme ::selection {

            background: rgba(255, 79, 109, 0.20);

            color: #222222;

        }


        /* ========================================================
           HR / DIVIDERS
           ======================================================== */

        body.socyfie-theme hr {

            border-color: var(--socyfie-border-light) !important;

        }


        /* ========================================================
           NIGHT MODE + SOCYFIE THEME
           ======================================================== */

        /*
         * Keep existing night-mode backgrounds.
         * This section ONLY changes text/link colors.
         */


        /* General text in night mode */

        body.socyfie-night-mode .content-container,
        body.socyfie-night-mode .class-main,
        body.socyfie-night-mode main {

            color: #FFFFFF !important;

        }


        /* Common text elements */

        body.socyfie-night-mode p,
        body.socyfie-night-mode span,
        body.socyfie-night-mode label,
        body.socyfie-night-mode small,
        body.socyfie-night-mode li,
        body.socyfie-night-mode td,
        body.socyfie-night-mode th {

            color: #FFFFFF;

        }


        /* Headings */

        body.socyfie-night-mode h1,
        body.socyfie-night-mode h2,
        body.socyfie-night-mode h3,
        body.socyfie-night-mode h4,
        body.socyfie-night-mode h5,
        body.socyfie-night-mode h6 {

            color: #FFFFFF !important;

        }


        /* ========================================================
           LINKS
           ======================================================== */

        body.socyfie-night-mode a,
        body.socyfie-night-mode a:visited {

            color: var(--socyfie-primary) !important;

        }


        body.socyfie-night-mode a:hover {

            color: var(--socyfie-secondary) !important;

        }


        /* Hashtags */

        body.socyfie-night-mode .hashtag,
        body.socyfie-night-mode .hashtag-link {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           HEADER
           ======================================================== */

        body.socyfie-night-mode header,
        body.socyfie-night-mode .header,
        body.socyfie-night-mode .site-header,
        body.socyfie-night-mode .navbar {

            color: var(--socyfie-primary) !important;

        }


        body.socyfie-night-mode header h1,
        body.socyfie-night-mode header h2,
        body.socyfie-night-mode header h3,
        body.socyfie-night-mode header h4,
        body.socyfie-night-mode header h5,
        body.socyfie-night-mode header h6,
        body.socyfie-night-mode .header h1,
        body.socyfie-night-mode .header h2,
        body.socyfie-night-mode .header h3,
        body.socyfie-night-mode .header h4,
        body.socyfie-night-mode .header h5,
        body.socyfie-night-mode .header h6,
        body.socyfie-night-mode .navbar-brand {

            color: var(--socyfie-primary) !important;

        }


        /* Header links */

        body.socyfie-night-mode header a,
        body.socyfie-night-mode .header a,
        body.socyfie-night-mode .navbar a {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           ICONS IN NIGHT MODE
           ======================================================== */

        body.socyfie-night-mode .text-primary,
        body.socyfie-night-mode .icon-primary,
        body.socyfie-night-mode .primary-icon {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           FORM TEXT
           ======================================================== */

        body.socyfie-night-mode input,
        body.socyfie-night-mode textarea,
        body.socyfie-night-mode select {

            color: #FFFFFF !important;

        }


        body.socyfie-night-mode input::placeholder,
        body.socyfie-night-mode textarea::placeholder {

            color: #BBBBBB !important;

        }


        /* ========================================================
           MEDIA ITEMS
           ======================================================== */

        /*
         * IMPORTANT:
         *
         * No background is specified here.
         *
         * Therefore .col.media-item keeps the background
         * provided by your existing night-mode CSS.
         */

        body.socyfie-night-mode .col.media-item {

            color: #FFFFFF;

        }


        body.socyfie-night-mode .col.media-item p,
        body.socyfie-night-mode .col.media-item span,
        body.socyfie-night-mode .col.media-item small,
        body.socyfie-night-mode .col.media-item label {

            color: #FFFFFF;

        }


        body.socyfie-night-mode .col.media-item a {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           MEDIA CARD TEXT
           ======================================================== */

        body.socyfie-night-mode .media-wrapper,
        body.socyfie-night-mode .media-content {

            color: #FFFFFF;

        }


        body.socyfie-night-mode .media-wrapper p,
        body.socyfie-night-mode .media-wrapper span,
        body.socyfie-night-mode .media-wrapper small,
        body.socyfie-night-mode .media-content p,
        body.socyfie-night-mode .media-content span,
        body.socyfie-night-mode .media-content small {

            color: #FFFFFF;

        }


        body.socyfie-night-mode .media-wrapper a,
        body.socyfie-night-mode .media-content a {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           MUTED TEXT
           ======================================================== */

        body.socyfie-night-mode .text-muted,
        body.socyfie-night-mode .muted,
        body.socyfie-night-mode .secondary-text {

            color: #CCCCCC !important;

        }


        /* ========================================================
           BUTTON TEXT
           ======================================================== */

        /*
         * Don't turn buttons white here.
         * Primary buttons should retain the pink/orange gradient.
         */

        body.socyfie-night-mode .btn-primary,
        body.socyfie-night-mode .primary-button,
        body.socyfie-night-mode .create-button,
        body.socyfie-night-mode .submit-button {

            color: #FFFFFF !important;

        }


        /* ========================================================
           ACTIVE SOCIAL ICONS
           ======================================================== */

        body.socyfie-night-mode .like.active,
        body.socyfie-night-mode .liked,
        body.socyfie-night-mode .heart.active,
        body.socyfie-night-mode .bookmark.active {

            color: var(--socyfie-primary) !important;

        }


        /* ========================================================
           BORDERS
           ======================================================== */

        body.socyfie-night-mode hr {

            border-color: rgba(255, 255, 255, 0.15) !important;

        }



        /* ========================================================
           DISABLED ELEMENTS
           ======================================================== */

        body.socyfie-theme .disabled,
        body.socyfie-theme button:disabled,
        body.socyfie-theme input:disabled {

            opacity: 0.55;

        }

        `;

        document.head.appendChild(style);
    }


    /*
     * ------------------------------------------------------------
     * ENABLE SOCYFIE THEME
     * ------------------------------------------------------------
     */

    function enableSocyfieTheme() {

        document.body.classList.add("socyfie-theme");

        localStorage.setItem("platform-theme", THEME_NAME);

    }


    /*
     * ------------------------------------------------------------
     * DISABLE SOCYFIE THEME
     * ------------------------------------------------------------
     */

    function disableSocyfieTheme() {

        document.body.classList.remove("socyfie-theme");

        localStorage.removeItem("platform-theme");

    }


    /*
     * ------------------------------------------------------------
     * TOGGLE THEME
     * ------------------------------------------------------------
     */

    window.toggleSocyfieTheme = function () {

        if (document.body.classList.contains("socyfie-theme")) {

            disableSocyfieTheme();

        } else {

            enableSocyfieTheme();

        }

    };


    /*
     * ------------------------------------------------------------
     * APPLY SAVED THEME
     * ------------------------------------------------------------
     */

    const savedTheme = localStorage.getItem("platform-theme");

    if (savedTheme === THEME_NAME) {

        enableSocyfieTheme();

    } else {

        /*
         * If you want this new theme to ALWAYS be enabled,
         * change this to:
         *
         * enableSocyfieTheme();
         */

    }


    /*
     * ------------------------------------------------------------
     * GLOBAL ACCESS
     * ------------------------------------------------------------
     */

    window.SocyfieTheme = {

        enable: enableSocyfieTheme,

        disable: disableSocyfieTheme,

        toggle: window.toggleSocyfieTheme

    };

});
