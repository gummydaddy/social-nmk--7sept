(function () {
    'use strict';

    let activeMedia = null;

    let startDistance = 0;
    let currentScale = 1;

    let startCenterX = 0;
    let startCenterY = 0;

    let initialTransform = '';

    function getDistance(touch1, touch2) {
        const dx =
            touch2.clientX - touch1.clientX;

        const dy =
            touch2.clientY - touch1.clientY;

        return Math.sqrt(
            dx * dx + dy * dy
        );
    }

    function getCenter(touch1, touch2) {
        return {
            x:
                (touch1.clientX + touch2.clientX) / 2,

            y:
                (touch1.clientY + touch2.clientY) / 2
        };
    }


    /*
     * ---------------------------------------------------------
     * PINCH START
     * ---------------------------------------------------------
     */

    document.addEventListener(
        'touchstart',
        function (event) {

            /*
             * Only activate when exactly two fingers
             * are touching a pinch-enabled media element.
             */
            if (event.touches.length !== 2) {
                return;
            }

            const target =
                event.target.closest(
                    '.pinch-zoom-media'
                );

            if (!target) {
                return;
            }

            activeMedia = target;

            const touch1 = event.touches[0];
            const touch2 = event.touches[1];

            startDistance =
                getDistance(
                    touch1,
                    touch2
                );

            const center =
                getCenter(
                    touch1,
                    touch2
                );

            startCenterX = center.x;
            startCenterY = center.y;

            currentScale = 1;

            initialTransform =
                activeMedia.style.transform || '';

            /*
             * Prevent Safari from interpreting this as
             * page-level pinch zoom.
             */
            event.preventDefault();

        },
        { passive: false }
    );


    /*
     * ---------------------------------------------------------
     * PINCH MOVE
     * ---------------------------------------------------------
     */

    document.addEventListener(
        'touchmove',
        function (event) {

            if (
                !activeMedia ||
                event.touches.length !== 2
            ) {
                return;
            }

            const touch1 = event.touches[0];
            const touch2 = event.touches[1];

            const distance =
                getDistance(
                    touch1,
                    touch2
                );

            if (startDistance <= 0) {
                return;
            }

            /*
             * Calculate pinch scale.
             */
            let scale =
                distance / startDistance;

            /*
             * Limit zoom.
             */
            scale = Math.max(
                1,
                Math.min(scale, 3)
            );

            currentScale = scale;

            /*
             * Keep the media centered around the
             * pinch point.
             */
            const center =
                getCenter(
                    touch1,
                    touch2
                );

            const deltaX =
                center.x - startCenterX;

            const deltaY =
                center.y - startCenterY;

            activeMedia.style.transform =
                `translate(${deltaX}px, ${deltaY}px) scale(${scale})`;

            event.preventDefault();

        },
        { passive: false }
    );


    /*
     * ---------------------------------------------------------
     * PINCH END
     * ---------------------------------------------------------
     */

    document.addEventListener(
        'touchend',
        function (event) {

            if (!activeMedia) {
                return;
            }

            /*
             * When one or both fingers are released,
             * immediately restore original size.
             */
            if (event.touches.length < 2) {

                resetMedia();

            }

        },
        { passive: true }
    );


    /*
     * ---------------------------------------------------------
     * TOUCH CANCEL
     * ---------------------------------------------------------
     */

    document.addEventListener(
        'touchcancel',
        function () {

            if (activeMedia) {
                resetMedia();
            }

        },
        { passive: true }
    );


    /*
     * ---------------------------------------------------------
     * RESET MEDIA
     * ---------------------------------------------------------
     */

    function resetMedia() {

        if (!activeMedia) {
            return;
        }

        activeMedia.style.transform =
            initialTransform;

        activeMedia = null;

        startDistance = 0;
        currentScale = 1;

        startCenterX = 0;
        startCenterY = 0;

        initialTransform = '';

    }

})();
