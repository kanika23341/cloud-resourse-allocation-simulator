from pydantic import BaseModel


class VMRequest(BaseModel):
    name: str
    cpu: int
    ram: int
    duration: float
    algorithm: str = "best_fit"


class Server:
    def __init__(
        self,
        name: str,
        total_cpu: int,
        total_ram: int,
        cost_per_hour: float
    ):
        self.name = name
        self.total_cpu = total_cpu
        self.total_ram = total_ram

        self.available_cpu = total_cpu
        self.available_ram = total_ram

        self.cost_per_hour = cost_per_hour
        self.vms = []

    def can_allocate(self, vm: VMRequest) -> bool:
        return (
            self.available_cpu >= vm.cpu
            and self.available_ram >= vm.ram
        )

    def allocate(self, vm: VMRequest):
        self.available_cpu -= vm.cpu
        self.available_ram -= vm.ram

        self.vms.append(vm.name)

    def get_utilization(self):
        cpu_utilization = (
            (self.total_cpu - self.available_cpu)
            / self.total_cpu
        ) * 100

        ram_utilization = (
            (self.total_ram - self.available_ram)
            / self.total_ram
        ) * 100

        return {
            "cpu_utilization": round(cpu_utilization, 2),
            "ram_utilization": round(ram_utilization, 2)
        }

    def to_dict(self):
        utilization = self.get_utilization()

        return {
            "name": self.name,
            "total_cpu": self.total_cpu,
            "available_cpu": self.available_cpu,
            "total_ram": self.total_ram,
            "available_ram": self.available_ram,
            "cost_per_hour": self.cost_per_hour,
            "vms": self.vms,
            "cpu_utilization": utilization["cpu_utilization"],
            "ram_utilization": utilization["ram_utilization"]
        }