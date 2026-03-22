"""
agents.py (v2)
GMエージェント + Refereeエージェント — フルRPG対応版

探索・移動・会話・装備追加・バトルのすべてを処理する。
"""

import json
import re
import random

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from rules import (
    resolve_battle_turn,
    IMMUTABLE_RULES_SUMMARY,
    classify_action,
)
from world_memory import WorldMemory
from world_map import (
    get_location, get_available_actions, resolve_movement,
    get_random_encounter, check_maou_castle_access,
    get_world_map_text,
)
from game_state import GameState
from balance import (
    scale_maou, get_party_avg_level,
    validate_equipment, BALANCE_RULES_SUMMARY,
)
import game_state as gs_module

# ---------------------------------------------------------------------------
# LLMクライアント
# ---------------------------------------------------------------------------

def _llm(temperature: float = 0.75) -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", temperature=temperature)

def _llm_strict() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", temperature=0.0)


# ---------------------------------------------------------------------------
# 探索GMプロンプト
# ---------------------------------------------------------------------------

EXPLORE_GM_PROMPT = """あなたは「アルデニア大陸」のゲームマスターです。

【役割】
プレイヤーの行動・現在地・世界設定をもとに、日本語で臨場感あふれるナラティブを生成してください。
探索・会話・移動・ショッピング・仲間加入など、バトル以外の状況も豊かに描写してください。

【制約】
- 世界設定に存在しない場所・人物・アイテムを作り出してはならない
- 行動の成否は「行動結果」に従い、勝手に変更しない
- 日本語、150〜250文字程度のナラティブテキストのみを出力すること"""

BATTLE_GM_PROMPT = """あなたは「アルデニア大陸」のゲームマスターです。

【役割】
プレイヤーの行動とバトル結果をもとに、日本語で臨場感あふれる戦闘ナラティブを生成してください。

【絶対制約】
- HP・ダメージ・勝敗は「バトル結果」に記載されたファクトを忠実に使用する
- 死者を生き返らせるような描写は禁止
- 数値を自分で変更してはならない
- 日本語、200〜300文字程度のナラティブテキストのみを出力すること"""


# ---------------------------------------------------------------------------
# Refereeプロンプト
# ---------------------------------------------------------------------------

REFEREE_PROMPT = """あなたはゲームの厳格なReferee（審判）です。

GMのナラティブが以下に違反していないか検証してください：
1. 不変ゲームルール（ダメージ計算・勝敗・HP上限）との矛盾
2. 世界設定・確立されたロアとの矛盾
3. バランスルール（装備上限・魔王スケーリング）との矛盾

必ず以下のJSON形式のみで応答すること：
{
  "valid": true または false,
  "issues": ["問題点1", "問題点2"],
  "corrected_narrative": "修正済みナラティブ（valid=falseの場合のみ。それ以外はnull）"
}"""

EQUIPMENT_REFEREE_PROMPT = """あなたはゲームバランスのReferee（審判）です。

プレイヤーが追加しようとしている装備が、ゲームバランスルールに違反していないか検証してください。

必ず以下のJSON形式のみで応答すること：
{
  "valid": true または false,
  "item_name": "装備名（あなたが整形した日本語名）",
  "slot": "weapon / armor / shield / accessory / item のいずれか",
  "bonus_attack": 数値（0以上）,
  "bonus_defense": 数値（0以上）,
  "bonus_magic": 数値（0以上）,
  "bonus_speed": 数値（0以上）,
  "description": "装備の説明文",
  "issues": ["バランス上の問題点"],
  "warnings": ["注意点・調整内容"]
}"""


# ---------------------------------------------------------------------------
# GM生成
# ---------------------------------------------------------------------------

def gm_explore(player_action: str, action_result: dict, context_docs: str, game_state: GameState) -> str:
    """探索・移動・会話用GMナラティブ生成。"""
    human = f"""【現在地】{game_state.current_location}
【世界設定（RAG）】
{context_docs}

【プレイヤーの行動】{player_action}
【行動結果】{json.dumps(action_result, ensure_ascii=False)}

ナラティブを日本語で生成してください。"""
    resp = _llm().invoke([SystemMessage(content=EXPLORE_GM_PROMPT), HumanMessage(content=human)])
    return resp.content.strip()


def gm_battle(player_action: str, battle_result: dict, context_docs: str) -> str:
    """バトル用GMナラティブ生成。"""
    human = f"""【世界設定（RAG）】
{context_docs}

【プレイヤーの行動】{player_action}
【バトル結果（ファクト・変更禁止）】
{battle_result.get('summary', '')}

ナラティブを日本語で生成してください。"""
    resp = _llm().invoke([SystemMessage(content=BATTLE_GM_PROMPT), HumanMessage(content=human)])
    return resp.content.strip()


# ---------------------------------------------------------------------------
# Referee検証
# ---------------------------------------------------------------------------

def referee_validate_narrative(narrative: str, result: dict, context: str) -> dict:
    """GMナラティブの妥当性を検証する。"""
    human = f"""【不変ゲームルール】{IMMUTABLE_RULES_SUMMARY}
【世界設定】{context}
【ファクト】{json.dumps(result, ensure_ascii=False, default=str)}
【GMナラティブ（検証対象）】{narrative}

JSON形式で検証結果を返してください。"""
    resp = _llm_strict().invoke([SystemMessage(content=REFEREE_PROMPT), HumanMessage(content=human)])
    return _parse_json(resp.content, {"valid": True, "issues": [], "corrected_narrative": None})


def referee_validate_equipment(user_input: str, character: dict) -> dict:
    """
    ユーザーの「装備追加」指示をRefereeが解析・検証する。
    Returns: パース済み装備dict（balance.pyで上限チェック後）
    """
    human = f"""【バランスルール】{BALANCE_RULES_SUMMARY}
【対象キャラクター基本ステータス】
  ATK={character.get('attack', 0)}, DEF={character.get('defense', 0)}, MAGIC={character.get('magic', 0)}

【プレイヤーが追加したい装備の説明】
"{user_input}"

上記の説明から装備を解析し、バランスルールに従ってJSON形式で出力してください。
能力値が過剰な場合は上限に調整し、warningsに記録してください。"""

    resp = _llm_strict().invoke([
        SystemMessage(content=EQUIPMENT_REFEREE_PROMPT),
        HumanMessage(content=human)
    ])
    raw = _parse_json(resp.content, {
        "valid": False, "item_name": "不明なアイテム", "slot": "item",
        "bonus_attack": 0, "bonus_defense": 0, "bonus_magic": 0, "bonus_speed": 0,
        "description": "", "issues": ["解析失敗"], "warnings": [],
    })

    # balance.py で2重チェック
    validation = validate_equipment(raw, character)
    if not validation["valid"]:
        raw["valid"] = False
        raw["issues"].extend(validation["issues"])
        raw["warnings"].extend(validation["warnings"])
        # 調整済み値を適用
        for key in ["bonus_attack", "bonus_defense", "bonus_magic"]:
            if key in validation["adjusted_item"]:
                raw[key] = validation["adjusted_item"][key]

    return raw


# ---------------------------------------------------------------------------
# 行動ルーター
# ---------------------------------------------------------------------------

def run_turn(player_action: str, game_state: GameState, world_memory: WorldMemory) -> dict:
    """
    プレイヤーの1ターンを処理する統合パイプライン。
    行動を自動判定して適切な処理に振り分ける。
    """
    action_lower = player_action.lower()
    loc_data = get_location(game_state.current_location)

    # --- 移動 ---
    dest = resolve_movement(player_action, game_state.current_location)
    if dest and not game_state.in_battle:
        return _handle_movement(player_action, dest, game_state, world_memory)

    # --- 休息 ---
    rest_kw = ["宿", "休む", "休息", "泊まる", "rest", "sleep"]
    if any(k in action_lower for k in rest_kw) and loc_data.get("can_rest") and not game_state.in_battle:
        return _handle_rest(player_action, game_state, world_memory)

    # --- ショッピング ---
    shop_kw = ["買う", "購入", "ショップ", "武器屋", "道具屋", "shop", "buy"]
    if any(k in action_lower for k in shop_kw) and loc_data.get("has_shop") and not game_state.in_battle:
        return _handle_shop(player_action, game_state, world_memory)

    # --- 仲間加入 ---
    join_kw = ["仲間", "パーティー", "加入", "連れて", "join"]
    if any(k in action_lower for k in join_kw) and not game_state.in_battle:
        return _handle_npc_join(player_action, game_state, world_memory)

    # --- 魔王に挑む ---
    maou_kw = ["魔王", "ザーグ", "ラスボス", "最終決戦"]
    if any(k in action_lower for k in maou_kw) and not game_state.in_battle:
        return _handle_maou_challenge(player_action, game_state, world_memory)

    # --- バトル中の行動 or 探索してエンカウント ---
    if game_state.in_battle and game_state.current_enemy:
        return _handle_battle_action(player_action, game_state, world_memory)

    # --- フィールド探索（エンカウント判定） ---
    explore_kw = ["探索", "歩く", "進む", "戦う", "モンスター", "敵", "explore", "walk"]
    if any(k in action_lower for k in explore_kw) or loc_data.get("encounter_rate", 0) > 0:
        return _handle_exploration(player_action, game_state, world_memory)

    # --- フリーテキスト（探索ナラティブ） ---
    return _handle_free_action(player_action, game_state, world_memory)


# ---------------------------------------------------------------------------
# 各アクションハンドラ
# ---------------------------------------------------------------------------

def _handle_movement(action: str, dest: str, gs: GameState, wm: WorldMemory) -> dict:
    """移動処理。"""
    # 魔王城へのアクセス条件チェック
    if "魔王城" in dest:
        ok, reason = check_maou_castle_access(gs)
        if not ok:
            return {
                "type": "blocked",
                "narrative": f"⚠️ **{dest}への道は塞がれている。**\n\n{reason}\n\nまずは他の場所を探索しよう。",
                "referee": {"valid": True, "issues": []},
                "context_used": "",
                "game_state_update": {},
            }
        gs.set_flag("maou_castle_unlocked", True)

    prev = gs.current_location
    gs.current_location = dest
    gs.in_battle = False
    gs.current_enemy = None

    # 訪問フラグ
    flag_map = {
        "西の町ブラック": "visited_west_town",
        "湖畔の村エルリア": "visited_lake_village",
        "古代の神殿": "visited_ancient_temple",
        "魔王軍前線基地": "visited_frontline_base",
    }
    for loc_key, flag in flag_map.items():
        if loc_key in dest:
            gs.set_flag(flag, True)

    context = wm.get_context_string(dest + " " + action)
    loc_info = get_location(dest)
    action_result = {
        "moved_from": prev, "moved_to": dest,
        "description": loc_info.get("description", ""),
        "available_actions": get_available_actions(dest, gs),
    }
    narrative = gm_explore(action, action_result, context, gs)
    ref = referee_validate_narrative(narrative, action_result, context)
    if not ref.get("valid") and ref.get("corrected_narrative"):
        narrative = ref["corrected_narrative"]

    wm.add_event(f"【移動】{prev} → {dest}: {narrative[:80]}", "move_log")

    return {
        "type": "move",
        "narrative": narrative,
        "referee": ref,
        "context_used": context,
        "available_actions": action_result["available_actions"],
        "game_state_update": {"location": dest},
    }


def _handle_rest(action: str, gs: GameState, wm: WorldMemory) -> dict:
    """宿屋休息：HPとMPを全回復。"""
    for member in gs.party:
        member["hp"] = member["max_hp"]
        member["mp"] = member["max_mp"]
        member["status_effects"] = []

    context = wm.get_context_string(gs.current_location + " 休息")
    action_result = {"rested": True, "party_healed": [m["name"] for m in gs.party]}
    narrative = gm_explore(action, action_result, context, gs)
    ref = referee_validate_narrative(narrative, action_result, context)
    if not ref.get("valid") and ref.get("corrected_narrative"):
        narrative = ref["corrected_narrative"]

    return {
        "type": "rest",
        "narrative": narrative,
        "referee": ref,
        "context_used": context,
        "available_actions": get_available_actions(gs.current_location, gs),
        "game_state_update": {},
    }


def _handle_shop(action: str, gs: GameState, wm: WorldMemory) -> dict:
    """ショップ案内。"""
    loc = get_location(gs.current_location)
    shop_items = loc.get("shop_items", [])
    context = wm.get_context_string(gs.current_location + " ショップ")
    action_result = {
        "shop_open": True,
        "items": [{k: v for k, v in item.items() if k != "description"} for item in shop_items],
        "message": "以下のアイテムが購入できます。「〇〇を買う」と入力してください。",
    }
    narrative = gm_explore(action, action_result, context, gs)

    # アイテムリスト付きで返す
    item_list = "\n".join(
        f"- **{item['name']}** ({item.get('price', '?')}G) — {item.get('description', '')}"
        for item in shop_items
    )
    full_narrative = narrative + f"\n\n**【商品一覧】**\n{item_list}"

    return {
        "type": "shop",
        "narrative": full_narrative,
        "referee": {"valid": True, "issues": []},
        "context_used": context,
        "available_actions": get_available_actions(gs.current_location, gs),
        "game_state_update": {},
        "shop_items": shop_items,
    }


def _handle_npc_join(action: str, gs: GameState, wm: WorldMemory) -> dict:
    """仲間加入処理。"""
    loc = get_location(gs.current_location)
    npc_info = loc.get("npc_party_member")
    context = wm.get_context_string(gs.current_location + " 仲間")

    if not npc_info:
        action_result = {"join_result": "この場所には加入できる仲間がいない"}
        narrative = gm_explore(action, action_result, context, gs)
        return {"type": "npc", "narrative": narrative, "referee": {"valid": True, "issues": []},
                "context_used": context, "available_actions": get_available_actions(gs.current_location, gs),
                "game_state_update": {}}

    flag = npc_info["flag"]
    char = npc_info["character"]
    if gs.get_flag(flag):
        action_result = {"join_result": f"{char['name']}はすでにパーティーに加入している"}
        narrative = gm_explore(action, action_result, context, gs)
        return {"type": "npc", "narrative": narrative, "referee": {"valid": True, "issues": []},
                "context_used": context, "available_actions": get_available_actions(gs.current_location, gs),
                "game_state_update": {}}

    # 加入
    gs.party.append(dict(char))
    gs.set_flag(flag, True)
    action_result = {"join_result": f"{char['name']}がパーティーに加入した！", "member": char["name"]}
    narrative = gm_explore(action, action_result, context, gs)
    wm.add_event(f"【仲間加入】{char['name']}がパーティーに加わった", "party_log")

    return {"type": "join", "narrative": narrative, "referee": {"valid": True, "issues": []},
            "context_used": context, "available_actions": get_available_actions(gs.current_location, gs),
            "game_state_update": {"party_joined": char["name"]}}


def _handle_maou_challenge(action: str, gs: GameState, wm: WorldMemory) -> dict:
    """魔王への挑戦。アクセス条件チェック後バトル開始。"""
    if gs.current_location != "魔王城":
        ok, reason = check_maou_castle_access(gs)
        if not ok:
            return {
                "type": "blocked",
                "narrative": f"⚠️ まだ魔王城への道は開かれていない。\n\n{reason}",
                "referee": {"valid": True, "issues": []},
                "context_used": "",
                "available_actions": get_available_actions(gs.current_location, gs),
                "game_state_update": {},
            }

    avg_lv = get_party_avg_level(gs.party)
    maou = scale_maou(avg_lv)
    maou["status_effects"] = []
    maou["equipment"] = {}
    gs.current_enemy = maou
    gs.in_battle = True

    context = wm.get_context_string("魔王ザーグ 最終決戦")
    action_result = {
        "battle_start": True,
        "enemy": maou["name"],
        "enemy_hp": maou["hp"],
        "party_avg_lv": avg_lv,
        "scale_applied": f"Lv{avg_lv}スケール適用済み",
        "trial_correction": "装備ボーナスに試練補正(0.7倍)が適用される",
    }
    narrative = gm_explore(action, action_result, context, gs)
    wm.add_event(f"【最終決戦開始】勇者たちが魔王ザーグに挑んだ（Lv{avg_lv}）", "boss_log")

    return {
        "type": "battle_start",
        "narrative": narrative,
        "referee": {"valid": True, "issues": []},
        "context_used": context,
        "available_actions": ["攻撃する", "魔法を使う", "回復する", "防御する"],
        "game_state_update": {"in_battle": True, "enemy": maou["name"]},
        "is_maou_battle": True,
    }


def _handle_battle_action(action: str, gs: GameState, wm: WorldMemory) -> dict:
    """バトル中の行動処理。"""
    enemy = gs.current_enemy
    is_maou = enemy.get("name") == "闇の魔王ザーグ" and enemy.get("phase2_hp") is not None

    # 魔王第2形態チェック
    if is_maou and not enemy.get("phase2_active") and enemy["hp"] <= enemy.get("phase2_hp", 0):
        enemy["phase2_active"] = True
        enemy["attack"] = int(enemy["attack"] * 1.3)
        enemy["magic"]  = int(enemy["magic"]  * 1.3)
        gs.current_enemy = enemy
        context = wm.get_context_string("魔王 第2形態")
        return {
            "type": "phase2",
            "narrative": (
                "⚡ **魔王ザーグが第2形態に変化した！！**\n\n"
                "闇のオーラが膨れ上がり、魔王の力が更なる次元に達した。"
                "攻撃力・魔法力が大幅に上昇している！"
            ),
            "referee": {"valid": True, "issues": []},
            "context_used": context,
            "available_actions": ["攻撃する", "魔法を使う", "回復する", "防御する"],
            "game_state_update": {},
            "is_maou_battle": True,
        }

    result = resolve_battle_turn(action, gs.party, enemy, is_maou_battle=is_maou)
    gs.current_enemy = enemy
    gs.turn += 1

    context = wm.get_context_string(action + " " + enemy.get("name", ""))
    narrative = gm_battle(action, result, context)

    ref = referee_validate_narrative(narrative, result, context)
    for _ in range(2):
        if ref.get("valid", True):
            break
        if ref.get("corrected_narrative"):
            narrative = ref["corrected_narrative"]
            break
        narrative = gm_battle(action + f"\n修正: {','.join(ref.get('issues', []))}", result, context)
        ref = referee_validate_narrative(narrative, result, context)

    outcome = result.get("outcome", "ongoing")
    if outcome == "player_win":
        gs.in_battle = False
        gs.current_enemy = None
        if is_maou:
            gs.victory = True
        wm.add_event(
            f"【バトル終了】{action} → {enemy['name']}を倒した。EXP+{result.get('exp_gained', 0)}",
            "battle_log"
        )
    elif outcome == "enemy_win":
        gs.game_over = True
        gs.in_battle = False
    elif result.get("flee_success"):
        gs.in_battle = False
        gs.current_enemy = None

    return {
        "type": "battle",
        "narrative": narrative,
        "referee": ref,
        "battle_result": result,
        "context_used": context,
        "available_actions": ["攻撃する", "魔法を使う", "回復する", "防御する", "逃げる"] if outcome == "ongoing" else [],
        "game_state_update": {"outcome": outcome},
        "outcome": outcome,
        "is_maou_battle": is_maou,
        "level_ups": result.get("level_ups", []),
    }


def _handle_exploration(action: str, gs: GameState, wm: WorldMemory) -> dict:
    """フィールド探索とエンカウント。"""
    enemy = get_random_encounter(gs.current_location)
    context = wm.get_context_string(gs.current_location + " 探索")

    if enemy:
        gs.current_enemy = enemy
        gs.in_battle = True
        action_result = {
            "encounter": True,
            "enemy": enemy["name"],
            "location": gs.current_location,
        }
        wm.add_event(f"【エンカウント】{gs.current_location}で{enemy['name']}と遭遇", "battle_log")
    else:
        action_result = {
            "encounter": False,
            "location": gs.current_location,
            "description": "モンスターとは遭遇しなかった。",
        }

    narrative = gm_explore(action, action_result, context, gs)
    return {
        "type": "encounter" if enemy else "explore",
        "narrative": narrative,
        "referee": {"valid": True, "issues": []},
        "context_used": context,
        "available_actions": (
            ["攻撃する", "魔法を使う", "回復する", "防御する", "逃げる"]
            if enemy else get_available_actions(gs.current_location, gs)
        ),
        "game_state_update": {"in_battle": bool(enemy)},
        "enemy": enemy,
    }


def _handle_free_action(action: str, gs: GameState, wm: WorldMemory) -> dict:
    """その他のフリーアクション（会話・調査など）。"""
    context = wm.get_context_string(action + " " + gs.current_location)
    action_result = {
        "free_action": action,
        "location": gs.current_location,
    }
    narrative = gm_explore(action, action_result, context, gs)
    ref = referee_validate_narrative(narrative, action_result, context)
    if not ref.get("valid") and ref.get("corrected_narrative"):
        narrative = ref["corrected_narrative"]

    wm.add_event(f"【行動】{gs.current_location}で「{action}」: {narrative[:60]}", "action_log")

    return {
        "type": "free",
        "narrative": narrative,
        "referee": ref,
        "context_used": context,
        "available_actions": get_available_actions(gs.current_location, gs),
        "game_state_update": {},
    }


# ---------------------------------------------------------------------------
# 装備追加パイプライン
# ---------------------------------------------------------------------------

def add_equipment_pipeline(user_input: str, target_member: dict, gs: GameState, wm: WorldMemory) -> dict:
    """
    ユーザーの自然文から装備を解析し、Refereeがバランス検証。
    承認された装備をパーティーメンバーへ適用する。
    """
    item = referee_validate_equipment(user_input, target_member)

    if not item.get("valid") and item.get("issues"):
        return {
            "success": False,
            "item": item,
            "narrative": (
                f"⚠️ **Referee判定: この装備は追加できません。**\n\n"
                + "\n".join(f"- {i}" for i in item["issues"])
            ),
        }

    # 装備をスロットに装着
    slot = item.get("slot", "accessory")
    target_member.setdefault("equipment", {})[slot] = {
        "name": item.get("item_name", "不明なアイテム"),
        "bonus_attack":  item.get("bonus_attack", 0),
        "bonus_defense": item.get("bonus_defense", 0),
        "bonus_magic":   item.get("bonus_magic", 0),
        "bonus_speed":   item.get("bonus_speed", 0),
        "description":   item.get("description", ""),
    }

    wm.add_event(
        f"【装備追加】{target_member['name']}が「{item.get('item_name')}」を装備した",
        "item_log"
    )

    warnings_text = ""
    if item.get("warnings"):
        warnings_text = "\n⚠️ **調整内容:**\n" + "\n".join(f"- {w}" for w in item["warnings"])

    return {
        "success": True,
        "item": item,
        "narrative": (
            f"✅ **{target_member['name']}が「{item.get('item_name')}」を装備した！**\n\n"
            f"{item.get('description', '')}{warnings_text}"
        ),
    }


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def _parse_json(content: str, fallback: dict) -> dict:
    try:
        m = re.search(r"\{.*?\}", content, re.DOTALL)
        if m:
            parsed = json.loads(m.group())
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass
    return fallback
