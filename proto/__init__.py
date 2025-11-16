import sys
import types
from . import net_pb2

_overfield = types.ModuleType("proto.OverField_pb2")
_overfield.__package__ = "proto"
_overfield.__file__ = __file__

sys.modules["proto.OverField_pb2"] = net_pb2
