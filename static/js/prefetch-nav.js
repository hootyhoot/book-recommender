// Fallback for browsers without Speculation Rules support (Safari,
// Firefox): prefetch a same-origin nav link's HTML as soon as the
// pointer hovers it, same intent as the speculationrules block in
// base.html - by the time an actual click lands, the response is
// already in the HTTP cache.
(function () {
    var requested = {};
    document.querySelectorAll('a.nav-btn[href^="/"]').forEach(function (a) {
        a.addEventListener('pointerenter', function () {
            var href = a.getAttribute('href');
            if (requested[href]) return;
            requested[href] = true;
            var link = document.createElement('link');
            link.rel = 'prefetch';
            link.href = href;
            document.head.appendChild(link);
        }, { once: true });
    });
})();
