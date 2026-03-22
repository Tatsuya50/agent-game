"""
app.py
Streamlit チャット UI — 自律成長するワールド・エージェント PoC
"""

import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# --- ページ設定（Streamlit起動の最初に必ず呼ぶ） ---
st.set_page_config(
    page_title="World Agent PoC | アルデニア大陸",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- カスタムCSS ---
st.markdown("""
<style>
/* 全体背景 */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%);
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #161b22 0%, #0d1117 100%);
    border-right: 1px solid #30363d;
}
/* ヘッダー */
h1 { color: #f0e6c8 !important; font-family: 'Georgia', serif; }
h3, h4 { color: #c9a96e !important; }
/* チャットメッセージ */
[data-testid="stChatMessage"] {
    background: rgba(22, 27, 34, 0.8) !important;
    border: 1px solid #30363d;
    border-radius: 12px;
    margin-bottom: 8px;
}
/* プログレスバーのHP色 */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #4ade80, #22c55e);
}
/* Referee成功バッジ */
[data-testid="stSuccess"] {
    background: rgba(34, 197, 94, 0.1) !important;
    border: 1px solid rgba(34, 197, 94, 0.3) !important;
}
/* Referee警告バッジ */
[data-testid="stWarning"] {
    background: rgba(234, 179, 8, 0.1) !important;
    border: 1px solid rgba(234, 179, 8, 0.3) !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 遅延インポート（APIキー確認後）
# ---------------------------------------------------------------------------
import rules
import agents
from rules import Character, get_default_player, get_default_enemy
from world_memory import WorldMemory


# ---------------------------------------------------------------------------
# セッション初期化
# ---------------------------------------------------------------------------
def init_session():
    if "player" not in st.session_state:
        st.session_state.player = get_default_player()
    if "enemy" not in st.session_state:
        st.session_state.enemy = get_default_enemy()
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "avatar": "📖",
                "content": (
                    "**アルデニア大陸へようこそ。**\n\n"
                    "闇の魔王ザーグが復活し、世界は再び危機に晒されている。\n"
                    "勇者アレンよ——汝の行動がこの世界の歴史を刻む。\n\n"
                    "**行動を入力して、戦いを始めよ。**\n\n"
                    "例: `剣で攻撃する` / `魔法を使う` / `回復する` / `防御する` / `逃げる`"
                ),
            }
        ]
    if "world_memory" not in st.session_state:
        with st.spinner("🌍 世界記憶を初期化中..."):
            st.session_state.world_memory = WorldMemory()
    if "game_over" not in st.session_state:
        st.session_state.game_over = False
    if "turn_count" not in st.session_state:
        st.session_state.turn_count = 0


init_session()


# ---------------------------------------------------------------------------
# コンポーネント: キャラクターステータス表示
# ---------------------------------------------------------------------------
def render_character_stats(char: Character, label: str, icon: str = "⚔️"):
    st.markdown(f"##### {icon} {label}")
    st.markdown(f"**{char.name}**")

    hp_pct = char.hp / char.max_hp if char.max_hp > 0 else 0
    mp_pct = char.mp / char.max_mp if char.max_mp > 0 else 0

    # HP バー
    hp_color = (
        "🟢" if hp_pct > 0.6 else
        "🟡" if hp_pct > 0.3 else
        "🔴"
    )
    st.markdown(f"{hp_color} **HP** `{char.hp} / {char.max_hp}`")
    st.progress(max(0.0, min(1.0, hp_pct)))

    # MP バー
    st.markdown(f"🔵 **MP** `{char.mp} / {char.max_mp}`")
    st.progress(max(0.0, min(1.0, mp_pct)))

    # ステータス
    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"⚔ATK `{char.attack}`")
        st.caption(f"🛡DEF `{char.defense}`")
    with col2:
        st.caption(f"✨MAG `{char.magic}`")
        st.caption(f"💨SPD `{char.speed}`")

    if char.status_effects:
        st.warning(f"⚠️ 状態異常: `{'・'.join(char.status_effects)}`")


# ---------------------------------------------------------------------------
# サイドバー
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚔️ ステータス")
    st.divider()

    render_character_stats(st.session_state.player, "プレイヤー", "🧙")
    st.divider()
    render_character_stats(st.session_state.enemy, "敵", "👹")
    st.divider()

    st.markdown(f"🕐 **経過ターン数:** `{st.session_state.turn_count}`")
    st.divider()

    st.markdown("**💡 行動コマンド例**")
    commands = [
        ("⚔️", "剣で攻撃する"),
        ("✨", "魔法を使う"),
        ("💚", "回復する"),
        ("🛡️", "防御する"),
        ("🏃", "逃げる"),
    ]
    for icon, cmd in commands:
        st.caption(f"{icon} `{cmd}`")

    st.divider()

    if st.button("🔄 ゲームをリセット", use_container_width=True, type="secondary"):
        for key in ["player", "enemy", "messages", "game_over", "turn_count", "world_memory"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    st.divider()
    with st.expander("ℹ️ システム情報"):
        st.caption("**LLM:** gpt-4o")
        st.caption("**RAG:** FAISS (local)")
        st.caption("**構成:** GM Agent + Referee Agent")
        st.caption("**バトル計算:** rules.py (LLM不関与)")
        faiss_path = "faiss_index"
        if os.path.exists(faiss_path):
            st.caption("🟢 FAISSインデックス: 有効")
        else:
            st.caption("🟡 FAISSインデックス: 未作成")


# ---------------------------------------------------------------------------
# メインエリア
# ---------------------------------------------------------------------------
st.markdown("# 🌍 自律成長するワールド・エージェント")
st.caption("あなたの行動が世界の歴史を刻む — AIが語るRPGアドベンチャー PoC | Powered by LangChain + FAISS")
st.divider()

# ---------------------------------------------------------------------------
# チャット履歴表示
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar=msg.get("avatar", "🧙")):
        st.markdown(msg["content"])

        # Referee バッジ表示
        if msg.get("referee"):
            ref = msg["referee"]
            if ref.get("valid", True):
                st.success("✅ Referee: ルール・世界設定との整合性を確認しました")
            else:
                issues_text = "\n".join(f"• {i}" for i in ref.get("issues", []))
                st.warning(
                    f"⚠️ Referee: 以下の問題を検出し修正しました\n{issues_text}"
                )

        # RAG コンテキスト（展開可能）
        if msg.get("context"):
            with st.expander("📚 参照した世界設定（RAGコンテキスト）"):
                for line in msg["context"].split("\n"):
                    if line.strip():
                        st.caption(line)

        # バトル詳細（展開可能）
        if msg.get("battle_info"):
            br = msg["battle_info"]
            with st.expander("⚔️ バトル詳細（確定的計算結果 — rules.py）"):
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(
                        "与ダメージ",
                        br.get("player_damage_dealt", 0),
                        help="rules.pyで計算した確定値"
                    )
                with col2:
                    st.metric(
                        "受ダメージ",
                        br.get("enemy_damage_dealt", 0),
                    )
                with col3:
                    st.metric(
                        "回復量",
                        br.get("player_heal", 0),
                    )
                with col4:
                    st.metric(
                        "毒ダメージ",
                        br.get("poison_damage", 0),
                    )
                if br.get("reason"):
                    st.info(f"ℹ️ {br['reason']}")
                if br.get("action_type"):
                    st.caption(f"行動種別: `{br['action_type']}`")


# ---------------------------------------------------------------------------
# 入力エリア
# ---------------------------------------------------------------------------
if not st.session_state.game_over:
    if not os.getenv("OPENAI_API_KEY"):
        st.error(
            "⛔ `.env` ファイルに `OPENAI_API_KEY` が設定されていません。\n\n"
            "`.env.example` をコピーして `.env` を作成し、APIキーを設定してください。"
        )
    else:
        user_input = st.chat_input(
            "行動を入力してください（例: 剣で攻撃する）",
            disabled=st.session_state.game_over,
        )

        if user_input:
            # ------ ユーザーメッセージを表示 ------
            st.session_state.messages.append({
                "role": "user",
                "avatar": "🧙",
                "content": user_input,
            })

            # ------ ターン処理 ------
            with st.spinner("⚙️ GM・Refereeエージェントが処理中..."):
                try:
                    player = st.session_state.player
                    enemy = st.session_state.enemy
                    wm = st.session_state.world_memory

                    turn_result = agents.run_turn(
                        player_action=user_input,
                        player=player,
                        enemy=enemy,
                        world_memory=wm,
                        max_retries=2,
                    )

                    # ------ キャラクター状態を更新 ------
                    st.session_state.player = Character.from_dict(turn_result["player"])
                    st.session_state.enemy = Character.from_dict(turn_result["enemy"])
                    st.session_state.turn_count += 1

                    # ------ GMナラティブをチャットに追加 ------
                    st.session_state.messages.append({
                        "role": "assistant",
                        "avatar": "📖",
                        "content": turn_result["narrative"],
                        "referee": turn_result["referee"],
                        "context": turn_result["context_used"],
                        "battle_info": turn_result["battle_result"],
                    })

                    # ------ ゲームオーバー / 勝利判定 ------
                    outcome = turn_result.get("outcome", "ongoing")

                    if outcome == "player_win":
                        st.session_state.game_over = True
                        st.balloons()
                        st.session_state.messages.append({
                            "role": "assistant",
                            "avatar": "🏆",
                            "content": (
                                "## 🎉 勝利！\n\n"
                                f"**{st.session_state.turn_count}ターン**で闇の魔王ザーグを討伐しました！\n\n"
                                "あなたの英雄譚はアルデニアの歴史に永遠に刻まれました。\n\n"
                                "*サイドバーの「ゲームリセット」で新しい冒険を始められます。*"
                            ),
                        })

                    elif outcome == "enemy_win":
                        st.session_state.game_over = True
                        st.session_state.messages.append({
                            "role": "assistant",
                            "avatar": "💀",
                            "content": (
                                "## 💀 ゲームオーバー\n\n"
                                "勇者アレンは力尽き、アルデニアに闇が覆い尽くした...\n\n"
                                "*サイドバーの「ゲームリセット」で再挑戦できます。*"
                            ),
                        })

                    elif outcome == "fled":
                        st.session_state.messages.append({
                            "role": "assistant",
                            "avatar": "🏃",
                            "content": "戦場から離脱することに成功した。しかし、魔王はまだ健在だ...",
                        })

                except Exception as e:
                    st.error(f"⚠️ エラーが発生しました: {e}")
                    import traceback
                    with st.expander("エラー詳細"):
                        st.code(traceback.format_exc())

            st.rerun()

else:
    # ゲーム終了後のUI
    st.info(
        "🏁 ゲームが終了しました。"
        "サイドバーの **「🔄 ゲームをリセット」** ボタンで新しい冒険を始められます。"
    )
