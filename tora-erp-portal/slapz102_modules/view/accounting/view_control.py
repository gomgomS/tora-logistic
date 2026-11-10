import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, request, url_for
from slapz102_stdlib import sanitize
from slapz102_stdlib import paginate

from accounting.accounting_proc import accounting_proc, PAGES, CODE_PREFIX_PATTERN
from accounting.audit_proc import audit_proc, AUDIT_MODELS
from auth.auth_proc import access_required
from view.accounting.view_accounting import base_data

# ---------------------------------------------------------------------------
# KONTROL — view / render layer: Item Jurnal (ledger lines) and Log Catatan
# (audit trail of every accounting record). Both read-only lists.
# ---------------------------------------------------------------------------


def _meta(data, slug):
    data["page"] = PAGES[slug]
    data["slug"] = slug
    return data
# end def

@access_required("accounting", "read")
def html_journal_items():
    params = sanitize.clean_html_dic(request.args.to_dict())
    proc = accounting_proc()
    data = _meta(base_data(), "journal-items")
    # ?prefix=1 / ?prefix=11 from the account-code tree on the left
    data["prefix"] = (params.get("prefix") or "").strip()
    if CODE_PREFIX_PATTERN.match(data["prefix"]) == None:
        data["prefix"] = ""
    # end if
    data["q"] = (params.get("q") or "").strip()
    page, per_page = paginate.read_params(params)
    pager = proc.page_journal_items(data["prefix"], data["q"], page, per_page)
    data["lines"] = pager["lines"]
    data["pager"] = pager
    data["tree"] = proc.journal_item_tree()
    data["page_args"] = {"prefix": data["prefix"], "q": data["q"]}
    return render_template("accounting_journal_items.html", data=data)
# end def

@access_required("accounting", "read")
def html_audit_trail():
    params = sanitize.clean_html_dic(request.args.to_dict())
    data = _meta(base_data(), "audit-trail")
    data["model"] = (params.get("model") or "").strip()
    if data["model"] not in AUDIT_MODELS:
        data["model"] = ""
    # end if
    data["q"] = (params.get("q") or "").strip()
    data["audit_models"] = AUDIT_MODELS
    page, per_page = paginate.read_params(params)
    pager = audit_proc().page_audit(data["model"], data["q"], page, per_page)
    for entry in pager["entries"]:
        record = entry.get("record")
        entry["url"] = ""
        if record != None and all(value not in [None, ""] for value in record["args"].values()):
            entry["url"] = url_for("accounting_blueprint." + record["ep"], **record["args"])
        # end if
    # end for
    data["entries"] = pager["entries"]
    data["pager"] = pager
    data["page_args"] = {"model": data["model"], "q": data["q"]}
    return render_template("accounting_audit_trail.html", data=data)
# end def
