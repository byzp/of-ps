# of-ps

> 本地加固包含 303 个处理器、奖励、社交、装备、活动和支付安全状态机，详见[加固说明](docs/hardening-v3.0.md)。
> 公共大厅代码基线：`lab/public-lobby-phase0` / `43444cb`，上游 `f23ec6a`，见 [PR #30](https://github.com/byzp/of-ps/pull/30)，尚未合并。

## 部署

1. 安装 `protoc`，编译协议：

   ```bash
   cd proto
   protoc net.proto --python_out .
   ```

2. 从[发布页](https://github.com/byzp/of-ps/releases)下载 `data.zip`，解压到 `resources`。不要使用其他来源资源。

3. 创建环境并安装依赖：

   ```bash
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements-server.txt
   pip install -r requirements-client.txt
   ```

4. 启动服务：

   ```bash
   python main.py
   ```

5. 启动代理：

   ```bash
   mitmdump --mode local:launcher.exe,PCSDKUI.exe,QtWebEngineProcess.exe,ZFGameBrowser.exe --set connection_strategy=lazy -s .\Redirect.py
   ```

   浏览器访问 `mitm.it`，安装证书。

6. 启动游戏目录中的 `launcher.exe`。

## 公共大厅

### 实现原理

当前是**单进程中心化薄主机 + 可选 KCP 跨服**，不是分布式副主机系统。

```text
客户端 → 登录 → TCP 会话 → 处理器 → 共享投影/场景记录
       → 全局快照 + AOI → 普通/批量队列 → 客户端
```

- 共享投影只保存场景、频道、位置、动作、表情等跨玩家状态，不复制完整背包。
- 每 0.5 秒发送频道完整位置快照；快照之间高频发送附近本地玩家。
- 远端玩家增量目前不经过 AOI，全局完整快照仍有平方级下行成本。
- 普通/批量队列按 4:1 调度，但仍共享 TCP，不是独立可靠通道。
- 位置和频道变更串行处理；掉线、重复登录和关服都会清理投影并广播离开。
- 快照原子保存共享投影和场景记录；恢复投影默认 30 秒过期。持久化需设置 `LOBBY_STATE_PATH`。
- KCP 支持跨服实体、位置、聊天和表情；共同邻居二跳中转不是 NAT 穿透。

### 当前边界

| 项目 | 状态 |
|---|---|
| 全量回归 | `983 passed, 88 subtests passed` |
| 双协议客户端 | 登录、位置、聊天、表情通过 |
| 双主机 KCP | 跨服实体、位置、社交、离开通过 |
| 显式故障转移 | 强杀、快照恢复、epoch 1→3、重新交互通过 |
| 真实客户端 | 同机两个进程、回环、自然位置同步、真实网络栈聊天/表情通过 |
| 未验收 | 真实移动输入、重启重连、数十客户端、多物理主机、公网、长时稳定 |

合成 100 客户端只能辅助诊断服务端管线，不能作为真实容量结论。

### 下一步

1. 广播移出全局会话锁，按频道 actor 处理。
2. 补事件序号、幂等键、恢复令牌。
3. 补客户端预测、远端插值和真实移动验收。
4. 补健康评分、协调层租约/CAS、自动选主和重连。
5. 通过后再做多分片、公网 Relay 和长时测试。

## 公共大厅配置

| 配置 | 默认值 | 作用 |
|---|---:|---|
| `SCENE_GLOBAL_SYNC_INTERVAL` | `0.5` | 全局位置快照间隔 |
| `SCENE_AOI_RADIUS` | `80` | 附近玩家高频半径 |
| `LOBBY_STATE_PATH` | `None` | 快照路径，`None` 关闭 |
| `LOBBY_HOST_ID` | `local-host` | 主机标识 |
| `LOBBY_LEASE_SECONDS` | `10` | 进程内租约 |
| `LOBBY_SNAPSHOT_INTERVAL_SEC` | `1` | 快照间隔 |
| `LOBBY_RESTORED_PROJECTION_TTL_SEC` | `30` | 恢复投影过期时间 |
| `AUTO_GENERATE_PLAYER_NAME` | `True` | 自动命名，跳过新手登记 |
| `ALLOW_LOCAL_TOKEN` | `False` | 本机测试 token 白名单 |
| `CHAT_RATE_LIMIT_*` | 每秒 2，突发 5 | 聊天限流 |
| `ACTION_RATE_LIMIT_*` | 每秒 5，突发 10 | 动作限流 |
| `EMOJI_RATE_LIMIT_*` | 每秒 3，突发 8 | 表情限流 |

## 验证

```bash
python -m pytest -q tests
python tools/lobby_e2e.py
python tools/lobby_failover_e2e.py
python tools/lobby_multihost_e2e.py
python tools/lobby_loadtest.py --help
```

- `lobby_e2e.py` 需要已启动且允许本机测试 token 的服务。
- `lobby_failover_e2e.py` 自行启动两个服务，强杀后显式提升替代主机。
- `lobby_multihost_e2e.py` 自行启动两个服务和 KCP。

## 控制台命令

| 命令 | 作用 |
|---|---|
| `give 玩家/全部 物品/全部 [数量]` | 发放物品 |
| `tp 玩家/全部 场景 [频道]` | 普通场景传送 |
| `tpd 玩家/全部 秘境` | 秘境传送 |
| `kick 玩家/全部` | 踢出玩家 |
| `players` | 在线玩家 |
| `link` | 已连接主机 |
| `metrics` | 联机指标 |
| `save` | 保存数据库 |
| `time 秒数` | 场景时间 |
| `firework 编号` | 烟花 |
| `stop` | 停止服务 |

## 可选 KCP

```bash
python utils/kcp/setup.py build_ext --inplace
```

频繁断线时可调整 `utils/kcp/ikcp.c` 或 `utils/kcp/_kcp.cpp` 的 `KCP_MINRTO` 后重新编译。

[![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=Discord&logoColor=white)](https://discord.gg/FvsjdMMCY6)
