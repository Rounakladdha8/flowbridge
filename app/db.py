import json, os, sqlite3

def conn():
    c = sqlite3.connect(os.getenv("DB_PATH", "app.db")); c.row_factory = sqlite3.Row; return c

def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS requests(
          id INTEGER PRIMARY KEY, text TEXT, extracted TEXT, citations TEXT,
          status TEXT, booking_id TEXT, error TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS executions(
          id INTEGER PRIMARY KEY, request_id INT, ok INT, detail TEXT,
          at TEXT DEFAULT CURRENT_TIMESTAMP);""")

def _row(r):
    if not r: return None
    d = dict(r); d["extracted"] = json.loads(d["extracted"]); d["citations"] = json.loads(d["citations"]); return d

def insert_request(text, info, cites, status):
    with conn() as c:
        return c.execute("INSERT INTO requests(text,extracted,citations,status) VALUES(?,?,?,?)",
                         (text, json.dumps(info), json.dumps(cites), status)).lastrowid

def update_request(rid, text, info, cites, status):
    with conn() as c:
        c.execute("UPDATE requests SET text=?,extracted=?,citations=?,status=? WHERE id=?",
                  (text, json.dumps(info), json.dumps(cites), status, rid))

def get_request(rid):
    with conn() as c: return _row(c.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone())

def list_requests():
    with conn() as c: return [_row(r) for r in c.execute("SELECT * FROM requests ORDER BY id DESC")]

def mark(rid, status, booking_id=None, error=None):
    with conn() as c:
        c.execute("UPDATE requests SET status=?,booking_id=?,error=? WHERE id=?", (status, booking_id, error, rid))

def log_exec(rid, ok, detail):
    with conn() as c: c.execute("INSERT INTO executions(request_id,ok,detail) VALUES(?,?,?)", (rid, int(ok), detail))

def executions(rid):
    with conn() as c: return [dict(r) for r in c.execute("SELECT * FROM executions WHERE request_id=? ORDER BY id", (rid,))]
