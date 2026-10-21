import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from slapz102_core import database
from slapz102_core import config

# ---------------------------------------------------------------------------
# SAMPLE MODULE — business logic layer.
#
# This module is the reference implementation of the framework pattern:
#   blueprint  -> route only, no business logic
#   view       -> reads the request, calls a proc, renders a template
#   proc       -> ALL database / business logic lives here
#
# Copy this folder when starting a new feature module.
# ---------------------------------------------------------------------------

def _slugify(title):
    slug = (title or "").strip().lower()
    cleaned = ""
    for char in slug:
        if char.isalnum() or char in "- ":
            cleaned = cleaned + char
        # end if
    # end for
    slug = "-".join(cleaned.split())
    return slug or "item"
# end def

class sample_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def list_items(self):
        recs = list(self.mgdDB.db_sample_item.find(
            {"is_deleted": False},
            {"_id": 0}
        ).sort("rec_timestamp", -1))
        return recs
    # end def

    def get_item(self, slug):
        rec = self.mgdDB.db_sample_item.find_one(
            {"slug": slug, "is_deleted": False},
            {"_id": 0}
        )
        return rec
    # end def

    def _unique_slug(self, slug):
        candidate = slug
        seq = 2
        while self.get_item(candidate) != None:
            candidate = slug + "-" + str(seq)
            seq = seq + 1
        # end while
        return candidate
    # end def

    def create_item(self, params):
        title = (params.get("title") or "").strip()
        body = (params.get("body") or "").strip()
        if title == "":
            return {"status": "ERROR", "desc": "Title is required"}
        # end if
        rec = database.new(self.mgdDB, "db_sample_item")
        rec.put("slug", self._unique_slug(_slugify(title)))
        rec.put("title", title)
        rec.put("body", body)
        rec.put("order", 0)
        rec.put("status", "PUBLISHED")
        rec.insert()
        return {"status": "SUCCESS", "desc": "Item created"}
    # end def

    # Soft delete (framework convention): flag is_deleted instead of removing
    # the document. Partial updates go through the collection handle with
    # update_one — that is how the original codebase performs updates.
    def delete_item(self, slug):
        existing = self.get_item(slug)
        if existing == None:
            return {"status": "ERROR", "desc": "Item not found"}
        # end if
        self.mgdDB.db_sample_item.update_one(
            {"slug": slug},
            {"$set": {"is_deleted": True}}
        )
        return {"status": "SUCCESS", "desc": "Item deleted"}
    # end def
# end class
