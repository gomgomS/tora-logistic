/* ---------------------------------------------------------------------------
 * Activity log pane (templates/_record_log.html).
 *
 * "Log catatan" opens the composer; "Log" posts the note with fetch so any
 * unsaved edits in the form next to it stay on the page. The server answers
 * with the rendered entry HTML, which is inserted at the top under
 * "Hari Ini". Without JavaScript the form posts normally and redirects back.
 * ------------------------------------------------------------------------- */
(function () {
    function init(pane) {
        var toggle = pane.querySelector("[data-log-toggle]");
        var form = pane.querySelector("[data-log-form]");
        var list = pane.querySelector("[data-log-list]");
        if (!toggle || !form || !list) {
            return;
        }
        var textarea = form.querySelector("textarea");
        var cancel = form.querySelector("[data-log-cancel]");
        var errorEl = form.querySelector("[data-log-error]");
        var submit = form.querySelector("button[type=submit]");

        function open() {
            form.hidden = false;
            toggle.classList.add("log-btn-active");
            textarea.focus();
        }
        function close() {
            form.hidden = true;
            toggle.classList.remove("log-btn-active");
            errorEl.textContent = "";
        }

        toggle.addEventListener("click", function () {
            if (form.hidden) {
                open();
            } else {
                close();
            }
        });
        cancel.addEventListener("click", function () {
            textarea.value = "";
            close();
        });
        textarea.addEventListener("keydown", function (e) {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                form.requestSubmit();
            }
        });

        form.addEventListener("submit", function (e) {
            e.preventDefault();
            if (textarea.value.trim() === "") {
                errorEl.textContent = "Catatan tidak boleh kosong";
                return;
            }
            submit.disabled = true;
            errorEl.textContent = "";
            fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: { "X-Requested-With": "fetch" },
                credentials: "same-origin"
            }).then(function (res) {
                return res.json();
            }).then(function (payload) {
                if (payload.status !== "SUCCESS") {
                    errorEl.textContent = payload.desc || "Catatan gagal disimpan";
                    return;
                }
                var first = list.firstElementChild;
                var hasToday = first && first.classList.contains("log-day") && first.textContent.trim() === "Hari Ini";
                var holder = document.createElement("div");
                holder.innerHTML = payload.html;
                var entry = holder.firstElementChild;
                if (hasToday) {
                    first.insertAdjacentElement("afterend", entry);
                } else {
                    var day = document.createElement("div");
                    day.className = "log-day";
                    day.innerHTML = "<span>Hari Ini</span>";
                    list.insertBefore(entry, list.firstChild);
                    list.insertBefore(day, entry);
                }
                textarea.value = "";
                close();
            }).catch(function () {
                errorEl.textContent = "Koneksi gagal, coba lagi";
            }).then(function () {
                submit.disabled = false;
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-log-pane]").forEach(init);
    });
})();
