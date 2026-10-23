// 地の切り替えと、値のコピー（docs/spec/12a の 10.2・10.3）。インラインのスクリプトは使わない。
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

  // 氏名の欄：カーソルが離れたら空白を ^ にする（docs/spec/12a の 10.5）。補助で、
  // サーバーの側でも同じ置き換えをする（app/core/person_name.py）。
  // JavaScript の \s は全角の空白（U+3000）も含む。
  document.addEventListener("focusout", function (event) {
    var input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.hasAttribute("data-person-name")) {
      return;
    }
    input.value = input.value.trim().replace(/\s*\^\s*/g, "^").replace(/\s+/g, "^");
  });

  // ワークリストの一覧：行を選んだら「取得し直す」を押せるようにする（docs/spec/12a の
  // 10.4）。行を選ばずに届いた要求は、サーバーの側でも問い合わせずに断る。
  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!(input instanceof HTMLInputElement) || input.name !== "key" || !input.form) {
      return;
    }
    input.form.querySelectorAll("button[data-needs-selection]").forEach(function (button) {
      button.disabled = false;
      button.removeAttribute("title");
    });
  });

  // 撮影の画面：シリーズ数を変えたら、枚数をシリーズごとに同じ数で埋める（CLI の
  // `-i` を省いたときと同じ）。枚数を手で直した後は上書きしない。
  var MAX_SERIES = 99;
  document.addEventListener("input", function (event) {
    var input = event.target;
    if (!(input instanceof HTMLInputElement)) {
      return;
    }
    var form = input.form;
    if (input.hasAttribute("data-images-list")) {
      input.setAttribute("data-edited", "");
      return;
    }
    var images = form && form.elements.namedItem("images");
    if (!images || !input.hasAttribute("data-series-count")) {
      return;
    }
    var count = parseInt(input.value, 10);
    if (images.hasAttribute("data-edited") || !(count >= 1 && count <= MAX_SERIES)) {
      return;
    }
    var each = parseInt(images.value.split(",")[0], 10);
    images.value = new Array(count).fill(each >= 1 ? each : 1).join(",");
  });

  // 撮影・送信：押したボタンで途中の文言を選び、新しい要求の前に前の結果を消す。
  // 応答が返らなかったとき（通信の失敗）は、結果の場所に知らせる。
  document.addEventListener("click", function (event) {
    var button = event.target.closest("form button[name='action']");
    if (button) {
      button.form.setAttribute("data-action", button.value);
    }
  });
  document.addEventListener("htmx:beforeRequest", function (event) {
    var form = event.target;
    if (form instanceof HTMLFormElement && form.id === "exam-form") {
      var result = document.getElementById("result");
      if (result) {
        result.replaceChildren();
      }
    }
  });
  function showFailure(event, message) {
    var form = event.target;
    var target = event.detail && event.detail.target;
    var place;
    if (target && target.id === "queue") {
      // PACS の画面の再送：表の上の知らせの場所に出す
      place = document.getElementById("queue-notice");
    } else {
      place =
        form instanceof HTMLFormElement &&
        document.getElementById(form.id === "exam-form" ? "result" : "send-result");
    }
    if (!place) {
      return;
    }
    var notice = document.createElement("div");
    notice.setAttribute("role", "alert");
    notice.className = "notice notice-error";
    notice.textContent = message;
    place.replaceChildren(notice);
  }
  document.addEventListener("htmx:sendError", function (event) {
    showFailure(event, "サーバーに届きませんでした。接続を確かめてから、もう一度押してください");
  });

  // PACS の送信ジョブ：2秒ごとに表を差し替えても、開いた「詳細」は開いたままにする。
  var openJobs = [];
  document.addEventListener("htmx:beforeSwap", function (event) {
    if (event.target.id === "queue") {
      openJobs = Array.prototype.map.call(
        event.target.querySelectorAll("details[open][data-job]"),
        function (details) {
          return details.getAttribute("data-job");
        }
      );
    }
  });
  // 再送を押してから応答が返るまでは、2秒ごとの差し替えを止める（差し替えると、押せなく
  // したボタンが押せる形で描き直される）。
  // 送信中のボタンは htmx が htmx-request の印を付け、応答の後（表を差し替えて消えたときも）
  // 印は残らない。
  function resendInFlight() {
    return document.querySelector('[hx-target="#queue"].htmx-request') !== null;
  }
  document.addEventListener("htmx:beforeRequest", function (event) {
    if (event.detail.elt.id === "queue" && resendInFlight()) {
      event.preventDefault();
    }
  });
  // 再送を押す直前に出ていた再取得（GET）の応答も、再送の応答が返るまでは差し替えない。
  // 差し替えの知らせは差し替える先（#queue）で出るので、再取得かは要求の動詞で見分ける
  document.addEventListener("htmx:beforeSwap", function (event) {
    var config = event.detail.requestConfig;
    if (event.target.id === "queue" && config && config.verb === "get" && resendInFlight()) {
      event.detail.shouldSwap = false;
    }
  });
  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.target.id === "queue") {
      openJobs.forEach(function (job) {
        var details = event.target.querySelector('details[data-job="' + job + '"]');
        if (details) {
          details.setAttribute("open", "");
        }
      });
    }
  });
})();
