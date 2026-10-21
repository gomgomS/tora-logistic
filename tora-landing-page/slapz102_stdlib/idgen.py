import datetime
import time
import random

def _get_api_call_id():
    now_time = int(time.time())
    current_date = datetime.datetime.now()
    hour_tm = current_date.hour
    minute_tm = current_date.minute
    second_tm = current_date.second
    start_id = str(now_time) + str(hour_tm) + str(minute_tm) + str(second_tm)
    random_num = random.randint(1, 10000000)
    invoice_code = "API_CALL_" + str(start_id) + "_" + str(random_num)
    return invoice_code
# end def
