from mitmproxy import http

ip = "localhost"
port = 21000

class Redirector:
    def request(self, flow: http.HTTPFlow) -> None:
        full_host = flow.request.pretty_host
        print(f"正在处理请求: {full_host}")

        suffix_matches = (
            ".inutan.com",
        )

        if full_host == "cdn-of.inutan.com":
            print(f"排除域名: {full_host}")
            return

        if any(full_host.endswith(suffix) for suffix in suffix_matches):
            print(f"重定向 {full_host} → {ip}:{port}")
            self._redirect(flow)
            return

    def _redirect(self, flow: http.HTTPFlow):
        flow.request.scheme = "http"
        flow.request.host = ip
        flow.request.port = port

        flow.request.headers["Host"] = flow.request.host

        if hasattr(flow, 'client_conn'):
            flow.client_conn.tls = False

addons = [Redirector()]
