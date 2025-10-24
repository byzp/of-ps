from dataclasses import dataclass
from typing import Optional


@dataclass
class UserData:
    uid: str
    username: str
    mobile: str
    is_guest: str
    reg_device: str
    sex_type: str
    check_key: str
    is_mb_user: int
    is_sns_user: int
    token: str


@dataclass
class ExtInfo:
    oauth_type: int
    oauth_id: str
    access_token: str


@dataclass
class LoginData:
    user_data: UserData
    auth_token: str
    ext_info: ExtInfo
    check_real_name: int
    is_adult: bool
    u_age: int
    ck_play_time: int
    guest_real_name: int
    id: int
    message: str
    success_url: str


@dataclass
class LoginResponse:
    status: bool
    data: LoginData
    message: str
