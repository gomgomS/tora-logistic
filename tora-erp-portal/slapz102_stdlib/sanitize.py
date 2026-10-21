import html
from html.parser import HTMLParser
from urllib.parse import urlparse

RICH_TAGS = [
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "span",
    "ul", "ol", "li", "blockquote", "a", "img"
]
RICH_VOID_TAGS = ["br", "img"]

def _safe_rich_url(value, image=False):
    clean = (value or "").strip()
    if clean == "":
        return ""
    # end if
    parsed = urlparse(clean)
    if parsed.scheme not in ["", "http", "https", "mailto", "tel"]:
        return ""
    # end if
    if image and parsed.scheme in ["mailto", "tel"]:
        return ""
    # end if
    if parsed.scheme == "" and not clean.startswith("/"):
        return ""
    # end if
    return clean
# end def

class _RichHTMLCleaner(HTMLParser):

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.output = []
        self.skip_depth = 0
    # end def

    def handle_starttag(self, tag, attrs):
        tag = (tag or "").lower()
        if tag in ["script", "style"]:
            self.skip_depth = self.skip_depth + 1
            return
        # end if
        if self.skip_depth > 0:
            return
        # end if
        if tag == "div":
            tag = "p"
        # end if
        if tag not in RICH_TAGS:
            return
        # end if
        safe_attrs = []
        attr_map = dict(attrs)
        if tag == "a":
            href = _safe_rich_url(attr_map.get("href"))
            if href != "":
                safe_attrs.append(("href", href))
                if href.startswith("http://") or href.startswith("https://"):
                    safe_attrs.append(("target", "_blank"))
                    safe_attrs.append(("rel", "noopener noreferrer"))
                # end if
            # end if
        # end if
        if tag == "img":
            src = _safe_rich_url(attr_map.get("src"), True)
            if src == "":
                return
            # end if
            safe_attrs.append(("src", src))
            safe_attrs.append(("alt", (attr_map.get("alt") or "")[0:250]))
        # end if
        if tag == "span":
            text_size = (attr_map.get("data-text-size") or "").strip().lower()
            if text_size in ["small", "normal", "large", "xlarge"]:
                safe_attrs.append(("data-text-size", text_size))
            # end if
        # end if
        attr_text = ""
        for key, value in safe_attrs:
            attr_text = attr_text + " " + key + '="' + html.escape(value, quote=True) + '"'
        # end for
        self.output.append("<" + tag + attr_text + ">")
    # end def

    def handle_endtag(self, tag):
        tag = (tag or "").lower()
        if tag in ["script", "style"]:
            if self.skip_depth > 0:
                self.skip_depth = self.skip_depth - 1
            # end if
            return
        # end if
        if self.skip_depth > 0:
            return
        # end if
        if tag == "div":
            tag = "p"
        # end if
        if tag in RICH_TAGS and tag not in RICH_VOID_TAGS:
            self.output.append("</" + tag + ">")
        # end if
    # end def

    def handle_data(self, data):
        if self.skip_depth == 0:
            self.output.append(html.escape(data or ""))
        # end if
    # end def
# end class

def clean_rich_html(value):
    parser = _RichHTMLCleaner()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.output).strip()
# end def

def clean_html_dic(params):
    for index, item in params.items():
        if isinstance(item, str):
            params[index] = html.escape(item)
        # end if
    # end for
    return params
# end def

def clean_html(param):
    clean_param = html.escape(param)
    return clean_param
# end def
