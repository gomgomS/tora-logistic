import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

import json
import random
import re
import urllib.request
import urllib.error
from urllib.parse import quote

from slapz102_core import config

from contacts.contacts_proc import contacts_proc, CATEGORIES
from fleet.fleet_proc import fleet_proc, VEHICLE_TYPES, OWNERSHIPS, DRIVER_TYPES
from shipments.shipments_proc import shipments_proc, SERVICE_TYPES, SERVICE_CITIES
from manifests.manifests_proc import manifests_proc

# ---------------------------------------------------------------------------
# AI ASSISTANT — proposes records, then writes them only after the user
# confirms. The model never receives a claim that data exists until the
# existing module procs return SUCCESS.
# ---------------------------------------------------------------------------

MAX_ACTIONS = 12
MAX_MESSAGES = 16


def _clip(value, limit):
    text = (value or "")
    if not isinstance(text, str):
        text = str(text)
    # end if
    text = text.strip()
    if len(text) > limit:
        text = text[:limit]
    # end if
    return text
# end def


_GIVEN = (
    "Alya", "Bagus", "Citra", "Dimas", "Eka", "Farah", "Gilang", "Hana",
    "Irfan", "Jihan", "Kamal", "Laras", "Mahendra", "Nadya", "Omar", "Putri",
    "Raka", "Salsa", "Teguh", "Ulfa", "Vino", "Wulan", "Yoga", "Zahra",
    "Arif", "Bella", "Cahya", "Dinda", "Fajar", "Galih", "Intan", "Johan",
    "Kirana", "Lukman", "Maya", "Naufal", "Okta", "Pandu", "Rini", "Surya"
)
_FAMILY = (
    "Wijaya", "Saputra", "Kusuma", "Pratama", "Hidayat", "Nugroho", "Lestari",
    "Ramadhan", "Setiawan", "Permata", "Wibowo", "Halim", "Santoso", "Utami",
    "Mahardika", "Kurniawan", "Anggraini", "Purnomo", "Handoko", "Siregar"
)


def _user_text(messages):
    parts = []
    for item in messages:
        if item.get("role") == "user":
            parts.append(item.get("content") or "")
        # end if
    # end for
    return " ".join(parts).lower()
# end def


def _person_name(proposed, user_text, used):
    # Keep a name only when the user actually typed it. Otherwise pick a
    # fresh Indonesian personal name so sample data is not Budi every time.
    name = (proposed or "").strip()
    haystack = (user_text or "").lower()
    if name != "" and len(name) >= 3:
        pattern = "(^|[^a-z])" + re.escape(name.lower()) + "([^a-z]|$)"
        if re.search(pattern, haystack) != None:
            used[name.lower()] = True
            return name
        # end if
    # end if
    attempt = 0
    while attempt < 24:
        attempt = attempt + 1
        picked = random.choice(_GIVEN) + " " + random.choice(_FAMILY)
        key = picked.lower()
        if key in used:
            continue
        # end if
        if _find_contact(picked, "") != None:
            used[key] = True
            continue
        # end if
        used[key] = True
        return picked
    # end while
    picked = random.choice(_GIVEN) + " " + random.choice(_FAMILY) + " " + str(random.randint(10, 99))
    used[picked.lower()] = True
    return picked
# end def


def _copy_place(args, prefix, city):
    if _clip(args.get(prefix + "_address"), 240) != "" and _clip(args.get(prefix + "_village"), 80) != "":
        return
    # end if
    place = manifests_proc().suggest_party_place(city)
    if place == None:
        return
    # end if
    args[prefix + "_province"] = place.get("province", "")
    args[prefix + "_regency"] = place.get("regency", "")
    args[prefix + "_district"] = place.get("district", "")
    args[prefix + "_village"] = place.get("village", "")
    args[prefix + "_postal_code"] = place.get("postal_code", "")
    args[prefix + "_address"] = place.get("address", "")
    settled = place.get("city", "") or (city or "")
    if prefix == "origin":
        if _clip(args.get("origin_city"), 80) == "":
            args["origin_city"] = settled
        # end if
    elif _clip(args.get("destination_city"), 80) == "":
        args["destination_city"] = settled
    # end if
# end def


def _prepare_generated(tool, args, user_text, used):
    if tool == "create_contact":
        args["name"] = _person_name(args.get("name"), user_text, used)
    elif tool == "create_driver":
        args["contact_name"] = _person_name(args.get("contact_name"), user_text, used)
    elif tool == "create_shipment":
        args["sender_name"] = _person_name(args.get("sender_name"), user_text, used)
        args["receiver_name"] = _person_name(args.get("receiver_name"), user_text, used)
        _copy_place(args, "origin", args.get("origin_city") or "")
        _copy_place(args, "destination", args.get("destination_city") or "")
    # end if
    return args
# end def


class ai_proc:

    def __init__(self, app=None):
        self.webapp = app
    # end def

    def _key(self):
        return (os_environ_key())
    # end def

    def _model(self):
        model = getattr(config, "G_OPENAI_MODEL", "") or "gpt-4o-mini"
        return model
    # end def

    def chat(self, messages):
        key = self._key()
        if key == "":
            return {
                "status": "ERROR",
                "desc": "Asisten belum diatur. Tambahkan OPENAI_API_KEY di .env lalu mulai ulang."
            }
        # end if
        cleaned = _clean_messages(messages)
        payload = {
            "model": self._model(),
            "temperature": 0.3,
            "messages": [{"role": "system", "content": _system_prompt()}] + cleaned,
            "tools": _tools(),
            "tool_choice": "auto"
        }
        try:
            data = _openai(key, payload)
        except Exception as exc:
            return {"status": "ERROR", "desc": "Asisten tidak bisa membalas. " + str(exc)}
        # end try
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        if not (message.get("tool_calls") or []) and _wants_records(cleaned):
            nudge = list(cleaned)
            spoken = (message.get("content") or "").strip()
            if spoken != "":
                nudge.append({"role": "assistant", "content": spoken})
            # end if
            nudge.append({
                "role": "user",
                "content": "Call the tools now for exactly those records."
            })
            payload["messages"] = [{"role": "system", "content": _system_prompt()}] + nudge[-MAX_MESSAGES:]
            try:
                data = _openai(key, payload)
            except Exception:
                data = {"choices": [{"message": message}]}
            # end try
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or message
        # end if
        reply = (message.get("content") or "").strip()
        user_text = _user_text(cleaned)
        proposals = _proposals_from_message(message, cleaned)
        proposals, added_route = _attach_route(proposals, user_text)
        if _route_needs_more_stops(proposals, user_text):
            need = _asked_transits(user_text)
            nudge = list(cleaned)
            if reply != "":
                nudge.append({"role": "assistant", "content": reply})
            # end if
            nudge.append({
                "role": "user",
                "content": "The route is short. Call create_hub for each new city and create_route with exactly "
                           + str(need + 2) + " stops: origin, " + str(need) + " transit cities, then the destination."
            })
            payload["messages"] = [{"role": "system", "content": _system_prompt()}] + nudge[-MAX_MESSAGES:]
            try:
                data = _openai(key, payload)
                repaired_message = ((data.get("choices") or [{}])[0]).get("message") or {}
                repaired = _proposals_from_message(repaired_message, cleaned)
                repaired, repaired_added = _attach_route(repaired, user_text)
                if len(repaired) > 0 and (not _route_needs_more_stops(repaired, user_text)):
                    proposals = repaired
                    added_route = repaired_added
                    spoken = (repaired_message.get("content") or "").strip()
                    if spoken != "":
                        reply = spoken
                    # end if
                # end if
            except Exception:
                pass
            # end try
        # end if
        if added_route and "rute" not in reply.lower() and "route" not in reply.lower():
            if reply != "":
                reply = reply + " "
            # end if
            reply = reply + "Rute juga siap disimpan. Tekan Konfirmasi."
        # end if
        if reply == "" and len(proposals) > 0:
            reply = "Data ini siap disimpan. Tekan Konfirmasi untuk menyimpan."
        # end if
        return {"status": "SUCCESS", "reply": reply, "proposals": proposals}
    # end def

    def apply(self, actions, user_id):
        if not isinstance(actions, list):
            return {"status": "ERROR", "desc": "Tidak ada data untuk dibuat"}
        # end if
        pending = []
        count = 0
        for action in actions:
            if count >= MAX_ACTIONS:
                break
            # end if
            if not isinstance(action, dict):
                continue
            # end if
            name = action.get("tool") or ""
            args = action.get("arguments") or {}
            if not isinstance(args, dict) or name not in _TOOL_NAMES:
                continue
            # end if
            pending.append((count, action))
            count = count + 1
        # end for
        # Hubs first, then the route that joins them.
        pending.sort(key=lambda item: (_action_rank(item[1].get("tool") or ""), item[0]))
        results = []
        for item in pending:
            action = item[1]
            results.append(self._run(action.get("tool") or "", action.get("arguments") or {}, user_id))
        # end for
        if len(results) == 0:
            return {"status": "ERROR", "desc": "Tidak ada data untuk dibuat"}
        # end if
        return {"status": "SUCCESS", "results": results}
    # end def

    def _run(self, name, args, user_id):
        try:
            if name == "create_contact":
                return self._contact(args)
            # end if
            if name == "create_vehicle":
                return self._vehicle(args)
            # end if
            if name == "create_driver":
                return self._driver(args)
            # end if
            if name == "create_hub":
                return self._hub(args)
            # end if
            if name == "update_hub":
                return self._hub_update(args)
            # end if
            if name == "create_shipment":
                return self._shipment(args, user_id)
            # end if
            if name == "create_route":
                return self._route(args)
            # end if
        except Exception as exc:
            return {"tool": name, "status": "ERROR", "desc": str(exc)}
        # end try
        return {"tool": name, "status": "ERROR", "desc": "Aksi tidak dikenal"}
    # end def

    def _contact(self, args):
        name = _clip(args.get("name"), 120)
        if name == "":
            name = _person_name("", "", {})
        # end if
        params = {
            "name": name,
            "company_name": _clip(args.get("company_name"), 120),
            "phone": _clip(args.get("phone"), 40),
            "email": _clip(args.get("email"), 120),
            "address": _clip(args.get("address"), 200),
            "city": _clip(args.get("city"), 80),
            "category": _clip(args.get("category"), 20).upper()
        }
        result = contacts_proc().create_contact(params)
        result["tool"] = "create_contact"
        result["label"] = params["name"]
        if result.get("status") == "SUCCESS":
            result["href"] = "/contacts"
        # end if
        return result
    # end def

    def _vehicle(self, args):
        params = {
            "plate_number": _clip(args.get("plate_number"), 20),
            "vehicle_type": _clip(args.get("vehicle_type"), 40),
            "ownership": _clip(args.get("ownership"), 20).upper() or "INTERNAL",
            "vendor_name": _clip(args.get("vendor_name"), 120)
        }
        result = fleet_proc().create_vehicle(params)
        result["tool"] = "create_vehicle"
        result["label"] = params["plate_number"]
        if result.get("status") == "SUCCESS":
            result["href"] = "/fleet"
        # end if
        return result
    # end def

    def _driver(self, args):
        contact_name = _clip(args.get("contact_name"), 120)
        if contact_name == "":
            contact_name = _person_name("", "", {})
        # end if
        contact = _find_contact(contact_name, "DRIVER")
        if contact == None and contact_name != "":
            created = contacts_proc().create_contact({
                "name": contact_name,
                "category": "DRIVER",
                "city": _clip(args.get("city"), 80),
                "phone": _clip(args.get("phone"), 40)
            })
            if created.get("status") != "SUCCESS":
                created["tool"] = "create_driver"
                return created
            # end if
            contact_id = created.get("id", "")
        else:
            contact_id = "" if contact == None else contact.get("id", "")
        # end if
        params = {
            "contact_id": contact_id,
            "license_number": _clip(args.get("license_number"), 40),
            "type": _clip(args.get("type"), 20).upper() or "INTERNAL"
        }
        result = fleet_proc().create_driver(params)
        result["tool"] = "create_driver"
        result["label"] = contact_name
        if result.get("status") == "SUCCESS":
            result["href"] = "/fleet"
        # end if
        return result
    # end def

    def _hub_params(self, args):
        params = {"name": _clip(args.get("name"), 80)}
        limits = {
            "province": 80,
            "regency": 80,
            "district": 80,
            "village": 80,
            "postal_code": 10,
            "address": 240,
            "new_name": 80
        }
        for key in limits:
            if key in args:
                params[key] = _clip(args.get(key), limits[key])
            # end if
        # end for
        return params
    # end def

    def _hub_ready(self, args):
        proc = manifests_proc()
        params = self._hub_params(args)
        params = proc.prepare_hub_args(params)
        # end if
        return proc, params
    # end def

    def _hub(self, args):
        proc, params = self._hub_ready(args)
        result = proc.create_hub(params)
        result["tool"] = "create_hub"
        result["label"] = result.get("name") or params["name"]
        if result.get("status") == "SUCCESS":
            result["href"] = "/hub?hub=" + quote(result["label"])
        # end if
        return result
    # end def

    def _hub_update(self, args):
        proc, params = self._hub_ready(args)
        result = proc.update_hub(params)
        result["tool"] = "update_hub"
        result["label"] = result.get("name") or params["name"]
        if result.get("status") == "SUCCESS":
            result["href"] = "/hub?hub=" + quote(result["label"])
        # end if
        return result
    # end def

    def _route(self, args):
        params = {
            "name": _clip(args.get("name"), 80),
            "stops": args.get("stops") or []
        }
        result = manifests_proc().create_route_by_stops(params)
        result["tool"] = "create_route"
        result["label"] = result.get("label") or result.get("name") or params["name"]
        if result.get("status") == "SUCCESS":
            result["href"] = "/routes"
        # end if
        return result
    # end def

    def _shipment(self, args, user_id):
        _copy_place(args, "origin", args.get("origin_city") or "")
        _copy_place(args, "destination", args.get("destination_city") or "")
        sender_name = _clip(args.get("sender_name"), 120)
        receiver_name = _clip(args.get("receiver_name"), 120)
        if sender_name == "":
            sender_name = _person_name("", "", {})
        # end if
        if receiver_name == "":
            receiver_name = _person_name("", "", {})
        # end if
        origin_city = _clip(args.get("origin_city"), 80)
        destination_city = _clip(args.get("destination_city"), 80)
        sender = self._ensure_party(
            sender_name,
            "CLIENT",
            origin_city,
            _clip(args.get("origin_address"), 200)
        )
        receiver = self._ensure_party(
            receiver_name,
            "RECEIVER",
            destination_city,
            _clip(args.get("destination_address"), 200)
        )
        if sender.get("status") != "SUCCESS":
            sender["tool"] = "create_shipment"
            return sender
        # end if
        if receiver.get("status") != "SUCCESS":
            receiver["tool"] = "create_shipment"
            return receiver
        # end if
        params = {
            "service_type": _clip(args.get("service_type"), 10).upper() or "LTL",
            "sender_id": sender.get("id", ""),
            "receiver_id": receiver.get("id", ""),
            "origin_city": origin_city,
            "origin_province": _clip(args.get("origin_province"), 80),
            "origin_regency": _clip(args.get("origin_regency"), 80),
            "origin_district": _clip(args.get("origin_district"), 80),
            "origin_village": _clip(args.get("origin_village"), 80),
            "origin_postal_code": _clip(args.get("origin_postal_code"), 10),
            "origin_address": _clip(args.get("origin_address"), 240),
            "destination_city": destination_city,
            "destination_province": _clip(args.get("destination_province"), 80),
            "destination_regency": _clip(args.get("destination_regency"), 80),
            "destination_district": _clip(args.get("destination_district"), 80),
            "destination_village": _clip(args.get("destination_village"), 80),
            "destination_postal_code": _clip(args.get("destination_postal_code"), 10),
            "destination_address": _clip(args.get("destination_address"), 240),
            "po_number": _clip(args.get("po_number"), 40)
        }
        result = shipments_proc().create_shipment(params, user_id or "SYSTEM")
        result["tool"] = "create_shipment"
        result["label"] = result.get("tracking_code", "")
        if result.get("status") == "SUCCESS":
            result["href"] = "/shipments/detail/" + result.get("tracking_code", "")
        # end if
        return result
    # end def

    def _ensure_party(self, name, category, city, address=""):
        found = _find_contact(name, category)
        if found != None:
            return {"status": "SUCCESS", "id": found.get("id", ""), "name": found.get("name", "")}
        # end if
        if name == "":
            name = _person_name("", "", {})
        # end if
        return contacts_proc().create_contact({
            "name": name,
            "category": category,
            "city": city,
            "address": address
        })
    # end def
# end class


def os_environ_key():
    import os
    return os.environ.get("OPENAI_API_KEY", "") or getattr(config, "G_OPENAI_API_KEY", "")
# end def


def _find_contact(name, category):
    if name == "":
        return None
    # end if
    query = {
        "is_deleted": False,
        "name": {"$regex": "^" + re.escape(name) + "$", "$options": "i"}
    }
    if category in CATEGORIES:
        query["category"] = category
    # end if
    rec = contacts_proc.mgdDB.db_contact.find_one(query)
    if rec == None:
        return None
    # end if
    rec["id"] = str(rec.pop("_id"))
    return rec
# end def


def _wants_records(messages):
    if len(messages) == 0:
        return False
    # end if
    last = messages[-1]
    if last.get("role") != "user":
        return False
    # end if
    text = (last.get("content") or "").lower()
    hints = (
        "create", "buat", "tambah", "generate", "add a", "add an",
        "new contact", "new order", "new hub", "new vehicle", "buatkan",
        "isi", "ubah", "ganti", "lengkapi", "detail", "update", "edit"
    )
    for hint in hints:
        if hint in text:
            return True
        # end if
    # end for
    return False
# end def


def _clean_messages(messages):
    out = []
    if not isinstance(messages, list):
        return out
    # end if
    for item in messages[-MAX_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        # end if
        role = item.get("role") or ""
        if role not in ("user", "assistant"):
            continue
        # end if
        content = _clip(item.get("content"), 2000)
        if content == "":
            continue
        # end if
        out.append({"role": role, "content": content})
    # end for
    return out
# end def


def _system_prompt():
    cities = ", ".join(SERVICE_CITIES)
    types = ", ".join(VEHICLE_TYPES)
    return (
        "You are Tora, the assistant inside the Tora Expedition ERP. "
        "Reply in Indonesian by default, in short plain sentences. "
        "Use shipping terms that Indonesian operators already say: AWB, manifest, hub, LTL, FTL, POD, feeder, charter, nopol, colly. "
        "If the user writes in English, reply in English. "
        "This portal stores contacts (CLIENT, RECEIVER, DRIVER, VENDOR), vehicles (" + types + "), "
        "drivers, transit hubs, and shipments (LTL or FTL). "
        "It does not have products, invoices, or analytic accounts. If the user asks for those, "
        "say they are not in this portal and offer the closest record instead: a contact, vehicle, hub, or shipment. "
        "When the user wants data created, call the tools in that same reply. "
        "A text-only list cannot be saved. The Konfirmasi button is the approval, so do not ask "
        "'shall I proceed' without also calling the tools. Do not say the records already exist. "
        "Use realistic Indonesian logistics examples when they ask you to generate sample data. "
        "Do not invent person names. Leave contact name, driver contact_name, sender_name, and receiver_name empty unless the user typed that exact name. "
        "The portal assigns a different random Indonesian personal name for each person. "
        "For a shipment, pass origin_city and destination_city. The portal fills the full pengirim and penerima address: province, regency, district, village, postal code, and street. "
        "Known cities: " + cities + ". You may use another city if the user names one. "
        "A hub stores name, province, regency (Kabupaten or Kota), district (kecamatan), "
        "village (kelurahan or desa), postal_code (5 digits, optional), and address (street). "
        "When you create a hub, fill those address fields with a realistic place in that city. "
        "When the user asks to fill or change a hub that already exists, call update_hub with that hub name and the new details. Do not call create_hub again for it. "
        "A route is the saved truck path: origin hub, transit hubs, then the destination hub. "
        "When the user asks to make a route, call create_route in that same reply. Hubs alone are not a route. "
        "Put every stop in the stops array in travel order, including the transit cities. "
        "If they leave the transit cities open, choose real cities that sit between the origin and the destination. "
        "Obey the transit count. Three transit cities means five stops: origin, three different cities, then the destination. Do not use fewer. "
        "Also call create_hub for each new stop, named '{City} Hub', with a full address. "
        "If they say Bali, use Denpasar as the hub city. You may still name the route Surabaya ke Bali. "
        "For a full example, create a client, a receiver, a vehicle, a driver, a hub, and one shipment."
    )
# end def


_TOOL_NAMES = [
    "create_contact", "create_vehicle", "create_driver", "create_hub", "update_hub",
    "create_route", "create_shipment"
]


def _tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "create_contact",
                "description": "Create a master contact.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "company_name": {"type": "string"},
                        "phone": {"type": "string"},
                        "email": {"type": "string"},
                        "address": {"type": "string"},
                        "city": {"type": "string"},
                        "category": {"type": "string", "enum": CATEGORIES}
                    },
                    "required": ["name", "category"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_vehicle",
                "description": "Register a truck.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "plate_number": {"type": "string"},
                        "vehicle_type": {"type": "string", "enum": VEHICLE_TYPES},
                        "ownership": {"type": "string", "enum": OWNERSHIPS},
                        "vendor_name": {"type": "string"}
                    },
                    "required": ["plate_number", "vehicle_type", "ownership"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_driver",
                "description": "Register a driver. Creates a DRIVER contact when the name is new.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "contact_name": {"type": "string"},
                        "license_number": {"type": "string"},
                        "type": {"type": "string", "enum": DRIVER_TYPES},
                        "phone": {"type": "string"},
                        "city": {"type": "string"}
                    },
                    "required": ["contact_name", "license_number", "type"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_hub",
                "description": "Add a transit hub. Always include the address detail, not only the name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "province": {"type": "string"},
                        "regency": {"type": "string", "description": "Kabupaten or Kota, for example Kota Semarang"},
                        "district": {"type": "string", "description": "Kecamatan"},
                        "village": {"type": "string", "description": "Kelurahan or desa"},
                        "postal_code": {"type": "string"},
                        "address": {"type": "string", "description": "Street, number, RT/RW"}
                    },
                    "required": ["name", "province", "regency", "district", "village", "address"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_hub",
                "description": "Fill or change the address detail of a hub that already exists. Match it by its current name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Current hub name"},
                        "new_name": {"type": "string"},
                        "province": {"type": "string"},
                        "regency": {"type": "string"},
                        "district": {"type": "string"},
                        "village": {"type": "string"},
                        "postal_code": {"type": "string"},
                        "address": {"type": "string"}
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_route",
                "description": "Save a truck route through hubs in travel order. Call this whenever the user asks for a route. Creating hubs is not enough. Include origin, every transit city, and the destination. If they ask for 3 transit cities, stops must contain 5 names.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Short route name, for example Surabaya ke Bali"},
                        "stops": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Hub or city names in travel order, origin first and destination last"
                        }
                    },
                    "required": ["stops"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_shipment",
                "description": "Create an order. Sender and receiver are found or created.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sender_name": {"type": "string"},
                        "receiver_name": {"type": "string"},
                        "origin_city": {"type": "string"},
                        "destination_city": {"type": "string"},
                        "service_type": {"type": "string", "enum": SERVICE_TYPES},
                        "po_number": {"type": "string"}
                    },
                    "required": ["sender_name", "receiver_name", "origin_city", "destination_city", "service_type"]
                }
            }
        }
    ]
# end def


def _hub_summary(args):
    parts = [_clip(args.get("name"), 80)]
    place = []
    for key in ("village", "district", "regency", "province"):
        text = _clip(args.get(key), 40)
        if text != "":
            place.append(text)
        # end if
    # end for
    if len(place) > 0:
        parts.append(", ".join(place))
    # end if
    postal = _clip(args.get("postal_code"), 10)
    if postal != "":
        parts.append(postal)
    # end if
    address = _clip(args.get("address"), 80)
    if address != "":
        parts.append(address)
    # end if
    return " · ".join(parts)
# end def


def _summary(name, args):
    if name == "create_contact":
        return _clip(args.get("name"), 80) + " · " + _clip(args.get("category"), 20).upper() + " · " + _clip(args.get("city"), 40)
    # end if
    if name == "create_vehicle":
        return _clip(args.get("plate_number"), 20) + " · " + _clip(args.get("vehicle_type"), 30)
    # end if
    if name == "create_driver":
        return _clip(args.get("contact_name"), 80) + " · " + _clip(args.get("license_number"), 30)
    # end if
    if name == "create_hub" or name == "update_hub":
        return _hub_summary(args)
    # end if
    if name == "create_shipment":
        origin = _clip(args.get("origin_address"), 40) or _clip(args.get("origin_city"), 20)
        destination = _clip(args.get("destination_address"), 40) or _clip(args.get("destination_city"), 20)
        return _clip(args.get("sender_name"), 40) + " → " + _clip(args.get("receiver_name"), 40) + " · " + origin + " – " + destination
    # end if
    if name == "create_route":
        stops = _stop_list(args.get("stops"))
        chain = " → ".join(stops)
        title = _clip(args.get("name"), 40)
        if title != "":
            return title + " · " + chain
        # end if
        return chain
    # end if
    return name
# end def


def _action_rank(name):
    if name == "create_hub" or name == "update_hub":
        return 0
    # end if
    if name == "create_route":
        return 2
    # end if
    return 1
# end def


def _stop_list(value):
    out = []
    if isinstance(value, str):
        value = value.replace("→", ",").replace("->", ",").split(",")
    # end if
    if not isinstance(value, list):
        return out
    # end if
    for item in value:
        text = _clip(item, 80)
        if text != "":
            out.append(text)
        # end if
    # end for
    return out
# end def


def _route_title(stops):
    if len(stops) < 2:
        return ""
    # end if
    ends = [stops[0], stops[-1]]
    clean = []
    for text in ends:
        for suffix in (" Hub", " Gudang"):
            if text.endswith(suffix):
                text = text[:-len(suffix)]
            # end if
        # end for
        clean.append(text.strip())
    # end for
    return _clip(clean[0] + " ke " + clean[1], 80)
# end def


def _wants_route(text):
    lowered = (text or "").lower()
    return "rute" in lowered or "route" in lowered
# end def


def _attach_route(proposals, user_text):
    # A request for a route used to come back as hubs only. If the model
    # listed the stops and skipped the route, add that route here.
    if not isinstance(proposals, list):
        return [], False
    # end if
    if not _wants_route(user_text):
        return proposals, False
    # end if
    hubs = []
    for item in proposals:
        if item.get("tool") != "create_hub":
            continue
        # end if
        name = _clip((item.get("arguments") or {}).get("name"), 80)
        if name != "":
            hubs.append(name)
        # end if
    # end for
    for item in proposals:
        if item.get("tool") != "create_route":
            continue
        # end if
        args = item.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        # end if
        stops = _stop_list(args.get("stops"))
        if len(stops) < 2 and len(hubs) >= 2:
            args["stops"] = list(hubs)
            if _clip(args.get("name"), 80) == "":
                args["name"] = _route_title(hubs)
            # end if
            item["arguments"] = args
            item["summary"] = _summary("create_route", args)
        # end if
        return proposals, False
    # end for
    if len(hubs) < 2:
        return proposals, False
    # end if
    args = {"stops": list(hubs), "name": _route_title(hubs)}
    proposals.append({
        "tool": "create_route",
        "arguments": args,
        "summary": _summary("create_route", args)
    })
    return proposals, True
# end def


def _asked_transits(text):
    lowered = (text or "").lower()
    match = re.search(r"(\d+)\s*(?:kota\s+)?transit", lowered)
    if match == None:
        match = re.search(r"(\d+)\s+kota\s+di\s+antara", lowered)
    # end if
    if match == None:
        return 0
    # end if
    try:
        count = int(match.group(1))
    except Exception:
        return 0
    # end try
    if count < 1 or count > 8:
        return 0
    # end if
    return count
# end def


def _route_needs_more_stops(proposals, text):
    need = _asked_transits(text)
    if need < 1 or not isinstance(proposals, list):
        return False
    # end if
    for item in proposals:
        if item.get("tool") != "create_route":
            continue
        # end if
        stops = _stop_list((item.get("arguments") or {}).get("stops"))
        return len(stops) < need + 2
    # end for
    return False
# end def


def _proposals_from_message(message, cleaned):
    proposals = []
    used = {}
    user_text = _user_text(cleaned)
    for call in (message or {}).get("tool_calls") or []:
        if len(proposals) >= MAX_ACTIONS:
            break
        # end if
        fn = call.get("function") or {}
        name = fn.get("name") or ""
        if name not in _TOOL_NAMES:
            continue
        # end if
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        # end try
        if not isinstance(args, dict):
            args = {}
        # end if
        if name == "create_hub" or name == "update_hub":
            args = manifests_proc().prepare_hub_args(args)
        # end if
        args = _prepare_generated(name, args, user_text, used)
        proposals.append({
            "tool": name,
            "arguments": args,
            "summary": _summary(name, args)
        })
    # end for
    return proposals
# end def


def _openai(key, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        res = urllib.request.urlopen(req, timeout=45)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(_openai_error(detail, exc.code))
    # end try
    return json.loads(res.read().decode("utf-8"))
# end def


def _openai_error(detail, code):
    try:
        parsed = json.loads(detail)
        message = ((parsed.get("error") or {}).get("message") or "")
    except Exception:
        message = ""
    # end try
    if message == "":
        message = "HTTP " + str(code)
    # end if
    return message
# end def
