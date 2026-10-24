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

  // 撮影の画面のルーチン：[外す] でシリーズの行を外す。最後の1行は外せない
  // （行が無い要求は、サーバーがルーチンの全部で撮るため。ADR-0025）。1行だけのルーチンは
  // 画面が最初から押せない形で出す
  var LAST_SERIES_TITLE = "最後の1行は外せません";
  function lockLastSeries(table) {
    var buttons = table.querySelectorAll("[data-remove-series]");
    buttons.forEach(function (button) {
      button.disabled = buttons.length <= 1;
      if (button.disabled) {
        button.title = LAST_SERIES_TITLE;
      } else {
        button.removeAttribute("title");
      }
    });
  }
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-remove-series]");
    if (!button) {
      return;
    }
    var table = button.closest("[data-routine-series]");
    var rows = table ? table.querySelectorAll("tbody tr") : [];
    if (rows.length <= 1) {
      return;
    }
    // 外した後は、次の行（無ければ前の行）の [外す] にフォーカスを移す
    var row = button.closest("tr");
    var next = row.nextElementSibling || row.previousElementSibling;
    row.remove();
    lockLastSeries(table);
    var focus = next && next.querySelector("[data-remove-series]");
    if (focus && !focus.disabled) {
      focus.focus();
    } else if (next) {
      next.querySelector("[name='routine_images']").focus();
    }
  });
  // テンプレートを変えたら、ルーチンをそのテンプレートで当て直して描き直す（ルーチンの名前を
  // 送らない）。テンプレートの確かめ直し（/exam/check）とは別の要求にする
  document.addEventListener("change", function (event) {
    var select = event.target;
    var fields = document.getElementById("routine-fields");
    if (!(select instanceof HTMLSelectElement) || select.id !== "exam-template" || !fields) {
      return;
    }
    var key = select.form && select.form.elements.namedItem("key");
    htmx.ajax("GET", "/exam/routine", {
      source: fields,
      target: fields,
      swap: "outerHTML",
      values: { template: select.value, key: key ? key.value : "" },
    });
  });
  // ルーチンを選び直して描き直した後は、ルーチンの選択にフォーカスを戻す
  var routineFocused = false;
  document.addEventListener("htmx:beforeSwap", function (event) {
    if (event.target.id === "routine-fields") {
      routineFocused = document.activeElement && document.activeElement.name === "routine";
    }
  });
  document.addEventListener("htmx:afterSettle", function (event) {
    var fields = document.getElementById("routine-fields");
    if (!fields || !(event.target === fields || fields.contains(event.target))) {
      return;
    }
    var table = fields.querySelector("[data-routine-series]");
    if (table) {
      lockLastSeries(table);
    }
    if (routineFocused) {
      fields.querySelector("[name='routine']").focus();
      routineFocused = false;
    }
  });
  // ルーチンを描き直せなかったとき（断られた・届かなかった）は、選択のそばに知らせる。
  // 描き直せないまま撮らないように、撮影のボタンも押せなくする
  function routineFailure(message) {
    var fields = document.getElementById("routine-fields");
    if (!fields) {
      return;
    }
    var notice = fields.querySelector("[data-routine-alert]") || document.createElement("p");
    notice.setAttribute("role", "alert");
    notice.setAttribute("data-routine-alert", "");
    notice.className = "text-danger sm:col-span-3";
    notice.textContent = message;
    fields.querySelector("label").after(notice);
    document.querySelectorAll("#actions button").forEach(function (button) {
      button.disabled = true;
    });
  }
  function isRoutineRequest(event) {
    var config = event.detail.requestConfig;
    return config && typeof config.path === "string" && config.path.indexOf("/exam/routine") === 0;
  }
  document.addEventListener("htmx:responseError", function (event) {
    if (isRoutineRequest(event)) {
      routineFailure("ルーチンを切り替えられませんでした。頁を読み込み直してから、もう一度選んでください");
    }
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
  // 情報バーの装置の切り替え（ADR-0023）が届かない・断られたときは、選択を元の装置に
  // 戻し、帯に知らせる（表示とサーバーの装置がずれないように）。
  function isStationSelect(element) {
    return element instanceof HTMLSelectElement && element.closest("#band") !== null;
  }
  function stationFailure(select, message) {
    Array.prototype.forEach.call(select.options, function (option) {
      option.selected = option.defaultSelected;
    });
    var band = select.closest("#band");
    var notice = band.querySelector("[data-station-alert]") || document.createElement("span");
    notice.setAttribute("role", "alert");
    notice.setAttribute("data-station-alert", "");
    notice.className = "text-danger";
    notice.textContent = message;
    select.closest("label").after(notice);
  }
  document.addEventListener("htmx:beforeSwap", function (event) {
    // 差し替えの知らせは差し替える先で出るので、要求を出した要素は requestConfig から取る
    var config = event.detail.requestConfig;
    var xhr = event.detail.xhr;
    if (config && isStationSelect(config.elt) && xhr && xhr.status >= 400) {
      event.detail.shouldSwap = false;
      stationFailure(
        config.elt,
        "装置を切り替えられませんでした。頁を読み込み直してから、もう一度選んでください"
      );
    }
  });
  document.addEventListener("htmx:sendError", function (event) {
    var message = "サーバーに届きませんでした。接続を確かめてから、もう一度押してください";
    if (isStationSelect(event.detail.elt)) {
      stationFailure(event.detail.elt, message);
      return;
    }
    if (isRoutineRequest(event)) {
      routineFailure(message);
      return;
    }
    showFailure(event, message);
  });

  // PACS の送信ジョブの「詳細」は、押したボタンのそばに浮かぶ枠（popover）に出す。
  // 枠は最上位の層に出るので、表の列の幅は変わらない。枠は操作の欄の左に出し、どの行の
  // 「詳細」「再送」も覆わない。左に収まらない狭い画面では、ボタンの下に出す。
  // popover に対応しないブラウザでは、枠はセルの中にそのまま出る（下の処理は動かさない）
  var SUPPORTS_POPOVER = typeof HTMLElement.prototype.showPopover === "function";
  var DETAIL_GAP = 4;
  var PAGE_GUTTER = 16; // 画面の端から離す幅（ページの左右の余白と同じ。10.2）
  function detailButton(popover) {
    return document.querySelector('[popovertarget="' + popover.id + '"]');
  }
  function placeDetail(popover) {
    var button = detailButton(popover);
    if (!button) {
      return;
    }
    var rect = button.getBoundingClientRect();
    // 左に出すときは、同じ行の「再送」も覆わないように、ボタンのある欄の左に出す
    var cell = (button.closest("td") || button).getBoundingClientRect();
    var vw = window.innerWidth;
    popover.style.left = "";
    popover.style.top = rect.top + "px";
    popover.style.right = vw - cell.left + DETAIL_GAP + "px";
    // 大きさを測って直す：画面の左右にはみ出せば、ボタンの下に左の余白から広げて出す。
    // 下にはみ出せば上へ寄せる。開く前（beforetoggle）は大きさを測れないので、開いた後の
    // 最初の描画の前（requestAnimationFrame）に測る。開いているときはその場で測る
    function fit() {
      var box = popover.getBoundingClientRect();
      var top = rect.top;
      if (box.left < PAGE_GUTTER || box.right > vw - PAGE_GUTTER) {
        top = rect.bottom + DETAIL_GAP;
        popover.style.left = PAGE_GUTTER + "px";
        popover.style.right = Math.min(Math.max(vw - rect.right, PAGE_GUTTER), vw / 2) + "px";
        box = popover.getBoundingClientRect();
      }
      if (top + box.height > window.innerHeight - PAGE_GUTTER) {
        top = Math.max(window.innerHeight - PAGE_GUTTER - box.height, PAGE_GUTTER);
      }
      popover.style.top = top + "px";
    }
    if (popover.matches(":popover-open")) {
      fit();
    } else {
      window.requestAnimationFrame(fit);
    }
  }
  function openDetail() {
    return SUPPORTS_POPOVER ? document.querySelector("#queue .job-detail:popover-open") : null;
  }
  document.addEventListener(
    "beforetoggle",
    function (event) {
      if (event.newState === "open" && event.target.classList.contains("job-detail")) {
        placeDetail(event.target);
      }
    },
    true
  );
  // Esc で閉じたときは、その行の「詳細」へフォーカスを戻す（開き直した枠には戻り先が無い）
  document.addEventListener(
    "toggle",
    function (event) {
      var popover = event.target;
      // 差し替えで外された枠の知らせは、新しい枠を開き直した後に届くので見ない
      if (
        event.newState !== "closed" ||
        !popover.classList.contains("job-detail") ||
        !popover.isConnected
      ) {
        return;
      }
      var active = document.activeElement;
      var button = detailButton(popover);
      if (button && (active === document.body || popover.contains(active))) {
        button.focus();
      }
    },
    true
  );
  ["scroll", "resize"].forEach(function (name) {
    window.addEventListener(
      name,
      function () {
        var popover = openDetail();
        if (popover) {
          placeDetail(popover);
        }
      },
      true
    );
  });
  // 2秒ごとに表を差し替えても、開いた枠は開いたままにし、フォーカスも同じ役割の要素に
  // 戻す。差し替えと開き直しは同じ描画の前に終わるので、閉じた枠は描かれない。
  // 差し替えなかったとき（再送の応答待ち）は afterSwap が来ず、次の beforeSwap で覚え直す
  var openJob = null;
  var focusedRole = null;
  function roleOf(element, queue) {
    if (!element || !queue.contains(element)) {
      return null;
    }
    var popover = element.closest(".job-detail");
    if (popover) {
      return {
        selector: "#" + popover.id + " button",
        index: Array.prototype.indexOf.call(popover.querySelectorAll("button"), element),
      };
    }
    if (element.hasAttribute("popovertarget")) {
      return {
        selector: '[popovertarget="' + element.getAttribute("popovertarget") + '"]',
        index: 0,
      };
    }
    return null;
  }
  document.addEventListener("htmx:beforeSwap", function (event) {
    if (event.target.id === "queue") {
      var popover = openDetail();
      openJob = popover ? popover.id : null;
      focusedRole = roleOf(document.activeElement, event.target);
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
    if (event.target.id !== "queue") {
      return;
    }
    var popover = openJob ? document.getElementById(openJob) : null;
    if (popover && !popover.matches(":popover-open")) {
      popover.showPopover();
    }
    if (focusedRole) {
      var target = event.target.querySelectorAll(focusedRole.selector)[focusedRole.index];
      if (target) {
        target.focus();
      }
    }
    openJob = null;
    focusedRole = null;
  });
  // htmx は差し替えの後の落ち着かせ（settle）で、同じ id の要素の style を新しい要素の値
  // （無し）に戻すので、開いている枠の位置はその後に決め直す
  document.addEventListener("htmx:afterSettle", function (event) {
    var popover = event.target.id === "queue" ? openDetail() : null;
    if (popover) {
      placeDetail(popover);
    }
  });
})();
