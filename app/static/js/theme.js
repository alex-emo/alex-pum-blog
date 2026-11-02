/* 主题三态：auto → light → dark → auto，localStorage 记忆。 */
(function () {
  "use strict";

  var ORDER = ["auto", "light", "dark"];
  var LABEL = { auto: "跟随系统", light: "浅色", dark: "深色" };
  var root = document.documentElement;
  var media = window.matchMedia("(prefers-color-scheme: dark)");
  var button = document.getElementById("theme-toggle");

  function readMode() {
    var mode = root.dataset.themeMode;
    return ORDER.indexOf(mode) >= 0 ? mode : "auto";
  }

  function apply(mode) {
    root.dataset.themeMode = mode;
    root.dataset.theme = mode === "auto" ? (media.matches ? "dark" : "light") : mode;
    if (button) {
      var next = ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length];
      button.setAttribute("aria-label", "切换主题（当前：" + LABEL[mode] + "，点击切换为" + LABEL[next] + "）");
      button.title = "主题：" + LABEL[mode] + "（点击切换为" + LABEL[next] + "）";
    }
  }

  if (button) {
    button.addEventListener("click", function () {
      var mode = ORDER[(ORDER.indexOf(readMode()) + 1) % ORDER.length];
      try {
        localStorage.setItem("theme-mode", mode);
      } catch (e) {
        /* 隐私模式下写不进去，本次会话内仍然生效 */
      }
      apply(mode);
    });
  }

  media.addEventListener("change", function () {
    if (readMode() === "auto") apply("auto");
  });

  apply(readMode());
})();
