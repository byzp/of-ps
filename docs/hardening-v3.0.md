# of-ps 本地加固版

本页对应 `lab/v3.0-hardening`，基于官方 v3.0 合并后的本地实现。

## 模块

- `handlers/`：303 个协议处理器。
- `server/social.py`：好友、黑名单、私聊和未读。
- `server/activities.py`：签到、活动、战令、月卡、补给和转盘。
- `server/boss_rush.py` / `server/abyss.py`：Boss Rush 与深渊。
- `server/character_growth.py`：角色、装备、海报、铭刻和拆解。
- `server/mail_rewards.py`：邮件附件一次性领取。
- `server/payment_security.py` / `server/redemption.py`：支付拒绝、兑换码和账号安全。
- `server/gomoku.py`：五子棋棋盘、下注托管和幂等结算。
- `server/photo_share.py`：照片墙上传、权限和文件安全。

## 核心不变量

- 跨玩家操作按玩家 ID 排序持锁。
- 锁顺序固定为“玩家锁 → 数据库事务”。
- 奖励和消耗走统一 `item_mgr`。
- 配置缺失拒绝，不伪造金币或道具。
- 支付默认拒绝真实付款，不返回伪造成功。
- 邮件、活动、副本、五子棋等使用持久幂等键。

## 验证

```powershell
C:\OverFieldLab\runtime\ofps-venv\Scripts\python.exe -m pytest -q tests
```

基线结果：`911 passed, 88 subtests passed`（2026-11-27 全量复跑）。采集 / 掉落 / 拾取专项修复后必须复跑。

## 当前专项

- 采集、怪物死亡、Pickup、宝箱和探索奖励使用服务端权威状态；伪造索引、重复拾取和重复领奖会被拒绝。
- 照片快照损坏时拒绝上传并禁止空快照覆盖；删除文件失败保留记录，孤儿文件清理失败不会阻断其他文件。
- 支付订单、事件和交易记录损坏时受控拒绝且不发奖；间隙奖励移除 `10/10` 伪造兜底，要求完成状态、所有权/成员资格、权威配置和原子领取。
- 原始 TCP 分片、粘包、未认证重放和异常包纳入自动验收。
- 沙袋自动保存加锁读取状态，并在数据库关闭后安全退出，避免关停竞态。
- 无控制台/重定向场景下禁用交互命令提示，日志输出回退到普通文本；服务继续运行，可响应 SIGINT/SIGTERM/SIGBREAK 正常关停。
- 社交压力覆盖 8 线程 × 400 条私聊：3200 条请求/通知全部成功，未读数与最近 50 条历史在重启后保持一致。
- 网络层 40 周期 / 2000 次登录断线烟测残留会话为 0；1000 次登录性能基线约 39.91 登录/秒，tracemalloc 峰值约 75MB。

## 限制

- 跨服互联网联机未开放。
- 部分活动缺权威奖励配置，当前拒绝发奖。
- 上游 PR #29 仍 Open，维护者未 Review。
