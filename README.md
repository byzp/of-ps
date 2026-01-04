# of-ps

## 部署方法

1. 项目使用 Protocol Buffers 定义网络通信格式。需要先安装 `protoc` 编译器，将项目中的协议文件（`proto/net.proto`）编译为Python可用的代码。

   1. 下载[protoc](https://github.com/protocolbuffers/protobuf/releases)，选择`protoc-33.2-win64.zip`

   2. 添加到环境变量，选择PATH，进行编辑（**若原本就有设置过值，请不要替换**，在原本的值后面添加分号`;`即可，表现为：`D:\ffmpeg-8.0-essentials_build\bin;E:\other\protoc-33.2-win64\bin`）

   3. 验证

      ```bash
      (overfield) C:\Users\Admin>protoc --version
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
   (overfield) E:\of-ps>python main.py
   ```
   
5. 开启一个命令行窗口，启动代理转发（不要关闭此命令窗口）

   ```bash
   (overfield) E:\of-ps>mitmdump --mode local -s .\Redirect.py
   ```

   - 然后浏览器访问mitm.it
   - 点击Get mitmproxy-ca-cert.p12
   - 点击这个证书, 安装

6. 启动开发空间launcher本体

   1. 直接找到taptap的游戏文件夹，选择launcher.exe运行
   2. 例如`E:\TapTap\PC Games\176228\launcher.exe`




## 可选操作

- 项目仅存在一个不支持自由线程的依赖(python-snappy的依赖cramjam), 如果你使用python3.14t+, 可以尝试这个[修改版snappy](https://github.com/byzp/snappy-py)

- 互联模块允许服务器之间相互发现和连接，各个服务器的玩家可以在同一场景交互, 需要编译utils/kcp的扩展(如果频繁出现断线问题，请增大utils/kcp/_kcp.c第69行的KCP_MINRTO, 然后重新编译)
    ```
    python utils/kcp/setup.py build_ext --inplace
    ```

## 可选操作

- 项目仅存在一个不支持自由线程的依赖(python-snappy的依赖cramjam), 如果你使用python3.14t+, 可以尝试这个[修改版snappy](https://github.com/byzp/snappy-py)

- 互联模块允许服务器之间相互发现和连接，各个服务器的玩家可以在同一场景交互, 需要编译utils/kcp的扩展(如果频繁出现断线问题，请增大utils/kcp/_kcp.c第69行的KCP_MINRTO, 然后重新编译)
    ```
    python utils/kcp/setup.py build_ext --inplace
    ```