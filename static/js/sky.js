// Pixel sky behind the page: drifting clouds, and at night (dark theme) a
// field of glimmering 4-pointed stars with the occasional shooting star.
// Shared by mikhail.codes (homepage + inner pages) and books.mikhail.codes.
// Fixed to the viewport; colours come from CSS variables so it follows the
// theme. <canvas id="sky" data-clouds="off"> skips the clouds (the homepage
// hero draws its own).
(function () {
  var c = document.getElementById('sky');
  if (!c) return;
  var x = c.getContext('2d');
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var showClouds = c.getAttribute('data-clouds') !== 'off';
  var P = 8, S = 2; // cloud block size, star pixel size
  var W, H, clouds = [], stars = [], shooting = null, nextShot = 0, cloudColor, night;
  var STAR_COLORS = ['#eceee6', '#eceee6', '#eceee6', '#cfe4ff', '#ffe9b8'];
  c.style.imageRendering = 'pixelated';

  function loadTheme() {
    cloudColor = getComputedStyle(document.documentElement).getPropertyValue('--cloud').trim();
    night = document.documentElement.getAttribute('data-theme') !== 'light';
  }

  function size() {
    W = c.width = window.innerWidth; H = c.height = window.innerHeight;
    clouds = [];
    var n = Math.max(4, Math.round(W / 180));
    for (var i = 0; i < n; i++) {
      clouds.push({x: Math.random() * W, y: Math.random() * H, w: 3 + (Math.random() * 6 | 0), v: .15 + Math.random() * .3});
    }
    stars = [];
    var count = Math.round(W * H / 9000);
    for (var j = 0; j < count; j++) {
      // mixed sizes: lots of tiny specks, fewer twinklers, a rare bright one
      var r = Math.random(), size =
        r < 0.45 ? {px: 1, arm: 1} :   // tiny
        r < 0.80 ? {px: 2, arm: 1} :   // small
        r < 0.95 ? {px: 2, arm: 2} :   // medium
                   {px: 3, arm: 3};    // big
      stars.push({
        x: (Math.random() * W / S | 0) * S,
        y: (Math.random() * H / S | 0) * S,
        px: size.px, maxArm: size.arm,
        color: STAR_COLORS[Math.random() * STAR_COLORS.length | 0],
        phase: Math.random() * Math.PI * 2,
        speed: 0.6 + Math.random() * 1.6
      });
    }
  }

  // 4-pointed pixel star: a centre pixel with arms up/down/left/right whose
  // length steps with the glimmer (0 = just a dot, up to maxArm = full twinkle)
  function drawStar(s, t) {
    var g = (Math.sin(t * s.speed + s.phase) + 1) / 2; // 0..1
    var arm = s.maxArm === 1 ? (g > 0.75 ? 1 : 0) : Math.round(g * s.maxArm);
    var q = s.px;
    x.globalAlpha = 0.35 + 0.65 * (Math.round(g * 3) / 3);
    x.fillStyle = s.color;
    x.fillRect(s.x, s.y, q, q);
    for (var a = 1; a <= arm; a++) {
      x.fillRect(s.x + a * q, s.y, q, q);
      x.fillRect(s.x - a * q, s.y, q, q);
      x.fillRect(s.x, s.y + a * q, q, q);
      x.fillRect(s.x, s.y - a * q, q, q);
    }
    // big stars bloom: a dim diagonal halo around the centre at full glimmer
    if (s.maxArm === 3 && arm >= 2) {
      x.globalAlpha *= 0.45;
      x.fillRect(s.x - q, s.y - q, q, q); x.fillRect(s.x + q, s.y - q, q, q);
      x.fillRect(s.x - q, s.y + q, q, q); x.fillRect(s.x + q, s.y + q, q, q);
    }
  }

  // shooting star: a bright head falling on a steep diagonal (30-60 degrees
  // below horizontal) with a solid, tapering pixel tail behind it
  function launch(now) {
    var fromLeft = Math.random() < 0.5;
    var ang = (30 + Math.random() * 30) * Math.PI / 180, speed = 10 + Math.random() * 5;
    shooting = {
      x: fromLeft ? Math.random() * W * 0.6 : W * 0.4 + Math.random() * W * 0.6,
      y: Math.random() * H * 0.3,
      vx: (fromLeft ? 1 : -1) * Math.cos(ang) * speed,
      vy: Math.sin(ang) * speed,
      life: 0, max: 40 + (Math.random() * 25 | 0)
    };
    nextShot = now + 6000 + Math.random() * 9000;
  }

  function drawShooting() {
    var s = shooting, speed = Math.hypot(s.vx, s.vy), dx = s.vx / speed, dy = s.vy / speed;
    var fade = s.life > s.max - 10 ? (s.max - s.life) / 10 : 1;
    var L = Math.min(140, s.life * speed); // tail grows in, then stays ~140px
    x.fillStyle = '#eceee6';
    for (var k = 0; k <= L; k += S) {
      x.globalAlpha = fade * (1 - k / (L + 1)) * 0.9;
      var tx = (s.x - dx * k) / S | 0, ty = (s.y - dy * k) / S | 0;
      x.fillRect(tx * S, ty * S, S, k < 24 ? S * 2 : S); // thicker near the head
    }
    x.globalAlpha = fade;
    var hx = (s.x / S | 0) * S, hy = (s.y / S | 0) * S;
    x.fillRect(hx - S, hy - S, S * 3, S * 3);
    s.x += s.vx; s.y += s.vy; s.life++;
    if (s.life > s.max || s.x < -200 || s.x > W + 200 || s.y > H + 200) shooting = null;
  }

  function frame(now) {
    now = now || 0;
    var t = now / 1000;
    x.clearRect(0, 0, W, H);
    // stars first, clouds after, so clouds drift in front of the night sky
    if (night) {
      stars.forEach(function (s) { drawStar(s, reduce ? 1 : t); });
      if (!reduce) {
        if (!shooting && now > nextShot) launch(now);
        if (shooting) drawShooting();
      }
      x.globalAlpha = 1;
    }
    if (showClouds) {
      x.fillStyle = cloudColor;
      clouds.forEach(function (cl) {
        for (var i = 0; i < cl.w; i++) x.fillRect((cl.x + i * P) | 0, cl.y | 0, P, P);
        for (var j = 1; j < cl.w - 1; j++) x.fillRect((cl.x + j * P) | 0, (cl.y - P) | 0, P, P);
        if (!reduce) { cl.x += cl.v; if (cl.x > W) cl.x = -cl.w * P; }
      });
    }
    if (!reduce) requestAnimationFrame(frame);
  }

  loadTheme(); size();
  nextShot = 2500 + Math.random() * 4000; // first one fairly soon after load
  window.addEventListener('resize', function () { size(); if (reduce) frame(); });
  // theme toggles flip data-theme on <html>; stars only show at night
  new MutationObserver(function () { loadTheme(); if (reduce) frame(); })
    .observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
  if (reduce) frame(); else requestAnimationFrame(frame);
})();
