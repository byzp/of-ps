from mitmproxy import http

ip = "localhost"
port = 21000
rd_res = False


class Redirector:
    def request(self, flow: http.HTTPFlow) -> None:
        full_host = flow.request.pretty_host
        print(f"正在处理请求: {full_host}")

        suffix_matches = (".inutan.com",)

        if not rd_res and full_host == "cdn-of.inutan.com":
            print(f"排除域名: {full_host}")
            return

        if any(full_host.endswith(suffix) for suffix in suffix_matches):
            print(f"重定向 {full_host} → {ip}:{port}")
            self._redirect(flow, orig_host=full_host)
            return

    def _redirect(self, flow: http.HTTPFlow, orig_host: str):
        original_host = orig_host
        flow.request.scheme = "http"

        flow.request.host = ip
        flow.request.port = port

        flow.request.headers["Host"] = original_host
        try:
            flow.server_conn.address = (ip, port)
        except Exception:
            pass
        flow.server_conn.tls = False


addons = [Redirector()]
