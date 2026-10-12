// Drifting pixel clouds behind the page, same as mikhail.codes' hero sky.
// Fixed to the viewport, colour read from --cloud so it follows the theme.
(function () {
  var c = document.getElementById('sky');
  if (!c) return;
  var x = c.getContext('2d');
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var P = 8, W, H, clouds = [], color;

  function loadColor() { color = getComputedStyle(document.documentElement).getPropertyValue('--cloud').trim(); }
  function size() {
    W = c.width = window.innerWidth; H = c.height = window.innerHeight;
    var n = Math.max(4, Math.round(W / 180));
    clouds = [];
    for (var i = 0; i < n; i++) {
      clouds.push({x: Math.random() * W, y: Math.random() * H, w: 3 + (Math.random() * 6 | 0), v: .15 + Math.random() * .3});
    }
  }
  function frame() {
    x.clearRect(0, 0, W, H);
    x.fillStyle = color;
    clouds.forEach(function (cl) {
      for (var i = 0; i < cl.w; i++) x.fillRect((cl.x + i * P) | 0, cl.y | 0, P, P);
      for (var j = 1; j < cl.w - 1; j++) x.fillRect((cl.x + j * P) | 0, (cl.y - P) | 0, P, P);
      if (!reduce) { cl.x += cl.v; if (cl.x > W) cl.x = -cl.w * P; }
    });
    if (!reduce) requestAnimationFrame(frame);
  }

  loadColor(); size();
  window.addEventListener('resize', function () { size(); if (reduce) frame(); });
  // theme toggles flip data-theme on <html>; re-read the cloud colour when it changes
  new MutationObserver(function () { loadColor(); if (reduce) frame(); })
    .observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
  frame();
})();
