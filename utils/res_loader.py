import os
import json

res = {}
res_dir = "./resources/data"


def init():
    global res
    for f in os.listdir(res_dir):
        with open(os.path.join(res_dir, f), "r", encoding="UTF-8") as jf:
            res[f.split(".")[0]] = json.load(jf)
