/* 纪念页的蓝色 / 粉色花瓣飘落效果。
 * 全屏 canvas 覆盖在内容之上，pointer-events: none，不影响交互与阅读。
 */
(function () {
  "use strict";

  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }

  const canvas = document.createElement("canvas");
  canvas.className = "petals-canvas";
  canvas.setAttribute("aria-hidden", "true");
  document.body.appendChild(canvas);

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const COLORS = [
    ["#8fb6ff", "#d6e4ff"],
    ["#f7a6c4", "#ffd6e6"],
    ["#6f9eef", "#bcd3ff"],
    ["#f28ab2", "#ffc9de"],
  ];
  const COUNT = 34;

  let width = 0;
  let height = 0;
  let dpr = 1;
  let petals = [];

  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  function makePetal(seed) {
    const palette = COLORS[Math.floor(Math.random() * COLORS.length)];
    return {
      x: rand(0, width),
      y: seed ? rand(-height, height) : rand(-height * 0.4, -20),
      size: rand(6, 12),
      speed: rand(34, 72),
      swayAmp: rand(14, 40),
      swayFreq: rand(0.3, 1.1),
      swayPhase: rand(0, Math.PI * 2),
      rotation: rand(0, Math.PI * 2),
      rotationSpeed: rand(-0.6, 0.6),
      colorA: palette[0],
      colorB: palette[1],
      alpha: rand(0.45, 0.9),
    };
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function drawPetal(p) {
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(p.rotation);
    ctx.scale(0.62, 1.35);
    ctx.globalAlpha = p.alpha;
    const gradient = ctx.createLinearGradient(0, -p.size, 0, p.size);
    gradient.addColorStop(0, p.colorB);
    gradient.addColorStop(1, p.colorA);
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(0, -p.size);
    ctx.bezierCurveTo(p.size * 0.9, -p.size * 0.6, p.size * 0.75, p.size * 0.7, 0, p.size);
    ctx.bezierCurveTo(-p.size * 0.75, p.size * 0.7, -p.size * 0.9, -p.size * 0.6, 0, -p.size);
    ctx.fill();
    ctx.restore();
  }

  let last = performance.now();
  let rafId = 0;

  function frame(now) {
    const delta = Math.min((now - last) / 1000, 0.05);
    last = now;
    ctx.clearRect(0, 0, width, height);

    for (const p of petals) {
      p.y += p.speed * delta;
      p.swayPhase += p.swayFreq * delta;
      p.rotation += p.rotationSpeed * delta;
      const x = p.x + Math.sin(p.swayPhase) * p.swayAmp;
      if (p.y - p.size > height + 20) {
        Object.assign(p, makePetal(false));
        p.x = rand(0, width);
      }
      drawPetal({ ...p, x });
    }
    rafId = requestAnimationFrame(frame);
  }

  function start() {
    if (rafId) return;
    last = performance.now();
    rafId = requestAnimationFrame(frame);
  }

  function stop() {
    cancelAnimationFrame(rafId);
    rafId = 0;
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else start();
  });

  window.addEventListener("resize", resize);

  resize();
  petals = Array.from({ length: COUNT }, () => makePetal(true));
  start();
})();
