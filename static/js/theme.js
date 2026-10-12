(function () {
  var toggle = document.getElementById('theme-toggle');
  if (!toggle) return;
  toggle.addEventListener('click', function () {
    var root = document.documentElement;
    var next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    document.cookie = 'theme=' + next + '; path=/; max-age=31536000; SameSite=Lax' + (/(^|\.)mikhail\.codes$/.test(location.hostname) ? '; domain=mikhail.codes' : '');
  });
})();
