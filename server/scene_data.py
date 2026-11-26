import pickle
import threading
import time
from collections import defaultdict
from google.protobuf.message import DecodeError
from typing import Any, Dict, Optional, List

logger = logging.getLogger(__name__)

_scene: Dict[int, Dict[int, Dict[int, Any]]] = defaultdict(lambda: defaultdict(dict))
_action: List = []
_scene_action: Dict[int, Dict[int, List]] = defaultdict(lambda: defaultdict(list))
_chat_msg: List = []
_session_list: List = []
_rec_list: List = []

# 动作广播按 (scene_id, channel_id) 分片。每个分片只有一个消费者，
# 因此同一频道内的动作顺序稳定，不同频道可以并行处理。
_action_queues: List[queue.Queue] = []
_action_workers: List[threading.Thread] = []
_action_consumer = None
_action_worker_count = 0
_action_dispatch_lock = threading.Lock()
_action_dispatch_stopping = False
_ACTION_STOP = object()

lock_scene = threading.Lock()
lock_action = threading.Lock()
lock_scene_action = threading.Lock()
lock_chat_msg = threading.Lock()
lock_session = threading.Lock()
lock_rec_list = threading.Lock()

_LOCATION_NS = "player_location"
_LOCATION_KEY = "last"
_LOCATION_SAVE_INTERVAL = 2.0
_last_location_save = {}


def save_session_location(session, force=False):
    now = time.monotonic()
    previous = _last_location_save.get(session.player_id, 0.0)
    if not force and now - previous < _LOCATION_SAVE_INTERVAL:
        return
    position = session.pos.get(session.scene_id)
    rotation = session.scene_player.team.char1.rot
    payload = {
        "scene_id": int(session.scene_id),
        "channel_id": int(session.channel_id),
        "position": position.SerializeToString() if position is not None else b"",
        "rotation": rotation.SerializeToString() if rotation is not None else b"",
    }
    import utils.db as db
    db.set_kv(session.player_id, _LOCATION_NS, _LOCATION_KEY, pickle.dumps(payload))
    _last_location_save[session.player_id] = now


def load_session_location(player_id):
    import utils.db as db
    raw = db.get_kv(player_id, _LOCATION_NS, _LOCATION_KEY)
    if not raw:
        return None
    try:
        payload = pickle.loads(raw)
        if not isinstance(payload, dict):
            return None
        scene_id = int(payload["scene_id"])
        channel_id = int(payload["channel_id"])
        if scene_id <= 0 or channel_id <= 0:
            return None
        return payload
    except (KeyError, TypeError, ValueError, pickle.UnpicklingError):
        return None


def restore_session_location(session):
    payload = load_session_location(session.player_id)
    if not payload:
        return False
    from proto.net_pb2 import Vector3
    session.scene_id = int(payload["scene_id"])
    session.channel_id = int(payload["channel_id"])
    position = Vector3()
    rotation = Vector3()
    try:
        position.ParseFromString(payload.get("position", b""))
        rotation.ParseFromString(payload.get("rotation", b""))
    except DecodeError:
        return False
    if position.SerializeToString():
        session.pos[session.scene_id] = position
        session.scene_player.team.char1.pos.CopyFrom(position)
    if rotation.SerializeToString():
        session.scene_player.team.char1.rot.CopyFrom(rotation)
    return True


def get_session():
    session_tmp = []
    with lock_session:
        for session in _session_list:
            if session.logged_in and session.running:
                session_tmp.append(session)
        return session_tmp


def get_recorder(scene_id: int, channel_id: int) -> Optional[Any]:
    with lock_scene:
        sc = _scene.get(scene_id)
        if not sc:
            return {}
        ch = sc.get(channel_id)
        if not ch:
            return {}
        return dict(ch)


def up_recorder(scene_id: int, channel_id: int, player_id: int, rec_data: Any) -> None:
    with lock_scene:
        with lock_rec_list:
            _scene[scene_id][channel_id][player_id] = rec_data
            rec = (scene_id, channel_id)
            if rec not in _rec_list:
                _rec_list.append(rec)


def up_action(scene_id: int, channel_id: int, msg) -> None:
    with _action_dispatch_lock:
        if _action_queues and not _action_dispatch_stopping:
            _action_queues[_action_shard(scene_id, channel_id)].put(
                (scene_id, channel_id, msg)
            )
        else:
            # worker 尚未启动时保留旧队列语义，启动时会转移这些消息。
            with lock_action:
                _action.append([scene_id, channel_id, msg])


def _action_shard(scene_id: int, channel_id: int) -> int:
    """返回动作键对应的固定分片。不要使用进程随机化的 hash。"""
    return ((int(scene_id) * 2654435761) ^ int(channel_id)) % _action_worker_count


def start_action_workers(consumer, worker_count: int) -> None:
    """启动动作广播分片 worker，并转移启动前积压的动作。"""
    global _action_consumer, _action_worker_count, _action_dispatch_stopping
    worker_count = max(1, int(worker_count))
    with _action_dispatch_lock:
        if _action_workers:
            return
        _action_consumer = consumer
        _action_worker_count = worker_count
        _action_dispatch_stopping = False
        _action_queues[:] = [queue.Queue() for _ in range(worker_count)]
        with lock_action:
            pending = list(_action)
            _action.clear()
        for item in pending:
            _action_queues[_action_shard(item[0], item[1])].put(tuple(item))
        for index in range(worker_count):
            worker = threading.Thread(
                target=_action_worker,
                args=(index,),
                daemon=True,
                name=f"action-sync-{index}",
            )
            _action_workers.append(worker)
            worker.start()


def _action_worker(index: int) -> None:
    action_queue = _action_queues[index]
    while True:
        item = action_queue.get()
        try:
            if item is _ACTION_STOP:
                return
            with _action_dispatch_lock:
                consumer = _action_consumer
            if consumer is not None:
                consumer(*item)
        except Exception:
            logger.exception("Action sync worker failed for item %r", item)
        finally:
            action_queue.task_done()


def stop_action_workers(drain: bool = False) -> None:
    """停止动作 worker。关闭流程默认丢弃尚未发送的广播。"""
    global _action_dispatch_stopping, _action_consumer, _action_worker_count
    with _action_dispatch_lock:
        if not _action_workers:
            return
        _action_dispatch_stopping = True
        workers = list(_action_workers)
        queues = list(_action_queues)
    if drain:
        for action_queue in queues:
            action_queue.join()
    else:
        for action_queue in queues:
            while True:
                try:
                    action_queue.get_nowait()
                except queue.Empty:
                    break
                action_queue.task_done()
    with _action_dispatch_lock:
        for action_queue in queues:
            action_queue.put(_ACTION_STOP)
    for worker in workers:
        worker.join(timeout=2.0)
    alive = any(worker.is_alive() for worker in workers)
    with _action_dispatch_lock:
        if alive:
            return
        _action_workers.clear()
        _action_queues.clear()
        _action_consumer = None
        _action_worker_count = 0


def get_scene_sessions(scene_id: int, channel_id: int) -> List[Any]:
    """获取指定场景频道的在线会话快照，避免广播线程持有全局会话锁发送数据。"""
    with lock_session:
        return [
            session
            for session in _session_list
            if session.running
            and session.logged_in
            and session.scene_id == scene_id
            and session.channel_id == channel_id
        ]


def up_scene_action(scene_id: int, channel_id: int, action: Any) -> None:
    with lock_scene_action:
        _scene_action[scene_id][channel_id].append(action)


def up_chat_msg(chat_channel_id: int, scene_id: int, channel_id: int, notice) -> None:
    with lock_chat_msg:
        _chat_msg.append([chat_channel_id, scene_id, channel_id, notice])


def get_scene_id(player_id: int) -> Optional[int]:
    saved = load_session_location(player_id)
    if saved:
        return int(saved["scene_id"])
    with lock_scene:
        for scene_id, channels in _scene.items():
            for channel_id, players in channels.items():
                if player_id in players:
                    return scene_id
    return 9999


def get_channel_id(player_id: int) -> Optional[int]:
    saved = load_session_location(player_id)
    if saved:
        return int(saved["channel_id"])
    with lock_scene:
        for scene_id, channels in _scene.items():
            for channel_id, players in channels.items():
                if player_id in players:
                    return channel_id
    return 1


def get_scene_player(scene_id, channel_id):
    players = []
    with lock_session:
        for session in _session_list:
            if session.running == False or session.logged_in == False:
                continue
            if session.scene_id == scene_id and session.channel_id == channel_id:
                # 获取所有同场景玩家
                players.append(session.scene_player)
        return players
