"""
rules.py
確定的ゲームロジック（ダメージ計算・HP/MP管理・勝敗判定）
LLMはこのモジュールの「計算結果」を受け取るだけで、
ロジック自体には一切触れません。これが「不変ルール」の核心です。
"""

import random
from dataclasses import dataclass, field
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# データ型定義
# ---------------------------------------------------------------------------

@dataclass
class Character:
    name: str
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    attack: int
    defense: int
    magic: int
    speed: int
    status_effects: list = field(default_factory=list)

    def is_alive(self) -> bool:
        return self.hp > 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_mp,
            "attack": self.attack,
            "defense": self.defense,
            "magic": self.magic,
            "speed": self.speed,
            "status_effects": list(self.status_effects),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        return cls(
            name=d["name"],
            hp=d["hp"],
            max_hp=d["max_hp"],
            mp=d["mp"],
            max_mp=d["max_mp"],
            attack=d["attack"],
            defense=d["defense"],
            magic=d["magic"],
            speed=d["speed"],
            status_effects=list(d.get("status_effects", [])),
        )


# ---------------------------------------------------------------------------
# キーワード分類テーブル（行動テキスト → 行動種別）
# ---------------------------------------------------------------------------

PHYSICAL_KEYWORDS = {"攻撃", "たたかう", "撃つ", "斬る", "殴る", "attack", "strike", "slash", "剣"}
MAGIC_KEYWORDS = {"魔法", "呪文", "ファイア", "サンダー", "ブリザド", "スペル", "magic", "spell", "炎", "氷", "雷"}
DEFENSE_KEYWORDS = {"防御", "守る", "ガード", "身を守る", "guard", "defend", "block"}
FLEE_KEYWORDS = {"逃げる", "逃走", "逃げ出す", "flee", "run", "escape", "撤退"}
HEAL_KEYWORDS = {"回復", "治す", "ヒール", "heal", "restore", "ポーション", "薬草"}


# ---------------------------------------------------------------------------
# 不変ルール要約（Refereeエージェントの判定基準として渡す文字列）
# ---------------------------------------------------------------------------

IMMUTABLE_RULES_SUMMARY = """
【不変ゲームルール（Referee判定基準）】
1. 物理攻撃ダメージ = max(1, 攻撃者ATK - 防御者DEF) × 乱数係数[0.85〜1.15] × スキル倍率
2. 魔法攻撃ダメージ = 攻撃者MAGIC × 1.5 × 乱数係数[0.90〜1.10] × スキル倍率（防御力を無視）
3. HP・MPの回復量は最大値を絶対に超えない
4. HP=0のキャラクターは行動不能。生き返りは不可能
5. 1ターンに与えられる最大ダメージ = 対象の最大HP × 75%
6. MP残量が必要コストを下回る場合、魔法・回復は発動不可
7. 状態異常「毒」は毎ターン最大HPの5%のダメージを与え続ける
8. 状態異常の重複適用は不可（同一効果は1回のみ有効）
9. 防御行動時、プレイヤーの実質防御力は2倍になる
10. 逃走成功率は40%。失敗時は敵の攻撃を受ける
"""


# ---------------------------------------------------------------------------
# 不変ゲームロジック関数群
# ---------------------------------------------------------------------------

def calculate_damage(
    attacker: "Character",
    defender: "Character",
    action_type: Literal["physical", "magic"] = "physical",
    skill_power: float = 1.0,
) -> dict:
    """
    確定的ダメージ計算。
    乱数はゲームルール外に振れないよう範囲を制限。
    LLMはこの関数の存在も計算式も知らない。
    """
    if not attacker.is_alive():
        return {
            "damage": 0,
            "is_miss": True,
            "action_type": action_type,
            "reason": "攻撃者はすでに倒れている",
            "variance": 0.0,
        }

    # スタン状態は行動不能
    if "スタン" in attacker.status_effects:
        return {
            "damage": 0,
            "is_miss": True,
            "action_type": action_type,
            "reason": "スタン状態のため行動不能",
            "variance": 0.0,
        }

    rng = random.random()

    if action_type == "physical":
        base = max(1, attacker.attack - defender.defense)
        variance = 0.85 + rng * 0.30          # 0.85 〜 1.15
        raw_damage = int(base * variance * skill_power)

    elif action_type == "magic":
        if attacker.mp < 10:
            return {
                "damage": 0,
                "is_miss": True,
                "action_type": action_type,
                "reason": "MP不足のため魔法が使用できない",
                "variance": 0.0,
            }
        base = attacker.magic * 1.5
        variance = 0.90 + rng * 0.20          # 0.90 〜 1.10
        raw_damage = int(base * variance * skill_power)

    else:
        return {"damage": 0, "is_miss": True, "action_type": action_type, "reason": "不明な行動種別", "variance": 0.0}

    # ルール5: 1ターン最大ダメージ上限 = 相手最大HPの75%
    max_damage = int(defender.max_hp * 0.75)
    final_damage = min(raw_damage, max_damage)

    return {
        "damage": final_damage,
        "is_miss": False,
        "action_type": action_type,
        "reason": None,
        "variance": round(variance, 3),
    }


def apply_damage(character: "Character", damage: int) -> "Character":
    """HPを減少させる。0未満にはならない。（不変ルール）"""
    character.hp = max(0, character.hp - damage)
    return character


def apply_heal(character: "Character", amount: int) -> tuple:
    """
    HP回復。ルール3: 最大HPを超えない。
    Returns: (更新後キャラクター, 実際に回復した量)
    """
    before = character.hp
    character.hp = min(character.max_hp, character.hp + amount)
    actual_heal = character.hp - before
    return character, actual_heal


def apply_mp_cost(character: "Character", cost: int) -> tuple:
    """
    MP消費。MP不足の場合はFalseを返す。
    Returns: (更新後キャラクター, 成功フラグ)
    """
    if character.mp < cost:
        return character, False
    character.mp = max(0, character.mp - cost)
    return character, True


def apply_status_effect(character: "Character", effect: str) -> tuple:
    """
    状態異常適用。ルール8: 重複適用不可。
    Returns: (更新後キャラクター, 適用成功フラグ)
    """
    if effect in character.status_effects:
        return character, False
    character.status_effects.append(effect)
    return character, True


def apply_poison_tick(character: "Character") -> tuple:
    """
    ルール7: 毒ダメージ処理（毎ターン最大HPの5%）。
    Returns: (更新後キャラクター, 毒ダメージ量)
    """
    if "毒" not in character.status_effects:
        return character, 0
    poison_damage = max(1, int(character.max_hp * 0.05))
    character.hp = max(0, character.hp - poison_damage)
    return character, poison_damage


def check_battle_outcome(
    player: "Character", enemy: "Character"
) -> Literal["player_win", "enemy_win", "ongoing"]:
    """
    ルール10: 勝敗判定。純粋なPython関数。
    LLMはこの結果を絶対に覆せない。これがシステムの根幹。
    """
    if not enemy.is_alive():
        return "player_win"
    if not player.is_alive():
        return "enemy_win"
    return "ongoing"


def classify_action(
    action_text: str,
) -> Literal["physical", "magic", "defend", "flee", "heal", "unknown"]:
    """プレイヤー行動テキストを行動種別に分類する（LLM不使用）。"""
    text = action_text.lower()
    for kw in MAGIC_KEYWORDS:
        if kw in text:
            return "magic"
    for kw in HEAL_KEYWORDS:
        if kw in text:
            return "heal"
    for kw in DEFENSE_KEYWORDS:
        if kw in text:
            return "defend"
    for kw in FLEE_KEYWORDS:
        if kw in text:
            return "flee"
    for kw in PHYSICAL_KEYWORDS:
        if kw in text:
            return "physical"
    return "physical"  # デフォルトは物理攻撃


# ---------------------------------------------------------------------------
# デフォルトキャラクター
# ---------------------------------------------------------------------------

def get_default_player() -> Character:
    return Character(
        name="勇者アレン",
        hp=100, max_hp=100,
        mp=50,  max_mp=50,
        attack=25, defense=10,
        magic=20, speed=15,
    )


def get_default_enemy() -> Character:
    return Character(
        name="闇の魔王ザーグ",
        hp=150, max_hp=150,
        mp=80,  max_mp=80,
        attack=30, defense=8,
        magic=35, speed=12,
    )
