/* ---------------------------------------------------------------------------
 * Relation picker (templates/_combobox.html) for detail pages.
 *
 *   <script type="application/json" id="accountOptions">[{value, label, description}]</script>
 *   <div data-combo data-combo-source="accountOptions">
 *       <input data-combo-input> <input type="hidden" data-combo-value>
 *   </div>
 *
 * Focus opens the first 8 options (label + muted description), typing
 * filters on label and description, "Cari lebih..." shows every match.
 * Leaving without picking restores the last chosen value. Listeners are
 * delegated on document, so rows cloned from a <template> need no setup.
 * The menu is attached to <body> with position: fixed so scrolling tables
 * do not clip it.
 *
 * Big collections (contacts): data-combo-url="/api/contacts?category=CLIENT"
 * instead of data-combo-source. The picker calls it with &q=<typed text>
 * and reads {results: [{value|id, label|name, description}]}.
 * ------------------------------------------------------------------------- */
(function () {
    var LIMIT = 8;
    var sources = {};
    var menu = null;
    var state = null;
    var remoteTimer = null;

    function remote(box, q) {
        var url = box.getAttribute("data-combo-url");
        var token = {};
        state.token = token;
        fetch(url + (url.indexOf("?") === -1 ? "?" : "&") + "q=" + encodeURIComponent(q || ""), { credentials: "same-origin" })
            .then(function (res) { return res.json(); })
            .then(function (payload) {
                if (!state || state.token !== token) {
                    return;
                }
                state.remote = (payload.results || payload || []).map(function (o) {
                    return { value: o.value || o.id, label: o.label || o.name || o.text || "", description: o.description || "" };
                });
                render();
            })
            .catch(function () {
                if (state && state.token === token) {
                    state.remote = [];
                    render();
                }
            });
    }

    function options(box) {
        var id = box.getAttribute("data-combo-source");
        if (!(id in sources)) {
            var el = document.getElementById(id);
            try {
                sources[id] = el ? JSON.parse(el.textContent) : [];
            } catch (e) {
                sources[id] = [];
            }
        }
        return sources[id];
    }

    function matches(box, q) {
        var all = options(box);
        q = (q || "").trim().toLowerCase();
        if (q === "") {
            return all;
        }
        return all.filter(function (o) {
            return o.label.toLowerCase().indexOf(q) !== -1 || (o.description || "").toLowerCase().indexOf(q) !== -1;
        });
    }

    function ensureMenu() {
        if (menu) {
            return menu;
        }
        menu = document.createElement("div");
        menu.className = "app-combo-menu";
        menu.setAttribute("role", "listbox");
        menu.hidden = true;
        document.body.appendChild(menu);
        // Keep focus in the input while clicking the menu.
        menu.addEventListener("mousedown", function (e) {
            e.preventDefault();
        });
        menu.addEventListener("click", function (e) {
            var item = e.target.closest("[data-combo-index]");
            if (item) {
                choose(parseInt(item.getAttribute("data-combo-index"), 10));
                return;
            }
            if (e.target.closest("[data-combo-more]") && state) {
                state.showAll = true;
                render();
            }
        });
        return menu;
    }

    function position() {
        if (!state) {
            return;
        }
        var rect = state.input.getBoundingClientRect();
        menu.style.minWidth = Math.max(rect.width, 300) + "px";
        menu.style.left = Math.max(4, Math.min(rect.left, window.innerWidth - menu.offsetWidth - 4)) + "px";
        var top = rect.bottom + 2;
        if (top + menu.offsetHeight > window.innerHeight && rect.top > menu.offsetHeight + 4) {
            top = rect.top - menu.offsetHeight - 2;
        }
        menu.style.top = top + "px";
    }

    function render() {
        var list = state.remote !== undefined ? (state.remote || []) : matches(state.box, state.typed ? state.input.value : "");
        var shown = state.showAll ? list : list.slice(0, LIMIT);
        state.items = shown;
        if (state.index >= shown.length) {
            state.index = shown.length - 1;
        }
        menu.innerHTML = "";
        if (shown.length === 0) {
            var empty = document.createElement("div");
            empty.className = "app-combo-empty";
            empty.textContent = state.remote === null ? "Mencari ..." : "Tidak ada yang cocok";
            menu.appendChild(empty);
        }
        shown.forEach(function (o, i) {
            var item = document.createElement("div");
            item.className = "app-combo-item";
            if (i === state.index) {
                item.className = item.className + " app-combo-item-active";
            }
            if (o.value === state.hidden.value) {
                item.className = item.className + " app-combo-item-selected";
            }
            item.setAttribute("role", "option");
            item.setAttribute("data-combo-index", String(i));
            var label = document.createElement("div");
            label.className = "app-combo-label";
            label.textContent = o.label;
            item.appendChild(label);
            if (o.description) {
                var desc = document.createElement("div");
                desc.className = "app-combo-desc";
                desc.textContent = o.description;
                item.appendChild(desc);
            }
            menu.appendChild(item);
        });
        if (!state.showAll && list.length > LIMIT) {
            var more = document.createElement("div");
            more.className = "app-combo-more";
            more.setAttribute("data-combo-more", "");
            more.textContent = "Cari lebih...";
            menu.appendChild(more);
        }
        menu.hidden = false;
        state.input.setAttribute("aria-expanded", "true");
        position();
        var activeItem = menu.querySelector(".app-combo-item-active");
        if (activeItem) {
            activeItem.scrollIntoView({ block: "nearest" });
        }
    }

    function open(box) {
        var input = box.querySelector("[data-combo-input]");
        var hidden = box.querySelector("[data-combo-value]");
        if (input.disabled || input.readOnly) {
            return;
        }
        if (!box.hasAttribute("data-combo-label")) {
            box.setAttribute("data-combo-label", input.value);
        }
        ensureMenu();
        state = { box: box, input: input, hidden: hidden, items: [], index: 0, showAll: false, typed: false };
        input.select();
        if (box.hasAttribute("data-combo-url")) {
            state.remote = null;
            render();
            remote(box, "");
            return;
        }
        var all = options(box);
        for (var i = 0; i < all.length && i < LIMIT; i++) {
            if (all[i].value === hidden.value) {
                state.index = i;
            }
        }
        render();
    }

    function close(restore) {
        if (!state) {
            return;
        }
        if (restore) {
            state.input.value = state.box.getAttribute("data-combo-label") || "";
        }
        state.input.setAttribute("aria-expanded", "false");
        menu.hidden = true;
        state = null;
    }

    function choose(i) {
        var o = state && state.items[i];
        if (!o) {
            return;
        }
        var box = state.box;
        close(false);
        window.appCombo.set(box, o.value, o.label);
    }

    // Set a picker from page code (e.g. picking a document fills Pelanggan).
    // Fires "change" on the hidden input when the value changed.
    window.appCombo = {
        set: function (box, value, label) {
            var hidden = box.querySelector("[data-combo-value]");
            var input = box.querySelector("[data-combo-input]");
            var changed = hidden.value !== value;
            hidden.value = value;
            input.value = label;
            input.title = label;
            box.setAttribute("data-combo-label", label);
            if (changed) {
                hidden.dispatchEvent(new Event("change", { bubbles: true }));
            }
        },
        options: options
    };

    function boxOf(target) {
        return target && target.closest ? target.closest("[data-combo]") : null;
    }

    document.addEventListener("focusin", function (e) {
        if (e.target.matches && e.target.matches("[data-combo-input]")) {
            open(boxOf(e.target));
        }
    });

    document.addEventListener("focusout", function (e) {
        if (state && e.target === state.input) {
            close(true);
        }
    });

    document.addEventListener("input", function (e) {
        if (state && e.target === state.input) {
            state.typed = true;
            state.index = 0;
            state.showAll = false;
            if (state.box.hasAttribute("data-combo-url")) {
                var box = state.box;
                var q = state.input.value;
                clearTimeout(remoteTimer);
                remoteTimer = setTimeout(function () {
                    if (state && state.box === box) {
                        remote(box, q);
                    }
                }, 200);
                return;
            }
            render();
        }
    });

    document.addEventListener("keydown", function (e) {
        if (!state || e.target !== state.input) {
            return;
        }
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            var step = e.key === "ArrowDown" ? 1 : -1;
            state.index = Math.max(0, Math.min(state.items.length - 1, state.index + step));
            render();
        } else if (e.key === "Enter") {
            e.preventDefault();
            choose(state.index);
        } else if (e.key === "Escape") {
            e.preventDefault();
            close(true);
        } else if (e.key === "Tab") {
            if (state.typed && state.items.length > 0) {
                choose(state.index);
            } else {
                close(true);
            }
        }
    });

    window.addEventListener("scroll", function (e) {
        if (state && e.target !== menu) {
            position();
        }
    }, true);

    window.addEventListener("resize", function () {
        close(true);
    });
})();
