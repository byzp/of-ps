"""极简追踪日志: 直接追加写文件, 不依赖 logging 配置。

用途: 排查游戏内具体操作(染色/换装/骑乘等)到底走到哪一步、返回什么状态。
服务端的 logging 会被 uvicorn 等组件动过, 这里绕开它, 保证一定有输出。
"""

import os
import threading
import time

_LOCK = threading.Lock()
_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_PATH = os.path.join(_DIR, "trace.log")


def trace(tag, **kw):
    try:
        os.makedirs(_DIR, exist_ok=True)
        parts = []
        for k, v in kw.items():
            parts.append("%s=%r" % (k, v))
        line = "%s [%s] %s\n" % (
            time.strftime("%Y-%m-%d %H:%M:%S"),
            tag,
            " ".join(parts),
        )
        with _LOCK:
            with open(_PATH, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass
