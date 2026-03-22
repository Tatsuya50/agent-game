"""
game_state.py
中央ゲーム状態管理

セッション間で永続化すべきすべての状態をここで管理する。
"""

from dataclasses import dataclass, field
from typing import Optional
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# パーティーメンバー定義（dict形式で管理）
# ---------------------------------------------------------------------------

def make_character(
    name: str,
    level: int = 1,
    hp: int = 100, max_hp: int = 100,
    mp: int = 30, max_mp: int = 30,
    attack: int = 20, defense: int = 10,
    magic: int = 15, speed: int = 12,
    exp: int = 0, exp_to_next: int = 100,
    status_effects: list = None,
    equipment: dict = None,
    is_player: bool = False,
    description: str = "",
) -> dict:
    return {
        "name": name,
        "level": level,
        "hp": hp, "max_hp": max_hp,
        "mp": mp, "max_mp": max_mp,
        "attack": attack, "defense": defense,
        "magic": magic, "speed": speed,
        "exp": exp, "exp_to_next": exp_to_next,
        "status_effects": status_effects or [],
        "equipment": equipment or {},
        "is_player": is_player,
        "description": description,
    }


def default_player() -> dict:
    return make_character(
        name="勇者アレン", level=1,
        hp=100, max_hp=100,
        mp=40,  max_mp=40,
        attack=22, defense=12,
        magic=18, speed=15,
        exp=0, exp_to_next=100,
        is_player=True,
        description="孤児院出身の若き剣士。師匠ガルダに鍛えられた正義の勇者。",
    )


# ---------------------------------------------------------------------------
# ゲームフラグ定義
# ---------------------------------------------------------------------------

DEFAULT_FLAGS = {
    # 進行フラグ
    "maou_castle_unlocked": False,       # 魔王城の封印が解けたか
    "four_heavenly_defeated": 0,         # 四天王の討伐数（0〜4）
    "lucifer_seal_broken": False,        # 古代神殿でルシファーの封印破壊
    # 仲間加入フラグ
    "lucia_joined": False,               # 仲間：ルシア（西の町）
    "galm_joined": False,                # 仲間：ガルム（湖畔の村）
    # ショップ・イベントフラグ
    "visited_west_town": False,
    "visited_lake_village": False,
    "visited_ancient_temple": False,
    "visited_frontline_base": False,
    # 四天王個別フラグ
    "heavenly_lich_defeated": False,
    "heavenly_balgan_defeated": False,
    "heavenly_sishai_defeated": False,
    "heavenly_summoner_defeated": False,
}


# ---------------------------------------------------------------------------
# 中央ゲーム状態
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    # 現在地
    current_location: str = "始まりの村リーデン"

    # パーティー（dict形式リスト）
    party: list = field(default_factory=lambda: [default_player()])

    # 所持アイテム（インベントリ）
    inventory: list = field(default_factory=list)

    # 進行フラグ
    flags: dict = field(default_factory=lambda: dict(DEFAULT_FLAGS))

    # ターン数
    turn: int = 0

    # 現在の交戦中の敵（バトル中はここに入る）
    current_enemy: Optional[dict] = None

    # バトル状態
    in_battle: bool = False

    # ゲーム終了状態
    game_over: bool = False
    victory: bool = False

    def get_player(self) -> dict:
        """パーティー内のプレイヤーキャラを取得する。"""
        for m in self.party:
            if m.get("is_player"):
                return m
        return self.party[0] if self.party else default_player()

    def get_party_avg_level(self) -> int:
        if not self.party:
            return 1
        levels = [m.get("level", 1) for m in self.party]
        return max(1, round(sum(levels) / len(levels)))

    def get_alive_members(self) -> list:
        return [m for m in self.party if m.get("hp", 0) > 0]

    def is_party_dead(self) -> bool:
        return all(m.get("hp", 0) <= 0 for m in self.party)

    def add_item(self, item: dict) -> None:
        self.inventory.append(item)

    def set_flag(self, flag_name: str, value) -> None:
        self.flags[flag_name] = value

    def get_flag(self, flag_name: str, default=False):
        return self.flags.get(flag_name, default)

    def to_dict(self) -> dict:
        return {
            "current_location": self.current_location,
            "party": self.party,
            "inventory": self.inventory,
            "flags": self.flags,
            "turn": self.turn,
            "current_enemy": self.current_enemy,
            "in_battle": self.in_battle,
            "game_over": self.game_over,
            "victory": self.victory,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        gs = cls()
        gs.current_location = d.get("current_location", "始まりの村リーデン")
        gs.party = d.get("party", [default_player()])
        gs.inventory = d.get("inventory", [])
        gs.flags = {**DEFAULT_FLAGS, **d.get("flags", {})}
        gs.turn = d.get("turn", 0)
        gs.current_enemy = d.get("current_enemy")
        gs.in_battle = d.get("in_battle", False)
        gs.game_over = d.get("game_over", False)
        gs.victory = d.get("victory", False)
        return gs

    def save(self, path: str = "game_save.json") -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str = "game_save.json") -> "GameState":
        p = Path(path)
        if not p.exists():
            return cls()
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
