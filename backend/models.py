from pydantic import BaseModel, Field
from typing import Literal, Any

class VMRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    cpu: int = Field(ge=1, le=64)
    ram: int = Field(ge=1, le=256)
    duration: float = Field(gt=0, le=8760)
    algorithm: Literal["first_fit", "best_fit"] = "best_fit"

class StorageRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    storage_type: Literal["archive", "large", "small", "nosql", "sql", "fast_retrieval"]
    size_gb: float = Field(gt=0, le=100000)
    data: str = Field(default="", max_length=100000)

class DatabaseConfigRequest(BaseModel):
    read_replicas: int = Field(default=2, ge=0, le=8)
    shards: int = Field(default=3, ge=1, le=16)
    backup_mode: Literal["sync", "async"] = "sync"
    zones: int = Field(default=3, ge=1, le=6)
    cache_enabled: bool = True

class DatabaseWriteRequest(BaseModel):
    key: str = Field(min_length=1, max_length=250)
    value: Any

class ResetRequest(BaseModel):
    confirm: bool = False
