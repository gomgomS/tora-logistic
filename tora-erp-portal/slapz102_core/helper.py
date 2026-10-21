import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_stdlib")

from slapz102_stdlib import idgen

class response_msg:

    mapping_data = {
        "status": "message_action",
        "desc": "message_desc",
        "status_code": "status_code",
        "data": "message_data",
    }

    def __init__(self, status, desc, data, status_code="xxxx"):
        call_id = idgen._get_api_call_id()
        self.response = {
            "id": call_id,
            "status_code": status_code,
            "status": status,
            "desc": desc,
            "data": data,
            "message_id": call_id,
            "message_action": status,
            "message_desc": desc,
            "message_data": data
        }
    # end def

    def put(self, key, value):
        if not (key in self.response):
            raise ValueError("SETTING_NON_EXISTING_FIELD", key, value)
        # end if
        self.response[key] = value
        if key in self.mapping_data:
            self.response[self.mapping_data[key]] = value
        # end if
    # end def

    def get(self):
        return self.response
    # end def
# end class

def response_msg_factory(status, desc, data, status_code="xxxx"):
    return response_msg(status, desc, data, status_code)
# end def
