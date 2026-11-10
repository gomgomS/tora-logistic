/* ---------------------------------------------------------------------------
 * Default list page behaviour (templates/contacts.html is the reference).
 *
 * Resizable columns:
 *   <table class="app-list" id="xList" data-table-key="contacts">
 *     <th data-key="name" data-width="240">Nama</th>
 *     <th data-col="email" data-width="220">Email</th>   (data-col also works as key)
 *     <th class="app-list-optional">...</th>              (filler, takes the rest)
 *   Drag the right edge of a header to resize, double-click it to reset.
 *   Widths are saved per table in localStorage ("tora.list.<key>.widths").
 *
 * Dropdowns:        <button data-dropdown="menuId">  toggles #menuId
 * Column chooser:   <div id="menuId" data-col-menu-for="xList"> with
 *                   <input type="checkbox" value="<data-col>"> per column and
 *                   an optional <button data-col-reset>; visibility is saved
 *                   in localStorage ("tora.list.<key>.columns").
 * Row selection:    <table data-select-bar="barId">, header checkbox
 *                   [data-check-all], row checkboxes tbody input[name=ids];
 *                   the bar (hidden until something is selected) holds
 *                   [data-select-count].
 * Row click:        <tr data-href="..."> opens the record.
 * ------------------------------------------------------------------------- */
(function () {
    var MIN_WIDTH = 60;
    var FILLER_WIDTH = 40;

    function storageKey(table) {
        return "tora.list." + table.getAttribute("data-table-key") + ".widths";
    }

    function loadWidths(table) {
        try {
            return JSON.parse(localStorage.getItem(storageKey(table))) || {};
        } catch (e) {
            return {};
        }
    }

    function colKey(th) {
        return th.getAttribute("data-key") || th.getAttribute("data-col");
    }

    function heads(table) {
        return table.querySelectorAll("thead th[data-width]");
    }

    function saveWidths(table) {
        var widths = {};
        heads(table).forEach(function (th) {
            widths[colKey(th)] = parseInt(th.style.width, 10);
        });
        try {
            localStorage.setItem(storageKey(table), JSON.stringify(widths));
        } catch (e) {}
    }

    // The table never squeezes columns below their set width: its minimum
    // width is the sum of the visible columns, and the filler column takes
    // whatever space is left in a wide window.
    function refresh(table) {
        var total = FILLER_WIDTH;
        table.querySelectorAll("thead th").forEach(function (th) {
            if (th.classList.contains("app-col-hidden")) {
                return;
            }
            if (th.hasAttribute("data-width")) {
                total = total + parseInt(th.style.width, 10);
            } else if (th.classList.contains("app-list-check")) {
                total = total + 30;
            }
        });
        table.style.minWidth = total + "px";
    }

    function reset(table) {
        heads(table).forEach(function (th) {
            th.style.width = th.getAttribute("data-width") + "px";
        });
        try {
            localStorage.removeItem(storageKey(table));
        } catch (e) {}
        refresh(table);
    }

    function startDrag(e, table, th) {
        e.preventDefault();
        e.stopPropagation();
        var startX = e.clientX;
        var startWidth = th.getBoundingClientRect().width;
        document.body.classList.add("app-col-resizing");
        function move(ev) {
            var width = Math.max(MIN_WIDTH, Math.round(startWidth + ev.clientX - startX));
            th.style.width = width + "px";
            refresh(table);
        }
        function stop() {
            document.removeEventListener("pointermove", move);
            document.removeEventListener("pointerup", stop);
            document.body.classList.remove("app-col-resizing");
            saveWidths(table);
        }
        document.addEventListener("pointermove", move);
        document.addEventListener("pointerup", stop);
    }

    function init(table) {
        var saved = loadWidths(table);
        heads(table).forEach(function (th) {
            var width = parseInt(saved[colKey(th)] || th.getAttribute("data-width"), 10);
            if (!(width >= MIN_WIDTH)) {
                width = parseInt(th.getAttribute("data-width"), 10);
            }
            th.style.width = width + "px";
            var handle = document.createElement("span");
            handle.className = "app-col-resizer";
            handle.setAttribute("aria-hidden", "true");
            handle.title = "Geser untuk ubah lebar, klik dua kali untuk reset";
            handle.addEventListener("pointerdown", function (e) {
                startDrag(e, table, th);
            });
            handle.addEventListener("click", function (e) {
                e.stopPropagation();
            });
            handle.addEventListener("dblclick", function (e) {
                e.stopPropagation();
                th.style.width = th.getAttribute("data-width") + "px";
                refresh(table);
                saveWidths(table);
            });
            th.appendChild(handle);
        });
        table.classList.add("app-list-resizable");
        refresh(table);
    }

    function bindDropdown(toggle) {
        var menu = document.getElementById(toggle.getAttribute("data-dropdown"));
        if (!menu) {
            return;
        }
        function setOpen(open) {
            menu.classList.toggle("app-dropdown-open", open);
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
        }
        toggle.addEventListener("click", function (e) {
            e.stopPropagation();
            setOpen(!menu.classList.contains("app-dropdown-open"));
        });
        menu.addEventListener("click", function (e) {
            e.stopPropagation();
        });
        document.addEventListener("click", function () {
            setOpen(false);
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") {
                setOpen(false);
            }
        });
    }

    function initColumnChooser(menu) {
        var table = document.getElementById(menu.getAttribute("data-col-menu-for"));
        if (!table) {
            return;
        }
        var key = "tora.list." + (table.getAttribute("data-table-key") || table.id) + ".columns";
        var boxes = menu.querySelectorAll("input[type=checkbox]");
        function apply() {
            boxes.forEach(function (box) {
                table.querySelectorAll('[data-col="' + box.value + '"]').forEach(function (cell) {
                    cell.classList.toggle("app-col-hidden", !box.checked);
                });
            });
            if (table.hasAttribute("data-table-key")) {
                refresh(table);
            }
        }
        var saved = null;
        try {
            saved = JSON.parse(localStorage.getItem(key));
        } catch (e) {
            saved = null;
        }
        if (Array.isArray(saved)) {
            boxes.forEach(function (box) {
                box.checked = saved.indexOf(box.value) !== -1;
            });
            apply();
        }
        boxes.forEach(function (box) {
            box.addEventListener("change", function () {
                var visible = [];
                boxes.forEach(function (b) {
                    if (b.checked) {
                        visible.push(b.value);
                    }
                });
                try {
                    localStorage.setItem(key, JSON.stringify(visible));
                } catch (e) {}
                apply();
            });
        });
        var resetBtn = menu.querySelector("[data-col-reset]");
        if (resetBtn) {
            resetBtn.addEventListener("click", function () {
                reset(table);
            });
        }
    }

    function initSelection(table) {
        var bar = document.getElementById(table.getAttribute("data-select-bar"));
        var checkAll = table.querySelector("[data-check-all]");
        var rowBoxes = table.querySelectorAll("tbody input[name=ids]");
        if (!bar || !checkAll) {
            return;
        }
        var countEl = bar.querySelector("[data-select-count]");
        function refreshSelection() {
            var n = 0;
            rowBoxes.forEach(function (box) {
                box.closest("tr").classList.toggle("app-row-selected", box.checked);
                if (box.checked) {
                    n = n + 1;
                }
            });
            if (countEl) {
                countEl.textContent = n;
            }
            bar.hidden = n === 0;
            checkAll.checked = n > 0 && n === rowBoxes.length;
            checkAll.indeterminate = n > 0 && n < rowBoxes.length;
        }
        checkAll.addEventListener("change", function () {
            rowBoxes.forEach(function (box) {
                box.checked = checkAll.checked;
            });
            refreshSelection();
        });
        rowBoxes.forEach(function (box) {
            box.addEventListener("change", refreshSelection);
        });
    }

    function initRowLinks(table) {
        table.querySelectorAll("tbody tr[data-href]").forEach(function (row) {
            row.addEventListener("click", function (e) {
                if (e.target.closest(".app-list-check, a, button, input, label")) {
                    return;
                }
                window.location.href = row.getAttribute("data-href");
            });
        });
    }

    // Form tabs: .app-tabs > .app-tab[data-tab] switch the sibling
    // .app-tab-panel[data-panel] inside the same .app-form-sheet.
    function initTabs(bar) {
        var scope = bar.closest(".app-form-sheet") || document;
        var tabs = bar.querySelectorAll(".app-tab[data-tab]");
        var panels = scope.querySelectorAll(".app-tab-panel[data-panel]");
        tabs.forEach(function (tab) {
            tab.addEventListener("click", function () {
                var name = tab.getAttribute("data-tab");
                tabs.forEach(function (t) {
                    var active = t === tab;
                    t.classList.toggle("app-tab-active", active);
                    t.setAttribute("aria-selected", active ? "true" : "false");
                });
                panels.forEach(function (panel) {
                    panel.hidden = panel.getAttribute("data-panel") !== name;
                });
            });
        });
        // A required field inside a hidden tab: open that tab so the browser
        // can show its validation message.
        scope.addEventListener("invalid", function (e) {
            var panel = e.target.closest(".app-tab-panel[data-panel]");
            if (panel && panel.hidden) {
                var tab = bar.querySelector('.app-tab[data-tab="' + panel.getAttribute("data-panel") + '"]');
                if (tab) {
                    tab.click();
                }
            }
        }, true);
    }

    // Side panel (account-code tree): [data-side-toggle] hides / shows it;
    // the choice is kept per page in localStorage.
    function initSidePanel(layout) {
        var key = "appSide:" + (layout.getAttribute("data-side-layout") || "default");
        try {
            if (localStorage.getItem(key) === "collapsed") {
                layout.classList.add("app-side-collapsed");
            }
        } catch (e) { /* storage blocked: start open */ }
        layout.querySelectorAll("[data-side-toggle]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var collapsed = layout.classList.toggle("app-side-collapsed");
                try {
                    localStorage.setItem(key, collapsed ? "collapsed" : "open");
                } catch (e) { /* ignore */ }
            });
        });
    }

    window.AppList = { init: init, refresh: refresh, reset: reset };

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("table.app-list[data-table-key]").forEach(init);
        document.querySelectorAll("[data-dropdown]").forEach(bindDropdown);
        document.querySelectorAll("[data-col-menu-for]").forEach(initColumnChooser);
        document.querySelectorAll("table[data-select-bar]").forEach(initSelection);
        document.querySelectorAll("table.app-list").forEach(initRowLinks);
        document.querySelectorAll(".app-tabs").forEach(initTabs);
        document.querySelectorAll("[data-side-layout]").forEach(initSidePanel);
    });
})();
