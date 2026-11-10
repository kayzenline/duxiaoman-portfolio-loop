"""SQLite scenario store. Saves the *inputs* (name, snapshot id, ops), never derived results."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = '''CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    ops_json TEXT NOT NULL,
    created_at TEXT NOT NULL)'''


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute(SCHEMA)

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def add(self, name, snapshot_id, ops):
        created = datetime.now(timezone.utc).isoformat(timespec='seconds')
        with closing(self._connect()) as db, db:  # `with db` commits or rolls back
            cur = db.execute('INSERT INTO scenarios (name, snapshot_id, ops_json, created_at) VALUES (?,?,?,?)',
                             (name, snapshot_id, json.dumps(ops, ensure_ascii=False), created))
            return self.get(cur.lastrowid, db)

    def get(self, scenario_id, db=None):
        own = db is None
        db = db or self._connect()
        try:
            row = db.execute('SELECT * FROM scenarios WHERE id = ?', (scenario_id,)).fetchone()
        finally:
            if own:
                db.close()
        return None if row is None else {'id': row['id'], 'name': row['name'], 'snapshot_id': row['snapshot_id'],
                                         'ops': json.loads(row['ops_json']), 'created_at': row['created_at']}

    def list(self):
        with closing(self._connect()) as db:
            rows = db.execute('SELECT id, name, snapshot_id, ops_json, created_at FROM scenarios ORDER BY id DESC').fetchall()
        return [{'id': r['id'], 'name': r['name'], 'snapshot_id': r['snapshot_id'],
                 'op_count': len(json.loads(r['ops_json'])), 'created_at': r['created_at']} for r in rows]
