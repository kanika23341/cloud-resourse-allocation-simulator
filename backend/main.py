from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, connect, transaction, log_event
from models import VMRequest, ResetRequest
from scheduler import Server, select_server
from ec2_instances import EC2_INSTANCE_TYPES
from cloud_services import router as cloud_services_router, start_background_workers, stop_background_workers
from instance_service import router as instance_router, schedule_worker
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    backup_task = await start_background_workers()
    schedule_task = asyncio.create_task(schedule_worker())
    yield
    schedule_task.cancel()
    try:
        await schedule_task
    except asyncio.CancelledError:
        pass
    await stop_background_workers(backup_task)

app = FastAPI(
    title="CloudLab — Cloud Resource Allocation Simulator",
    description="A persistent local simulator for VM scheduling, storage, replication, backups, sharding, and zones.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cloud_services_router)
app.include_router(instance_router)

def _servers(c):
    rows = c.execute("SELECT * FROM servers ORDER BY name").fetchall()
    vms = c.execute("SELECT * FROM vm_allocations ORDER BY id").fetchall()
    by_server = {r["name"]: [] for r in rows}
    for vm in vms:
        if vm["server_name"] in by_server:
            by_server[vm["server_name"]].append({
                "id": vm["id"], "name": vm["name"], "cpu": vm["cpu"], "ram": vm["ram"],
                "duration": vm["duration"], "algorithm": vm["algorithm"], "estimated_cost": vm["estimated_cost"]
            })
    try:
        instances = c.execute("SELECT id, instance_name, vcpu, ram_gb, assigned_server FROM managed_instances WHERE status='running'").fetchall()
        for instance in instances:
            if instance["assigned_server"] in by_server:
                by_server[instance["assigned_server"]].append({
                    "id": f"ec2-{instance['id']}", "name": instance["instance_name"],
                    "cpu": instance["vcpu"], "ram": instance["ram_gb"],
                    "algorithm": "EC2 instance", "estimated_cost": 0
                })
    except Exception:
        # Keep /servers compatible with a database created by an older project version.
        pass
    result = []
    for row in rows:
        item = dict(row)
        item["used_cpu"] = item["total_cpu"] - item["available_cpu"]
        item["used_ram"] = item["total_ram"] - item["available_ram"]
        item["vms"] = by_server[row["name"]]
        result.append(item)
    return result

@app.get("/")
def home():
    return {"message": "CloudLab API is running", "docs": "/docs", "database": "SQLite"}

@app.get("/health")
def health():
    c = connect()
    try:
        c.execute("SELECT 1").fetchone()
        return {"status": "healthy", "database": "connected"}
    finally:
        c.close()

@app.get("/servers")
def get_servers():
    c = connect()
    try:
        return {"servers": _servers(c)}
    finally:
        c.close()

@app.post("/allocate")
def allocate_vm(vm: VMRequest):
    request = vm.model_dump()
    with transaction() as c:
        rows = c.execute("SELECT * FROM servers ORDER BY name").fetchall()
        servers = [Server(name=r["name"], total_cpu=r["total_cpu"], total_ram=r["total_ram"],
                          cost_per_hour=r["cost_per_hour"], available_cpu=r["available_cpu"],
                          available_ram=r["available_ram"]) for r in rows]
        selected = select_server(request, servers)
        if selected is None:
            raise HTTPException(409, "No server has enough free CPU and RAM for this VM.")
        cost = round(selected.cost_per_hour * vm.duration, 2)
        c.execute("UPDATE servers SET available_cpu=?, available_ram=? WHERE name=?",
                  (selected.available_cpu - vm.cpu, selected.available_ram - vm.ram, selected.name))
        cur = c.execute("""INSERT INTO vm_allocations(name,cpu,ram,duration,algorithm,server_name,estimated_cost)
                            VALUES(?,?,?,?,?,?,?)""",
                        (vm.name, vm.cpu, vm.ram, vm.duration, vm.algorithm, selected.name, cost))
        log_event(c, "compute", f"Allocated VM '{vm.name}' to {selected.name} using {vm.algorithm}.")
        server = c.execute("SELECT * FROM servers WHERE name=?", (selected.name,)).fetchone()
        state = dict(server)
        state["used_cpu"] = state["total_cpu"] - state["available_cpu"]
        state["used_ram"] = state["total_ram"] - state["available_ram"]
    return {"success": True, "message": "VM allocated successfully.", "vm": {**request, "id": cur.lastrowid},
            "allocation": {"server": selected.name, "algorithm": vm.algorithm, "estimated_cost": cost},
            "server_state": state}

@app.post("/reset")
def reset_simulation():
    with transaction() as c:
        c.execute("DELETE FROM vm_allocations")
        c.execute("UPDATE servers SET available_cpu=total_cpu, available_ram=total_ram")
        # Re-reserve host capacity for currently running EC2-style instances.
        running = c.execute("SELECT assigned_server, vcpu, ram_gb FROM managed_instances WHERE status='running'").fetchall()
        for instance in running:
            if instance["assigned_server"]:
                c.execute("UPDATE servers SET available_cpu=MAX(0, available_cpu-?), available_ram=MAX(0, available_ram-?) WHERE name=?",
                          (instance["vcpu"], instance["ram_gb"], instance["assigned_server"]))
        log_event(c, "system", "Legacy VM allocations reset; managed instances and their reserved capacity were preserved.")
    return {"success": True, "message": "Legacy VM allocations reset. Managed instances, storage, and database records were preserved."}

@app.get("/metrics")
def get_metrics():
    c = connect()
    try:
        servers = c.execute("SELECT * FROM servers").fetchall()
        total_cpu = sum(r["total_cpu"] for r in servers)
        free_cpu = sum(r["available_cpu"] for r in servers)
        total_ram = sum(r["total_ram"] for r in servers)
        free_ram = sum(r["available_ram"] for r in servers)
        active_legacy = c.execute("SELECT COUNT(*) n FROM vm_allocations").fetchone()["n"]
        active_instances = c.execute("SELECT COUNT(*) n FROM managed_instances WHERE status='running'").fetchone()["n"]
        active = active_legacy + active_instances
        hourly_cost = sum(r["cost_per_hour"] for r in servers if r["available_cpu"] < r["total_cpu"] or r["available_ram"] < r["total_ram"])
        storage = c.execute("SELECT COALESCE(SUM(monthly_cost),0) n FROM storage_objects").fetchone()["n"]
        db_count = c.execute("SELECT COUNT(*) n FROM primary_records").fetchone()["n"]
        running_instance_cost = c.execute("SELECT COALESCE(SUM(price_per_hour),0) n FROM managed_instances WHERE status='running'").fetchone()["n"]
        return {"active_vms": active, "running_instances": active_instances,
                "cpu_utilization": round((total_cpu-free_cpu)/total_cpu*100, 2) if total_cpu else 0,
                "ram_utilization": round((total_ram-free_ram)/total_ram*100, 2) if total_ram else 0,
                "hourly_cost": round(hourly_cost, 2), "instance_hourly_cost": round(running_instance_cost, 2), "storage_monthly_cost": round(storage, 4),
                "database_records": db_count, "servers": len(servers)}
    finally:
        c.close()

@app.get("/ec2/instances")
def get_ec2_instances():
    return {"instances": list(EC2_INSTANCE_TYPES.values())}
