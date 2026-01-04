# of-ps

## 使用方法

- python版本至少需要3.10

- 拉取仓库，下载[protoc](https://github.com/protocolbuffers/protobuf/releases)并将其添加到环境变量

- 进入项目的proto文件夹编译net.proto (仅需net.proto，cfg.proto用于转换一些asset)

    ```
    cd proto
    protoc net.proto --python_out .
    ```

 - 从[releases](https://github.com/byzp/of-ps/releases)下载最新的data.zip，解压到项目的resources文件夹，请勿使用其他来源的资源，一些字段可能存在差异导致无法运行

- 为项目创建一个venv并下载依赖

    ```
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements-server.txt
    pip install -r requirements-client.txt
    ```
- 启动程序
    ```
    python main.py
    ```
- 启动代理转发
    ```
    mitmdump --mode local -s .\Redirect.py
    ```
- 安装mitmproxy证书：浏览器访问[mitm.it](http://mitm.it)，下载[证书](https://mitm.it/cert/p12)然后点击安装(仅需做一次)

- 启动客户端 (请从安装目录直接启动本体，不要从启动器启动，仅在taptap版pc客户端经过测试，不保证其他端可用)


## 可选操作

- 项目仅存在一个不支持自由线程的依赖(python-snappy的依赖cramjam), 如果你使用python3.14t+, 可以尝试这个[修改版snappy](https://github.com/byzp/snappy-py)

- 互联模块允许服务器之间相互发现和连接，各个服务器的玩家可以在同一场景交互, 需要编译utils/kcp的扩展(如果频繁出现断线问题，请增大utils/kcp/_kcp.c第69行的KCP_MINRTO, 然后重新编译)
    ```
    python utils/kcp/setup.py build_ext --inplace
    ```