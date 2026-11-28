from config import Config


class DispatchHandler:
    @staticmethod
    def hot_update():
        return {
            "status": True,
            "message": "success",
            "hotOssUrl": Config.RES_URL,
            "currentVersion": Config.RES_VERSION,
            "server": "cn_prod_main",
            "ssAppId": "c969ebf346794cc797ed6eb6c3eac089",
            "ssServerUrl": Config.SS_SERVER_URL,
            "open_gm": True,
            "open_error_log": True,
            "open_netConnecting_log": True,
            "ipAddress": "127.0.0.1",
            "payUrl": Config.PAY_URL,
            "isTestServer": True,
            "error_log_level": 2,
            "server_id": "10001",
            "open_cs": True,
        }

    @staticmethod
    def region_info():
        return {
            "status": True,
            "message": "success",
            "gate_tcp_ip": Config.GAME_SERVER_GADGET_IP,
            "gate_tcp_port": Config.GAME_SERVER_GADGET_PORT,
            "is_server_open": True,
            "text": "",
            "client_log_tcp_ip": Config.GAME_SERVER_GADGET_IP,
            "client_log_tcp_port": Config.GAME_SERVER_GADGET_PORT,
            "currentVersion": Config.RES_VERSION,
            "photo_share_cdn_url": Config.PHOTO_SHARE_CDN_URL,
        }
