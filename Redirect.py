import logging
import re

from mitmproxy import ctx, http, tls

ip = "127.0.0.1"
port = 21000
rd_res = False

logger = logging.getLogger(__name__)


class Redirector:
    @staticmethod
    def _host_pattern() -> str:
        resource_exclusion = (
            "" if rd_res else r"(?!cdn-of\.inutan\.com\.?(?::\d+)?$)"
        )
        return rf"^{resource_exclusion}(?:[^.:]+\.)+inutan\.com\.?(?::\d+)?$"

    def load(self, loader) -> None:
        # 在协议识别时放行其他连接，避免先替换 HTTPS 证书再到 request 中放行。
        ctx.options.update(allow_hosts=[self._host_pattern()])

    def tls_clienthello(self, data: tls.ClientHelloData) -> None:
        # 请求将转发到 HTTP 私服，不需要先与官方服务器完成 TLS 握手。
        if data.client_hello.sni and re.fullmatch(
            self._host_pattern(), data.client_hello.sni, re.IGNORECASE
        ):
            data.establish_server_tls_first = False

    def request(self, flow: http.HTTPFlow) -> None:
        full_host = flow.request.pretty_host
        if not re.fullmatch(self._host_pattern(), full_host, re.IGNORECASE):
            return

        self._redirect(flow, orig_host=full_host)
        logger.info("重定向 %s → %s:%s", full_host, ip, port)

    def _redirect(self, flow: http.HTTPFlow, orig_host: str) -> None:
        original_host_header = flow.request.host_header or orig_host
        flow.request.scheme = "http"
        flow.request.host = ip
        flow.request.port = port
        flow.request.host_header = original_host_header


addons = [Redirector()]
