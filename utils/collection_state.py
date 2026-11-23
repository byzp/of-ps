"""收藏进度按资源表中的点位所属场景统计，登录与收集响应共用。"""

import utils.db as db
from config import Config
from proto.net_pb2 import PBCollectionRewardData
from utils.res_loader import res


def scene_items(player_id, scene_id):
    # CollectionTreasureInfos是宝箱点位，不能当作书籍、水晶等收藏品。
    ids = set()
    for row in res["CollectionItem"]["collection_item"]["datas"]:
        region = row["i_d"] // 1000 % 100
        if Config.COLLECTION_REGION_SCENES.get(region, region) == scene_id:
            ids.add(row["i_d"])
    result = {}
    for collection_type, blob in db.get_collection(player_id):
        item = PBCollectionRewardData()
        item.ParseFromString(blob)
        if item.item_id in ids:
            result.setdefault(collection_type, []).append(item)
    return result


def fill_progress(collection, scene_id, count):
    collection.level = 1
    collection.exp = count
    sheet = Config.COLLECTION_LEVEL_SHEETS.get(collection.type)
    if not sheet:
        return
    row = next(
        (row for row in res["Level"][sheet]["datas"] if row["i_d"] == scene_id), None
    )
    if row is None:
        return
    for entry in row.get(sheet + "_info", ()):
        need = entry.get("need_exp", 0)
        if not need or collection.exp < need:
            break
        collection.exp -= need
        collection.level = entry["level"] + 1
