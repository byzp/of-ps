# of-ps

## 部署方法

1. 项目使用 Protocol Buffers 定义网络通信格式。需要先安装 `protoc` 编译器，将项目中的协议文件（`proto/net.proto`）编译为Python可用的代码。

   1. 下载[protoc](https://github.com/protocolbuffers/protobuf/releases)

   2. 解压并将bin所在目录添加到环境变量

   3. 验证

      ```bash
      protoc --version
      libprotoc 33.2
      ```

   4. 在cmd中进入项目的proto文件夹编译net.proto (仅需net.proto，cfg.proto用于转换一些asset)

      ```bash
      cd proto
      protoc net.proto --python_out .
      ```

2. 从[releases](https://github.com/byzp/of-ps/releases)下载最新的data.zip，解压到项目的resources文件夹，请勿使用其他来源的资源，一些字段可能存在差异导致无法运行

   1. 目录结构表现为：

      ```bash
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

3. 进入项目目录下，创建虚拟环境并安装所需依赖

   1. 使用venv

      ```bash
      python -m venv venv
      .\venv\Scripts\Activate.ps1
      pip install -r requirements-server.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
      pip install -r requirements-client.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
      ```

   2. 使用conda

      ```bash
      conda create -n overfield python=3.10
      conda activate overfield
      pip install -r requirements-server.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
      pip install -r requirements-client.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
      ```

4. 开启一个命令行窗口，启动服务器（不要关闭此命令窗口）

   ```bash
   python main.py
   ```
   
5. 开启一个命令行窗口，启动代理转发（不要关闭此命令窗口）

   ```bash
   mitmdump --mode local -s .\Redirect.py
   ```

   - 然后浏览器访问mitm.it
   - 点击Get mitmproxy-ca-cert.p12
   - 点击这个证书, 安装

6. 启动开放空间launcher本体

   1. 直接找到taptap的游戏文件夹，选择launcher.exe运行
   2. 例如`E:\TapTap\PC Games\176228\launcher.exe`

## 可用控制台命令

所有可用命令均定义在 [`utils/cmd.py`](./utils/cmd.py) 与 [`utils/cmd_exec.py`](./utils/cmd_exec.py) 中。

- 给予玩家物品, item_id 可在 `resources/data/String_Simplified.json` 搜索物品名称寻找 (give all all 可导入全部物品)
   ```
   give player_id/all item_id/all [num]
   # give 1000001 102 100        # 给指定玩家指定物品
   # give all 108                # 给所有玩家指定物品
   # give all all                # 给所有玩家发放全部物品
   ```
- 放烟花, id 可在 `resources/data/FireworksParty.json` 找到
   ```
   firework id [dur_time] [start_time]
   ```
- 设置场景时间, num 的取值范围为 1-86400 (秒)
   ```
   time num
   ```
- 传送 (常规场景), scene_id 可在 `resources/data/Scene.json` 找到
   ```
   tp player_id/all scene_id [channel_id]
   ```
- 传送 (秘境/副本), dungeon_id 可在 `resources/data/Dungeon.json` 找到
   ```
   tpd player_id/all dungeon_id
   ```
- 踢出玩家
   ```
   kick player_id/all
   ```
- 显示已连接的玩家
   ```
   players
   ```
- 显示互联的其他服务器
   ```
   link
   ```
- 手动保存数据到数据库
   ```
   save
   ```
- 停止服务器
   ```
   stop
   ```
- 显示此帮助信息
   ```
   help
   ```


## 可选操作

- 项目仅存在一个不支持自由线程的依赖(python-snappy的依赖cramjam), 如果你使用python3.14t+, 可以尝试这个[修改版snappy](https://github.com/byzp/snappy-py)

- 互联模块允许服务器之间相互发现和连接，各个服务器的玩家可以在同一场景交互, 需要编译utils/kcp的扩展(如果频繁出现断线问题，请增大utils/kcp/_kcp.c第69行的KCP_MINRTO, 然后重新编译)
    ```
    python utils/kcp/setup.py build_ext --inplace
    ```

## 

[![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/FvsjdMMCY6)