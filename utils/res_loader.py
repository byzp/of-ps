import os
import json
from PIL import Image

res = {}
data_dir = "./resources/data"
img_dir = "./resources/swirlnoisetexture"


def convert_lists_to_tuples(obj):
    if isinstance(obj, list):
        return tuple(convert_lists_to_tuples(item) for item in obj)
    elif isinstance(obj, dict):
        return {key: convert_lists_to_tuples(value) for key, value in obj.items()}
    else:
        return obj


def init():
    res.clear()
    for directory in (data_dir, img_dir):
        if not os.path.isdir(directory):
            raise FileNotFoundError(f'Required resource directory is missing: {directory}')
    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith('.json'):
            continue
        path = os.path.join(data_dir, filename)
        try:
            with open(path, 'r', encoding='UTF-8') as source:
                res[filename.split('.')[0]] = json.load(source)
        except (OSError, ValueError) as error:
            raise ValueError(f'Cannot load resource {path}: {error}') from error
    for filename in sorted(os.listdir(img_dir)):
        try:
            res[filename] = Image.open(os.path.join(img_dir, filename)).convert('RGBA')
        except (OSError, ValueError) as error:
            raise ValueError(f'Cannot load resource {filename}: {error}') from error
    required = {
        'Scene': ('scene', 'datas'),
        'Shop': ('grid', 'datas'),
        'ScenesConfigAsset': ('Scenes',),
        'Achieve': ('achieve', 'datas'),
        'Item': ('item', 'datas'),
        'PlayerUnlock': ('player_unlock', 'datas'),
        'Quest': ('quest', 'datas'),
        'Story': ('story', 'datas'),
    }
    for name, keys in required.items():
        value = res.get(name)
        for key in keys:
            value = value.get(key) if isinstance(value, dict) else None
        if not value:
            raise ValueError(f'Required resource table is missing or empty: {name}.{".".join(keys)}')
    for key in res:
        res[key] = convert_lists_to_tuples(res[key])
