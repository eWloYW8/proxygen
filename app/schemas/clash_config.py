from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ProxyGroup(BaseModel):
    name: str
    type: str
    proxies: List[str] = []
    url: Optional[str] = None
    interval: Optional[int] = None
    tolerance: Optional[int] = None
    filter: Optional[str] = None
    removable: bool = Field(False, exclude=True)

class RuleProvider(BaseModel):
    type: str
    path: str

class ClashConfig(BaseModel):
    mixed_port: int = Field(7890, alias="mixed-port")
    allow_lan: bool = Field(False, alias="allow-lan")
    mode: str = Field("Rule", alias="mode")
    log_level: str = Field("info", alias="log-level")
    external_controller: str = Field(":9090", alias="external-controller")
    proxies: List[Dict[str, Any]] = []
    proxy_groups: List[ProxyGroup] = Field(..., alias="proxy-groups")
    rules: List[str] = []

    model_config = {
        "populate_by_name": True
    }