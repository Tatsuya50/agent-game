"""
balance.py
バランス調整エンジン — ゲームバランスを守る純粋Python関数群

【設計思想】
「どんな装備を追加されても魔王戦は苦戦する」を保証する。
LLMは絶対にこの層に関与しない。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rules import Character

# ---------------------------------------------------------------------------
# 魔王基本ステータス（Lv1パーティー想定のベースライン）
# ---------------------------------------------------------------------------

MAOU_BASE_STATS = {
    "name": "闇の魔王ザーグ",
    "hp": 800,
    "max_hp": 800,
    "mp": 300,
    "max_mp": 300,
    "attack": 75,
    "defense": 55,
    "magic": 85,
    "speed": 40,
    "status_effects": [],
    "level": 99,
    "exp_reward": 0,
}

# ---------------------------------------------------------------------------
# バランス定数（ゲームデザインの核心。変更は要慎重）
# ---------------------------------------------------------------------------

# 魔王: パーティー平均Lvごとの強化係数（18%）
MAOU_SCALE_PER_LEVEL = 0.18

# 装備: 1アイテムのATK/DEF上昇上限（キャラ基本値の50%）
EQUIPMENT_STAT_CAP_RATIO = 0.50

# 魔王戦「試練補正」: 装備ボーナスを70%に圧縮
TRIAL_CORRECTION_RATIO = 0.70

# レベル差による試練補正追加（Lv10以上なら緩和しない）
MAOU_PHASE2_HP_THRESHOLD = 0.50   # HP50%以下で第2形態

# 装備ステータス上限（絶対値キャップ。過剰装備の抑止）
ABSOLUTE_ATK_CAP = 150
ABSOLUTE_DEF_CAP = 120
ABSOLUTE_MAGIC_CAP = 140

# ---------------------------------------------------------------------------
# Referee用: バランスルール要約文字列
# ---------------------------------------------------------------------------

BALANCE_RULES_SUMMARY = f"""
【装備・バランス不変ルール（Referee判定基準）】
1. 1アイテムのATK上昇はキャラ基本ATKの{int(EQUIPMENT_STAT_CAP_RATIO*100)}%まで
2. 1アイテムのDEF上昇はキャラ基本DEFの{int(EQUIPMENT_STAT_CAP_RATIO*100)}%まで
3. ATKの絶対上限は{ABSOLUTE_ATK_CAP}、DEFは{ABSOLUTE_DEF_CAP}、MAGICは{ABSOLUTE_MAGIC_CAP}
4. 魔王戦では装備ボーナスに{int(TRIAL_CORRECTION_RATIO*100)}%の試練補正が自動適用される
5. 魔王はパーティー平均Lvに応じてスケールするため、レベルを上げても必ず苦戦する
6. 「無条件に勝てる装備」「死なない装備」「HP無限回復」は設定として存在しない
7. HP最大値は999が上限。MP最大値は500が上限
"""


# ---------------------------------------------------------------------------
# 魔王スケーリング（LLM不関与）
# ---------------------------------------------------------------------------

def scale_maou(party_avg_level: int) -> dict:
    """
    パーティー平均レベルに応じた魔王ステータスを計算して返す。
    どんなに強くなっても必ず苦戦するよう設計。
    """
    scale = 1.0 + max(0, party_avg_level - 1) * MAOU_SCALE_PER_LEVEL
    stats = {k: v for k, v in MAOU_BASE_STATS.items()}

    # 数値ステータスのみスケール
    for key in ["hp", "max_hp", "mp", "max_mp", "attack", "defense", "magic"]:
        stats[key] = int(MAOU_BASE_STATS[key] * scale)

    # 第2形態HP閾値も更新
    stats["phase2_hp"] = int(stats["max_hp"] * MAOU_PHASE2_HP_THRESHOLD)
    stats["phase2_active"] = False

    return stats


def get_party_avg_level(party: list) -> int:
    """パーティーの平均レベルを返す。"""
    if not party:
        return 1
    levels = [m.get("level", 1) if isinstance(m, dict) else getattr(m, "level", 1) for m in party]
    return max(1, round(sum(levels) / len(levels)))


# ---------------------------------------------------------------------------
# 装備バランス検証（LLM不関与）
# ---------------------------------------------------------------------------

def validate_equipment_stat(
    stat_name: str,
    bonus_value: int,
    character_base_value: int,
) -> tuple:
    """
    装備の能力値上昇が許容範囲内かチェックする。
    Returns: (許可フラグ: bool, 調整後の値: int, 理由: str)
    """
    cap = int(character_base_value * EQUIPMENT_STAT_CAP_RATIO)

    # 絶対値キャップも適用
    abs_cap_map = {
        "attack": ABSOLUTE_ATK_CAP,
        "defense": ABSOLUTE_DEF_CAP,
        "magic": ABSOLUTE_MAGIC_CAP,
    }
    abs_cap = abs_cap_map.get(stat_name, 9999)
    effective_cap = min(cap, abs_cap)

    if bonus_value <= effective_cap:
        return True, bonus_value, f"OK（上限 {effective_cap}）"
    else:
        return False, effective_cap, (
            f"「{stat_name}+{bonus_value}」はゲームバランス上限（+{effective_cap}）を超えるため、"
            f"+{effective_cap}に自動調整されます"
        )


def validate_equipment(item: dict, character_base: dict) -> dict:
    """
    装備アイテム全体を検証し、調整済みアイテムを返す。
    Returns: {
        "valid": bool,
        "adjusted_item": dict,
        "issues": list[str],
        "warnings": list[str],
    }
    """
    adjusted = dict(item)
    issues = []
    warnings = []
    is_valid = True

    for stat_key in ["attack", "defense", "magic", "speed"]:
        bonus_key = f"bonus_{stat_key}"
        if bonus_key in item and item[bonus_key] > 0:
            base_val = character_base.get(stat_key, 10)
            ok, adjusted_val, reason = validate_equipment_stat(
                stat_key, item[bonus_key], base_val
            )
            if not ok:
                is_valid = False
                warnings.append(reason)
                adjusted[bonus_key] = adjusted_val

    # 禁止ワードチェック（即時却下）
    forbidden_phrases = [
        "無敵", "絶対", "infinite", "unlimited",
        "HP無限", "不死", "全回復（毎ターン）",
    ]
    name = item.get("name", "")
    desc = item.get("description", "")
    for phrase in forbidden_phrases:
        if phrase in name or phrase in desc:
            issues.append(f"「{phrase}」を含む装備はゲームバランス上使用できません")
            is_valid = False

    return {
        "valid": is_valid,
        "adjusted_item": adjusted,
        "issues": issues,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 試練補正（魔王戦のみ適用）
# ---------------------------------------------------------------------------

def apply_trial_correction(attacker_stats: dict) -> dict:
    """
    魔王戦専用: 装備ボーナスにTRIAL_CORRECTION_RATIOを乗算し、
    プレイヤーの過剰強化を無効化する。
    equipment_bonusのみ圧縮し、基本ステータスはそのまま。
    """
    corrected = dict(attacker_stats)
    for bonus_key in ["bonus_attack", "bonus_defense", "bonus_magic"]:
        if bonus_key in corrected:
            corrected[bonus_key] = int(corrected[bonus_key] * TRIAL_CORRECTION_RATIO)
    return corrected


def get_effective_stats(character_dict: dict, is_maou_battle: bool = False) -> dict:
    """
    装備込みの実効ステータスを計算して返す（LLMには渡さない計算層）。
    魔王戦では試練補正も適用。
    """
    stats = dict(character_dict)
    equipment = character_dict.get("equipment", {})

    bonus_atk = sum(e.get("bonus_attack", 0) for e in equipment.values())
    bonus_def = sum(e.get("bonus_defense", 0) for e in equipment.values())
    bonus_mag = sum(e.get("bonus_magic", 0) for e in equipment.values())
    bonus_spd = sum(e.get("bonus_speed", 0) for e in equipment.values())

    if is_maou_battle:
        bonus_atk = int(bonus_atk * TRIAL_CORRECTION_RATIO)
        bonus_def = int(bonus_def * TRIAL_CORRECTION_RATIO)
        bonus_mag = int(bonus_mag * TRIAL_CORRECTION_RATIO)

    stats["effective_attack"] = stats.get("attack", 0) + bonus_atk
    stats["effective_defense"] = stats.get("defense", 0) + bonus_def
    stats["effective_magic"] = stats.get("magic", 0) + bonus_mag
    stats["effective_speed"] = stats.get("speed", 0) + bonus_spd

    return stats
