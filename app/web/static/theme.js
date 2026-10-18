// 地（明るい地・暗い地）を、描く前に決める（spec/12 の 10.2）。覚えが無ければ明るい地。
(function () {
  var theme = "light";
  try {
    if (window.localStorage.getItem("dtg-theme") === "dark") {
      theme = "dark";
    }
  } catch (error) {
    theme = "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
