EC2_INSTANCE_TYPES = {
    "t3.micro": {"name": "t3.micro", "family": "General purpose", "vcpu": 2, "ram_gb": 1, "price_per_hour": 0.0104, "use_case": "Tiny demos and development"},
    "t3.small": {"name": "t3.small", "family": "General purpose", "vcpu": 2, "ram_gb": 2, "price_per_hour": 0.0208, "use_case": "Light web services"},
    "t3.medium": {"name": "t3.medium", "family": "General purpose", "vcpu": 2, "ram_gb": 4, "price_per_hour": 0.0416, "use_case": "Small application servers"},
    "m7i.large": {"name": "m7i.large", "family": "General purpose", "vcpu": 2, "ram_gb": 8, "price_per_hour": 0.1008, "use_case": "Balanced application workloads"},
    "c7i.large": {"name": "c7i.large", "family": "Compute optimized", "vcpu": 2, "ram_gb": 4, "price_per_hour": 0.0893, "use_case": "CPU-heavy services"},
    "r7i.large": {"name": "r7i.large", "family": "Memory optimized", "vcpu": 2, "ram_gb": 16, "price_per_hour": 0.1323, "use_case": "Memory-heavy services"},
    "c7i.xlarge": {"name": "c7i.xlarge", "family": "Compute optimized", "vcpu": 4, "ram_gb": 8, "price_per_hour": 0.1786, "use_case": "Parallel compute workloads"},
}
