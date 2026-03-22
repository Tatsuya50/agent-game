# 🌍 自律成長するワールド・エージェント PoC

LangChain + FAISS + Streamlit で構築したAI駆動のRPGシステム。
プレイヤーの行動によって世界の歴史（RAG）が更新されますが、
ゲームの基本ルール（物理法則）はAIによって書き換えられない堅牢な設計です。

## システム構成

```
agent-game/
├── rules.py          # 確定的ゲームロジック（LLM不関与）
├── world_memory.py   # FAISS RAG 世界記憶
├── agents.py         # GM + Referee エージェント
├── app.py            # Streamlit UI
├── pyproject.toml    # uv 依存管理
└── .env              # APIキー（要作成）
```

## セットアップ

```bash
# 1. .env を作成してAPIキーを設定
cp .env.example .env
# .env を編集して OPENAI_API_KEY=sk-... を設定

# 2. 依存パッケージインストール（初回のみ）
uv add langchain langchain-openai langchain-community faiss-cpu streamlit python-dotenv openai tiktoken

# 3. 起動
uv run streamlit run app.py
```

## 設計の核心: AIがルールを書き換えられない仕組み

```
プレイヤー入力
    ↓
[rules.py で確定的バトル計算] ← LLM完全排除
    ↓
[FAISS RAG で世界設定を検索]
    ↓
[GM Agent: ナラティブ生成]    ← バトル結果はファクトとして渡す
    ↓
[Referee Agent: 矛盾検証]     ← 温度0、JSON出力、最大2回リトライ
    ↓
[world_memory に行動ログ追記]  ← 世界の歴史が蓄積される
```
