import json
from ..database import get_db


def create_project(db_path, user_id, name):
    with get_db(db_path) as db:
        cur = db.execute("INSERT INTO projects(user_id,name,timeline_json) VALUES(?,?,?)", (user_id, name, json.dumps({"clips": [], "audio_tracks": [], "markers": []})))
        db.commit()
        return cur.lastrowid
