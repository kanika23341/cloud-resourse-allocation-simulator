from models import VMRequest, Server
class LoadBalancer:
    def __init__(self, servers):
        self.servers = servers
    def get_available_servers(self, vm: VMRequest):
        return [
            server
            for server in self.servers
            if server.can_allocate(vm)
        ]
    def first_fit(self, vm: VMRequest):
        for server in self.servers:
            if server.can_allocate(vm):
                return server
        return None
    def best_fit(self, vm: VMRequest):
        suitable_servers = self.get_available_servers(vm)
        if not suitable_servers:
            return None
        def remaining_resources(server):
            remaining_cpu = server.available_cpu - vm.cpu
            remaining_ram = server.available_ram - vm.ram
            return remaining_cpu + remaining_ram
        return min(
            suitable_servers,
            key=remaining_resources
        )
    def least_loaded(self, vm: VMRequest):
        suitable_servers = self.get_available_servers(vm)
        if not suitable_servers:
            return None
        def load_score(server):
            utilization = server.get_utilization()
            cpu = utilization["cpu_utilization"]
            ram = utilization["ram_utilization"]
            return (cpu + ram) / 2
        return min(
            suitable_servers,
            key=load_score
        )
    def select_server(self, vm: VMRequest):
        if vm.algorithm == "first_fit":
            return self.first_fit(vm)
        if vm.algorithm == "best_fit":
            return self.best_fit(vm)
        if vm.algorithm == "least_loaded":
            return self.least_loaded(vm)
        return self.best_fit(vm)
class AutoScaler:
    def __init__(self, servers):
        self.servers = servers
        self.server_counter = len(servers) + 1
    def can_scale(self, vm: VMRequest):
        for server in self.servers:
            if server.can_allocate(vm):
                return False
        return True

    def create_server_for_vm(self, vm: VMRequest):
        cpu = max(vm.cpu, 4)
        ram = max(vm.ram, 8)
        server = Server(
            f"auto-server-{self.server_counter:02d}",
            cpu,
            ram,
            0.10
        )
        self.server_counter += 1
        self.servers.append(server)
        return server
class Scheduler:
    def __init__(self, servers):
        self.servers = servers
        self.load_balancer = LoadBalancer(servers)
        self.auto_scaler = AutoScaler(servers)

    def schedule(self, vm: VMRequest):
        server = self.load_balancer.select_server(vm)
        if server is not None:
            return server
        if self.auto_scaler.can_scale(vm):
            return self.auto_scaler.create_server_for_vm(vm)

        return None