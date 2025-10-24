from flask import jsonify
from dataclasses import asdict
from config import Config


class DispatchHandler:
    @staticmethod
    def hot_update():
        return '{"status":true,"message":"success","hotOssUrl":"http://cdn-of.inutan.com/Resources;https://cdn-of.inutan.com/Resources","currentVersion":"2025-09-19-16-44-33_2025-09-29-11-44-13","server":"cn_prod_main","ssAppId":"c969ebf346794cc797ed6eb6c3eac089","ssServerUrl":"https://te-of.inutan.com","open_gm":false,"open_error_log":false,"open_netConnecting_log":false,"ipAddress":"112.0.51.26","payUrl":"http://api-callback-of.inutan.com:19701","isTestServer":true,"error_log_level":2,"server_id":"10001","open_cs":false}'

    @staticmethod
    def region_info():
        return (
            '{"status":true,"message":"success","gate_tcp_ip":"'
            + Config.GAME_SERVER_IP
            + '","gate_tcp_port":11033,"is_server_open":true,"text":"","client_log_tcp_ip":"'
            + Config.GAME_SERVER_IP
            + '","client_log_tcp_port":11033,"currentVersion":"2025-09-19-16-44-33_2025-09-29-11-44-13","photo_share_cdn_url":"https://cdn-photo-of.inutan.com/cn_prod_main"}'
        )
