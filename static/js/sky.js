// Pixel sky behind the page, shared by mikhail.codes (homepage + inner pages)
// and books.mikhail.codes. Fixed to the viewport; colours come from CSS
// variables so it follows the theme.
//   always:  three layers of drifting clouds (far / mid / near) for depth
//   night:   glimmering 4-pointed stars + the occasional shooting star
//   day:     a far-off jet laying a contrail, and small flocks of birds
// <canvas id="sky" data-clouds="off"> skips the clouds.
(function () {
  var c = document.getElementById('sky');
  if (!c) return;
  var x = c.getContext('2d');
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var showClouds = c.getAttribute('data-clouds') !== 'off';
  var S = 2; // star / sprite pixel size
  var W, H, layers = [], stars = [], shooting = null, nextShot = 0, night;
  var jet = null, nextJet = 0, trail = [], flock = null, nextFlock = 0;
  var pal = {};
  var STAR_COLORS = ['#eceee6', '#eceee6', '#eceee6', '#cfe4ff', '#ffe9b8'];
  c.style.imageRendering = 'pixelated';

  function css(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  // blend two #rrggbb colours: t=0 -> a, t=1 -> b
  function mix(a, b, t) {
    var pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16), out = 0;
    for (var sh = 16; sh >= 0; sh -= 8) {
      var ca = (pa >> sh) & 255, cb = (pb >> sh) & 255;
      out |= Math.round(ca + (cb - ca) * t) << sh;
    }
    return '#' + ('00000' + out.toString(16)).slice(-6);
  }

  function loadTheme() {
    night = document.documentElement.getAttribute('data-theme') !== 'light';
    var cloud = css('--cloud') || '#1a1c18', bg = css('--bg') || '#0c0d0b';
    // far clouds sit closer to the background colour, near ones are full strength
    pal.cloud = [mix(bg, cloud, 0.45), mix(bg, cloud, 0.75), cloud];
    pal.ink = css('--ink-muted') || '#6b6046';
  }

  // ---------- clouds: three parallax layers ----------
  // per = one cloud per this many px of width; the day sky is about twice as
  // cloudy as the night one so the stars still show through after dark
  var LAYERS = [
    {P: 4, speed: [0.05, 0.12], per: 200, perDay: 100},  // far: small, slow
    {P: 6, speed: [0.12, 0.25], per: 260, perDay: 130},  // mid
    {P: 8, speed: [0.25, 0.45], per: 340, perDay: 170}   // near: big, quicker
  ];
  function rnd(n) { return Math.random() * n | 0; }
  // a puffy pixel cloud, roughly symmetric: a rounded underside, a wide base,
  // a narrower middle and a bump on top, each row centred over the one below
  // (with a little jitter) so neither side ends up as a one-sided staircase
  function makeCloud(L, xpos) {
    var w = 5 + rnd(7);
    var mid = Math.max(3, w - 2 - rnd(3));
    var midOff = Math.min(Math.max(1, ((w - mid) >> 1) + rnd(3) - 1), w - mid - 1);
    var bump = Math.max(2, mid - 2 - rnd(2));
    var bumpOff = midOff + Math.min(Math.max(0, ((mid - bump) >> 1) + rnd(3) - 1), mid - bump);
    return {
      x: xpos, y: Math.random() * H * 0.9,
      v: L.speed[0] + Math.random() * (L.speed[1] - L.speed[0]),
      // [offset, width] per row, bottom to top; the first row sits under the base.
      // Small clouds skip the top bump so they don't come out tall and pawn-shaped.
      rows: w >= 7 ? [[1, w - 2], [0, w], [midOff, mid], [bumpOff, bump]] : [[1, w - 2], [0, w], [midOff, mid]]
    };
  }
  function buildClouds() {
    layers = LAYERS.map(function (L) {
      var n = Math.max(2, Math.round(W / (night ? L.per : L.perDay))), out = [];
      for (var i = 0; i < n; i++) out.push(makeCloud(L, Math.random() * W));
      return out;
    });
  }
  function drawCloudLayer(i) {
    var L = LAYERS[i], P = L.P;
    x.fillStyle = pal.cloud[i];
    layers[i].forEach(function (cl, k) {
      cl.rows.forEach(function (r, ri) {
        x.fillRect(Math.round(cl.x + r[0] * P), Math.round(cl.y - (ri - 1) * P), r[1] * P, P);
      });
      if (!reduce) {
        cl.x += cl.v;
        // drifted off the right edge: respawn as a fresh cloud off the left edge
        if (cl.x > W) layers[i][k] = makeCloud(L, -cl.rows[1][1] * P);
      }
    });
  }

  // ---------- stars (night) ----------
  function makeStars() {
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

  // ---------- day: a far-off jet laying a twin contrail ----------
  // tiny side-view airliner, nose to the right, 2px pixels
  var JET = ['T.......', 'TTFFFFFF', '..WWW...'];
  var JET_PAL = {T: '#b85a3a', F: '#6b6046', W: '#8d9288'};
  function launchJet(now) {
    var dir = Math.random() < 0.5 ? 1 : -1;
    jet = {
      x: dir > 0 ? -30 : W + 30, y: H * (0.06 + Math.random() * 0.22),
      vx: dir * (0.55 + Math.random() * 0.35), vy: -(Math.random() * 0.06), dir: dir, emit: 0
    };
    nextJet = now + 20000 + Math.random() * 20000;
  }
  function drawJet() {
    var j = jet;
    // drop a contrail puff every few frames behind each of the two engines
    if (++j.emit % 3 === 0) {
      var tailX = j.dir > 0 ? j.x : j.x + JET[0].length * S;
      trail.push({x: tailX, y: j.y + 4, age: 0}, {x: tailX, y: j.y + 7, age: 0});
    }
    JET.forEach(function (row, ry) {
      for (var i = 0; i < row.length; i++) {
        var ch = row[j.dir > 0 ? i : row.length - 1 - i]; // mirror when flying left
        if (JET_PAL[ch]) {
          x.fillStyle = JET_PAL[ch];
          x.fillRect(Math.round(j.x / S) * S + i * S, Math.round(j.y / S) * S + ry * S, S, S);
        }
      }
    });
    j.x += j.vx; j.y += j.vy;
    if (j.x < -60 || j.x > W + 60) jet = null;
  }
  // contrail puffs widen and fade over ~9s, so the two engine trails merge
  function drawTrail() {
    var keep = [];
    x.fillStyle = '#ffffff';
    for (var i = 0; i < trail.length; i++) {
      var p = trail[i];
      p.age++;
      var life = p.age / 540;
      if (life >= 1) continue;
      keep.push(p);
      var spread = 1 + Math.floor(life * 4); // 1..4 pixels thick
      x.globalAlpha = (1 - life) * 0.85;
      x.fillRect(Math.round(p.x / S) * S, Math.round((p.y - spread) / S) * S, S * 2, S * spread);
    }
    trail = keep;
    x.globalAlpha = 1;
  }

  // ---------- day: a small V of flapping pixel birds ----------
  var BIRD = [['#...#', '.#.#.', '..#..'], ['.....', '##.##', '..#..']]; // wings up / level
  var BQ = 3; // bird pixel size
  function launchFlock(now) {
    var dir = Math.random() < 0.5 ? 1 : -1, n = 3 + (Math.random() * 5 | 0), birds = [];
    for (var i = 0; i < n; i++) {
      var rank = Math.ceil(i / 2), side = i % 2 ? -1 : 1; // leader, then alternate arms of the V
      birds.push({dx: -dir * rank * 22, dy: i ? side * rank * 12 : 0, phase: Math.random() * 6});
    }
    flock = {x: dir > 0 ? -40 : W + 40, y: H * (0.1 + Math.random() * 0.4), vx: dir * (1.1 + Math.random() * 0.6), t: 0, birds: birds};
    nextFlock = now + 12000 + Math.random() * 13000;
  }
  function drawFlock() {
    var f = flock;
    f.t++;
    x.fillStyle = pal.ink;
    x.globalAlpha = 0.75;
    f.birds.forEach(function (b) {
      var shape = BIRD[Math.floor((f.t + b.phase * 10) / 9) % 2];
      var bx = Math.round((f.x + b.dx) / BQ) * BQ;
      var by = Math.round((f.y + b.dy + Math.sin((f.t + b.phase * 20) / 25) * 3) / BQ) * BQ;
      shape.forEach(function (row, ry) {
        for (var i = 0; i < row.length; i++) if (row[i] === '#') x.fillRect(bx + i * BQ, by + ry * BQ, BQ, BQ);
      });
    });
    x.globalAlpha = 1;
    f.x += f.vx;
    if (f.x < -120 || f.x > W + 120) flock = null;
  }

  function size() {
    W = c.width = window.innerWidth; H = c.height = window.innerHeight;
    buildClouds();
    makeStars();
    trail = [];
  }

  function frame(now) {
    now = now || 0;
    var t = now / 1000;
    x.clearRect(0, 0, W, H);
    // back to front: stars, far clouds, jet + contrail, mid clouds, birds, near clouds
    if (night) {
      stars.forEach(function (s) { drawStar(s, reduce ? 1 : t); });
      if (!reduce) {
        if (!shooting && now > nextShot) launch(now);
        if (shooting) drawShooting();
      }
      x.globalAlpha = 1;
    }
    if (showClouds) drawCloudLayer(0);
    if (!night && !reduce) {
      if (!jet && now > nextJet) launchJet(now);
      drawTrail();
      if (jet) drawJet();
    }
    if (showClouds) drawCloudLayer(1);
    if (!night && !reduce) {
      if (!flock && now > nextFlock) launchFlock(now);
      if (flock) drawFlock();
    }
    if (showClouds) drawCloudLayer(2);
    if (!reduce) requestAnimationFrame(frame);
  }

  loadTheme(); size();
  // first events fairly soon after load
  nextShot = 2500 + Math.random() * 4000;
  nextJet = 3000 + Math.random() * 4000;
  nextFlock = 6000 + Math.random() * 6000;
  // phones resize the viewport height as the address bar shows/hides; only
  // regenerate the sky when the width really changes, otherwise just stretch
  window.addEventListener('resize', function () {
    if (window.innerWidth === W) { H = c.height = window.innerHeight; c.width = W; }
    else size();
    if (reduce) frame();
  });
  // theme toggles flip data-theme on <html>: stars at night, jets + birds by day
  new MutationObserver(function () { loadTheme(); buildClouds(); trail = []; jet = null; flock = null; if (reduce) frame(); })
    .observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
  if (reduce) frame(); else requestAnimationFrame(frame);
})();
