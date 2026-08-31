from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import VMRequest, Server
from ec2_instances import EC2_INSTANCE_TYPES
from scheduler import Scheduler
app = FastAPI(
    title="Cloud Resource Allocation Simulator",
    description="Simulates VM allocation across cloud servers.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

def create_servers():
    return [
        Server("server-01", 16, 32, 0.82),
        Server("server-02", 8, 16, 0.54),
        Server("server-03", 32, 64, 1.45),
        Server("server-04", 16, 32, 0.91)
    ]


servers = create_servers()
scheduler = Scheduler(servers)

@app.get("/")
def home():

    return {
        "message": "Cloud Resource Allocation Simulator API is running"
    }


@app.get("/servers")
def get_servers():

    return {
        "servers": [
            server.to_dict()
            for server in servers
        ]
    }


@app.post("/allocate")
def allocate_vm(vm: VMRequest):

    selected_server = scheduler.schedule(vm)

    if selected_server is None:

        return {
            "success": False,
            "message": "No server has enough resources for this VM."
        }

    selected_server.allocate(vm)

    estimated_cost = (
        selected_server.cost_per_hour
        * vm.duration
    )

    return {
        "success": True,

        "message": "VM allocated successfully.",

        "vm": {
            "name": vm.name,
            "cpu": vm.cpu,
            "ram": vm.ram,
            "duration": vm.duration
        },

        "allocation": {
            "server": selected_server.name,
            "algorithm": vm.algorithm,
            "estimated_cost": round(
                estimated_cost,
                2
            )
        },

        "server_state": selected_server.to_dict()
    }


@app.post("/reset")
def reset_simulation():

    global servers,scheduler

    servers = create_servers()
    scheduler=Scheduler(servers)
    return {
        "success": True,
        "message": "Simulation reset successfully."
    }


@app.get("/metrics")
def get_metrics():

    total_cpu = 0
    available_cpu = 0

    total_ram = 0
    available_ram = 0

    hourly_cost = 0
    active_vms = 0

    for server in servers:

        total_cpu += server.total_cpu
        available_cpu += server.available_cpu

        total_ram += server.total_ram
        available_ram += server.available_ram

        active_vms += len(server.vms)

        if server.vms:
            hourly_cost += server.cost_per_hour

    cpu_utilization = (
        (total_cpu - available_cpu)
        / total_cpu
    ) * 100

    ram_utilization = (
        (total_ram - available_ram)
        / total_ram
    ) * 100

    return {
        "active_vms": active_vms,

        "cpu_utilization": round(
            cpu_utilization,
            2
        ),

        "ram_utilization": round(
            ram_utilization,
            2
        ),

        "hourly_cost": round(
            hourly_cost,
            2
        )
    }

@app.get("/ec2/instances")
def get_ec2_instances():
    return {
        "instances": list(
            EC2_INSTANCE_TYPES.values()
        )
    }