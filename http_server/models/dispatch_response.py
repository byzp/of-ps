from dataclasses import dataclass
from typing import Optional


@dataclass
class DispatchResponse:
    status: bool
    message: str
    hot_oss_url: Optional[str] = None
    current_version: Optional[str] = None
    server: Optional[str] = None
    ss_app_id: Optional[str] = None
    ss_server_url: Optional[str] = None
    open_gm: Optional[bool] = None
    open_error_log: Optional[bool] = None
    open_net_connecting_log: Optional[bool] = None
    ip_address: Optional[str] = None
    pay_url: Optional[str] = None
    is_test_server: Optional[bool] = None
    error_log_level: Optional[int] = None
    reserved_parameter1: Optional[str] = None
    gate_tcp_ip: Optional[str] = None
    gate_tcp_port: Optional[int] = None
    is_server_open: Optional[bool] = None
    text: Optional[str] = None
    client_log_tcp_ip: Optional[str] = None
    client_log_tcp_port: Optional[int] = None