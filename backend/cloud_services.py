import asyncio
import json
import time
from fastapi import APIRouter, HTTPException
from database import connect, transaction, log_event
from models import StorageRequest, DatabaseConfigRequest, DatabaseWriteRequest
router = APIRouter(prefix="/cloud", tags=["Cloud Services"])

STORAGE_TIERS = {
    "archive": {"label": "Archive", "cost_per_gb_month": 0.35, "latency_ms": 500, "description": "Lowest-cost, slow retrieval"},
    "large": {"label": "Large Objects", "cost_per_gb_month": 1.70, "latency_ms": 100, "description": "General large-object storage"},
    "small": {"label": "Small Objects", "cost_per_gb_month": 2.10, "latency_ms": 80, "description": "Small files and documents"},
    "nosql": {"label": "NoSQL", "cost_per_gb_month": 2.55, "latency_ms": 15, "description": "Flexible key-value/document workloads"},
    "sql": {"label": "SQL", "cost_per_gb_month": 3.00, "latency_ms": 10, "description": "Structured relational records"},
    "fast_retrieval": {"label": "Fast Retrieval", "cost_per_gb_month": 5.10, "latency_ms": 2, "description": "Low-latency access tier"},
}

_replication_task = None
_replication_wakeup = None
_stop_worker = False

def _config(c):
    row = c.execute("SELECT * FROM cloud_config WHERE id=1").fetchone()
    return dict(row)

def _apply_replication_batch(limit=100):
    processed = 0
    with transaction() as c:
        jobs = c.execute("SELECT * FROM replication_queue WHERE status='pending' ORDER BY id LIMIT ?", (limit,)).fetchall()
        for job in jobs:
            c.execute("""INSERT INTO replica_records(replica_id,key,value_json,shard_id,version,updated_at)
                         VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
                         ON CONFLICT(replica_id,key) DO UPDATE SET
                         value_json=excluded.value_json, shard_id=excluded.shard_id,
                         version=excluded.version, updated_at=CURRENT_TIMESTAMP
                         WHERE excluded.version >= replica_records.version""",
                      (job["replica_id"], job["key"], job["value_json"], job["shard_id"], job["version"]))
            c.execute("UPDATE replication_queue SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=?", (job["id"],))
            processed += 1
        if processed:
            log_event(c, "replication", f"Applied {processed} asynchronous replica update(s).")
    return processed

async def _replication_worker():
    while not _stop_worker:
        try:
            _apply_replication_batch()
        except Exception:
            # Keep the worker alive & pending jobs remain visible for diagnosis.
            pass
        await asyncio.sleep(0.35)

async def start_replication_worker():
    global _replication_task, _stop_worker
    _stop_worker = False
    if _replication_task is None or _replication_task.done():
        _replication_task = asyncio.create_task(_replication_worker())

async def stop_replication_worker():
    global _stop_worker, _replication_task
    _stop_worker = True
    if _replication_task:
        _replication_task.cancel()
        try:
            await _replication_task
        except asyncio.CancelledError:
            pass
        _replication_task = None

def _record_dict(row):
    return dict(row) if row else None

@router.get("/storage/types")
def storage_types():
    return {"tiers": [{"key": key, **value} for key, value in STORAGE_TIERS.items()]}

@router.post("/storage")
def create_storage(req: StorageRequest):
    tier = STORAGE_TIERS[req.storage_type]
    monthly_cost = round(req.size_gb * tier["cost_per_gb_month"], 4)
    with transaction() as c:
        cur = c.execute("""INSERT INTO storage_objects(name,storage_type,size_gb,data,monthly_cost,latency_ms)
                           VALUES(?,?,?,?,?,?)""",
                        (req.name, req.storage_type, req.size_gb, req.data, monthly_cost, tier["latency_ms"]))
        row = c.execute("SELECT * FROM storage_objects WHERE id=?", (cur.lastrowid,)).fetchone()
        log_event(c, "storage", f"Created {req.name} in {tier['label']} storage ({req.size_gb:g} GB).")
    return {"success": True, "object": dict(row)}

@router.get("/storage")
def list_storage():
    c = connect()
    try:
        rows = c.execute("SELECT * FROM storage_objects ORDER BY id DESC").fetchall()
        return {"objects": [dict(r) for r in rows],
                "total_monthly_cost": round(sum(r["monthly_cost"] for r in rows), 4)}
    finally:
        c.close()

@router.delete("/storage/{object_id}")
def delete_storage(object_id: int):
    with transaction() as c:
        row = c.execute("SELECT name FROM storage_objects WHERE id=?", (object_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Storage object not found.")
        c.execute("DELETE FROM storage_objects WHERE id=?", (object_id,))
        log_event(c, "storage", f"Deleted storage object {row['name']}.")
    return {"success": True, "message": "Storage object deleted."}

@router.post("/database/configure")
def configure_database(req: DatabaseConfigRequest):
    with transaction() as c:
        c.execute("""UPDATE cloud_config SET read_replicas=?, shards=?, backup_mode=?, zones=?, cache_enabled=? WHERE id=1""",
                  (req.read_replicas, req.shards, req.backup_mode, req.zones, int(req.cache_enabled)))
        # Recreate replica topology from the new configuration
        c.execute("DELETE FROM replica_records")
        c.execute("DELETE FROM replication_queue WHERE status='pending'")
        records = c.execute("SELECT * FROM primary_records").fetchall()

        for rec in records:
            if req.backup_mode == "sync":
                c.execute("""INSERT INTO backup_records(key,value_json,shard_id,version,mode,status)
                             VALUES(?,?,?,?, 'sync', 'completed')""",
                          (rec["key"], rec["value_json"], rec["shard_id"], rec["version"]))
            for replica_id in range(1, req.read_replicas + 1):
                c.execute("""INSERT INTO replication_queue(replica_id,key,value_json,shard_id,version,status)
                             VALUES(?,?,?,?,?,'pending')""",
                          (replica_id, rec["key"], rec["value_json"], rec["shard_id"], rec["version"]))
                
        if not req.cache_enabled:
            c.execute("DELETE FROM cache_entries")
        log_event(c, "database", f"Database configured: {req.read_replicas} replicas, {req.shards} shards, {req.backup_mode} backups, {req.zones} zones.")
    
    return {"success": True, "config": {"read_replicas": req.read_replicas, "shards": req.shards,
            "backup_mode": req.backup_mode, "zones": req.zones, "cache_enabled": req.cache_enabled},
            "message": "Configuration saved. Existing records are queued for replica synchronization."
            }

@router.get("/database")
def database_status():
    c = connect()
    try:
        config = _config(c)
        primary_count = c.execute("SELECT COUNT(*) n FROM primary_records").fetchone()["n"]
        replica_count = c.execute("SELECT COUNT(*) n FROM replica_records").fetchone()["n"]
        pending = c.execute("SELECT COUNT(*) n FROM replication_queue WHERE status='pending'").fetchone()["n"]
        completed = c.execute("SELECT COUNT(*) n FROM replication_queue WHERE status='completed'").fetchone()["n"]
        backups = c.execute("SELECT COUNT(*) n FROM backup_records WHERE status='completed'").fetchone()["n"]
        cache_hits = c.execute("SELECT COALESCE(SUM(hits),0) n FROM cache_entries").fetchone()["n"]
        return {"config": config, "primary_records": primary_count, "replica_record_copies": replica_count,
                "pending_replications": pending, "completed_replications": completed,
                "completed_backups": backups, "cache_hits": cache_hits}
    finally:
        c.close()

@router.post("/database/write")
def write_record(req: DatabaseWriteRequest):
    value_json = json.dumps(req.value, separators=(",", ":"), sort_keys=True)
    with transaction() as c:
        cfg = _config(c)
        previous = c.execute("SELECT version FROM primary_records WHERE key=?", (req.key,)).fetchone()
        version = (previous["version"] + 1) if previous else 1
        shard_id = (sum(req.key.encode("utf-8")) % cfg["shards"]) + 1
        c.execute("""INSERT INTO primary_records(key,value_json,shard_id,version,updated_at)
                     VALUES(?,?,?,?,CURRENT_TIMESTAMP)
                     ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                     shard_id=excluded.shard_id, version=excluded.version, updated_at=CURRENT_TIMESTAMP""",
                  (req.key, value_json, shard_id, version))
        backup_status = "not_requested"
        if cfg["backup_mode"] == "sync":
            c.execute("""INSERT INTO backup_records(key,value_json,shard_id,version,mode,status)
                         VALUES(?,?,?,?, 'sync', 'completed')""",
                      (req.key, value_json, shard_id, version))
            backup_status = "completed_before_ack"
        else:
            c.execute("""INSERT INTO backup_queue(key,value_json,shard_id,version,status)
                         VALUES(?,?,?,?,'pending')""",
                      (req.key, value_json, shard_id, version))
            backup_status = "queued"
        for replica_id in range(1, cfg["read_replicas"] + 1):
            c.execute("""INSERT INTO replication_queue(replica_id,key,value_json,shard_id,version,status)
                         VALUES(?,?,?,?,?,'pending')""",
                      (replica_id, req.key, value_json, shard_id, version))
        if cfg["cache_enabled"]:
            c.execute("DELETE FROM cache_entries WHERE key=?", (req.key,))
        log_event(c, "write", f"Wrote key '{req.key}' to primary shard {shard_id}; replica updates queued.")
    return {"success": True, "key": req.key, "version": version, "shard_id": shard_id,
            "backup_mode": cfg["backup_mode"], "backup_status": backup_status,
            "replication_status": "queued", "replicas_queued": cfg["read_replicas"],
            "message": "Primary write committed. Async replica updates are queued."}

@router.get("/database/read/{key:path}")
def read_record(key: str):
    c = connect()
    try:
        cfg = _config(c)
        if cfg["cache_enabled"]:
            cached = c.execute("SELECT * FROM cache_entries WHERE key=?", (key,)).fetchone()
            if cached:
                c.execute("UPDATE cache_entries SET hits=hits+1 WHERE key=?", (key,))
                return {"success": True, "key": key, "value": json.loads(cached["value_json"]),
                        "source": "cache", "version": cached["version"], "cache_hit": True,
                        "consistency": "cached value; may be stale until invalidated"}
        replicas = cfg["read_replicas"]
        selected_replica = 0
        if replicas:
            c.execute("CREATE TABLE IF NOT EXISTS routing_counter (id INTEGER PRIMARY KEY CHECK(id=1), counter INTEGER NOT NULL)")
            c.execute("INSERT OR IGNORE INTO routing_counter VALUES(1,0)")
            c.execute("UPDATE routing_counter SET counter=counter+1 WHERE id=1")
            selected_replica = (c.execute("SELECT counter FROM routing_counter WHERE id=1").fetchone()["counter"] - 1) % replicas + 1
            row = c.execute("SELECT * FROM replica_records WHERE replica_id=? AND key=?", (selected_replica, key)).fetchone()
            source = f"replica-{selected_replica}"
        else:
            row = None
            source = "primary"
        if row is None:
            row = c.execute("SELECT * FROM primary_records WHERE key=?", (key,)).fetchone()
            source = "primary-fallback" if replicas else "primary"
        if row is None:
            raise HTTPException(404, "Key not found.")
        value = json.loads(row["value_json"])
        if cfg["cache_enabled"]:
            c.execute("""INSERT INTO cache_entries(key,value_json,version,hits,updated_at)
                         VALUES(?,?,?,0,CURRENT_TIMESTAMP)
                         ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                         version=excluded.version, updated_at=CURRENT_TIMESTAMP""",
                      (key, row["value_json"], row["version"]))
        log_event(c, "read", f"Read key '{key}' from {source}.")
        return {"success": True, "key": key, "value": value, "source": source,
                "version": row["version"], "shard_id": row["shard_id"], "cache_hit": False,
                "consistency": "replica read may briefly lag primary" if source.startswith("replica") else "primary read"}
    finally:
        c.close()

@router.get("/database/backups")
def backup_history():
    c = connect()
    try:
        rows = c.execute("""SELECT id,key,value_json,shard_id,version,mode,status,created_at FROM backup_records
                           UNION ALL
                           SELECT -id AS id,key,value_json,shard_id,version,'async' AS mode,status,created_at FROM backup_queue WHERE status='pending'
                           ORDER BY id DESC LIMIT 100""").fetchall()
        return {"backups": [dict(r) for r in rows]}
    finally:
        c.close()

@router.get("/database/replicas")
def replica_status():
    c = connect()
    try:
        cfg = _config(c)
        replicas = []
        for replica_id in range(1, cfg["read_replicas"] + 1):
            rows = c.execute("SELECT COUNT(*) n, COALESCE(MAX(version),0) max_version FROM replica_records WHERE replica_id=?", (replica_id,)).fetchone()
            replicas.append({"replica_id": replica_id, "name": f"read-replica-{replica_id}",
                             "record_copies": rows["n"], "max_version": rows["max_version"]})
        pending = c.execute("SELECT COUNT(*) n FROM replication_queue WHERE status='pending'").fetchone()["n"]
        completed = c.execute("SELECT COUNT(*) n FROM replication_queue WHERE status='completed'").fetchone()["n"]
        return {"replicas": replicas, "pending": pending, "completed": completed}
    finally:
        c.close()

@router.get("/load-balancer")
def load_balancer_status():
    c = connect()
    try:
        cfg = _config(c)
        return {"strategy": "round_robin", "write_target": "primary",
                "read_targets": [f"read-replica-{i}" for i in range(1, cfg["read_replicas"] + 1)] or ["primary"],
                "shards": cfg["shards"], "backup_mode": cfg["backup_mode"],
                "zones": cfg["zones"], "cache_enabled": bool(cfg["cache_enabled"]),
                "routing_policy": "Writes -> primary; reads -> cache then round-robin replica; primary fallback if replica is behind"}
    finally:
        c.close()

@router.get("/zones")
def availability_zones():
    c = connect()
    try:
        cfg = _config(c)
        zones = [{"id": i, "name": f"zone-{chr(97+i)}", "status": "healthy", "shards": []}
                 for i in range(cfg["zones"])]
        for shard in range(1, cfg["shards"] + 1):
            zones[(shard - 1) % cfg["zones"]]["shards"].append(f"shard-{shard}")
        return {"zones": zones, "shards": cfg["shards"], "cache_enabled": bool(cfg["cache_enabled"]),
                "placement_policy": "round-robin shard placement across simulated zones"}
    finally:
        c.close()

@router.get("/activity")
def recent_activity(limit: int = 30):
    limit = max(1, min(limit, 100))
    c = connect()
    try:
        rows = c.execute("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return {"events": [dict(r) for r in rows]}
    finally:
        c.close()

async def process_async_backups():
    while True:
        try:
            with transaction() as c:
                jobs = c.execute("SELECT * FROM backup_queue WHERE status='pending' ORDER BY id LIMIT 100").fetchall()
                for job in jobs:
                    c.execute("""INSERT INTO backup_records(key,value_json,shard_id,version,mode,status)
                                 VALUES(?,?,?,?, 'async', 'completed')""",
                              (job["key"], job["value_json"], job["shard_id"], job["version"]))
                    c.execute("UPDATE backup_queue SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=?", (job["id"],))
                    log_event(c, "backup", f"Asynchronous backup completed for key '{job['key']}', version {job['version']}.")
        except Exception:
            pass
        await asyncio.sleep(0.5)

async def start_background_workers():
    await start_replication_worker()
    return asyncio.create_task(process_async_backups())

async def stop_background_workers(backup_task):
    await stop_replication_worker()
    if backup_task:
        backup_task.cancel()
        try:
            await backup_task
        except asyncio.CancelledError:
            pass
