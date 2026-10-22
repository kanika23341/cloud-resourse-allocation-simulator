from dataclasses import dataclass, field
from typing import Any

@dataclass
class Server:
    name: str
    total_cpu: int
    total_ram: int
    cost_per_hour: float
    available_cpu: int | None = None
    available_ram: int | None = None
    vms: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.available_cpu is None:
            self.available_cpu = self.total_cpu
        if self.available_ram is None:
            self.available_ram = self.total_ram

    def can_allocate(self, vm):
        return self.available_cpu >= vm["cpu"] and self.available_ram >= vm["ram"]

    def allocate(self, vm):
        self.available_cpu -= vm["cpu"]
        self.available_ram -= vm["ram"]
        self.vms.append(vm)

    def to_dict(self):
        return {
            "name": self.name,
            "total_cpu": self.total_cpu,
            "available_cpu": self.available_cpu,
            "used_cpu": self.total_cpu - self.available_cpu,
            "total_ram": self.total_ram,
            "available_ram": self.available_ram,
            "used_ram": self.total_ram - self.available_ram,
            "cost_per_hour": self.cost_per_hour,
            "vms": self.vms,
        }

def first_fit(vm, servers):
    for server in servers:
        if server.can_allocate(vm):
            return server
    return None

def best_fit(vm, servers):
    suitable = [s for s in servers if s.can_allocate(vm)]
    if not suitable:
        return None
    return min(suitable, key=lambda s: (s.available_cpu - vm["cpu"]) +
                                      (s.available_ram - vm["ram"]))

def select_server(vm, servers):
    return first_fit(vm, servers) if vm["algorithm"] == "first_fit" else best_fit(vm, servers)
