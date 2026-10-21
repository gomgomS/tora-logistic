import datetime
import time
import copy
import pymongo
import random

from slapz102_core import model
from slapz102_core import config

from bson.objectid import ObjectId

db_conn_completed = False

db_conn = {}
for row in config.G_DATABASE_CONNECT:
    db_conn[row["dbname"]] = row["dbstring"]
# end for

db_active_con = {}
for row in config.G_DATABASE_CONNECT:
    db_active_con[row["dbname"]] = None
# end for

db = model.db

def get_database(database_name):
    return db_active_con[database_name]
# end def

def connect_db():
    global db_conn_completed
    for row in config.G_DATABASE_CONNECT:
        if db_active_con[row["dbname"]] == None:
            db_active_con[row["dbname"]] = pymongo.MongoClient(db_conn[row["dbname"]])
        # end if
    # end for
    db_conn_completed = True
# end def

def get_db_conn(db_name):
    global db_conn_completed
    if not db_conn_completed:
        connect_db()
    # end if
    handle = db_active_con[db_name][db_name]
    return handle
# end def

def _convert_datetime_to_timestamp(date_time, IN_MILLISECONDS=True):
    try:
        timestamp = int(date_time.strftime("%s"))
    except ValueError:
        timestamp = int(time.mktime(date_time.timetuple()))
    # end try
    if IN_MILLISECONDS:
        timestamp = timestamp * 1000 + int(date_time.microsecond / 1000)
        return timestamp
    # end if
    return timestamp
# end def

def _get_current_datetime(days=0, hours=0, minutes=0, seconds=0):
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(
        days=days, hours=hours, minutes=minutes, seconds=seconds
    )
# end def

def get_record(db_table):
    now = _get_current_datetime(hours=config.JKTA_TZ)
    timestamp = _convert_datetime_to_timestamp(now)
    record = copy.deepcopy(db[db_table])
    record["rec_timestamp"] = timestamp
    record["rec_timestamp_str"] = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp / 1000)
    )
    record["_id"] = ObjectId()
    record["pkey"] = str(record["_id"])
    record["is_deleted"] = False
    return record
# end def

def new(db_handle, db_table):
    now = _get_current_datetime(hours=config.JKTA_TZ)
    timestamp = _convert_datetime_to_timestamp(now)
    record = copy.deepcopy(db[db_table])
    record["__db__name__"] = db_table
    record["rec_timestamp"] = timestamp
    record["rec_timestamp_str"] = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp / 1000)
    )
    request_rec = db_handle.db_unique_counter.find_one_and_update(
        {},
        {"$inc": {"counter": 1}},
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER
    )
    now_time = int(time.time() * 1000)
    random_int = random.randint(1000, 9999)
    counter_val = 1
    if request_rec != None:
        counter_val = int(request_rec.get("counter", 1))
    # end if
    req_id = str(random_int) + "-" + str(counter_val) + "-" + str(now_time)
    record["_id"] = ObjectId()
    record["ipkey"] = str(record["_id"])
    record["pkey"] = str(record["_id"]) + "-" + req_id
    record["is_deleted"] = False
    mongo_record_model = model.mongo_model(record, record, db_handle)
    return mongo_record_model
# end def

def load(db_handle, db_table):
    record = copy.deepcopy(db[db_table])
    record["__db__name__"] = db_table
    mongo_record_model = model.mongo_model({}, record, db_handle)
    return mongo_record_model
# end def
