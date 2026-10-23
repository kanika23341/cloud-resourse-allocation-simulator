from datetime import datetime, timezone
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from database import connect, transaction, log_event
from ec2_instances import EC2_INSTANCE_TYPES
from scheduler import Server, select_server

router = APIRouter(prefix="/ec2", tags=["EC2-style instances"])

class LaunchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    instance_type: str
    storage_gb: int = Field(default=20, ge=8, le=2048)
    zone: str = Field(default="zone-a", pattern=r"^zone-[a-f]$")
    algorithm: Literal["first_fit", "best_fit"] = "best_fit"
    start_now: bool = True

class ScheduleRequest(BaseModel):
    action: Literal["start", "stop", "terminate"]
    run_at: datetime


def now_utc():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def instance_dict(row, at=None):
    d = dict(row)
    at = at or now_utc()
    started = parse_time(d.get("started_at"))
    terminated = parse_time(d.get("terminated_at"))
    created = parse_time(d.get("created_at"))
    accumulated = int(d.get("accumulated_seconds", 0))
    if d["status"] == "running" and started:
        accumulated += max(0, int((at - started).total_seconds()))
    d["runtime_seconds"] = accumulated
    d["runtime_hours"] = round(accumulated / 3600, 5)
    d["compute_cost"] = round(accumulated * float(d["price_per_hour"]) / 3600, 4)
    storage_end = terminated or at
    storage_seconds = max(0, int((storage_end - created).total_seconds())) if created else 0
    d["storage_cost"] = round(float(d["storage_gb"]) * 0.10 * storage_seconds / (30 * 24 * 3600), 4)
    d["total_cost"] = round(d["compute_cost"] + d["storage_cost"], 4)
    d["elapsed_label"] = f"{accumulated // 3600:02d}:{(accumulated % 3600) // 60:02d}:{accumulated % 60:02d}"
    return d


def get_instance(c, instance_id):
    row = c.execute("SELECT * FROM managed_instances WHERE id=?", (instance_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Instance not found.")
    return row


def reserve_capacity(c, instance, algorithm="best_fit"):
    request = {"cpu": instance["vcpu"], "ram": instance["ram_gb"], "algorithm": algorithm}
    rows = c.execute("SELECT * FROM servers ORDER BY name").fetchall()
    servers = [Server(name=r["name"], total_cpu=r["total_cpu"], total_ram=r["total_ram"],
                      cost_per_hour=r["cost_per_hour"], available_cpu=r["available_cpu"],
                      available_ram=r["available_ram"]) for r in rows]
    selected = select_server(request, servers)
    if selected is None:
        raise HTTPException(409, "No host server has enough available CPU and RAM for this instance.")
    c.execute("UPDATE servers SET available_cpu=?, available_ram=? WHERE name=?",
              (selected.available_cpu - instance["vcpu"], selected.available_ram - instance["ram_gb"], selected.name))
    return selected.name


def release_capacity(c, instance):
    if instance["assigned_server"]:
        c.execute("UPDATE servers SET available_cpu=MIN(total_cpu, available_cpu + ?), available_ram=MIN(total_ram, available_ram + ?) WHERE name=?",
                  (instance["vcpu"], instance["ram_gb"], instance["assigned_server"]))


def start_instance(c, row, algorithm="best_fit"):
    if row["status"] == "terminated":
        raise HTTPException(409, "A terminated instance cannot be started.")
    if row["status"] == "running":
        return dict(row)
    server = reserve_capacity(c, row, algorithm)
    started = now_utc().isoformat()
    c.execute("UPDATE managed_instances SET status='running', started_at=?, assigned_server=? WHERE id=?",
              (started, server, row["id"]))
    log_event(c, "compute", f"Started instance {row['instance_name']} on {server}.")
    return dict(c.execute("SELECT * FROM managed_instances WHERE id=?", (row["id"],)).fetchone())


def stop_instance(c, row):
    if row["status"] == "terminated":
        raise HTTPException(409, "A terminated instance cannot be stopped.")
    if row["status"] == "stopped":
        return dict(row)
    started = parse_time(row["started_at"])
    seconds = max(0, int((now_utc() - started).total_seconds())) if started else 0
    release_capacity(c, row)
    c.execute("UPDATE managed_instances SET status='stopped', started_at=NULL, stopped_at=?, accumulated_seconds=accumulated_seconds+?, assigned_server=NULL WHERE id=?",
              (now_utc().isoformat(), seconds, row["id"]))
    log_event(c, "compute", f"Stopped instance {row['instance_name']}; recorded {seconds} billable seconds.")
    return dict(c.execute("SELECT * FROM managed_instances WHERE id=?", (row["id"],)).fetchone())


def terminate_instance(c, row):
    if row["status"] == "terminated":
        return dict(row)
    if row["status"] == "running":
        stop_instance(c, row)
    c.execute("UPDATE managed_instances SET status='terminated', terminated_at=?, started_at=NULL, assigned_server=NULL WHERE id=?",
              (now_utc().isoformat(), row["id"]))
    log_event(c, "compute", f"Terminated instance {row['instance_name']}.")
    return dict(c.execute("SELECT * FROM managed_instances WHERE id=?", (row["id"],)).fetchone())


@router.get("/managed-instances")
def list_managed_instances(include_terminated: bool = True):
    c = connect()
    try:
        sql = "SELECT * FROM managed_instances"
        if not include_terminated:
            sql += " WHERE status != 'terminated'"
        rows = c.execute(sql + " ORDER BY id DESC").fetchall()
        instances = [instance_dict(r) for r in rows]
        return {"instances": instances,
                "summary": {"running": sum(x["status"] == "running" for x in instances),
                            "stopped": sum(x["status"] == "stopped" for x in instances),
                            "terminated": sum(x["status"] == "terminated" for x in instances),
                            "accrued_cost": round(sum(x["total_cost"] for x in instances), 4),
                            "compute_cost": round(sum(x["compute_cost"] for x in instances), 4),
                            "storage_cost": round(sum(x["storage_cost"] for x in instances), 4)}}
    finally:
        c.close()


@router.post("/managed-instances")
def launch_instance(req: LaunchRequest):
    spec = EC2_INSTANCE_TYPES.get(req.instance_type)
    if not spec:
        raise HTTPException(422, "Unknown instance type.")
    with transaction() as c:
        created = now_utc().isoformat()
        cur = c.execute("""INSERT INTO managed_instances
            (instance_name, instance_type, family, vcpu, ram_gb, storage_gb, zone, status, price_per_hour,
             created_at, started_at, accumulated_seconds, assigned_server)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'stopped', ?, ?, NULL, 0, NULL)""",
            (req.name.strip(), spec["name"], spec["family"], spec["vcpu"], spec["ram_gb"], req.storage_gb,
             req.zone, spec["price_per_hour"], created))
        row = c.execute("SELECT * FROM managed_instances WHERE id=?", (cur.lastrowid,)).fetchone()
        if req.start_now:
            start_instance(c, row, req.algorithm)
        else:
            log_event(c, "compute", f"Created stopped instance {req.name.strip()}.")
        row = c.execute("SELECT * FROM managed_instances WHERE id=?", (cur.lastrowid,)).fetchone()
        return {"success": True, "instance": instance_dict(row), "message": "Instance launched." if req.start_now else "Instance created in stopped state."}


@router.post("/managed-instances/{instance_id}/action/{action}")
def instance_action(instance_id: int, action: Literal["start", "stop", "terminate"]):
    with transaction() as c:
        row = get_instance(c, instance_id)
        if action == "start":
            updated = start_instance(c, row)
        elif action == "stop":
            updated = stop_instance(c, row)
        else:
            updated = terminate_instance(c, row)
        return {"success": True, "instance": instance_dict(updated), "message": f"Instance {action} action completed."}


@router.get("/managed-instances/{instance_id}")
def get_managed_instance(instance_id: int):
    c = connect()
    try:
        return {"instance": instance_dict(get_instance(c, instance_id))}
    finally:
        c.close()


@router.post("/managed-instances/{instance_id}/schedules")
def create_schedule(instance_id: int, req: ScheduleRequest):
    run_at = req.run_at
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)
    run_at = run_at.astimezone(timezone.utc)
    if run_at <= now_utc():
        raise HTTPException(422, "Scheduled time must be in the future.")
    with transaction() as c:
        get_instance(c, instance_id)
        cur = c.execute("INSERT INTO instance_schedules(instance_id, action, run_at, status) VALUES (?, ?, ?, 'pending')",
                        (instance_id, req.action, run_at.isoformat()))
        log_event(c, "schedule", f"Scheduled {req.action} for instance #{instance_id} at {run_at.isoformat()}.")
        return {"success": True, "schedule": dict(c.execute("SELECT * FROM instance_schedules WHERE id=?", (cur.lastrowid,)).fetchone())}


@router.get("/schedules")
def list_schedules():
    c = connect()
    try:
        rows = c.execute("""SELECT s.*, i.instance_name FROM instance_schedules s
                           JOIN managed_instances i ON i.id=s.instance_id ORDER BY s.run_at""").fetchall()
        return {"schedules": [dict(r) for r in rows]}
    finally:
        c.close()


async def schedule_worker():
    while True:
        try:
            with transaction() as c:
                due = c.execute("SELECT * FROM instance_schedules WHERE status='pending' AND run_at<=? ORDER BY run_at LIMIT 25",
                                (now_utc().isoformat(),)).fetchall()
                for job in due:
                    try:
                        row = get_instance(c, job["instance_id"])
                        if job["action"] == "start":
                            start_instance(c, row)
                        elif job["action"] == "stop":
                            stop_instance(c, row)
                        else:
                            terminate_instance(c, row)
                        c.execute("UPDATE instance_schedules SET status='completed', completed_at=? WHERE id=?",
                                  (now_utc().isoformat(), job["id"]))
                    except Exception as exc:
                        c.execute("UPDATE instance_schedules SET status='failed', completed_at=?, error=? WHERE id=?",
                                  (now_utc().isoformat(), str(exc)[:500], job["id"]))
                        log_event(c, "schedule", f"Schedule #{job['id']} failed: {str(exc)[:300]}")
        except Exception:
            # A later polling cycle retries database access; individual failed jobs are marked above.
            pass
        await asyncio.sleep(2)
