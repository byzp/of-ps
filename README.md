# of-ps
of emu server

- 含有大量硬编码数据
- 处于早期开发阶段
- 请使用mitmproxy的透明代理模式, 某些流量会绕过系统代理

```bash
mitmdump --mode local -s .\Redirect.py
```

- 程序设计为多线程而非多进程，使用Python free-threading 可以大幅提升并发能力