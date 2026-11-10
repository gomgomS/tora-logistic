import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from flask import render_template, redirect, request, url_for
from flask_login import current_user
from slapz102_stdlib import csrf
from slapz102_stdlib import sanitize
from slapz102_stdlib import paginate

from accounting.accounting_proc import PAGES
from accounting.products_proc import products_proc, PRODUCT_TYPES, PRODUCT_FILTERS
from auth.auth_proc import access_required
from record_log.record_log_proc import record_log_proc
from view.record_log.view_record_log import actor_from_user
from view.accounting.view_accounting import base_data

# ---------------------------------------------------------------------------
# PRODUK — view / render layer. Pelanggan > Produk (/accounting/client-
# products, filter Penjualan) and Vendor > Produk (/accounting/vendor-
# products, filter Pembelian) show the same catalogue; a product opens under
# the route it was opened from. ?filter=all removes the default filter.
# ---------------------------------------------------------------------------

LOG_MODEL = "product"
FILTER_ALL = "all"

PRODUCT_SHELLS = {
    "client": {"shell": "client", "slug": "client-products", "list_ep": "client_products", "ep": "client_product",
               "default_filter": "sale"},
    "vendor": {"shell": "vendor", "slug": "vendor-products", "list_ep": "vendor_products", "ep": "vendor_product",
               "default_filter": "purchase"}
}


def _ep(shell, name):
    return "accounting_blueprint." + PRODUCT_SHELLS[shell]["ep"] + "_" + name
# end def

def _list_ep(shell):
    return "accounting_blueprint." + PRODUCT_SHELLS[shell]["list_ep"]
# end def

def _meta(data, shell):
    ps = PRODUCT_SHELLS[shell]
    data["ps"] = ps
    data["page"] = PAGES[ps["slug"]]
    data["slug"] = ps["slug"]
    return data
# end def

def _url(seq, shell, **message):
    return url_for(_ep(shell, "edit"), seq=seq, **message)
# end def

def _result_redirect(seq, result, shell):
    key = "success" if result.get("status") == "SUCCESS" else "error"
    return redirect(_url(seq, shell, **{key: result.get("desc", "")}))
# end def

def _form_data(product, shell):
    proc = products_proc()
    data = _meta(base_data(), shell)
    data["product"] = product
    data["product_types"] = PRODUCT_TYPES
    data["sale_tax_options"] = proc.tax_options("sale")
    data["purchase_tax_options"] = proc.tax_options("purchase")
    data["log_groups"] = []
    if product != None:
        data["log_groups"] = record_log_proc().list_groups(LOG_MODEL, product["id"])
    # end if
    return data
# end def

@access_required("accounting", "read")
def html_products(shell):
    params = sanitize.clean_html_dic(request.args.to_dict())
    ps = PRODUCT_SHELLS[shell]
    data = _meta(base_data(), shell)
    data["filter"] = (params.get("filter") or ps["default_filter"]).strip()
    if data["filter"] != FILTER_ALL and data["filter"] not in PRODUCT_FILTERS:
        data["filter"] = ps["default_filter"]
    # end if
    data["filter_all"] = FILTER_ALL
    data["filters"] = PRODUCT_FILTERS
    data["q"] = (params.get("q") or "").strip()
    page, per_page = paginate.read_params(params)
    pager = products_proc().page_products("" if data["filter"] == FILTER_ALL else data["filter"], data["q"], page, per_page)
    data["products"] = pager["products"]
    data["pager"] = pager
    data["page_args"] = {"filter": data["filter"], "q": data["q"]}
    return render_template("accounting_products.html", data=data)
# end def

@access_required("accounting", "create")
def html_product_new(shell):
    return render_template("accounting_product_form.html", data=_form_data(None, shell))
# end def

@access_required("accounting", "read")
def html_product_edit(seq, shell):
    product = products_proc().get_by_seq(seq)
    if product == None:
        return redirect(url_for(_list_ep(shell), error="Produk tidak ditemukan"))
    # end if
    return render_template("accounting_product_form.html", data=_form_data(product, shell))
# end def

@access_required("accounting", "create")
def html_product_create(shell):
    if not csrf.validate():
        return redirect(url_for(_ep(shell, "new"), error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = products_proc().create_product(params, actor_from_user(current_user))
    if result.get("status") != "SUCCESS":
        return redirect(url_for(_ep(shell, "new"), error=result.get("desc", "")))
    # end if
    return _result_redirect(result["seq"], result, shell)
# end def

@access_required("accounting", "update")
def html_product_update(seq, shell):
    if not csrf.validate():
        return redirect(_url(seq, shell, error="Sesi tidak valid, coba lagi"))
    # end if
    params = sanitize.clean_html_dic(request.form.to_dict())
    result = products_proc().update_product(seq, params, actor_from_user(current_user))
    return _result_redirect(seq, result, shell)
# end def
