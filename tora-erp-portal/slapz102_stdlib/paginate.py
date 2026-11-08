# ---------------------------------------------------------------------------
# Server-side pagination helpers (pure functions: no Flask, no database).
#
#   view:  page, per_page = paginate.read_params(params)
#   proc:  total = coll.count_documents(query)
#          pager = paginate.build(total, page, per_page)
#          recs = coll.find(query, projection).sort(sort).skip(pager["offset"]).limit(pager["per_page"])
#
# Template: templates/_pagination.html renders pager_compact / pager_bar.
# ---------------------------------------------------------------------------

PAGE_SIZES = [20, 40, 80, 200]
DEFAULT_PAGE_SIZE = 80

def _to_int(value, fallback):
    try:
        return int(value)
    except Exception:
        return fallback
    # end try
# end def

def read_params(params):
    # Only whitelisted page sizes are accepted, so a request can never ask
    # MongoDB for an unbounded page.
    page = _to_int(params.get("page"), 1)
    if page < 1:
        page = 1
    # end if
    per_page = _to_int(params.get("per_page"), DEFAULT_PAGE_SIZE)
    if per_page not in PAGE_SIZES:
        per_page = DEFAULT_PAGE_SIZE
    # end if
    return page, per_page
# end def

def _window(page, pages, radius=2):
    # Page numbers around the current page, with None for a gap:
    # [1, None, 4, 5, 6, 7, 8, None, 20]
    out = []
    low = max(2, page - radius)
    high = min(pages - 1, page + radius)
    out.append(1)
    if low > 2:
        out.append(None)
    # end if
    for number in range(low, high + 1):
        out.append(number)
    # end for
    if high < pages - 1:
        out.append(None)
    # end if
    if pages > 1:
        out.append(pages)
    # end if
    return out
# end def

def build(total, page, per_page):
    if per_page not in PAGE_SIZES:
        per_page = DEFAULT_PAGE_SIZE
    # end if
    pages = max(1, (total + per_page - 1) // per_page)
    if page < 1:
        page = 1
    # end if
    if page > pages:
        page = pages
    # end if
    offset = (page - 1) * per_page
    start = 0
    end = 0
    if total > 0:
        start = offset + 1
        end = min(offset + per_page, total)
    # end if
    return {
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": per_page,
        "default_per_page": DEFAULT_PAGE_SIZE,
        "page_sizes": PAGE_SIZES,
        "offset": offset,
        "start": start,
        "end": end,
        "has_prev": page > 1,
        "has_next": page < pages,
        "window": _window(page, pages)
    }
# end def
