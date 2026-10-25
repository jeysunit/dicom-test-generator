// 地の切り替えと、値のコピー（docs/spec/12a の 10.2・10.3）。インラインのスクリプトは使わない。
(function () {
  var root = document.documentElement;
  var COPIED_MS = 1200;
  var LOGIN_EXPIRED_MESSAGE = "ログインが切れました。ページを読み込み直して、ログインし直してください";

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("#theme-toggle");
    if (toggle) {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        window.localStorage.setItem("dtg-theme", next);
      } catch (error) {
        // 覚えられなくても、いまのページの地は変わる
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

  // ワークリストの一覧：行を選んだら「再検索」を押せるようにする（docs/spec/12a の
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

  // 数の欄の検証の文言：ブラウザの検証の文言は、ブラウザの言語（英語など）で出る。
  // 画面のほかの知らせと同じ日本語にする。欄の名前は data-count-label に置く。
  // 範囲は欄の min・max から読む。値を直したら、次の検証まで文言を消す
  document.addEventListener(
    "invalid",
    function (event) {
      var input = event.target;
      var label = input instanceof HTMLInputElement && input.getAttribute("data-count-label");
      if (!label) {
        return;
      }
      var state = input.validity;
      var message = "";
      if (state.valueMissing || state.badInput) {
        message = label + "を入れてください";
      } else if (state.rangeUnderflow || state.rangeOverflow) {
        message = label + "は " + input.min + "〜" + input.max + " で入れてください";
      } else if (state.stepMismatch) {
        message = label + "は整数で入れてください";
      }
      input.setCustomValidity(message);
    },
    true
  );
  document.addEventListener("input", function (event) {
    var input = event.target;
    if (input instanceof HTMLInputElement && input.hasAttribute("data-count-label")) {
      input.setCustomValidity("");
    }
  });

  // 撮影の画面のルーチン：[外す] で行を撮影の対象から外す。行は消さずに薄く出し、ボタンを
  // [戻す] に替える。[戻す] で外す前の画像数のまま対象に戻る。外した行の欄は押せなくし、
  // 要求に入れない。撮影の対象の最後の1行は外せない（対象の行が無い要求は、サーバーが
  // ルーチンの全部で撮るため。ADR-0025）。1行だけのルーチンは画面が最初から押せない形で出す。
  // 押せないボタンは disabled にせず aria-disabled にする（disabled は Tab で止まらず、
  // 理由がキーボードとタッチに届かない）。理由は aria-describedby で見えない文に結ぶ
  var LAST_SERIES_TITLE = "最後の1行は外せません";
  var LAST_SERIES_NOTE_ID = "last-series-note";
  function isLocked(button) {
    return button.disabled || button.getAttribute("aria-disabled") === "true";
  }
  function unlock(button) {
    button.removeAttribute("aria-disabled");
    button.removeAttribute("aria-describedby");
    button.removeAttribute("title");
  }
  function lockLastSeries(table) {
    var active = table.querySelectorAll("tbody tr:not([data-removed]) [data-remove-series]");
    active.forEach(function (button) {
      if (active.length <= 1) {
        button.setAttribute("aria-disabled", "true");
        button.setAttribute("aria-describedby", LAST_SERIES_NOTE_ID);
        button.title = LAST_SERIES_TITLE;
      } else {
        unlock(button);
      }
    });
  }
  function setRemoved(row, removed) {
    var button = row.querySelector("[data-remove-series]");
    var description = button.getAttribute("data-description");
    row.toggleAttribute("data-removed", removed);
    row.classList.toggle("series-removed", removed);
    row.querySelectorAll("input").forEach(function (input) {
      input.disabled = removed;
    });
    button.textContent = removed ? "戻す" : "外す";
    button.setAttribute("aria-label", description + (removed ? " を戻す" : " を外す"));
    button.disabled = false;
    unlock(button);
  }
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-remove-series]");
    if (!button || isLocked(button)) {
      return;
    }
    var table = button.closest("[data-routine-series]");
    var row = button.closest("tr");
    var removing = !row.hasAttribute("data-removed");
    if (
      removing &&
      table.querySelectorAll("tbody tr:not([data-removed])").length <= 1
    ) {
      return;
    }
    // フォーカスは押したボタン（[外す]・[戻す] が入れ替わる）に残す
    setRemoved(row, removing);
    lockLastSeries(table);
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
    // 描き直せたので、前の失敗の印を外す
    var form = fields.closest("form");
    if (form) {
      form.removeAttribute("data-routine-failed");
    }
  });
  // ルーチンを描き直せなかったとき（断られた・届かなかった）は、選択のそばに知らせる。
  // 選んだルーチンと表の行がずれたまま撮らないように、描き直せるまで撮影の要求を止める
  // （ボタンを押せなくするだけでは、htmx の後処理や撮影のボタンの描き直しで戻るため）
  var ROUTINE_FAILED_MESSAGE =
    "ルーチンを切り替えられませんでした。ページを読み込み直してから、もう一度選んでください";
  function routineFailure(message) {
    var fields = document.getElementById("routine-fields");
    if (!fields) {
      return;
    }
    var notice = fields.querySelector("[data-routine-alert]") || document.createElement("p");
    notice.setAttribute("role", "alert");
    notice.setAttribute("data-routine-alert", "");
    notice.className = "text-danger sm:col-span-3";
    notice.tabIndex = -1;
    notice.textContent = message;
    fields.querySelector("label").after(notice);
    var form = fields.closest("form");
    if (form) {
      form.setAttribute("data-routine-failed", "");
    }
  }
  document.addEventListener("htmx:beforeRequest", function (event) {
    var form = event.detail.elt;
    if (
      form instanceof HTMLFormElement &&
      form.id === "exam-form" &&
      form.hasAttribute("data-routine-failed")
    ) {
      event.preventDefault();
      var fields = document.getElementById("routine-fields");
      var notice = fields && fields.querySelector("[data-routine-alert]");
      if (notice) {
        notice.focus();
      }
    }
  });
  function isRoutineRequest(event) {
    var config = event.detail.requestConfig;
    return config && typeof config.path === "string" && config.path.indexOf("/exam/routine") === 0;
  }
  // 断られた応答（4xx・5xx）でルーチンの欄を差し替えない（差し替えると選択ごと消える）
  document.addEventListener("htmx:beforeSwap", function (event) {
    var xhr = event.detail.xhr;
    if (isRoutineRequest(event) && xhr && xhr.status >= 400) {
      event.detail.shouldSwap = false;
      routineFailure(xhr.status === 401 ? LOGIN_EXPIRED_MESSAGE : ROUTINE_FAILED_MESSAGE);
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
  // 撮影の要求を送ってから応答が返るまでは、ルーチンの欄を触れなくする（#53）。
  // disabled にすると htmx が応答の後に戻し、外した行の欄まで押せる形に戻るので、
  // inert（値は要求に入ったまま、操作だけを止める）を使う。送らなかった要求（止めた
  // 要求）では beforeSend が来ないので、付けたままにならない
  function routineFieldsOf(event) {
    var form = event.detail.elt;
    if (!(form instanceof HTMLFormElement) || form.id !== "exam-form") {
      return null;
    }
    return document.getElementById("routine-fields");
  }
  document.addEventListener("htmx:beforeSend", function (event) {
    var fields = routineFieldsOf(event);
    if (fields) {
      fields.inert = true;
    }
  });
  document.addEventListener("htmx:afterRequest", function (event) {
    var fields = routineFieldsOf(event);
    if (fields) {
      fields.inert = false;
      // 押したボタンは応答まで押せず、フォーカスが本文の先頭へ落ちる。応答の後は、
      // 結果の場所へフォーカスを移し、キーボードの人が位置を見失わないようにする。
      // 結果の知らせは aria-live で読み上げられる。応答を待つ間に別の欄へ移って入力して
      // いるときは、その入力を邪魔しない（フォーカスが本文の先頭か、撮影のボタンの
      // 並びにあるときだけ移す）
      var result = document.getElementById("result");
      var active = document.activeElement;
      var lost = !active || active === document.body || active.closest("#actions") !== null;
      if (result && lost) {
        result.focus();
      }
    }
  });
  function failurePlace(event) {
    var detail = event.detail || {};
    var config = detail.requestConfig || {};
    var source = config.elt || detail.elt || event.target;
    var form = source instanceof HTMLFormElement ? source : source.closest("form");
    var target = detail.target;
    if (target && target.id === "queue") {
      // PACS の画面の再送信：表の上の知らせの場所に出す
      return document.getElementById("queue-notice");
    }
    // 一覧・予約の詳細（行を選んだとき）・接続確認の結果は、差し替える先にそのまま出す
    if (
      target &&
      (target.id === "results" || target.id === "detail" || target.id.indexOf("echo-") === 0)
    ) {
      return target;
    }
    if (form && form.id === "query-form") {
      return document.getElementById("results");
    }
    if (form && form.id === "exam-form") {
      return document.getElementById("result");
    }
    if (target && (target.id === "result" || target.id === "send-result")) {
      return target;
    }
    return form ? document.getElementById("send-result") : null;
  }
  function showFailure(event, message) {
    var place = failurePlace(event);
    if (!place) {
      return;
    }
    var notice = document.createElement("div");
    notice.setAttribute("role", "alert");
    notice.className = "notice notice-error";
    notice.textContent = message;
    place.replaceChildren(notice);
  }
  // 接続の状態（上の帯）の装置の切り替え（ADR-0023）が届かない・断られたときは、選択を
  // 元の装置に戻し、枠に知らせる（表示とサーバーの装置がずれないように）。
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
        xhr.status === 401 ? LOGIN_EXPIRED_MESSAGE :
          "装置を切り替えられませんでした。ページを読み込み直してから、もう一度選んでください"
      );
    }
  });
  // 装置の切り替えが断られたときは、差し替えた枠が閉じたままで理由が見えないので、開き直す。
  document.addEventListener("htmx:afterSettle", function (event) {
    var config = event.detail.requestConfig;
    if (!config || config.path !== "/station") {
      return;
    }
    var band = document.getElementById("band");
    if (band && band.hasAttribute("data-notice") && typeof band.showPopover === "function") {
      band.showPopover();
    }
  });
  document.addEventListener("htmx:beforeSwap", function (event) {
    var xhr = event.detail.xhr;
    if (xhr && xhr.status === 401) {
      event.detail.shouldSwap = false;
      var config = event.detail.requestConfig;
      if (!(config && isStationSelect(config.elt)) && !isRoutineRequest(event)) {
        showFailure(event, LOGIN_EXPIRED_MESSAGE);
      }
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

  // 失敗のまとめての再送信の確認の窓（標準の dialog）。開くボタンと閉じるボタンの印で動かす
  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-dialog-open]");
    if (opener) {
      var dialog = document.getElementById(opener.getAttribute("data-dialog-open"));
      if (dialog && typeof dialog.showModal === "function") {
        dialog.showModal();
      }
      return;
    }
    var closer = event.target.closest("[data-dialog-close]");
    if (closer && closer.closest("dialog")) {
      closer.closest("dialog").close();
    }
  });
  // 2秒ごとに表を差し替えても、フォーカスは同じ役割の要素（data-focus-key）に戻す。
  // 差し替えなかったとき（再送信の応答待ち）は afterSwap が来ず、次の beforeSwap で覚え直す
  var focusedRole = null;
  // 狭い画面で表を横にスクロールしている位置も、差し替えの後に戻す（差し替えると新しい
  // 要素になり、左端に戻って、押そうとしていた右側の [もう一度送る]・[詳細] が動く）
  var queueScroll = 0;
  function queueWrap(queue) {
    return queue.querySelector(".overflow-x-auto");
  }
  function roleOf(element) {
    if (!element || element === document.body) {
      return null;
    }
    // 状態の要約（#queue-sum）は #queue の外にあり、同じ応答で差し替わるので、外も見る
    var keyed = element.closest("[data-focus-key]");
    if (keyed) {
      return { selector: '[data-focus-key="' + keyed.getAttribute("data-focus-key") + '"]', index: 0 };
    }
    return null;
  }
  document.addEventListener("htmx:beforeSwap", function (event) {
    if (event.target.id === "queue") {
      focusedRole = roleOf(document.activeElement);
      var wrap = queueWrap(event.target);
      queueScroll = wrap ? wrap.scrollLeft : 0;
    }
  });
  // 再送信を押してから応答が返るまでは、2秒ごとの差し替えを止める（差し替えると、押せなく
  // したボタンが押せる形で描き直される）。
  // 送信中のボタンは htmx が htmx-request の印を付け、応答の後（表を差し替えて消えたときも）
  // 印は残らない。
  function resendInFlight() {
    // 再送信のボタン（行の [もう一度送る]・詳細の同じボタン・確認の窓の [再送信する]）だけを見る。
    // 絞り込みや行の選択の GET は、自分の応答を止めない
    return document.querySelector("[data-resend].htmx-request, #retry-failed.htmx-request") !== null;
  }
  document.addEventListener("htmx:beforeRequest", function (event) {
    if (event.detail.elt.id === "queue" && resendInFlight()) {
      event.preventDefault();
    }
  });
  // 再送信を押す直前に出ていた再取得（GET）の応答も、再送信の応答が返るまでは差し替えない。
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
    var wrap = queueWrap(event.target);
    if (wrap) {
      wrap.scrollLeft = queueScroll;
    }
    if (focusedRole) {
      var target = document.querySelectorAll(focusedRole.selector)[focusedRole.index];
      if (target) {
        target.focus();
      }
    }
    focusedRole = null;
  });
})();
