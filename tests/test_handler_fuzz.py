import importlib
import inspect
import pickle
import tempfile
import threading
from pathlib import Path

from config import Config
import utils.db as db
from network.packet_factory import PacketFactory


class FuzzSession:
    def __init__(self):
        self.running = True
        self.address = "fuzz"
        self.player_id = 1
        self.player_name = "Fuzz"
        self.level = 10
        self.world_level = 1
        self.scene_id = 1
        self.channel_id = 1
        self.dungeon = [0, 0, 0, -1]
        self.dungeon_token = ""
        self.quests = {}
        self.temp_pack = []
        self.fishing = False
        self.fishing_token = ""
        self.drop_items = {}
        self.world_monster_tokens = {}
        self.drop_lock = threading.Lock()
        self.sent = []

    def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))

    def close(self):
        self.running = False


def test_all_handlers_contain_malformed_packets_without_granting_items():
    with tempfile.TemporaryDirectory() as directory:
        old_path = Config.DB_PATH
        old_memory = Config.IN_MEMORY
        db.exit()
        Config.DB_PATH = str(Path(directory) / "fuzz.db")
        Config.IN_MEMORY = False
        db.init()
        try:
            db.db.execute(
                "INSERT INTO players(player_id, player_name, level, world_level, unlock_functions) "
                "VALUES (1, 'Fuzz', 10, 1, ?)",
                (pickle.dumps([]),),
            )
            PacketFactory.initialize_handlers(Config.HANDLERS_PACKAGE)
            handlers = sorted(Path(Config.HANDLERS_PACKAGE.replace(".", "/")).glob("*.py"))
            handlers = [path for path in handlers if path.name != "__init__.py"]
            assert len(handlers) == 303
            payloads = (b"", b"\xff", bytes(range(32)))
            for path in handlers:
                module = importlib.import_module(f"handlers.{path.stem}")
                handler_class = getattr(module, "Handler", None)
                assert inspect.isclass(handler_class), path.name
                for payload in payloads:
                    session = FuzzSession()
                    PacketFactory._handle_packet(handler_class(), session, payload, 0, 0)
                    item_rows = db.db.execute(
                        "SELECT COUNT(*) FROM items WHERE player_id=1"
                    ).fetchone()[0]
                    instance_rows = db.db.execute(
                        "SELECT COUNT(*) FROM items_s WHERE player_id=1"
                    ).fetchone()[0]
                    assert item_rows == 0 and instance_rows == 0, (
                        f"{path.name} granted an item from malformed packet {payload!r}"
                    )
        finally:
            PacketFactory.shutdown()
            db.exit()
            Config.DB_PATH = old_path
            Config.IN_MEMORY = old_memory
