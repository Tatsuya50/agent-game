"""
world_map.py
ワールドマップ定義 — 拠点・接続・イベント・エンカウント

「始まりの村」から「魔王城」まで、自由に探索できるRPGワールド。
"""

import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game_state import GameState

# ---------------------------------------------------------------------------
# ワールドマップ定義
# ---------------------------------------------------------------------------

LOCATIONS = {
    "始まりの村リーデン": {
        "display_name": "🏘️ 始まりの村リーデン",
        "description": (
            "緑豊かな丘の上に佇む小さな村。勇者アレンが育った故郷。"
            "村の長老が魔王復活の予言を告げた場所でもある。"
        ),
        "connected_to": ["西の町ブラック", "湖畔の村エルリア", "フィールド（リーデン近郊）"],
        "can_rest": True,
        "has_shop": False,
        "npc_hints": ["村の長老から情報を聞く", "旅の準備をする"],
        "encounter_rate": 0.0,
        "enemy_pool": [],
        "events": [
            {
                "id": "elder_talk",
                "trigger": "長老",
                "description": "村の長老から魔王復活と四天王についての情報を得る。",
            }
        ],
    },

    "フィールド（リーデン近郊）": {
        "display_name": "🌿 フィールド（リーデン近郊）",
        "description": "始まりの村周辺に広がる草原。弱いモンスターが出没する。経験値稼ぎに最適。",
        "connected_to": ["始まりの村リーデン", "西の町ブラック", "湖畔の村エルリア"],
        "can_rest": False,
        "has_shop": False,
        "npc_hints": [],
        "encounter_rate": 0.7,
        "enemy_pool": ["スライム", "コボルト", "ゴブリン"],
        "events": [],
    },

    "西の町ブラック": {
        "display_name": "⚔️ 西の町ブラック",
        "description": (
            "冒険者が集まる活気ある商業都市。武器屋と鍛冶場が有名。"
            "腕利きの剣士ルシアがここに滞在している。"
        ),
        "connected_to": ["始まりの村リーデン", "フィールド（リーデン近郊）", "古代の神殿"],
        "can_rest": True,
        "has_shop": True,
        "shop_items": [
            {"name": "鋼鉄の剣", "price": 500, "bonus_attack": 8, "slot": "weapon",
             "description": "よく研ぎ澄まされた鋼鉄製の剣"},
            {"name": "鎖帷子", "price": 400, "bonus_defense": 6, "slot": "armor",
             "description": "軽量で動きやすい鎖の鎧"},
            {"name": "回復薬（小）", "price": 50, "heal": 30, "slot": "item",
             "description": "HPを30回復する"},
            {"name": "回復薬（中）", "price": 150, "heal": 80, "slot": "item",
             "description": "HPを80回復する"},
        ],
        "npc_hints": ["ルシアに話しかける", "武器屋を覗く", "酒場で情報収集"],
        "encounter_rate": 0.0,
        "enemy_pool": [],
        "npc_party_member": {
            "join_condition": "visited_west_town",
            "flag": "lucia_joined",
            "character": {
                "name": "剣士ルシア",
                "level": 3,
                "hp": 120, "max_hp": 120,
                "mp": 20, "max_mp": 20,
                "attack": 30, "defense": 18,
                "magic": 8, "speed": 20,
                "exp": 0, "exp_to_next": 200,
                "status_effects": [],
                "equipment": {
                    "weapon": {"name": "鋼鉄の剣", "bonus_attack": 8}
                },
                "is_player": False,
                "description": "凄腕の女剣士。クールな性格だが仲間思い。",
            },
        },
        "events": [],
    },

    "湖畔の村エルリア": {
        "display_name": "💧 湖畔の村エルリア",
        "description": (
            "澄んだ湖のほとりに建つ自然豊かな村。回復薬の素材が採れることで有名。"
            "老魔法使いのガルムが引退後に暮らしている。"
        ),
        "connected_to": ["始まりの村リーデン", "フィールド（リーデン近郊）", "古代の神殿"],
        "can_rest": True,
        "has_shop": True,
        "shop_items": [
            {"name": "回復薬（大）", "price": 300, "heal": 150, "slot": "item",
             "description": "HPを150回復する"},
            {"name": "万能薬", "price": 500, "heal": 0, "cure_all": True, "slot": "item",
             "description": "全状態異常を回復する"},
            {"name": "魔法の杖", "price": 600, "bonus_magic": 10, "slot": "weapon",
             "description": "魔力を高める神秘の杖"},
            {"name": "魔法のローブ", "price": 450, "bonus_defense": 4, "bonus_magic": 6, "slot": "armor",
             "description": "魔法攻撃への耐性を持つ"},
        ],
        "npc_hints": ["ガルムに話しかける", "薬草屋を訪ねる"],
        "encounter_rate": 0.0,
        "enemy_pool": [],
        "npc_party_member": {
            "join_condition": "visited_lake_village",
            "flag": "galm_joined",
            "character": {
                "name": "魔法使いガルム",
                "level": 4,
                "hp": 80, "max_hp": 80,
                "mp": 90, "max_mp": 90,
                "attack": 12, "defense": 8,
                "magic": 40, "speed": 10,
                "exp": 0, "exp_to_next": 250,
                "status_effects": [],
                "equipment": {
                    "weapon": {"name": "魔法の杖", "bonus_magic": 10}
                },
                "is_player": False,
                "description": "引退した老魔法使いだが、その魔力は健在。孫のような勇者を助けるため立ち上がる。",
            },
        },
        "events": [],
    },

    "古代の神殿": {
        "display_name": "🏛️ 古代の神殿",
        "description": (
            "古代文明の遺跡に建つ謎めいた神殿。内部には強力なモンスターが潜み、"
            "伝説の武器が眠ると言われている。四天王の手下も配置されている。"
        ),
        "connected_to": ["西の町ブラック", "湖畔の村エルリア", "魔王軍前線基地"],
        "can_rest": False,
        "has_shop": False,
        "npc_hints": ["ダンジョンを探索する"],
        "encounter_rate": 0.85,
        "enemy_pool": ["ダークナイト", "スケルトン兵", "石像ゴーレム"],
        "treasure": [
            {"name": "勇者の盾", "bonus_defense": 15, "slot": "shield",
             "description": "古代の勇者が使ったとされる盾。高い防御力を持つ"},
            {"name": "光の宝珠", "bonus_magic": 12, "slot": "accessory",
             "description": "光の魔力が宿る宝珠。魔法威力が上がる"},
        ],
        "events": [
            {
                "id": "ancient_boss",
                "trigger": "ボス",
                "description": "神殿の守護者を倒すと封印が解け、魔王軍前線基地への道が開ける。",
                "flag_on_clear": "lucifer_seal_broken",
            }
        ],
    },

    "魔王軍前線基地": {
        "display_name": "☠️ 魔王軍前線基地",
        "description": (
            "魔王軍が構えた巨大な砦。四天王のうち複数がここを拠点にしている。"
            "非常に危険な場所。しっかり準備してから挑むべきだ。"
        ),
        "connected_to": ["古代の神殿", "魔王城"],
        "can_rest": False,
        "has_shop": False,
        "npc_hints": ["四天王と戦う"],
        "encounter_rate": 0.9,
        "enemy_pool": ["魔王軍兵士", "リッチの骸骨兵", "バルガンの竜騎士"],
        "four_heavenly_battles": [
            {
                "id": "heavenly_lich",
                "flag": "heavenly_lich_defeated",
                "name": "四天王リッチ",
                "level": 12,
                "hp": 400, "max_hp": 400,
                "mp": 200, "max_mp": 200,
                "attack": 55, "defense": 30,
                "magic": 70, "speed": 25,
                "exp_reward": 500,
            },
            {
                "id": "heavenly_balgan",
                "flag": "heavenly_balgan_defeated",
                "name": "四天王バルガン",
                "level": 14,
                "hp": 500, "max_hp": 500,
                "mp": 80, "max_mp": 80,
                "attack": 80, "defense": 50,
                "magic": 20, "speed": 30,
                "exp_reward": 600,
            },
        ],
        "events": [],
    },

    "魔王城": {
        "display_name": "🏰 魔王城",
        "description": (
            "闇のオーラに包まれた魔王ザーグの居城。たどり着いた者には最大の試練が待ち受ける。"
            "封印が解けなければ入ることはできない。"
        ),
        "connected_to": ["魔王軍前線基地"],
        "can_rest": False,
        "has_shop": False,
        "npc_hints": ["魔王ザーグに挑む"],
        "encounter_rate": 0.95,
        "enemy_pool": ["魔王親衛隊", "ダークドラゴン"],
        "requires_flag": "maou_castle_unlocked",
        "events": [
            {
                "id": "final_boss",
                "trigger": "魔王",
                "description": "闇の魔王ザーグとの最終決戦。",
                "is_final_boss": True,
            }
        ],
    },
}


# ---------------------------------------------------------------------------
# ワールドマップ関数
# ---------------------------------------------------------------------------

def get_location(name: str) -> dict:
    """ロケーション情報を返す。存在しない場合はデフォルトを返す。"""
    return LOCATIONS.get(name, LOCATIONS["始まりの村リーデン"])


def get_available_actions(location_name: str, game_state=None) -> list:
    """
    その場所でできる行動の一覧を返す（UI表示・GMへのヒント用）。
    """
    loc = get_location(location_name)
    actions = []

    # 移動
    for dest in loc.get("connected_to", []):
        actions.append(f"「{dest}」へ移動する")

    # 休息
    if loc.get("can_rest"):
        actions.append("宿に泊まって回復する")

    # ショップ
    if loc.get("has_shop"):
        actions.append("武器屋・道具屋で買い物をする")

    # NPC
    for hint in loc.get("npc_hints", []):
        actions.append(hint)

    # イベント
    for event in loc.get("events", []):
        actions.append(event["description"])

    # 探索
    if loc.get("encounter_rate", 0) > 0:
        actions.append("ダンジョンを探索する / 戦闘を探す")

    # 仲間加入
    if game_state and loc.get("npc_party_member"):
        npc_info = loc["npc_party_member"]
        flag = npc_info.get("flag", "")
        if not game_state.get_flag(flag):
            char_name = npc_info["character"]["name"]
            actions.append(f"{char_name}に話しかけて仲間にする")

    return actions


def resolve_movement(action_text: str, current_location: str) -> Optional[str]:
    """
    テキストから移動先を特定する。マッチしない場合はNoneを返す。
    """
    text = action_text.lower()
    loc = get_location(current_location)

    # 現在地の接続先を優先チェック
    for dest in loc.get("connected_to", []):
        keywords = [dest, dest.replace("（", "").replace("）", "")]
        # 拠点名の主要キーワードを抽出して部分一致
        name_parts = dest.replace("🏘️", "").replace("⚔️", "").replace("💧", "").strip()
        for part in name_parts.split("（")[0].split("・"):
            part = part.strip()
            if part and (part in action_text or part.lower() in text):
                return dest

    # 全ロケーションから検索
    for loc_name in LOCATIONS:
        core_name = loc_name.split("（")[0].strip()
        if core_name in action_text:
            return loc_name

    return None


def get_random_encounter(location_name: str) -> Optional[dict]:
    """
    ランダムエンカウントの判定と敵情報を返す。
    """
    loc = get_location(location_name)
    rate = loc.get("encounter_rate", 0.0)

    if random.random() > rate:
        return None  # エンカウントなし

    pool = loc.get("enemy_pool", [])
    if not pool:
        return None

    enemy_name = random.choice(pool)
    return _build_enemy(enemy_name, location_name)


def _build_enemy(name: str, location: str) -> dict:
    """
    敵名と場所から敵ステータスを生成する。
    場所の難易度に応じてスケールする純粋Python関数。
    """
    # 場所別の難易度係数
    difficulty = {
        "フィールド（リーデン近郊）": 1.0,
        "古代の神殿": 2.5,
        "魔王軍前線基地": 3.5,
        "魔王城": 4.5,
    }.get(location, 1.5)

    base = {
        # 弱い敵
        "スライム":     {"hp": 30, "attack": 8, "defense": 3, "magic": 2, "exp_reward": 15},
        "コボルト":     {"hp": 45, "attack": 12, "defense": 5, "magic": 0, "exp_reward": 20},
        "ゴブリン":     {"hp": 55, "attack": 15, "defense": 6, "magic": 0, "exp_reward": 25},
        # 中程度
        "ダークナイト": {"hp": 120, "attack": 35, "defense": 20, "magic": 5, "exp_reward": 80},
        "スケルトン兵": {"hp": 100, "attack": 28, "defense": 15, "magic": 10, "exp_reward": 70},
        "石像ゴーレム": {"hp": 150, "attack": 30, "defense": 30, "magic": 0, "exp_reward": 100},
        # 強い敵
        "魔王軍兵士":   {"hp": 200, "attack": 50, "defense": 30, "magic": 15, "exp_reward": 150},
        "リッチの骸骨兵": {"hp": 180, "attack": 45, "defense": 25, "magic": 35, "exp_reward": 180},
        "バルガンの竜騎士": {"hp": 250, "attack": 60, "defense": 40, "magic": 10, "exp_reward": 200},
        "魔王親衛隊":   {"hp": 300, "attack": 65, "defense": 45, "magic": 20, "exp_reward": 250},
        "ダークドラゴン": {"hp": 400, "attack": 70, "defense": 40, "magic": 50, "exp_reward": 350},
    }.get(name, {"hp": 60, "attack": 20, "defense": 10, "magic": 5, "exp_reward": 40})

    return {
        "name": name,
        "level": max(1, int(difficulty * 3)),
        "hp": int(base["hp"] * difficulty),
        "max_hp": int(base["hp"] * difficulty),
        "mp": 20,
        "max_mp": 20,
        "attack": int(base["attack"] * difficulty),
        "defense": int(base["defense"] * difficulty),
        "magic": int(base["magic"] * difficulty),
        "speed": 10,
        "status_effects": [],
        "equipment": {},
        "exp_reward": int(base["exp_reward"] * difficulty),
    }


def check_maou_castle_access(game_state) -> tuple:
    """
    魔王城へのアクセス条件をチェックする。
    Returns: (アクセス可: bool, 理由: str)
    """
    flags = game_state.flags

    # 四天王を2体以上討伐 OR 古代神殿の封印解除が条件
    four_defeated = sum([
        flags.get("heavenly_lich_defeated", False),
        flags.get("heavenly_balgan_defeated", False),
        flags.get("heavenly_sishai_defeated", False),
        flags.get("heavenly_summoner_defeated", False),
    ])

    if flags.get("maou_castle_unlocked"):
        return True, "魔王城の封印は解けている"

    if four_defeated >= 2 and flags.get("lucifer_seal_broken", False):
        return True, f"四天王{four_defeated}体討伐＋古代神殿の封印解除により、魔王城への道が開いた"

    reasons = []
    if four_defeated < 2:
        reasons.append(f"四天王をあと{2 - four_defeated}体討伐が必要")
    if not flags.get("lucifer_seal_broken"):
        reasons.append("古代の神殿の封印を解く必要がある")

    return False, "封印が解けていない: " + "、".join(reasons)


def get_world_map_text(current_location: str) -> str:
    """テキスト形式のワールドマップ表示を返す。"""
    lines = ["```", "【アルデニア大陸 ワールドマップ】", ""]
    for name, data in LOCATIONS.items():
        marker = "▶ " if name == current_location else "  "
        display = data.get("display_name", name)
        lines.append(f"{marker}{display}")
    lines.append("```")
    return "\n".join(lines)
