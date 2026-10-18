// 地の切り替えと、値のコピー（spec/12 の 10.2・10.3）。インラインのスクリプトは使わない。
(function () {
  var root = document.documentElement;
  var COPIED_MS = 1200;

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("#theme-toggle");
    if (toggle) {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        window.localStorage.setItem("dtg-theme", next);
      } catch (error) {
        // 覚えられなくても、いまの頁の地は変わる
      }
      return;
    }
    var copy = event.target.closest("[data-copy]");
    if (copy && navigator.clipboard) {
      navigator.clipboard.writeText(copy.getAttribute("data-copy")).then(function () {
        copy.classList.add("copied");
        window.setTimeout(function () {
          copy.classList.remove("copied");
        }, COPIED_MS);
      });
    }
  });
})();
