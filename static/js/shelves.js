(function () {
    var toggles = document.querySelectorAll('.section-toggle');

    function setOpen(toggle, open) {
        toggle.setAttribute('aria-expanded', String(open));
        var wrap = document.getElementById(toggle.getAttribute('aria-controls'));
        if (wrap) wrap.dataset.open = String(open);
    }

    toggles.forEach(function (toggle) {
        toggle.addEventListener('click', function () {
            var willOpen = toggle.getAttribute('aria-expanded') !== 'true';
            toggles.forEach(function (other) {
                setOpen(other, other === toggle ? willOpen : false);
            });
        });
    });
})();

// Tap-to-pull-out for touch devices: hover doesn't exist on touch, so the
// pull-out reveal (title/cover) needs a first tap, with a second tap on
// the same book following the link. matchMedia('(hover: none)') keeps
// this off any device that has real hover (mouse/trackpad), including
// touchscreen laptops - it only activates where hover genuinely isn't
// available.
(function () {
    if (!window.matchMedia('(hover: none)').matches) return;

    var openEl = null;

    function close() {
        if (openEl) {
            openEl.classList.remove('touch-open');
            openEl = null;
        }
    }

    document.querySelectorAll('.book-spine, .favorite-book').forEach(function (el) {
        el.addEventListener('click', function (e) {
            if (el.classList.contains('touch-open')) return; // second tap: follow the link
            e.preventDefault();
            close();
            el.classList.add('touch-open');
            openEl = el;
        });
    });

    document.addEventListener('click', function (e) {
        if (openEl && !openEl.contains(e.target)) close();
    });
})();
