import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "cloudlab.db")

def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn

@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()

def init_db():
    # sqlite3.executescript manages its own transaction boundaries, so schema
    # creation is intentionally performed on a plain connection first.
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS servers (
            name TEXT PRIMARY KEY, total_cpu INTEGER NOT NULL, total_ram INTEGER NOT NULL,
            cost_per_hour REAL NOT NULL, available_cpu INTEGER NOT NULL, available_ram INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vm_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, cpu INTEGER NOT NULL,
            ram INTEGER NOT NULL, duration REAL NOT NULL, algorithm TEXT NOT NULL,
            server_name TEXT NOT NULL, estimated_cost REAL NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS storage_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, storage_type TEXT NOT NULL,
            size_gb REAL NOT NULL, data TEXT NOT NULL DEFAULT '', monthly_cost REAL NOT NULL,
            latency_ms REAL NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cloud_config (
            id INTEGER PRIMARY KEY CHECK(id=1), read_replicas INTEGER NOT NULL,
            shards INTEGER NOT NULL, backup_mode TEXT NOT NULL, zones INTEGER NOT NULL,
            cache_enabled INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS primary_records (
            key TEXT PRIMARY KEY, value_json TEXT NOT NULL, shard_id INTEGER NOT NULL,
            version INTEGER NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS replica_records (
            replica_id INTEGER NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL,
            shard_id INTEGER NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(replica_id, key)
        );
        CREATE TABLE IF NOT EXISTS replication_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT, replica_id INTEGER NOT NULL, key TEXT NOT NULL,
            value_json TEXT NOT NULL, shard_id INTEGER NOT NULL, version INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS backup_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, value_json TEXT NOT NULL,
            shard_id INTEGER NOT NULL, version INTEGER NOT NULL, mode TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS backup_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, value_json TEXT NOT NULL,
            shard_id INTEGER NOT NULL, version INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cache_entries (
            key TEXT PRIMARY KEY, value_json TEXT NOT NULL, version INTEGER NOT NULL,
            hits INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS routing_counter (
            id INTEGER PRIMARY KEY CHECK(id=1), counter INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS managed_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_name TEXT NOT NULL,
            instance_type TEXT NOT NULL,
            family TEXT NOT NULL,
            vcpu INTEGER NOT NULL,
            ram_gb INTEGER NOT NULL,
            storage_gb INTEGER NOT NULL,
            zone TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('running','stopped','terminated')),
            price_per_hour REAL NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            stopped_at TEXT,
            terminated_at TEXT,
            accumulated_seconds INTEGER NOT NULL DEFAULT 0,
            assigned_server TEXT,
            FOREIGN KEY(assigned_server) REFERENCES servers(name)
        );
        CREATE TABLE IF NOT EXISTS instance_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('start','stop','terminate')),
            run_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','completed','failed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            error TEXT,
            FOREIGN KEY(instance_id) REFERENCES managed_instances(id)
        );
        CREATE INDEX IF NOT EXISTS idx_instance_schedules_due ON instance_schedules(status, run_at);
        INSERT OR IGNORE INTO routing_counter(id,counter) VALUES(1,0);
        """)
    finally:
        conn.close()
    with transaction() as c:
        c.execute("INSERT OR IGNORE INTO cloud_config (id, read_replicas, shards, backup_mode, zones, cache_enabled) VALUES (1, 2, 3, 'sync', 3, 1)")
        seed_servers(c)

def seed_servers(c):
    defaults = [
        ("server-01", 16, 32, 69.70),
        ("server-02", 8, 16, 45.90),
        ("server-03", 32, 64, 123.25),
        ("server-04", 16, 32, 77.35),
    ]
    count = c.execute("SELECT COUNT(*) AS n FROM servers").fetchone()["n"]
    if count == 0:
        for name, cpu, ram, cost in defaults:
            c.execute("INSERT INTO servers VALUES (?, ?, ?, ?, ?, ?)",
                      (name, cpu, ram, cost, cpu, ram))

def log_event(c, event_type, message):
    c.execute("INSERT INTO activity(event_type, message) VALUES (?, ?)", (event_type, message))
