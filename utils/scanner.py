import importlib
import pkgutil
from typing import List, Type


def scan_handlers(package_name: str) -> List[Type]:
    """Scan package for handler classes"""
    handlers = []

    try:
        package = importlib.import_module(package_name)

        for _, module_name, _ in pkgutil.iter_modules(package.__path__):
            full_module_name = f"{package_name}.{module_name}"
            module = importlib.import_module(full_module_name)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and hasattr(attr, "msg_id"):
                    handlers.append(attr)

    except Exception as e:
        raise Exception(f"Failed to scan package {package_name}: {e}")

    return handlers
