"""
world_memory.py
FAISSを用いた動的ワールド知識ベース（RAG）
世界の歴史・設定・プレイヤー行動ログをベクトル化して保存・検索する。
ユーザーの行動によって世界記憶は動的に成長していく。
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

# FAISSインデックスの保存先
INDEX_PATH = Path("faiss_index")

# ---------------------------------------------------------------------------
# 世界の初期ロア（静的シード。変更不可の世界基盤設定）
# ---------------------------------------------------------------------------

INITIAL_LORE = [
    "【世界設定】アルデニア大陸は6000年前に神々の戦争によって三つの大陸に分断された。それぞれが異なる文明を持ち、今も交流・対立が続く。",
    "【世界設定】魔法は「マナストーン」から湧き出るエネルギーを操ることで発動する。一般人はMPを持たないが、特訓により開花することもある。",
    "【世界設定】光の神殿は聖なる結界に守られており、アンデッドや魔族は敷地内に侵入できない。聖職者の聖域とされている。",
    "【世界設定】死者を蘇生させることは禁忌とされており、現存するいかなる魔法でも不可能とされている。",
    "【世界設定】ドラゴン族は炎への耐性を持つが、氷属性魔法に高い弱点を持つ。古竜には精神魔法が無効化される。",
    "【歴史】500年前、勇者ルシアンが魔王軍を撃退したことで「黄金の50年」と呼ばれる平和の時代が到来した。",
    "【歴史】100年前、禁断の儀式によって魔王ザーグの封印が弱まり始めたと言われている。魔族の活動が再び活発化した。",
    "【地理】王都カルンは巨大な石の城壁に囲まれた要塞都市。人口約50万人で大陸最大の商業都市でもある。",
    "【地理】ダルグ火山は魔王軍の本拠地とされており、常に不気味な赤い煙が立ち上っている。一般人の接近は禁じられている。",
    "【キャラクター】勇者アレンは孤児院出身の若き剣士。師匠ガルダに剣術と精神力を叩き込まれ、光の神殿の巫女から使命を授かった。",
    "【キャラクター】闇の魔王ザーグは1000年前に封印されていた古の存在。復活後は四天王を率いてアルデニア征服を企てている。",
    "【キャラクター】魔王軍の四天王はリッチ（死霊術師）、バルガン（竜騎士）、シシャイ（暗殺者）、そして名を秘した謎の召喚師で構成される。",
    "【ルール】魔法の詠唱には時間を要するため、連続での同一魔法使用は通常不可能とされている。",
    "【ルール】勇者の剣「光刃」は魔族に対して通常の1.5倍のダメージを与える特性がある。",
]


class WorldMemory:
    """
    FAISSベースのワールド知識ベース。
    初回起動時は初期ロアを投入し、以降はプレイヤーの行動で動的に成長する。
    """

    def __init__(self, index_path: Path = INDEX_PATH):
        self.index_path = index_path
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.vectorstore: Optional[FAISS] = None
        self._initialize()

    def _initialize(self) -> None:
        """FAISSインデックスをロード、または新規作成する。"""
        if self.index_path.exists():
            try:
                self.vectorstore = FAISS.load_local(
                    str(self.index_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                print(f"[WorldMemory] インデックスをロードしました ({self.index_path})")
                return
            except Exception as e:
                print(f"[WorldMemory] インデックスのロードに失敗。新規作成します。({e})")

        print("[WorldMemory] 初期ロアでFAISSインデックスを新規作成します...")
        docs = [
            Document(
                page_content=lore,
                metadata={"type": "initial_lore", "timestamp": "genesis"},
            )
            for lore in INITIAL_LORE
        ]
        self.vectorstore = FAISS.from_documents(docs, self.embeddings)
        self.save()
        print(f"[WorldMemory] 初期ロア {len(INITIAL_LORE)} 件を登録しました。")

    def add_event(self, text: str, event_type: str = "action_log") -> None:
        """
        新しいイベント・設定をベクトル化して世界記憶に追加する。
        プレイヤーの行動ログや新設定はここから蓄積される。
        """
        doc = Document(
            page_content=text,
            metadata={
                "type": event_type,
                "timestamp": datetime.now().isoformat(),
            },
        )
        self.vectorstore.add_documents([doc])
        self.save()

    def search(self, query: str, k: int = 4) -> list:
        """クエリに関連する世界設定・ロアを上位k件返す。"""
        results = self.vectorstore.similarity_search(query, k=k)
        return [doc.page_content for doc in results]

    def save(self) -> None:
        """FAISSインデックスをディスクに永続化する。"""
        self.index_path.mkdir(exist_ok=True)
        self.vectorstore.save_local(str(self.index_path))

    def get_context_string(self, query: str, k: int = 4) -> str:
        """
        検索結果を1つの文字列に整形してプロンプトへ挿入できる形式で返す。
        """
        results = self.search(query, k=k)
        if not results:
            return "（関連する世界設定が見つかりませんでした）"
        return "\n".join(f"- {r}" for r in results)
