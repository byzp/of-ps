# of-ps

[中文介绍](https://github.com/byzp/of-ps/blob/main/README_zh.md)

> 本地加固分支 `lab/v3.0-hardening` 包含 303 个处理器、奖励/社交/装备/活动/支付安全状态机和完整测试。详见[本地加固说明](docs/hardening-v3.0.md)。公共大厅实验位于 `lab/public-lobby-phase0`，尚未合并上游 PR #29。

## Deployment

### 1. Install Protocol Buffers

This project uses Protocol Buffers to define network communication formats. You need to install the `protoc` compiler and compile the protocol file (`proto/net.proto`) to Python code.

1. Download [protoc](https://github.com/protocolbuffers/protobuf/releases)
2. Extract and add the `bin` directory to your `PATH` environment variable
3. Verify installation:
   ```bash
   protoc --version
   libprotoc 33.2
   ```
4. Navigate to the `proto` folder and compile `net.proto` (only `net.proto` is required; `cfg.proto` is used for asset conversion):
   ```bash
   cd proto
   protoc net.proto --python_out .
   ```

### 2. Download Resources

Download the latest `data.zip` from the [releases page](https://github.com/byzp/of-ps/releases) and extract it into the `resources` folder. **Do not use resources from other sources**, as field differences may cause runtime errors.

Expected directory structure:
```
of-ps
├─ .gitignore
├─ LICENSE
├─ README.md
├─ Redirect.py
├─ build.bat
├─ config.py
├─ handlers
├─ http_server
├─ main.py
├─ network
├─ proto
│    ├─ __init__.py
│    ├─ cfg.proto
│    ├─ net.proto
│    └─ net_pb2.py
├─ requirements-client.txt
├─ requirements-server.txt
├─ resources
│    ├─ data
│    └─ webstatic
├─ server
├─ tools
└─ utils
```

### 3. Create Virtual Environment & Install Dependencies

**Using venv:**
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-server.txt
pip install -r requirements-client.txt
```

**Using conda:**
```bash
conda create -n overfield python=3.10
conda activate overfield
pip install -r requirements-server.txt
pip install -r requirements-client.txt
```

Optional standalone build: install `pyinstaller` in the same environment before running `build.bat`.

### 4. Start the Server

Open a terminal and run (keep this window open):
```bash
python main.py
```

### 5. Start the Proxy (mitmproxy)

Open another terminal and run (keep this window open):
```bash
mitmdump --mode local:launcher.exe,PCSDKUI.exe,QtWebEngineProcess.exe,ZFGameBrowser.exe --set connection_strategy=lazy -s .\Redirect.py
```

- Visit `mitm.it` in your browser
- Click "Get mitmproxy-ca-cert.p12"
- Install the certificate

### 6. Launch the Game Client

Find `launcher.exe` in the game folder (e.g. from TapTap):
```
E:\TapTap\PC Games\176228\launcher.exe
```

## Public Lobby Experiment (In Progress)

The experiment branch adds shared player projections, persistent channel snapshots, low-frequency global plus AOI position sync, separate normal/bulk send queues, multiplayer metrics, host leases, and snapshot failover. Two independent real game clients have completed login, same-scene bidirectional position sync, and real NetSession chat/emoji send and receive on a hidden desktop. It does **not** yet provide public automatic host election, multi-shard coordination, client prediction, or dozens-of-real-clients acceptance, and must not be described as a production-ready public lobby.

Key settings in `config.py`:

- `SCENE_GLOBAL_SYNC_INTERVAL`: global position snapshot interval, default `0.5` seconds.
- `SCENE_AOI_RADIUS`: high-frequency nearby-player radius, default `80`.
- `LOBBY_STATE_PATH`: lobby snapshot path; `None` disables persistence.
- `LOBBY_HOST_ID`, `LOBBY_LEASE_SECONDS`, `LOBBY_SNAPSHOT_INTERVAL_SEC`: host identity, lease, and periodic snapshot settings.
- `LOBBY_RESTORED_PROJECTION_TTL_SEC`: expiry for restored projections without an active session, default `30` seconds, preventing ghost players.
- `AUTO_GENERATE_PLAYER_NAME`: generates a default name and skips client onboarding.
- `ALLOW_LOCAL_TOKEN`, `LOCAL_TOKEN_UIDS`: local-test token allowlist, disabled by default.
- `CHAT_RATE_LIMIT_*`, `ACTION_RATE_LIMIT_*`, `EMOJI_RATE_LIMIT_*`: per-session token-bucket rates and burst capacities for chat, actions, and emoji.

Common validation commands:

```bash
python -m pytest -q tests
python tools/lobby_loadtest.py --help
python tools/lobby_failover_e2e.py
```

`tools/lobby_e2e.py` requires a running server that allows the local test token and checks two-client login, mutual position visibility, chat, and emoji broadcast. `tools/lobby_failover_e2e.py` starts two windowless server processes, kills the host, and verifies snapshot restore, epoch advancement, and renewed interaction.

## Available Console Commands

All commands are defined in [`utils/cmd.py`](./utils/cmd.py) and [`utils/cmd_exec.py`](./utils/cmd_exec.py).

> **Conventions:**
> - `player_id/all` — target a specific player by ID, or `all` for every connected player
> - `[param]` — optional parameter

- **Give items** — find `item_id` by searching item names in `resources/data/String_Simplified.json` (`give all all` grants every item)
   ```
   give player_id/all item_id/all [num]
   # give 1000001 102 100        # give item 102 to player 1000001 (100 copies)
   # give all 108                # give item 108 to all players
   # give all all                # give all items to all players
   ```
- **Launch fireworks** — find `id` in `resources/data/FireworksParty.json`
   ```
   firework id [dur_time] [start_time]
   ```
- **Set scene time** — `num` ranges from 1 to 86400 (seconds)
   ```
   time num
   ```
- **Teleport (normal scenes)** — find `scene_id` in `resources/data/Scene.json`
   ```
   tp player_id/all scene_id [channel_id]
   ```
- **Teleport (instances/dungeons)** — find `dungeon_id` in `resources/data/Dungeon.json`
   ```
   tpd player_id/all dungeon_id
   ```
- **Kick a player**
   ```
   kick player_id/all
   ```
- **List connected players**
   ```
   players
   ```
- **List linked (interconnected) servers**
   ```
   link
   ```
- **Force-save data to database**
   ```
   save
   ```
- **Show process-local multiplayer metrics**
   ```
   metrics
   ```
- **Stop the server**
   ```
   stop
   ```
- **Show this help message**
   ```
   help
   ```

## Optional

### Interconnection / KCP Module

The interconnection module allows servers to discover each other and link, enabling players from different servers to interact in the same scene. You need to compile the KCP extension:

```bash
python utils/kcp/setup.py build_ext --inplace
```

If you experience frequent disconnections, increase `KCP_MINRTO` in `utils/kcp/ikcp.c` or `utils/kcp/_kcp.cpp`, then recompile.

## 

[![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/FvsjdMMCY6)