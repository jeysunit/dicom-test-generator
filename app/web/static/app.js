// 地の切り替えと、値のコピー（docs/spec/12a の 10.2・10.3）。インラインのスクリプトは使わない。
(function () {
  var root = document.documentElement;
  var COPIED_MS = 1200;
  var LOGIN_EXPIRED_MESSAGE = "ログインが切れました。ページを読み込み直して、ログインし直してください";

  // 左のナビの開閉（上の帯の左端のボタン）。閉じたことを覚え、次に開いたページでも閉じておく
  function setNav(open) {
    var shell = document.querySelector(".shell");
    var button = document.getElementById("nav-toggle");
    if (!shell || !button) {
      return;
    }
    shell.classList.toggle("collapsed", !open);
    button.setAttribute("aria-expanded", open ? "true" : "false");
    // 絵と読み上げの名前は替えない。ホバーの title だけ次の操作にする
    button.setAttribute("title", open ? "ナビを閉じる" : "ナビを開く");
  }
  try {
    if (window.localStorage.getItem("dtg-nav") === "closed") {
      setNav(false);
    }
  } catch (error) {
    // 覚えが読めなければ開いたまま
  }

  document.addEventListener("click", function (event) {
    var navToggle = event.target.closest("#nav-toggle");
    if (navToggle) {
      var open = navToggle.getAttribute("aria-expanded") !== "true";
      setNav(open);
      try {
        window.localStorage.setItem("dtg-nav", open ? "open" : "closed");
      } catch (error) {
        // 覚えられなくても、いまのページのナビは変わる
      }
      return;
    }
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
    convertPhonetic(input);
    // 補正した後の値で、欄の誤りの表示を確かめ直す（値の代入では input が起きない）
    checkField(input);
  });

  // 緊急の患者の欄：入力のたびに確かめ、誤りの文を欄（label）の外の直下に 1 行出す。欄は
  // aria-invalid と aria-describedby で結ぶ（欄の下の文は読み上げない。画面の上の知らせだけが
  // 読み上げる）。文は data-message（サーバーと同じ文。app/core/patient_input.py）。ブラウザの
  // 検証の吹き出しは使わない（form は novalidate）。送る前に全部を確かめ、誤りがあれば送らずに
  // 最初の誤りの欄へ移る。漢字の氏名は、文字コードが JIS のときだけ JIS X 0208 の字かどうかを
  // 確かめる（UTF-8 なら制限しない）。範囲は含みすぎてよく、最後の判定はサーバーが行う
  var PATIENT_ID_CHARS = /^[\x20-\x7E]*$/;
  var PATIENT_ID_DELIMITERS = /[\\^~&|]/;
  var ALPHABETIC_CHARS = /^[A-Za-z' ^-]*$/;
  // JIS X 0208 の字を全部含む範囲（含みすぎてよい。サーバーが正確に判定する。正しい氏名を
  // 画面で止めないため、範囲を狭めない）
  var IDEOGRAPHIC_RANGES = [
    [0x20, 0x7e], [0xa0, 0xf7], [0x391, 0x3c9], [0x401, 0x451], [0x2010, 0x23ff],
    [0x2500, 0x266f], [0x3000, 0x303f], [0x3041, 0x3096], [0x309b, 0x309e],
    [0x30a1, 0x30fe], [0x4e00, 0x9fff], [0xff01, 0xff5e], [0xffe0, 0xffe5],
  ];
  function isIdeographic(value) {
    return Array.from(value).every(function (char) {
      var code = char.codePointAt(0);
      return IDEOGRAPHIC_RANGES.some(function (range) {
        return code >= range[0] && code <= range[1];
      });
    });
  }
  function today() {
    var now = new Date();
    var month = ("0" + (now.getMonth() + 1)).slice(-2);
    var day = ("0" + now.getDate()).slice(-2);
    return now.getFullYear() + "-" + month + "-" + day;
  }
  // 生年月日の上限：ブラウザの現地の今日と、画面を開いたときのサーバーの今日（設定のタイム
  // ゾーン。data-today）の遅いほうではなく、進んでいるほうにする。サーバーより先に行きすぎて
  // 止めない（UTC のブラウザで日本の朝に今日生まれを入れても通す）。最後の判定はサーバーが行う
  function latestBirthDate(input) {
    var server = input.getAttribute("data-today") || "";
    var local = today();
    return server > local ? server : local;
  }
  var PHONETIC_CHARS = /^[ァ-ヺ・-ヾ^ ]*$/;
  var HIRAGANA = /[ぁ-ゖゝゞ]/g;
  var HIRAGANA_TO_KATAKANA = 0x60;
  function charsetIsJis(input) {
    var form = input.form;
    var select = form && form.elements.namedItem("charset");
    var value = select ? select.value : "auto";
    if (value === "auto" || value === "") {
      var holder = form && form.querySelector("[data-charset-fallback]");
      value = holder ? holder.getAttribute("data-charset-fallback") : "utf8";
    }
    return value === "jis" || value === "jis_kana";
  }
  function isAcceptable(input, kind, value) {
    var text = value.replace(/\s+/g, " ");
    if (kind === "patient-id") {
      return PATIENT_ID_CHARS.test(value) && !PATIENT_ID_DELIMITERS.test(value);
    }
    if (kind === "alphabetic") {
      return ALPHABETIC_CHARS.test(text);
    }
    if (kind === "ideographic") {
      return !charsetIsJis(input) || isIdeographic(text);
    }
    if (kind === "phonetic") {
      return input.hasAttribute("data-test-mode") || PHONETIC_CHARS.test(text);
    }
    if (kind === "birth-date") {
      return !value || value <= latestBirthDate(input);
    }
    return true;
  }
  function showFieldError(input, message) {
    var line = document.getElementById(input.getAttribute("data-error-line") || "error-" + input.name);
    if (line) {
      // 誤りの行は、印（.ic）と文（.t）。文の置き場が無い行は、行の全体を文にする
      var text = line.querySelector ? line.querySelector(".t") : null;
      (text || line).textContent = message;
      line.hidden = !message;
    }
    if (message) {
      input.setAttribute("aria-invalid", "true");
    } else {
      input.removeAttribute("aria-invalid");
    }
  }
  // 送るのを止めたとき、画面の上に誤りの件数を知らせる（role="alert"。欄の下の文は読み上げない）
  function showErrorSummary(count) {
    var box = document.getElementById("error-summary");
    var notice = box && box.querySelector(".notice");
    var text = notice && notice.querySelector(".t");
    if (!text) {
      return;
    }
    text.textContent = count ? "入力に誤りが " + count + " 件あります。最初の誤りの欄に移ります。" : "";
    notice.hidden = !count;
  }
  function checkField(input) {
    var kind = input.getAttribute("data-check");
    if (!kind) {
      // 確かめの無い欄は、直したらサーバーで断られた誤りを消す
      showFieldError(input, "");
      return true;
    }
    var message = "";
    if (input.required && input.value.trim() === "") {
      message = input.getAttribute("data-required-message") || "";
    } else if (!isAcceptable(input, kind, input.value)) {
      message = input.getAttribute("data-message") || "";
    }
    showFieldError(input, message);
    return !message;
  }
  // かな：ひらがなをカタカナに直し、直したことを欄の下に知らせる（試験の形では直さない）
  function convertPhonetic(input) {
    if (input.getAttribute("data-check") !== "phonetic" || input.hasAttribute("data-test-mode")) {
      return;
    }
    var note = document.getElementById("note-" + input.name);
    var converted = input.value.replace(HIRAGANA, function (char) {
      return String.fromCharCode(char.charCodeAt(0) + HIRAGANA_TO_KATAKANA);
    });
    var changed = converted !== input.value;
    input.value = converted;
    if (note) {
      note.textContent = changed ? input.getAttribute("data-note") || "" : "";
      note.hidden = !changed;
    }
  }
  document.addEventListener("input", function (event) {
    var input = event.target;
    if (input instanceof HTMLInputElement) {
      var note = document.getElementById("note-" + input.name);
      if (note && input.getAttribute("data-check") === "phonetic") {
        note.hidden = true;
      }
      checkField(input);
    }
  });
  document.addEventListener("change", function (event) {
    var input = event.target;
    if (input instanceof HTMLInputElement) {
      checkField(input);
    } else if (input instanceof HTMLSelectElement && input.name === "charset" && input.form) {
      // 文字コードを変えたら、漢字の氏名を確かめ直す
      var name = input.form.elements.namedItem("name_ideographic");
      if (name instanceof HTMLInputElement) {
        checkField(name);
      }
    }
    // 確かめの無い欄（性別・検査名など）は、直したらサーバーで断られた誤りを消す
    if (input instanceof HTMLSelectElement) {
      showFieldError(input, "");
    }
  });
  // 送る前に全部を確かめる。誤りがあれば送らず、最初の誤りの欄へ移る
  document.addEventListener("htmx:beforeRequest", function (event) {
    var form = event.detail.elt;
    if (!(form instanceof HTMLFormElement) || form.id !== "exam-form") {
      return;
    }
    var first = null;
    var failed = 0;
    showErrorSummary(0);
    // 前の応答でサーバーが断った誤りは、送り直す前に消す（確かめの無い欄は、ここでしか消えない）
    Array.prototype.forEach.call(form.elements, function (control) {
      if (control.name && !control.hasAttribute("data-check")) {
        showFieldError(control, "");
      }
    });
    form.querySelectorAll("[data-check]").forEach(function (input) {
      if (input instanceof HTMLInputElement || input instanceof HTMLSelectElement) {
        convertPhonetic(input);
        if (!checkField(input)) {
          failed += 1;
          first = first || input;
        }
      }
    });
    if (first) {
      event.preventDefault();
      showErrorSummary(failed);
      first.focus();
      return;
    }
    // form は novalidate なので、ブラウザの検証は自分で呼ぶ。確かめの無い欄（数の欄）の範囲・
    // 必須・整数を、ほかの欄と同じく欄の外の 1 行に出す（吹き出しは使わない）。日本語の文は
    // 下の invalid が setCustomValidity で付けるので、validationMessage にその文が入る
    var invalids = Array.prototype.filter.call(form.elements, function (control) {
      return control.willValidate && !control.hasAttribute("data-check") && !control.checkValidity();
    });
    if (invalids.length) {
      event.preventDefault();
      invalids.forEach(function (control) {
        showFieldError(control, control.validationMessage);
      });
      showErrorSummary(invalids.length);
      invalids[0].focus();
    }
  });
  // サーバーで断った誤りも、その欄の下に結ぶ
  document.addEventListener("htmx:afterSwap", function (event) {
    var notice = event.target.querySelector
      ? event.target.querySelector("[data-error-field]")
      : null;
    var form = document.getElementById("exam-form");
    var field = notice && form && form.elements.namedItem(notice.getAttribute("data-error-field"));
    if (field && field.name) {
      showFieldError(field, notice.textContent.trim());
      field.focus();
    }
  });

  // 身元不明の患者（docs/spec/12a の 10.5）。「仮の ID を作る」はサーバーに頭と日時の番号を作らせて
  // 患者ID の欄に入れる（同じ秒に2回押しても重ならないよう、番号はサーバーが決める）。
  // 「氏名が分からない」は、設定の漢字・かなの氏名を入れて欄を読むだけにし、英字は空にする
  // （サーバーも同じ値に置き換える）。外すと、入れた値を消して欄を戻す。
  // 撮った後の固定（下の lockEmergency）の間は、どちらも患者の欄に書かない。固定するたびに
  // lockCount を数え、押した後に撮った（固定した）仮の ID の応答は捨てる
  var lockCount = 0;
  var UNKNOWN_NAME_FIELDS = ["name_alphabetic", "name_ideographic", "name_phonetic"];
  function emergencyLocked() {
    var section = document.getElementById("emergency-patient");
    return !!section && section.hasAttribute("data-locked");
  }
  document.addEventListener("click", function (event) {
    var button = event.target instanceof Element ? event.target.closest("[data-temporary-id]") : null;
    var form = button && button.closest("form");
    var field = form && form.elements.namedItem("patient_id");
    if (!button || !(field instanceof HTMLInputElement) || emergencyLocked()) {
      return;
    }
    var pressedAt = lockCount;
    var meta = document.querySelector('meta[name="csrf-token"]');
    button.disabled = true;
    fetch("/exam/temporary-id", {
      method: "POST",
      headers: { "X-CSRF-Token": meta ? meta.getAttribute("content") || "" : "" },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("status " + response.status);
        }
        return response.json();
      })
      .then(function (body) {
        if (pressedAt !== lockCount) {
          return;
        }
        field.value = body.patient_id;
        checkField(field);
        mirrorPatient(form);
        field.focus();
      })
      .catch(function () {
        if (pressedAt === lockCount) {
          showFieldError(field, "仮の ID を作れませんでした。もう一度押してください。");
        }
      })
      .then(function () {
        button.disabled = emergencyLocked();
      });
  });
  document.addEventListener("change", function (event) {
    var box = event.target;
    if (!(box instanceof HTMLInputElement) || !box.hasAttribute("data-unknown-name") || !box.form) {
      return;
    }
    if (emergencyLocked()) {
      box.checked = !box.checked;
      return;
    }
    var values = {
      name_alphabetic: "",
      name_ideographic: box.getAttribute("data-ideographic") || "",
      name_phonetic: box.getAttribute("data-phonetic") || "",
    };
    Object.keys(values).forEach(function (name) {
      var input = box.form.elements.namedItem(name);
      if (input instanceof HTMLInputElement) {
        input.value = box.checked ? values[name] : "";
        input.readOnly = box.checked;
        convertPhonetic(input);
        if (box.checked) {
          checkField(input);
        } else {
          showFieldError(input, "");
        }
      }
    });
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
      (target.id === "results" ||
        target.id === "detail" ||
        target.id === "pick-banner" ||
        target.id.indexOf("echo-") === 0)
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
    notice.className = "notice";
    notice.setAttribute("data-k", "err");
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
  // 枠の中の「接続確認」の結果も、差し替えた枠を開き直して見せる。
  document.addEventListener("htmx:afterSettle", function (event) {
    var config = event.detail.requestConfig;
    if (!config || (config.path !== "/station" && config.path !== "/link/check")) {
      return;
    }
    var band = document.getElementById("band");
    var reopen = config.path === "/link/check" || (band && band.hasAttribute("data-notice"));
    if (band && reopen && typeof band.showPopover === "function" && !band.matches(":popover-open")) {
      band.showPopover();
    }
    if (band && config.path === "/link/check") {
      var result = band.querySelector("#conn-result");
      announceConnResult(result ? result.getAttribute("data-result") : null);
    }
  });
  // 「条件をクリア」（部品集の「検索の帯」）：条件をページの初期の条件（サーバーが描いた
  // 初めの値。予定の日は今日）に戻し、URL の条件の引数も消して、帯の最初の欄に焦点を置く。
  // type="reset" のように、いま開いている URL の値に戻すのではない。取得した一覧は替えない
  document.addEventListener("click", function (event) {
    var clear = event.target.closest("[data-clear-conditions]");
    var form = clear && document.getElementById(clear.getAttribute("data-clear-conditions"));
    if (!form) {
      return;
    }
    form.reset();
    try {
      window.history.replaceState(window.history.state, "", window.location.pathname);
    } catch (error) {
      // 住所を書き換えられなくても、条件は戻っている
    }
    var first = form.querySelector("input:not([type=hidden]), select");
    if (first) {
      first.focus();
    }
  });
  // 手で押した「接続確認」の結果の読み上げ（部品集の 3 つの型）。結果の 1 文は読み上げの欄
  // （#conn-result。popover の中）に入れる。先に空にして、同じ文が続いても読み直されるようにする。
  // 欄は中身ごと差し替わるので、差し替えた後の欄に入れる
  function announceConnResult(text) {
    var result = document.querySelector("#band #conn-result");
    if (!result || !text) {
      return;
    }
    result.textContent = "";
    window.setTimeout(function () {
      result.textContent = text;
    }, 50);
  }
  // 届かない・断られたときは、差し替わらない中身の欄に「確かめられなかった」の型を入れる
  function connCheckFailed(event) {
    var config = event.detail && event.detail.requestConfig;
    if (!config || config.path !== "/link/check") {
      return;
    }
    var result = document.querySelector("#band #conn-result");
    announceConnResult(result ? result.getAttribute("data-unreadable") : null);
  }
  document.addEventListener("htmx:responseError", connCheckFailed);
  document.addEventListener("htmx:sendError", connCheckFailed);
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
    return queue.querySelector(".tbl-wrap");
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
  // 絞り込み・状態の要約・行の選択の要求（data-queue-action）が返る前に再取得が重なると、
  // 古い条件の応答が新しい応答を上書きする。再取得は、その間は出さない。要求を出す側にも
  // hx-sync="#queue:replace" を付け、先に出ていた再取得は取り消す
  function interactionInFlight() {
    return document.querySelector("[data-queue-action].htmx-request") !== null;
  }
  document.addEventListener("htmx:beforeRequest", function (event) {
    if (event.detail.elt.id === "queue" && (resendInFlight() || interactionInFlight())) {
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

  // 撮影の画面の「文字コード（画像）」：JIS（半角カナと漢字）を選んだときだけ注意を出す（10.5）
  document.addEventListener("change", function (event) {
    var select = event.target;
    if (!(select instanceof HTMLSelectElement) || select.id !== "exam-charset") {
      return;
    }
    document.querySelectorAll("[data-charset-warning]").forEach(function (note) {
      note.hidden = note.getAttribute("data-charset-warning").split(" ").indexOf(select.value) < 0;
    });
  });

  // 緊急の患者：入れた値を、操作の行の真上の「撮る患者と送信先」に写す（10.5）
  var SEX_TEXT = { M: "男", F: "女", O: "その他" };
  // 生年月日の括弧の中身（元号の漢字 1 字と年・満年齢）。始まりの日で決め、年 ＝ 西暦の年 − 始まりの年 ＋ 1。
  // 明治（1868/10/23）より前は元号を出さず、年齢だけ。画面を開いた日が基準（app/core/wareki.py と同じ規則）
  var ERAS = [[2019, 5, 1, "令"], [1989, 1, 8, "平"], [1926, 12, 25, "昭"], [1912, 7, 30, "大"], [1868, 10, 23, "明"]];
  function dateParts(iso) {
    var match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
    if (!match) {
      return null;
    }
    var parts = [Number(match[1]), Number(match[2]), Number(match[3])];
    var check = new Date(parts[0], parts[1] - 1, parts[2]);
    var valid = check.getMonth() === parts[1] - 1 && check.getDate() === parts[2];
    return valid ? parts : null;
  }
  function birthParen(iso, todayIso) {
    var born = dateParts(iso);
    var now = dateParts(todayIso);
    if (!born || !now) {
      return "";
    }
    var items = [];
    for (var i = 0; i < ERAS.length; i += 1) {
      var era = ERAS[i];
      var after = born[0] !== era[0] ? born[0] > era[0] : born[1] !== era[1] ? born[1] > era[1] : born[2] >= era[2];
      if (after) {
        items.push(era[3] + (born[0] - era[0] + 1));
        break;
      }
    }
    var age = now[0] - born[0] - (now[1] < born[1] || (now[1] === born[1] && now[2] < born[2]) ? 1 : 0);
    if (age >= 0) {
      items.push(age + "歳");
    }
    return "（" + items.join("・") + "）";
  }
  function mirrorPatient(form) {
    var target = document.getElementById("exam-target");
    if (!target || !form) {
      return;
    }
    target.querySelectorAll("[data-mirror]").forEach(function (cell) {
      var input = form.elements.namedItem(cell.getAttribute("data-mirror"));
      var value = input ? input.value.replace(/\^/g, " ").replace(/\s+/g, " ").trim() : "";
      cell.textContent = value || cell.getAttribute("data-empty");
    });
    var birth = target.querySelector("[data-mirror-birth]");
    if (birth) {
      var date = form.elements.namedItem("birth_date");
      var sex = form.elements.namedItem("sex");
      var sexText = sex ? SEX_TEXT[sex.value] || "" : "";
      if (!date || !date.value) {
        birth.textContent = sexText ? "生年月日なし（" + sexText + "）" : "生年月日なし";
        birth.removeAttribute("title");
        return;
      }
      var paren = birthParen(date.value, date.getAttribute("data-today") || today());
      var day = date.value.replace(/-/g, "/");
      // 西暦と、括弧から後ろ（.unit）の 2 つに分ける。サーバーの描画と同じ形
      var full = paren ? day + paren + sexText : sexText ? day + " " + sexText : day;
      birth.textContent = paren ? day : full;
      if (paren) {
        var unit = document.createElement("span");
        unit.className = "unit";
        unit.textContent = paren + sexText;
        birth.appendChild(unit);
      }
      birth.setAttribute("title", full);
    }
  }
  ["input", "change", "focusout"].forEach(function (type) {
    document.addEventListener(type, function (event) {
      var input = event.target;
      if (input.closest && input.closest("#emergency-patient")) {
        mirrorPatient(input.form);
      }
    });
  });

  // 緊急の患者を撮った後：患者の欄を読むだけにする（前の患者の値のまま次の患者を撮らない）。
  // 「同じ患者でもう一度」で戻し、「次の緊急の患者」は空の欄の画面を開く（10.5）。
  // 撮った後にテンプレート・装置を選び直しても、撮った後の操作の行のままにする（done を送る）
  function examDone() {
    return document.querySelector("#actions [data-same-patient]") !== null;
  }
  // 「仮の ID を作る」「氏名が分からない」も押せなくする（押せると患者ID・氏名が変わり、
  // 「同じ患者でもう一度」で別の患者を撮れる）。戻すとき、「氏名が分からない」が入っていれば
  // 氏名の欄は読むだけのまま残す（撮る前に見せた氏名と、サーバーが置き換える氏名を同じにする）
  function lockEmergency(locked) {
    var section = document.getElementById("emergency-patient");
    if (!section) {
      return;
    }
    if (locked) {
      lockCount += 1;
    }
    var fields = section.querySelectorAll("input, select, button");
    var unknownName = false;
    fields.forEach(function (field) {
      if (field instanceof HTMLInputElement && field.hasAttribute("data-unknown-name")) {
        unknownName = field.checked;
      }
    });
    fields.forEach(function (field) {
      if (field instanceof HTMLSelectElement || field instanceof HTMLButtonElement || field.type === "checkbox") {
        field.disabled = locked;
      } else {
        field.readOnly = locked || (unknownName && UNKNOWN_NAME_FIELDS.indexOf(field.name) !== -1);
      }
    });
    section.toggleAttribute("data-locked", locked);
  }
  document.addEventListener("htmx:afterSettle", function () {
    var section = document.getElementById("emergency-patient");
    if (section && section.hasAttribute("data-locked") !== examDone()) {
      lockEmergency(examDone());
    }
  });
  document.addEventListener("htmx:configRequest", function (event) {
    var config = event.detail;
    var source = config.elt;
    if (
      config.path === "/exam/check" &&
      examDone() &&
      !(source instanceof Element && source.hasAttribute("data-same-patient"))
    ) {
      config.parameters.done = "1";
    }
  });

  // ワークリストの一覧：行のどこを押しても、その行を選ぶ（10.4）。選んだ行は CSS で地と左の
  // 線で示す。選ぶと、操作の行の真上に患者バナーを出し、「選んで撮影へ」を押せるようにする
  document.addEventListener("click", function (event) {
    var row = event.target.closest("#pick tbody tr");
    if (!row || event.target.closest("a, button, input, label")) {
      return;
    }
    var radio = row.querySelector("input[type='radio'][name='key']");
    if (radio && !radio.checked) {
      radio.checked = true;
      radio.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });
})();
