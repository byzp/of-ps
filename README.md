# of-ps

[中文介绍](https://github.com/byzp/of-ps/blob/main/README_zh.md)

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

### 4. Start the Server

Open a terminal and run (keep this window open):
```bash
python main.py
```

### 5. Start the Proxy (mitmproxy)

Open another terminal and run (keep this window open):
```bash
mitmdump --mode local -s .\Redirect.py
```

- Visit `mitm.it` in your browser
- Click "Get mitmproxy-ca-cert.p12"
- Install the certificate

### 6. Launch the Game Client

Find `launcher.exe` in the game folder (e.g. from TapTap):
```
E:\TapTap\PC Games\176228\launcher.exe
```

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
- **Stop the server**
   ```
   stop
   ```
- **Show this help message**
   ```
   help
   ```

## Optional

### Free-Threaded Python (3.13t+)

The only dependency that does not support free-threaded Python is `python-snappy` (via `cramjam`). If you are using Python 3.14t+, try this [modified snappy](https://github.com/byzp/snappy-py).

### Interconnection / KCP Module

The interconnection module allows servers to discover each other and link, enabling players from different servers to interact in the same scene. You need to compile the KCP extension:

```bash
python utils/kcp/setup.py build_ext --inplace
```

If you experience frequent disconnections, increase `KCP_MINRTO` at line 69 in `utils/kcp/_kcp.c`, then recompile.

## 

[![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/FvsjdMMCY6)