"""
app.py (v2)
Streamlit チャット UI — フルRPGワールド対応版
"""

import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="アルデニア大陸 | World Agent RPG",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# カスタムCSS
st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 60%, #0d1117 100%);
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #161b22 0%, #0d1117 100%);
    border-right: 1px solid #30363d;
}
h1 { color: #f0e6c8 !important; font-family: 'Georgia', serif; }
h3, h4 { color: #c9a96e !important; }
[data-testid="stChatMessage"] {
    background: rgba(22, 27, 34, 0.85) !important;
    border: 1px solid #30363d; border-radius: 12px; margin-bottom: 8px;
}
.stProgress > div > div > div { background: linear-gradient(90deg, #4ade80, #22c55e); }
</style>
""", unsafe_allow_html=True)

# --- 遅延インポート ---
import agents
from game_state import GameState
from world_map import get_available_actions, get_world_map_text, LOCATIONS

# ---------------------------------------------------------------------------
# セッション初期化
# ---------------------------------------------------------------------------

def init_session():
    if "game_state" not in st.session_state:
        st.session_state.game_state = GameState()
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "avatar": "📖",
                "content": (
                    "## ⚔️ アルデニア大陸へようこそ\n\n"
                    "闇の魔王ザーグが復活し、世界に危機が迫っている。\n"
                    "勇者アレンよ、汝の冒険がいま始まる。\n\n"
                    "**📍 現在地: 始まりの村リーデン**\n\n"
                    "行動を自由に入力してください。\n"
                    "例: `西の町へ行く` / `長老に話しかける` / `探索する` / `休む`\n\n"
                    "> 💡 **装備を追加したい場合は「装備を追加」ボタンを使ってください。**"
                ),
            }
        ]
    if "world_memory" not in st.session_state:
        with st.spinner("🌍 世界記憶を初期化中..."):
            from world_memory import WorldMemory
            st.session_state.world_memory = WorldMemory()
    if "show_equipment_panel" not in st.session_state:
        st.session_state.show_equipment_panel = False


init_session()
gs: GameState = st.session_state.game_state


# ---------------------------------------------------------------------------
# コンポーネント: キャラクターステータス
# ---------------------------------------------------------------------------

def render_member_stats(member: dict, compact: bool = False):
    name  = member.get("name", "?")
    hp    = member.get("hp", 0)
    maxhp = member.get("max_hp", 1)
    mp    = member.get("mp", 0)
    maxmp = member.get("max_mp", 1)
    lv    = member.get("level", 1)
    exp   = member.get("exp", 0)
    exp_n = member.get("exp_to_next", 100)

    hp_pct = max(0.0, min(1.0, hp / maxhp))
    mp_pct = max(0.0, min(1.0, mp / maxmp))
    hp_icon = "🟢" if hp_pct > 0.6 else "🟡" if hp_pct > 0.3 else "🔴"
    alive_label = "" if hp > 0 else " 💀"

    st.markdown(f"**{name}** Lv.{lv}{alive_label}")
    st.markdown(f"{hp_icon} HP `{hp}/{maxhp}`")
    st.progress(hp_pct)
    st.markdown(f"🔵 MP `{mp}/{maxmp}`")
    st.progress(mp_pct)

    if not compact:
        exp_pct = min(1.0, exp / max(1, exp_n))
        st.markdown(f"⭐ EXP `{exp}/{exp_n}`")
        st.progress(exp_pct)

        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"⚔ ATK`{member.get('attack',0)}`")
            st.caption(f"🛡 DEF`{member.get('defense',0)}`")
        with col2:
            st.caption(f"✨ MAG`{member.get('magic',0)}`")
            st.caption(f"💨 SPD`{member.get('speed',0)}`")

        equip = member.get("equipment", {})
        if equip:
            with st.expander("🎒 装備中"):
                for slot, item in equip.items():
                    bonuses = []
                    if item.get("bonus_attack", 0):  bonuses.append(f"ATK+{item['bonus_attack']}")
                    if item.get("bonus_defense", 0): bonuses.append(f"DEF+{item['bonus_defense']}")
                    if item.get("bonus_magic", 0):   bonuses.append(f"MAG+{item['bonus_magic']}")
                    st.caption(f"[{slot}] **{item['name']}** {' '.join(bonuses)}")

        if member.get("status_effects"):
            st.warning(f"⚠️ `{'・'.join(member['status_effects'])}`")


def render_enemy_stats(enemy: dict):
    if not enemy:
        return
    hp    = enemy.get("hp", 0)
    maxhp = enemy.get("max_hp", 1)
    hp_pct = max(0.0, min(1.0, hp / maxhp))
    hp_icon = "🟢" if hp_pct > 0.6 else "🟡" if hp_pct > 0.3 else "🔴"
    phase2 = enemy.get("phase2_active", False)
    label = f"**{enemy['name']}**"
    if phase2:
        label += " 🔥 第2形態"
    st.markdown(label)
    st.markdown(f"{hp_icon} HP `{hp}/{maxhp}`")
    st.progress(hp_pct)


# ---------------------------------------------------------------------------
# サイドバー
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 📊 ゲーム情報")
    st.divider()

    st.markdown(f"**📍 現在地**")
    loc_data = LOCATIONS.get(gs.current_location, {})
    st.info(loc_data.get("display_name", gs.current_location))

    st.divider()
    st.markdown("**👥 パーティー**")
    for i, member in enumerate(gs.party):
        with st.expander(f"{'💀' if member.get('hp',0)<=0 else '🧙' if member.get('is_player') else '⚔️'} {member['name']} Lv.{member.get('level',1)}", expanded=(i==0)):
            render_member_stats(member, compact=False)

    if gs.in_battle and gs.current_enemy:
        st.divider()
        st.markdown("**👹 交戦中の敵**")
        render_enemy_stats(gs.current_enemy)

    st.divider()
    st.markdown("**📜 進行状況**")
    flags = gs.flags
    four_count = sum([
        flags.get("heavenly_lich_defeated", False),
        flags.get("heavenly_balgan_defeated", False),
        flags.get("heavenly_sishai_defeated", False),
        flags.get("heavenly_summoner_defeated", False),
    ])
    st.caption(f"四天王討伐: {four_count}/4")
    st.caption(f"古代神殿封印: {'✅' if flags.get('lucifer_seal_broken') else '❌'}")
    st.caption(f"魔王城: {'🔓 解放済' if flags.get('maou_castle_unlocked') else '🔒 封印中'}")
    st.caption(f"ターン数: {gs.turn}")

    st.divider()
    st.markdown("**🗺️ ワールドマップ**")
    with st.expander("マップを見る"):
        st.code(get_world_map_text(gs.current_location).replace("```", ""), language=None)

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🎒 装備追加", use_container_width=True):
            st.session_state.show_equipment_panel = not st.session_state.show_equipment_panel
    with col2:
        if st.button("🔄 リセット", use_container_width=True, type="secondary"):
            for key in ["game_state", "messages", "world_memory", "show_equipment_panel"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()


# ---------------------------------------------------------------------------
# メインエリア
# ---------------------------------------------------------------------------

st.markdown("# 🌍 自律成長するワールド・エージェント RPG")
st.caption("始まりの村から魔王討伐まで — 自由に冒険できるAI駆動RPG | LangChain + FAISS + Streamlit")
st.divider()


# ---------------------------------------------------------------------------
# 装備追加パネル
# ---------------------------------------------------------------------------

if st.session_state.show_equipment_panel:
    with st.expander("🎒 装備追加パネル", expanded=True):
        st.markdown("**自然文で装備を説明してください。Refereeがバランス検証を行います。**")
        st.caption("例: `炎が宿った魔法の剣（ATK+20補正）` / `鋼鉄の盾（DEF大幅強化）` / `回復ポーション×3`")

        target_names = [m["name"] for m in gs.party]
        selected_target = st.selectbox("装備させるキャラクター", target_names)
        equip_input = st.text_area("装備の説明", placeholder="炎の剣、攻撃力がかなり上がる魔法の武器...")

        if st.button("✅ Refereeに検証させる", type="primary"):
            if equip_input.strip():
                target = next((m for m in gs.party if m["name"] == selected_target), gs.party[0])
                with st.spinner("Referee が装備を検証中..."):
                    result = agents.add_equipment_pipeline(equip_input, target, gs, st.session_state.world_memory)

                st.session_state.messages.append({
                    "role": "assistant",
                    "avatar": "🛡️",
                    "content": result["narrative"],
                    "referee": {
                        "valid": result["success"],
                        "issues": result.get("item", {}).get("issues", []),
                    },
                })
                st.session_state.show_equipment_panel = False
                st.rerun()


# ---------------------------------------------------------------------------
# チャット履歴
# ---------------------------------------------------------------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar=msg.get("avatar", "🧙")):
        st.markdown(msg["content"])

        # Referee バッジ
        if msg.get("referee"):
            ref = msg["referee"]
            if ref.get("valid", True):
                if ref.get("issues") == []:
                    pass  # 問題なしは表示不要（ノイズになる）
            else:
                issues = "\n".join(f"• {i}" for i in ref.get("issues", []))
                st.warning(f"⚠️ **Referee修正:** \n{issues}")

        # RAGコンテキスト
        if msg.get("context") and msg["context"].strip():
            with st.expander("📚 参照した世界設定（RAG）"):
                for line in msg["context"].split("\n"):
                    if line.strip():
                        st.caption(line)

        # バトル詳細
        if msg.get("battle_result"):
            br = msg["battle_result"]
            with st.expander("⚔️ バトル詳細（確定計算 by rules.py）"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("総与ダメージ", br.get("total_player_damage", 0))
                c2.metric("受ダメージ", br.get("enemy_damage_dealt", 0))
                c3.metric("回復量", br.get("total_heal", 0))
                c4.metric("EXP獲得", br.get("exp_gained", 0))
                if br.get("reason"):
                    st.info(f"ℹ️ {br['reason']}")

        # 行動サジェスト
        if msg.get("available_actions"):
            with st.expander("💡 この場所でできること"):
                for act in msg["available_actions"][:8]:
                    st.caption(f"▶ {act}")

        # レベルアップ通知
        if msg.get("level_ups"):
            for lu in msg["level_ups"]:
                st.success(f"⬆️ **{lu['name']}** が **Lv.{lu['new_level']}** にレベルアップ！")


# ---------------------------------------------------------------------------
# 入力エリア
# ---------------------------------------------------------------------------

if not gs.game_over and not gs.victory:
    if not os.getenv("OPENAI_API_KEY"):
        st.error("⛔ `.env` ファイルに `OPENAI_API_KEY` が設定されていません。")
    else:
        # バトル中のクイックアクションボタン
        if gs.in_battle:
            st.markdown("**⚡ クイックアクション:**")
            cols = st.columns(5)
            quick_actions = ["剣で攻撃する", "魔法を使う", "回復する", "防御する", "逃げる"]
            for i, (col, act) in enumerate(zip(cols, quick_actions)):
                if col.button(act, key=f"quick_{i}", use_container_width=True):
                    st.session_state._pending_action = act
        else:
            # 現在地の行動サジェスト
            actions = get_available_actions(gs.current_location, gs)
            if actions:
                st.markdown("**💡 行動例:**")
                cols = st.columns(min(4, len(actions)))
                for i, (col, act) in enumerate(zip(cols, actions[:4])):
                    short = act[:20] + "..." if len(act) > 20 else act
                    if col.button(short, key=f"suggest_{i}", use_container_width=True):
                        st.session_state._pending_action = act

        user_input = st.chat_input(
            "行動を自由に入力（例: 西の町へ行く / 魔法で攻撃 / 長老と話す）",
        )

        # ボタンからの入力を優先
        pending = st.session_state.pop("_pending_action", None)
        final_input = pending or user_input

        if final_input:
            st.session_state.messages.append({
                "role": "user",
                "avatar": "🧙",
                "content": final_input,
            })

            with st.spinner("⚙️ 処理中..."):
                try:
                    turn_result = agents.run_turn(
                        final_input,
                        gs,
                        st.session_state.world_memory,
                    )
                    gs.turn += 1 if turn_result.get("type") not in ["move", "rest", "shop"] else 0

                    msg_data = {
                        "role": "assistant",
                        "avatar": _get_avatar(turn_result.get("type", "free")),
                        "content": turn_result.get("narrative", ""),
                        "referee": turn_result.get("referee"),
                        "context": turn_result.get("context_used", ""),
                        "battle_result": turn_result.get("battle_result"),
                        "available_actions": turn_result.get("available_actions", []),
                        "level_ups": turn_result.get("level_ups", []),
                    }
                    st.session_state.messages.append(msg_data)

                    outcome = turn_result.get("outcome", "")

                    if outcome == "player_win" and turn_result.get("is_maou_battle"):
                        gs.victory = True
                        st.balloons()
                        st.session_state.messages.append({
                            "role": "assistant", "avatar": "🏆",
                            "content": (
                                "## 🎉 魔王討伐！ — エンディング\n\n"
                                f"**{gs.turn}ターン**の戦いの末、闇の魔王ザーグを倒した！\n\n"
                                "アルデニア大陸に平和が戻り、勇者アレンの名は永遠に語り継がれる。\n\n"
                                "*「ゲームリセット」で新しい冒険を始められます。*"
                            ),
                        })

                    elif gs.game_over or outcome == "enemy_win":
                        gs.game_over = True
                        st.session_state.messages.append({
                            "role": "assistant", "avatar": "💀",
                            "content": (
                                "## 💀 全滅...\n\n"
                                "パーティーは力尽きた。アルデニアに闇が広がっていく...\n\n"
                                "*「🔄 リセット」で再挑戦できます。*"
                            ),
                        })

                    elif outcome == "player_win":
                        pass  # 通常の敵討伐はナラティブ内で表現済み

                except Exception as e:
                    st.error(f"⚠️ エラーが発生しました: {e}")
                    import traceback
                    with st.expander("エラー詳細"):
                        st.code(traceback.format_exc())

            st.rerun()

elif gs.victory:
    st.success("🏆 ゲームクリア！魔王討伐おめでとうございます！「🔄 リセット」で再プレイできます。")

else:
    st.error("💀 ゲームオーバー。「🔄 リセット」で再チャレンジしましょう。")


def _get_avatar(action_type: str) -> str:
    return {
        "move": "🗺️", "rest": "🏨", "shop": "🏪",
        "join": "🤝", "battle": "⚔️", "phase2": "🔥",
        "battle_start": "⚔️", "encounter": "👹",
        "blocked": "🚫", "free": "📖", "explore": "🌿",
    }.get(action_type, "📖")
