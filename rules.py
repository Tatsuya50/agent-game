"""
rules.py (v2)
確定的ゲームロジック — フルRPG対応版

LLMは絶対にこの層に関与しない。
"""

import random
from dataclasses import dataclass, field
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# キーワード分類テーブル
# ---------------------------------------------------------------------------

PHYSICAL_KEYWORDS = {"攻撃", "たたかう", "斬る", "殴る", "attack", "strike", "slash", "剣", "撃つ"}
MAGIC_KEYWORDS    = {"魔法", "呪文", "ファイア", "サンダー", "ブリザド", "炎", "氷", "雷", "magic", "spell"}
DEFENSE_KEYWORDS  = {"防御", "守る", "ガード", "guard", "defend"}
FLEE_KEYWORDS     = {"逃げる", "逃走", "flee", "run", "escape", "撤退"}
HEAL_KEYWORDS     = {"回復", "ヒール", "heal", "ポーション", "薬草"}
ITEM_KEYWORDS     = {"アイテム", "道具", "使う", "item", "use"}

# ---------------------------------------------------------------------------
# 不変ルール要約（Referee判定基準）
# ---------------------------------------------------------------------------

IMMUTABLE_RULES_SUMMARY = """
【不変ゲームルール（Referee判定基準）】
1. 物理攻撃ダメージ = max(1, 実効ATK - 実効DEF) × 乱数係数[0.85〜1.15]
2. 魔法攻撃ダメージ = 実効MAGIC × 1.5 × 乱数係数[0.90〜1.10]（DEF無視）
3. HP・MPの回復値は最大値を超えない
4. HP=0のキャラは行動不能。死者の蘇生は不可能
5. 1ターン最大ダメージ = 相手最大HPの75%
6. MP不足時、魔法・回復は発動不可
7. 毒ダメージ = 最大HPの5%/ターン
8. 防御行動時: 受けるダメージを半減
9. 逃走成功率 = 40%（固定）
10. 経験値獲得後にレベルアップ条件を満たした場合、ステータスが成長する
11. 装備ボーナスは balance.py の上限に従う
12. 魔王戦では装備ボーナスに「試練補正」(0.7倍)が適用される
"""

# ---------------------------------------------------------------------------
# 純粋関数: ダメージ計算
# ---------------------------------------------------------------------------

def calculate_damage(
    attacker: dict,
    defender: dict,
    action_type: Literal["physical", "magic"] = "physical",
    skill_power: float = 1.0,
) -> dict:
    if attacker.get("hp", 0) <= 0:
        return {"damage": 0, "is_miss": True, "reason": "攻撃者はすでに倒れている", "variance": 0.0}
    if "スタン" in attacker.get("status_effects", []):
        return {"damage": 0, "is_miss": True, "reason": "スタン状態のため行動不能", "variance": 0.0}

    # 装備込みの実効ステータスを使用
    eff_atk = attacker.get("effective_attack", attacker.get("attack", 0))
    eff_def = defender.get("effective_defense", defender.get("defense", 0))
    eff_mag = attacker.get("effective_magic", attacker.get("magic", 0))

    rng = random.random()

    if action_type == "physical":
        base    = max(1, eff_atk - eff_def)
        variance = 0.85 + rng * 0.30
        raw     = int(base * variance * skill_power)

    elif action_type == "magic":
        if attacker.get("mp", 0) < 10:
            return {"damage": 0, "is_miss": True, "reason": "MP不足のため魔法が使用できない", "variance": 0.0}
        base    = eff_mag * 1.5
        variance = 0.90 + rng * 0.20
        raw     = int(base * variance * skill_power)

    else:
        return {"damage": 0, "is_miss": True, "reason": "不明な行動種別", "variance": 0.0}

    # ルール5: 1ターン最大ダメージ = 相手最大HPの75%
    final = min(raw, int(defender.get("max_hp", 999) * 0.75))
    return {"damage": final, "is_miss": False, "reason": None, "variance": round(variance, 3)}


def apply_damage(character: dict, damage: int) -> dict:
    character["hp"] = max(0, character["hp"] - damage)
    return character


def apply_heal(character: dict, amount: int) -> tuple:
    before = character["hp"]
    character["hp"] = min(character["max_hp"], character["hp"] + amount)
    return character, character["hp"] - before


def apply_mp_cost(character: dict, cost: int) -> tuple:
    if character.get("mp", 0) < cost:
        return character, False
    character["mp"] = max(0, character["mp"] - cost)
    return character, True


def apply_status_effect(character: dict, effect: str) -> tuple:
    effects = character.setdefault("status_effects", [])
    if effect in effects:
        return character, False
    effects.append(effect)
    return character, True


def apply_poison_tick(character: dict) -> tuple:
    if "毒" not in character.get("status_effects", []):
        return character, 0
    dmg = max(1, int(character.get("max_hp", 100) * 0.05))
    character["hp"] = max(0, character["hp"] - dmg)
    return character, dmg


def check_battle_outcome(party: list, enemy: dict) -> Literal["player_win", "enemy_win", "ongoing"]:
    """パーティー全滅 or 敵HP=0 で勝敗決定。"""
    if enemy.get("hp", 0) <= 0:
        return "player_win"
    if all(m.get("hp", 0) <= 0 for m in party):
        return "enemy_win"
    return "ongoing"


# ---------------------------------------------------------------------------
# レベルアップ
# ---------------------------------------------------------------------------

def gain_exp(character: dict, exp: int) -> dict:
    """経験値を獲得し、レベルアップを処理する。Returns 更新後キャラ。"""
    character["exp"] = character.get("exp", 0) + exp
    while character["exp"] >= character.get("exp_to_next", 100):
        character = _level_up(character)
    return character


def _level_up(character: dict) -> dict:
    character["exp"]         -= character.get("exp_to_next", 100)
    character["level"]        = character.get("level", 1) + 1
    lv                        = character["level"]

    # 成長量（レベルが上がるほど伸びが鈍化）
    character["max_hp"]   = int(character["max_hp"]   * 1.12)
    character["hp"]       = character["max_hp"]           # HP全回復
    character["max_mp"]   = int(character["max_mp"]   * 1.08)
    character["mp"]       = character["max_mp"]
    character["attack"]   = int(character["attack"]   * 1.07)
    character["defense"]  = int(character["defense"]  * 1.07)
    character["magic"]    = int(character["magic"]    * 1.07)
    character["speed"]    = int(character["speed"]    * 1.05)

    # HP/MPの上限
    character["max_hp"]  = min(999, character["max_hp"])
    character["max_mp"]  = min(500, character["max_mp"])
    character["hp"]      = min(999, character["hp"])
    character["mp"]      = min(500, character["mp"])

    # 次のレベルアップに必要な経験値（指数的に増加）
    character["exp_to_next"] = int(100 * (lv ** 1.5))

    character["leveled_up"] = True
    return character


# ---------------------------------------------------------------------------
# 装備適用
# ---------------------------------------------------------------------------

def apply_equipment_to_stats(character: dict) -> dict:
    """装備を含めた実効ステータスをcharacterに付与して返す。"""
    equipment = character.get("equipment", {})
    character["effective_attack"]  = character.get("attack", 0)  + sum(e.get("bonus_attack", 0)  for e in equipment.values())
    character["effective_defense"] = character.get("defense", 0) + sum(e.get("bonus_defense", 0) for e in equipment.values())
    character["effective_magic"]   = character.get("magic", 0)   + sum(e.get("bonus_magic", 0)   for e in equipment.values())
    character["effective_speed"]   = character.get("speed", 0)   + sum(e.get("bonus_speed", 0)   for e in equipment.values())
    return character


# ---------------------------------------------------------------------------
# 行動分類
# ---------------------------------------------------------------------------

def classify_action(text: str) -> str:
    t = text.lower()
    for kw in MAGIC_KEYWORDS:
        if kw in t: return "magic"
    for kw in HEAL_KEYWORDS:
        if kw in t: return "heal"
    for kw in DEFENSE_KEYWORDS:
        if kw in t: return "defend"
    for kw in FLEE_KEYWORDS:
        if kw in t: return "flee"
    for kw in ITEM_KEYWORDS:
        if kw in t: return "item"
    return "physical"


# ---------------------------------------------------------------------------
# バトル解決（1ターン）
# ---------------------------------------------------------------------------

def resolve_battle_turn(
    action_text: str,
    party: list,
    enemy: dict,
    is_maou_battle: bool = False,
) -> dict:
    """
    1ターンのバトルを純粋Python関数で解決する。
    パーティー全員が行動し、敵が反撃する。
    LLMはこの関数に一切関与しない。
    """
    from balance import apply_trial_correction, get_effective_stats

    action_type = classify_action(action_text)

    result = {
        "action_type": action_type,
        "player_action": action_text,
        "party_actions": [],
        "enemy_damage_dealt": 0,
        "total_player_damage": 0,
        "total_heal": 0,
        "poison_damage": 0,
        "exp_gained": 0,
        "level_ups": [],
        "is_miss": False,
        "reason": None,
        "flee_success": False,
        "outcome": "ongoing",
    }

    # --- 逃走処理 ---
    if action_type == "flee":
        success = random.random() < 0.40
        result["flee_success"] = success
        result["outcome"] = "fled" if success else "ongoing"
        if success:
            result["summary"] = "戦闘から逃走に成功した！"
            return result

    # --- プレイヤー（+仲間）の行動 ---
    alive_party = [m for m in party if m.get("hp", 0) > 0]

    for i, member in enumerate(alive_party):
        member = apply_equipment_to_stats(member)

        # 魔王戦は試練補正適用
        if is_maou_battle:
            member = get_effective_stats(member, is_maou_battle=True)

        act = action_type if i == 0 else "physical"  # 仲間は物理攻撃
        action_result = {"member": member["name"], "damage": 0, "heal": 0, "miss": False, "reason": None}

        if act == "physical":
            dmg_info = calculate_damage(member, enemy, "physical")
            action_result["miss"] = dmg_info["is_miss"]
            action_result["reason"] = dmg_info.get("reason")
            if not dmg_info["is_miss"]:
                enemy = apply_damage(enemy, dmg_info["damage"])
                action_result["damage"] = dmg_info["damage"]
                result["total_player_damage"] += dmg_info["damage"]

        elif act == "magic":
            mp_cost = 15
            member, mp_ok = apply_mp_cost(member, mp_cost)
            if mp_ok:
                dmg_info = calculate_damage(member, enemy, "magic", skill_power=1.2)
                action_result["miss"] = dmg_info["is_miss"]
                action_result["reason"] = dmg_info.get("reason")
                if not dmg_info["is_miss"]:
                    enemy = apply_damage(enemy, dmg_info["damage"])
                    action_result["damage"] = dmg_info["damage"]
                    result["total_player_damage"] += dmg_info["damage"]
            else:
                action_result["miss"] = True
                action_result["reason"] = "MP不足"

        elif act == "heal":
            mp_cost = 10
            member, mp_ok = apply_mp_cost(member, mp_cost)
            if mp_ok:
                member, healed = apply_heal(member, 30)
                action_result["heal"] = healed
                result["total_heal"] += healed
            else:
                action_result["miss"] = True
                action_result["reason"] = "MP不足のため回復できない"

        elif act == "defend":
            action_result["defend"] = True

        result["party_actions"].append(action_result)
        party[party.index(next(m for m in party if m["name"] == member["name"]))] = member

        # 敵が倒れたらそれ以降の行動は不要
        if enemy.get("hp", 0) <= 0:
            break

    result["is_miss"] = result["party_actions"][0]["miss"] if result["party_actions"] else False
    result["reason"] = result["party_actions"][0]["reason"] if result["party_actions"] else None

    # --- 敵の反撃 ---
    if enemy.get("hp", 0) > 0:
        enemy = apply_equipment_to_stats(enemy)
        target = alive_party[0] if alive_party else party[0]
        defend_mode = action_type == "defend"

        if defend_mode:
            orig_def = target["defense"]
            target["defense"] = orig_def * 2
        enemy_dmg = calculate_damage(enemy, target, "physical")
        if defend_mode:
            target["defense"] = orig_def

        if not enemy_dmg["is_miss"]:
            target = apply_damage(target, enemy_dmg["damage"])
            result["enemy_damage_dealt"] = enemy_dmg["damage"]
            party[party.index(next(m for m in party if m["name"] == target["name"]))] = target

    # --- 毒ダメージ ---
    for i, member in enumerate(party):
        if member.get("hp", 0) > 0:
            member, pdmg = apply_poison_tick(member)
            result["poison_damage"] += pdmg
            party[i] = member

    # --- 勝敗判定 ---
    result["outcome"] = check_battle_outcome(party, enemy)

    # --- 経験値獲得 ---
    if result["outcome"] == "player_win":
        exp = enemy.get("exp_reward", 50)
        result["exp_gained"] = exp
        for i, member in enumerate(party):
            before_lv = member.get("level", 1)
            party[i] = gain_exp(member, exp)
            if party[i].get("level", 1) > before_lv:
                result["level_ups"].append({
                    "name": party[i]["name"],
                    "new_level": party[i]["level"],
                })

    result["summary"] = _build_battle_summary(result, party, enemy)
    return result


def _build_battle_summary(result: dict, party: list, enemy: dict) -> str:
    parts = []
    for a in result.get("party_actions", []):
        if a.get("miss"):
            parts.append(f"{a['member']}の行動は失敗（{a.get('reason', 'ミス')}）")
        elif a.get("damage", 0) > 0:
            parts.append(f"{a['member']}が{enemy['name']}に{a['damage']}ダメージ")
        elif a.get("heal", 0) > 0:
            parts.append(f"{a['member']}がHPを{a['heal']}回復")
        elif a.get("defend"):
            parts.append(f"{a['member']}は防御態勢をとった")

    if result.get("enemy_damage_dealt", 0) > 0:
        first_alive = next((m for m in party if m["hp"] > 0), party[0])
        parts.append(f"{enemy['name']}が{first_alive['name']}に{result['enemy_damage_dealt']}ダメージ")
    if result.get("poison_damage", 0) > 0:
        parts.append(f"毒で{result['poison_damage']}ダメージ")

    if result["outcome"] == "player_win":
        parts.append(f"★ {enemy['name']}を倒した！ EXP+{result.get('exp_gained', 0)}")
        for lu in result.get("level_ups", []):
            parts.append(f"⬆️ {lu['name']}がLv{lu['new_level']}にレベルアップ！")
    elif result["outcome"] == "enemy_win":
        parts.append("★ パーティー全滅。ゲームオーバー。")

    # HP状況サマリー
    hp_parts = []
    for m in party:
        hp_parts.append(f"{m['name']}: HP{m['hp']}/{m['max_hp']}")
    hp_parts.append(f"{enemy['name']}: HP{enemy['hp']}/{enemy['max_hp']}")
    parts.append("（" + " | ".join(hp_parts) + "）")

    return " / ".join(parts)
