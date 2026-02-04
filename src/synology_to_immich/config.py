"""
設定管理モジュール

設定ファイル（TOML）の読み込みと、コマンドライン引数のマージを行う。

設定の優先順位（後で CLI を実装する際に使用）:
1. コマンドライン引数（最優先）
2. 設定ファイル（config.toml）
3. デフォルト値

TOML ファイルの構造例:
    [source]
    path = "smb://192.168.1.1/homes/user/Photo"
    smb_user = "username"
    smb_password = "password"

    [immich]
    url = "http://localhost:2283"
    api_key = "your-api-key"

    [migration]
    dry_run = false
    batch_size = 100
    batch_delay = 1.0

    [synology]
    db_host = "192.168.1.1"
    db_port = 5432
    db_user = "postgres"
    db_password = "password"
    db_name = "synofoto"
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# tomli は Python 3.11 未満で TOML を読み込むためのライブラリ
# Python 3.11 以降では標準ライブラリの tomllib が使える
import tomli


@dataclass
class Config:
    """
    アプリケーション設定を保持するデータクラス

    dataclass デコレータを使うことで:
    - __init__ メソッドが自動生成される
    - __repr__ メソッドが自動生成される（デバッグ時に便利）
    - フィールドの型ヒントが付く

    Attributes:
        source: 移行元のパス（SMB URL またはローカルパス）
                例: "smb://192.168.1.1/photos" または "/mnt/photos"
        immich_url: Immich サーバーの URL
                    例: "http://localhost:2283"
        immich_api_key: Immich API キー（Immich の設定画面で取得）

        dry_run: True の場合、実際にはアップロードしない（テスト用）
        batch_size: 一度に処理するファイル数（メモリ使用量に影響）
        batch_delay: バッチ間の待機秒数（サーバー負荷軽減のため）

        smb_user: SMB 接続用ユーザー名（認証が必要な場合）
        smb_password: SMB 接続用パスワード（認証が必要な場合）

        synology_db_host: Synology PostgreSQL ホスト（メタデータ取得用）
        synology_db_port: Synology PostgreSQL ポート（デフォルト: 5432）
        synology_db_user: Synology PostgreSQL ユーザー
        synology_db_password: Synology PostgreSQL パスワード
        synology_db_name: Synology PostgreSQL データベース名

        progress_db_path: 進捗データベースのパス（SQLite）
    """

    # ===== 必須設定 =====
    # これらは Config を作成する際に必ず指定する必要がある
    source: str  # 移行元パス
    immich_url: str  # Immich サーバー URL
    immich_api_key: str  # Immich API キー

    # ===== オプション設定（デフォルト値あり） =====
    # 指定しない場合はデフォルト値が使われる
    dry_run: bool = False  # True: アップロードをスキップ（テスト用）
    batch_size: int = 100  # 一度に処理するファイル数
    batch_delay: float = 1.0  # バッチ間の待機秒数

    # ===== SMB 設定 =====
    # SMB 接続の認証情報（ローカルパスの場合は不要）
    smb_user: Optional[str] = None  # SMB ユーザー名
    smb_password: Optional[str] = None  # SMB パスワード

    # ===== Synology DB 設定 =====
    # Synology Photos の PostgreSQL データベース接続情報
    # メタデータ（撮影日時、GPS 情報など）を取得するために使用
    synology_db_host: Optional[str] = None  # データベースホスト
    synology_db_port: int = 5432  # データベースポート（PostgreSQL デフォルト）
    synology_db_user: Optional[str] = None  # データベースユーザー
    synology_db_password: Optional[str] = None  # データベースパスワード
    synology_db_name: str = "synofoto"  # データベース名

    # ===== 進捗DB 設定 =====
    # field(default_factory=...) を使う理由:
    # Path オブジェクトのようなミュータブルなデフォルト値は
    # dataclass では default_factory を使う必要がある
    progress_db_path: Path = field(default_factory=lambda: Path("migration_progress.db"))

    @property
    def is_smb_source(self) -> bool:
        """
        ソースが SMB URL かどうかを判定する

        @property デコレータにより、メソッドをプロパティとして
        アクセスできる（括弧なしで config.is_smb_source と書ける）

        Returns:
            True: SMB URL の場合（"smb://" で始まる）
            False: ローカルパスの場合（"/mnt/photos" など）
        """
        # startswith() は文字列が指定した接頭辞で始まるかチェックする
        return self.source.startswith("smb://")


def load_config(config_path: Path) -> Config:
    """
    TOML ファイルから設定を読み込む

    TOML（Tom's Obvious, Minimal Language）は設定ファイル用のフォーマット。
    YAML より厳格で、JSON より人間が読み書きしやすい。

    Args:
        config_path: 設定ファイルのパス（Path オブジェクト）

    Returns:
        Config: 読み込んだ設定を格納した Config オブジェクト

    Raises:
        FileNotFoundError: 設定ファイルが存在しない場合

    使用例:
        config = load_config(Path("config.toml"))
        print(config.source)
    """
    # ファイルの存在確認
    # Path.exists() はファイルまたはディレクトリが存在するかチェックする
    if not config_path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

    # TOML ファイルを読み込む
    # "rb" はバイナリモードで読み込む（tomli の要件）
    with open(config_path, "rb") as f:
        # tomli.load() は TOML ファイルを Python の辞書に変換する
        data = tomli.load(f)

    # セクションごとにデータを取り出す
    # dict.get(key, default) は key が存在しない場合に default を返す
    # default を指定しない場合は None が返る
    source_section = data.get("source", {})  # [source] セクション
    immich_section = data.get("immich", {})  # [immich] セクション
    migration_section = data.get("migration", {})  # [migration] セクション
    synology_section = data.get("synology", {})  # [synology] セクション

    # Config オブジェクトを作成して返す
    # 各セクションから必要な値を取り出し、デフォルト値を指定
    return Config(
        # ===== 必須設定 =====
        source=source_section.get("path", ""),
        immich_url=immich_section.get("url", ""),
        immich_api_key=immich_section.get("api_key", ""),
        # ===== オプション設定 =====
        dry_run=migration_section.get("dry_run", False),
        batch_size=migration_section.get("batch_size", 100),
        batch_delay=migration_section.get("batch_delay", 1.0),
        # ===== SMB 設定 =====
        smb_user=source_section.get("smb_user"),
        smb_password=source_section.get("smb_password"),
        # ===== Synology DB 設定 =====
        synology_db_host=synology_section.get("db_host"),
        synology_db_port=synology_section.get("db_port", 5432),
        synology_db_user=synology_section.get("db_user"),
        synology_db_password=synology_section.get("db_password"),
        synology_db_name=synology_section.get("db_name", "synofoto"),
    )
