import time
import threading

scene = {}

sync_lock = threading.Lock()


def get_recorder(scene_id, channel_id):
    with sync_lock:
        return scene[scene_id][channel_id]


def up_recorder(scene_id, channel_id, user_id, rec_data):
    with sync_lock:
        global scene
        if scene.get(scene_id) is None:
            scene[scene_id] = {}
            scene[scene_id][channel_id] = {}
            scene[scene_id][channel_id][user_id] = rec_data
            return
        if scene[scene_id].get(channel_id) is None:
            scene[scene_id][channel_id] = {}
            scene[scene_id][channel_id][user_id] = rec_data
            return
        scene[scene_id][channel_id][user_id] = rec_data


def get_scene_id(user_id):
    return 9999
    with sync_lock:
        for scene_id, _ in scene:
            return scene_id


def get_channel_id(user_id):
    return 1
    with sync_lock:
        for scene_id, _ in scene:
            return scene_id
        return 9999


""" def get_players(user_id):
    return "players" :{
    "player_id": 9253086
    "player_name": "Vexuro."
    "team" {
      "char_1" {
        "char_id": 101001
        "outfit_preset" {
          "hat": 4012011
          "hair": 4011012
          "clothes": 4012013
          "hat_dye_scheme" {
            "is_un_lock: true"
          }
          "hair_dye_scheme" {
            "colors" {
              "red": 255
              "green": 197
              "blue": 55
            }
            "colors" {
              pos: 1
              red: 8
              green: 22
              blue: 255
            }
            is_un_lock: true
          }
          cloth_dye_scheme {
            colors {
              pos: 1
              red: 5
              green: 1
              blue: 254
            }
            colors {
              pos: 2
              red: 246
              green: 251
              blue: 255
            }
            colors {
              pos: 3
              red: 4
              green: 3
              blue: 2
            }
            colors {
              pos: 5
              red: 235
              green: 251
              blue: 249
            }
            colors {
              pos: 6
              red: 255
              green: 255
              blue: 255
            }
            is_un_lock: true
          }
          9 {
            1: 1
          }
        }
        character_appearance {
          badge: 5000
          umbrella_id: 4050
          logging_axe_instance_id: 33
        }
        pos {
          x: 2346
          z: 896
        }
        rot {
          y: 5934
        }
        weapon_id: 1101402
        weapon_star: 1
        char_lv: 6
        char_star: 2
        char_break_lv: 20
        posters {
          poster_id: 11120
          poster_star: 5
        }
      }
      char_2 {
        char_id: 302002
        outfit_preset {
          hair: 4032022
          clothes: 4032023
          hair_dye_scheme {
            is_un_lock: true
          }
          cloth_dye_scheme {
            is_un_lock: true
          }
          9: ""
        }
        character_appearance {
          badge: 5000
          umbrella_id: 4050
          logging_axe_instance_id: 33
        }
        pos {
          x: 2457
          z: 958
        }
        rot {
          y: 4435
        }
        weapon_id: 1303401
        weapon_star: 1
        char_lv: 11
        char_break_lv: 20
        armors {
          armor_id: 2311005
        }
        posters {
          poster_id: 11030
          poster_star: 4
        }
      }
      char_3 {
        char_id: 403002
        outfit_preset {
          hair: 4043022
          clothes: 4200073
          hair_dye_scheme {
            colors {
              pos: 1
              red: 255
              green: 135
              blue: 182
            }
            colors {
              red: 255
              green: 157
              blue: 178
            }
            is_un_lock: true
          }
          cloth_dye_scheme {
            is_un_lock: true
          }
          9: ""
        }
        character_appearance {
          badge: 5000
          umbrella_id: 4050
          logging_axe_instance_id: 33
        }
        pos {
          x: 2457
          z: 958
        }
        rot {
          y: 4435
        }
        weapon_id: 1401501
        weapon_star: 1
        char_lv: 17
        char_star: 2
        char_break_lv: 20
        armors {
          armor_id: 2412004
        }
        posters {
          poster_id: 10750
          poster_star: 5
        }
      }
    }
  } """
