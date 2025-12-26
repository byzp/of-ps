# of-ps
## of emu server

- 请使用mitmproxy的透明代理模式, 某些流量会绕过系统代理

```bash
mitmdump --mode local -s .\Redirect.py
```

- python版本至少需要3.10
