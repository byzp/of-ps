from flask import jsonify
from http_server.models.login_response import (
    LoginResponse,
    LoginData,
    UserData,
    ExtInfo,
)
from dataclasses import asdict


class LoginHandler:
    @staticmethod
    def handle_login():
        """Handle user login"""
        user_data = UserData(
            uid="123456",
            username="cyt",
            mobile="12345678901",
            is_guest="0",
            reg_device="text",
            sex_type="0",
            check_key="text",
            is_mb_user=0,
            is_sns_user=0,
            token="@171@213@178@152@169@171@179",
        )

        ext_info = ExtInfo(oauth_type=0, oauth_id="", access_token="")

        login_data = LoginData(
            user_data=user_data,
            auth_token="@198@221@158@168@215@205@190@191",
            ext_info=ext_info,
            check_real_name=0,
            is_adult=True,
            u_age=55,
            ck_play_time=0,
            guest_real_name=1,
            id=0,
            message="",
            success_url="https://sdkapi-of.inutan.com/login.success?uid=123456&username=cyt&userToken=%40171%40213%40178%40152%40169%40171%40179&authToken=%40198%40221%40158%40168%40215%40205%40190%40191&timeleft=-1",
        )

        response = LoginResponse(status=True, data=login_data, message="")

        return jsonify(asdict(response))
