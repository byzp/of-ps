import threading
from server.scene_data import _session_list as session_list
from network.cmd_id import CmdId

# 命令注册
COMMANDS = {}

def register_command(name, handler_func):
    """注册新命令"""
    COMMANDS[name] = handler_func

def send_to_all_clients(handler_class):
    """通用函数，用于向所有已连接的客户端发送通知"""
    if not session_list:
        print("没有已连接的客户端")
        return
        
    try:
        handler = handler_class()
        for session in session_list:
            if session.logged_in:
                handler.handle(session, b"", 0)
                print(f"已向玩家 {session.player_id} 发送通知")
    except Exception as e:
        print(f"错误: {e}")



# 定义调用函数
def send_weather_change():
    """向所有已连接的客户端发送天气变化通知"""
    from handlers.SceneWeatherChange import Handler
    send_to_all_clients(Handler)

def send_system_notice():
    """向所有已连接的客户端发送系统通知"""
    from handlers.SystemNotice import Handler
    send_to_all_clients(Handler)

def send_player_buff_notice():
    """向所有已连接的客户端发送玩家Buff通知"""
    from handlers.PlayerBuffNotice import Handler
    send_to_all_clients(Handler) #有问题

def send_gm_recommend_channel_notice():
    """向所有已连接的客户端发送GM推荐频道通知"""
    from handlers.GMRecommendChannelNotice import Handler
    send_to_all_clients(Handler)

def send_fireworks_start_notice():
    """向所有已连接的客户端发送烟花开始通知"""
    from handlers.FireworksStartNotice import Handler
    send_to_all_clients(Handler) #有问题

# 注册命令
register_command("1918", send_weather_change)
register_command("2016", send_system_notice)
register_command("1880", send_player_buff_notice)
register_command("2160", send_fireworks_start_notice)
register_command("2630", send_gm_recommend_channel_notice)








def start_command_handler():
    def handler():
        while True:
            try:
                cmd = input().strip()
                if cmd in COMMANDS:
                    COMMANDS[cmd]()
                elif cmd.lower() == "help":
                    print("可用命令:", ", ".join(COMMANDS.keys()))
                elif cmd.lower() in ["quit", "exit"]:
                    print("命令处理器已停止")
                    break
            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                print(f"错误: {e}")
    
    thread = threading.Thread(target=handler)
    thread.daemon = True
    thread.start()
    print("Command handler started。输入 'help' 查看可用命令。")
    return thread