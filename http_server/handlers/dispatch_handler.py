import json
from config import Config


class DispatchHandler:
    @staticmethod
    def hot_update():
        return json.loads(
            '{"status":true,"message":"success","hotOssUrl":"http://cdn-of.inutan.com/Resources;https://cdn-of.inutan.com/Resources","currentVersion":"'
            + Config.RES_VERSION
            + '","server":"cn_prod_main","ssAppId":"c969ebf346794cc797ed6eb6c3eac089","ssServerUrl":"https://te-of.inutan.com","open_gm":true,"open_error_log":true,"open_netConnecting_log":true,"ipAddress":"127.0.0.1","payUrl":"http://api-callback-of.inutan.com:19701","isTestServer":true,"error_log_level":2,"server_id":"10001","open_cs":true}'
        )

    @staticmethod
    def region_info():
        return json.loads(
            '{"status":true,"message":"success","gate_tcp_ip":"'
            + Config.GAME_SERVER_IP
            + '","gate_tcp_port":'
            + str(Config.GAME_SERVER_PORT)
            + ',"is_server_open":true,"text":"","client_log_tcp_ip":"'
            + Config.GAME_SERVER_IP
            + '","client_log_tcp_port":'
            + str(Config.GAME_SERVER_PORT)
            + ',"currentVersion":"'
            + Config.RES_VERSION
            + '","photo_share_cdn_url":"https://cdn-photo-of.inutan.com/cn_prod_main"}'
        )
