#!/usr/bin/env python3
"""Read only authority states, never credentials or session bindings."""
import argparse
import json
import sqlite3

p=argparse.ArgumentParser()
p.add_argument('--database',required=True)
p.add_argument('--room',required=True)
a=p.parse_args()
with sqlite3.connect('file:'+a.database+'?mode=ro',uri=True) as db:
    print(json.dumps({'authority':db.execute('SELECT state FROM meeting_host_authority WHERE room_name=?',(a.room,)).fetchall(),
        'operations':db.execute('SELECT count(*) FROM host_transfer_operation WHERE room_name=?',(a.room,)).fetchall()}))
