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
