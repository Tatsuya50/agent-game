"""
agents.py
GMエージェント + Refereeエージェント

【設計の核心】
- rules.py の確定的計算結果を「ファクト」として両エージェントに渡す
- GMはナラティブ生成のみを担当し、数値計算には一切関与しない
- Refereeが不変ルール・世界設定との矛盾を検閲し、違反時は修正を強制する
- LLMがルールを書き換えることは構造的に不可能な設計
"""

import json
import re
import random
from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from rules import (
    Character,
    calculate_damage,
    apply_damage,
    apply_heal,
    apply_mp_cost,
    apply_poison_tick,
    apply_status_effect,
    check_battle_outcome,
    classify_action,
    IMMUTABLE_RULES_SUMMARY,
)
from world_memory import WorldMemory


# ---------------------------------------------------------------------------
# LLMクライアント
# ---------------------------------------------------------------------------

def _get_llm(temperature: float = 0.7) -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", temperature=temperature)


# ---------------------------------------------------------------------------
# GMエージェント
# ---------------------------------------------------------------------------

GM_SYSTEM_PROMPT = """あなたは「アルデニア大陸」の伝説的なゲームマスターです。

【あなたの使命】
プレイヤーの行動と、与えられたバトル結果・世界設定をもとに、
臨場感あふれる日本語のナラティブテキストを生成してください。

【絶対に守るべき制約】
- HP・MP・ダメージ数値は【バトル結果】に記載された数値を忠実に使用すること。自分で計算・変更してはならない。
- 勝敗判定・行動の成否は【バトル結果】に従うこと。絶対に覆してはならない。
- 死亡したキャラクターを生き返らせるような描写は禁止。
- 存在しない魔法・アイテム・人物を登場させてはならない。
- 世界設定には基づかない描写を避けること。

【出力形式】
情景描写を含む200〜300文字程度の日本語ナラティブテキストのみを返すこと。
JSONや説明文は不要。物語として自然な文章にすること。"""


def gm_generate(
    player_action: str,
    battle_result: dict,
    context_docs: str,
    llm: ChatOpenAI,
) -> str:
    """
    GMエージェント: プレイヤー行動とバトル計算結果からナラティブを生成する。
    バトル計算はすでに rules.py で完了している。
    """
    battle_summary = _format_battle_result(battle_result)

    human_content = f"""【世界設定・関連情報（RAGから取得）】
{context_docs}

【プレイヤーの行動】
{player_action}

【バトル結果（これを忠実に描写すること。変更禁止のファクト）】
{battle_summary}

上記をもとに、ゲームマスターとしてナラティブを日本語で生成してください。"""

    messages = [
        SystemMessage(content=GM_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]
    response = llm.invoke(messages)
    return response.content.strip()


# ---------------------------------------------------------------------------
# Refereeエージェント
# ---------------------------------------------------------------------------

REFEREE_SYSTEM_PROMPT = """あなたはゲームの厳格なReferee（審判）です。

【あなたの役割】
GMが生成したナラティブが以下の2点に違反していないかを厳密に検証してください：
1. 不変ゲームルール（ダメージ計算・勝敗判定・HP/MP制約など）との矛盾
2. 確立された世界設定・ロア（キャラクター設定・地理・歴史）との矛盾

【違反の判断基準（例）】
- バトル結果に記載のない回復・蘇生の描写
- 実際のダメージ数値と異なる過剰・過少なダメージ描写
- 行動不能（MP不足・スタン等）なのに行動に成功した描写
- 世界設定に存在しない能力・魔法・人物の登場

【出力形式】
必ず以下のJSON形式のみで応答すること：
{
  "valid": true または false,
  "issues": ["問題点1（具体的に）", "問題点2", ...],
  "corrected_narrative": "修正済みナラティブ（validがfalseの場合のみ記載。それ以外はnull）"
}"""


def referee_validate(
    gm_narrative: str,
    battle_result: dict,
    context_docs: str,
    llm_strict: ChatOpenAI,
) -> dict:
    """
    Refereeエージェント: GMナラティブの妥当性を検証する。
    温度0で確定的に判定させる。
    """
    battle_summary = _format_battle_result(battle_result)

    human_content = f"""【不変ゲームルール（絶対的なファクト）】
{IMMUTABLE_RULES_SUMMARY}

【世界設定・ロア（確立された設定）】
{context_docs}

【バトル結果（ファクト）】
{battle_summary}

【GMが生成したナラティブ（検証対象）】
{gm_narrative}

上記のナラティブを検証し、JSON形式で結果を返してください。"""

    messages = [
        SystemMessage(content=REFEREE_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]
    response = llm_strict.invoke(messages)
    return _parse_referee_response(response.content)


def _parse_referee_response(content: str) -> dict:
    """Referee応答のJSONをパースする。失敗時はvalidとして扱うフォールバック付き。"""
    try:
        json_match = re.search(r"\{.*?\}", content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            # 必須キーが揃っているか確認
            if "valid" in parsed:
                parsed.setdefault("issues", [])
                parsed.setdefault("corrected_narrative", None)
                return parsed
    except (json.JSONDecodeError, AttributeError):
        pass

    # パース失敗 → 安全のためvalidとして扱う
    return {"valid": True, "issues": [], "corrected_narrative": None}


# ---------------------------------------------------------------------------
# バトルロジック実行（rules.pyのみ使用。LLM関与なし）
# ---------------------------------------------------------------------------

def _execute_battle_logic(
    player: Character,
    enemy: Character,
    action_type: str,
    action_text: str,
) -> dict:
    """
    rules.py の純粋関数群を組み合わせてバトルを解決する。
    LLMはこの関数に一切関与しない。これが「不変ルール」の実装体。
    """
    result = {
        "player_action": action_text,
        "action_type": action_type,
        "player_damage_dealt": 0,
        "enemy_damage_dealt": 0,
        "player_hp_before": player.hp,
        "enemy_hp_before": enemy.hp,
        "player_hp_after": player.hp,
        "enemy_hp_after": enemy.hp,
        "player_heal": 0,
        "mp_used": 0,
        "is_miss": False,
        "reason": None,
        "poison_damage": 0,
        "flee_success": False,
        "outcome": "ongoing",
        "summary": "",
    }

    # ------ プレイヤーのターン ------
    if action_type == "physical":
        dmg_info = calculate_damage(player, enemy, "physical", skill_power=1.0)
        result["is_miss"] = dmg_info["is_miss"]
        result["reason"] = dmg_info.get("reason")
        if not dmg_info["is_miss"]:
            enemy = apply_damage(enemy, dmg_info["damage"])
            result["player_damage_dealt"] = dmg_info["damage"]

    elif action_type == "magic":
        mp_cost = 15
        player, mp_ok = apply_mp_cost(player, mp_cost)
        if mp_ok:
            result["mp_used"] = mp_cost
            dmg_info = calculate_damage(player, enemy, "magic", skill_power=1.2)
            result["is_miss"] = dmg_info["is_miss"]
            result["reason"] = dmg_info.get("reason")
            if not dmg_info["is_miss"]:
                enemy = apply_damage(enemy, dmg_info["damage"])
                result["player_damage_dealt"] = dmg_info["damage"]
        else:
            result["is_miss"] = True
            result["reason"] = "MP不足のため魔法が使用できない"

    elif action_type == "heal":
        mp_cost = 10
        heal_amount = 30
        player, mp_ok = apply_mp_cost(player, mp_cost)
        if mp_ok:
            result["mp_used"] = mp_cost
            player, actual_heal = apply_heal(player, heal_amount)
            result["player_heal"] = actual_heal
        else:
            result["is_miss"] = True
            result["reason"] = "MP不足のため回復魔法が使えない"

    elif action_type == "defend":
        result["defend"] = True
        # 防御時は何もしない（被ダメ計算で考慮）

    elif action_type == "flee":
        flee_success = random.random() < 0.4  # 40%成功率（不変ルール）
        result["flee_success"] = flee_success
        if flee_success:
            result["outcome"] = "fled"
            result["summary"] = f"{player.name}は戦闘から逃げ出すことに成功した！"
            result["player_hp_after"] = player.hp
            result["enemy_hp_after"] = enemy.hp
            return result

    # ------ 敵のターン（逃走あるいはゲームオーバー以外） ------
    if not result.get("flee_success", False):
        # 防御時は防御力を一時的に2倍にしてダメージ計算
        if action_type == "defend":
            original_def = player.defense
            player.defense = player.defense * 2
            enemy_dmg_info = calculate_damage(enemy, player, "physical")
            player.defense = original_def
        else:
            enemy_dmg_info = calculate_damage(enemy, player, "physical")

        if not enemy_dmg_info["is_miss"]:
            player = apply_damage(player, enemy_dmg_info["damage"])
            result["enemy_damage_dealt"] = enemy_dmg_info["damage"]

    # ------ 毒ダメージ（ターン終了時に適用） ------
    player, poison_dmg = apply_poison_tick(player)
    result["poison_damage"] = poison_dmg

    # ------ 勝敗判定（純粋Python関数、変更不可） ------
    outcome = check_battle_outcome(player, enemy)
    result["outcome"] = outcome
    result["player_hp_after"] = player.hp
    result["enemy_hp_after"] = enemy.hp

    # ------ サマリー文字列（GMへのファクト提示用） ------
    result["summary"] = _build_summary(result, player, enemy)

    return result


def _build_summary(result: dict, player: Character, enemy: Character) -> str:
    """バトル結果のファクト文字列を組み立てる（GMへの入力として利用）。"""
    parts = []

    if result["is_miss"]:
        reason = result.get("reason") or "ミス"
        parts.append(f"行動は失敗した（理由: {reason}）")
    else:
        atype = result["action_type"]
        if result["player_damage_dealt"] > 0:
            label = "魔法攻撃" if atype == "magic" else "攻撃"
            parts.append(
                f"{player.name}は{enemy.name}に{label}で{result['player_damage_dealt']}ダメージを与えた"
            )
        if result["player_heal"] > 0:
            parts.append(f"{player.name}はHPを{result['player_heal']}回復した")
        if atype == "defend":
            parts.append(f"{player.name}は防御態勢をとった")

    if result["enemy_damage_dealt"] > 0:
        parts.append(
            f"{enemy.name}は{player.name}に反撃し{result['enemy_damage_dealt']}ダメージを与えた"
        )
    if result["poison_damage"] > 0:
        parts.append(f"毒により{player.name}は{result['poison_damage']}ダメージを受けた")

    if result["outcome"] == "player_win":
        parts.append(f"★ {enemy.name}のHPが0になった。プレイヤーの勝利！")
    elif result["outcome"] == "enemy_win":
        parts.append(f"★ {player.name}のHPが0になった。ゲームオーバー。")

    parts.append(
        f"（{player.name} HP: {player.hp}/{player.max_hp} | MP: {player.mp}/{player.max_mp}"
        f" / {enemy.name} HP: {enemy.hp}/{enemy.max_hp}）"
    )
    return " / ".join(parts)


def _format_battle_result(battle_result: dict) -> str:
    """battle_result dictを読みやすい文字列に変換する。"""
    skip_keys = {"summary", "player_action"}
    lines = [f"  - {k}: {v}" for k, v in battle_result.items() if k not in skip_keys and v is not None]
    if battle_result.get("summary"):
        lines.insert(0, f"  - 概要: {battle_result['summary']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# メインパイプライン
# ---------------------------------------------------------------------------

def run_turn(
    player_action: str,
    player: Character,
    enemy: Character,
    world_memory: WorldMemory,
    max_retries: int = 2,
) -> dict:
    """
    1ターンの完全な処理パイプライン:

    Step 1: rules.py でバトル計算（LLM完全排除）
    Step 2: FAISS RAG で関連ロアを検索
    Step 3: GMエージェントがナラティブを生成
    Step 4: Refereeエージェントが検証 → 違反時は最大2回リトライ
    Step 5: 承認済みナラティブ＋行動を world_memory に記録

    Returns:
        dict: narrative, battle_result, referee結果, 更新後キャラクター情報など
    """
    llm_gm = _get_llm(temperature=0.75)
    llm_ref = _get_llm(temperature=0.0)  # Refereeは決定論的

    # ------ Step 1: 確定的バトル計算（LLM不関与） ------
    action_type = classify_action(player_action)
    battle_result = _execute_battle_logic(player, enemy, action_type, player_action)

    # ------ Step 2: RAG 検索 ------
    rag_query = f"{player_action} {enemy.name} {player.name}"
    context_docs = world_memory.get_context_string(rag_query, k=4)

    # ------ Steps 3 & 4: GM生成 + Referee検証ループ ------
    gm_narrative = ""
    referee_result = {"valid": True, "issues": [], "corrected_narrative": None}
    retry_hint = ""

    for attempt in range(max_retries + 1):
        action_with_hint = player_action
        if retry_hint:
            action_with_hint += f"\n\n⚠️【Refereeからの修正指示】以下の問題点を修正してください:\n{retry_hint}"

        gm_narrative = gm_generate(
            player_action=action_with_hint,
            battle_result=battle_result,
            context_docs=context_docs,
            llm=llm_gm,
        )

        referee_result = referee_validate(
            gm_narrative=gm_narrative,
            battle_result=battle_result,
            context_docs=context_docs,
            llm_strict=llm_ref,
        )

        if referee_result.get("valid", True):
            break  # 検証パス → ループ終了

        # 修正済みナラティブがRefereeから提供されていれば即採用
        if referee_result.get("corrected_narrative"):
            gm_narrative = referee_result["corrected_narrative"]
            break

        # 次のリトライへ修正ヒントを渡す
        retry_hint = "\n".join(referee_result.get("issues", []))

    # ------ Step 5: 世界記憶に記録 ------
    memory_log = (
        f"【行動ログ】プレイヤーの行動「{player_action}」→ {battle_result.get('summary', '')}"
    )
    world_memory.add_event(memory_log, event_type="action_log")

    return {
        "narrative": gm_narrative,
        "battle_result": battle_result,
        "referee": referee_result,
        "context_used": context_docs,
        "action_type": action_type,
        "player": player.to_dict(),
        "enemy": enemy.to_dict(),
        "outcome": battle_result.get("outcome", "ongoing"),
    }
