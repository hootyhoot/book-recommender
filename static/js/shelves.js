// Covers in a shelf that starts collapsed ("want to read") carry data-src
// instead of src, so ~60 hidden covers don't compete with the visible ones
// on first load. They're swapped in once the page has finished loading, or
// earlier if the toggle is hovered, focused or pressed, so they're already
// there by the time the shelf opens.
(function () {
    var pending = document.querySelectorAll('img[data-src]');
    if (!pending.length) return;
    var done = false;
    function loadAll() {
        if (done) return;
        done = true;
        pending.forEach(function (img) { img.src = img.dataset.src; img.removeAttribute('data-src'); });
    }
    ['pointerenter', 'pointerdown', 'focus'].forEach(function (ev) {
        document.querySelectorAll('.section-toggle').forEach(function (t) { t.addEventListener(ev, loadAll, { once: true }); });
    });
    if (document.readyState === 'complete') loadAll();
    else window.addEventListener('load', loadAll);
})();

(function () {
    var toggles = document.querySelectorAll('.section-toggle');

    function setOpen(toggle, open) {
        toggle.setAttribute('aria-expanded', String(open));
        var wrap = document.getElementById(toggle.getAttribute('aria-controls'));
        if (!wrap) return;
        wrap.dataset.settled = 'false';
        wrap.dataset.open = String(open);
        if (open) {
            clearTimeout(wrap._settle);
            wrap._settle = setTimeout(function () {
                if (wrap.dataset.open === 'true') wrap.dataset.settled = 'true';
            }, 450);
        }
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
