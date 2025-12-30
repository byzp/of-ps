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
    pip install -r requirements-server.txt
    ```
- (此步骤可省略) 项目仅存在一个不支持自由线程的依赖(python-snappy的依赖cramjam), 如果你使用python3.14t+，可以尝试这个[修改版snappy](https://github.com/byzp/snappy-py)
- 启动程序
    ```
    python main.py
    ```
- 启动代理转发
    ```
    mitmdump --mode local -s .\Redirect.py
    ```
- 启动客户端 (仅在taptap版pc客户端经过测试，不保证其他端可用)

