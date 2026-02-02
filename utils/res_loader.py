import os
import json
from PIL import Image

res = {}
data_dir = "./resources/data"
img_dir = "./resources/swirlnoisetexture"


def init():
    global res
    for f in os.listdir(data_dir):
        with open(os.path.join(data_dir, f), "r", encoding="UTF-8") as jf:
            res[f.split(".")[0]] = json.load(jf)
    for f in os.listdir(img_dir):
        res[f] = Image.open(os.path.join(img_dir, f)).convert("RGBA")
