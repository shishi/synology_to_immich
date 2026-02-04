"""
進捗管理モジュール

SQLite データベースを使って移行の進捗を追跡する。
このモジュールは以下の機能を提供する：

- 移行済みファイルの記録
- 失敗/未対応ファイルの記録
- 増分移行のための状態管理（すでに移行したファイルはスキップ）

SQLite を使う理由：
- 単一ファイルで管理できる（追加のサーバー不要）
- トランザクション対応（中断しても安全）
- Python 標準ライブラリで対応（追加インストール不要）
"""

import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class FileStatus(Enum):
    """
    ファイルの移行ステータスを表す列挙型

    Enum（列挙型）を使うことで、タイポを防ぎ、
    IDE の補完も効くようになる。

    使用例:
        status = FileStatus.SUCCESS
        if status == FileStatus.FAILED:
            print("移行に失敗しました")
    """

    SUCCESS = "success"  # 移行成功
    FAILED = "failed"  # 移行失敗（リトライ可能）
    UNSUPPORTED = "unsupported"  # 未対応形式（リトライ不要）


class ProgressTracker:
    """
    移行進捗を SQLite で管理するクラス

    このクラスは、どのファイルが移行済みか、失敗したか、
    未対応だったかを追跡する。増分移行（前回の続きから再開）
    を実現するために使用される。

    使用例:
        # データベースを初期化
        tracker = ProgressTracker(Path("progress.db"))

        # 移行成功を記録
        tracker.record_file(
            source_path="/photos/IMG_001.jpg",
            source_hash="abc123",
            source_size=1024,
            source_mtime="2024-01-15T10:30:00",
            immich_asset_id="asset-uuid-001",
            status=FileStatus.SUCCESS,
        )

        # 移行済みかどうかを確認
        if tracker.is_migrated("/photos/IMG_001.jpg"):
            print("このファイルは移行済みです")

        # 必ず最後にクローズする
        tracker.close()

    Attributes:
        db_path: SQLite データベースファイルのパス
    """

    def __init__(self, db_path: Path):
        """
        ProgressTracker を初期化し、必要なテーブルを作成する

        Args:
            db_path: データベースファイルのパス。
                     存在しない場合は自動的に作成される。
        """
        # パスを保存（デバッグやログ出力で使う可能性がある）
        self.db_path = db_path

        # SQLite に接続（ファイルがなければ自動作成）
        # str() で Path を文字列に変換（sqlite3 は Path を直接受け付けない）
        self._conn = sqlite3.connect(str(db_path))

        # 結果を辞書形式で取得できるようにする
        # これにより row["column_name"] でアクセス可能になる
        self._conn.row_factory = sqlite3.Row

        # 必要なテーブルを作成
        self._create_tables()

    def _create_tables(self) -> None:
        """
        必要なテーブルを作成する

        このメソッドは __init__ から呼ばれる内部メソッド。
        アンダースコアで始まるメソッド名は「プライベート」を意味し、
        外部から直接呼び出すべきでないことを示す。

        SQLite の CREATE TABLE IF NOT EXISTS を使うことで、
        テーブルが存在しない場合のみ作成される。
        """
        # cursor は SQL 文を実行するためのオブジェクト
        cursor = self._conn.cursor()

        # 移行済みファイルテーブル
        # このテーブルが進捗管理の中心
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS migrated_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 自動採番される一意の ID
                source_path TEXT UNIQUE NOT NULL,      -- 元ファイルのパス（重複不可）
                source_hash TEXT,                      -- ファイルの SHA256 ハッシュ
                source_size INTEGER,                   -- ファイルサイズ（バイト）
                source_mtime TEXT,                     -- 元ファイルの更新日時
                immich_asset_id TEXT,                  -- Immich でのアセット ID
                migrated_at TEXT NOT NULL,             -- 移行した日時
                status TEXT NOT NULL,                  -- 移行ステータス
                error_message TEXT                     -- エラーメッセージ（失敗時）
            )
        """
        )

        # 既存テーブルに error_message カラムがない場合は追加
        # ALTER TABLE は IF NOT EXISTS をサポートしないので、例外を無視する
        try:
            cursor.execute(
                "ALTER TABLE migrated_files ADD COLUMN error_message TEXT"
            )
        except sqlite3.OperationalError:
            # カラムが既に存在する場合は無視
            pass

        # アルバムテーブル
        # Synology Photos のアルバムと Immich のアルバムの対応を記録
        # UNIQUE 制約を synology_album_id に追加して、UPSERT を可能にする
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS migrated_albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                synology_album_id INTEGER UNIQUE,  -- Synology Photos でのアルバム ID（重複不可）
                synology_album_name TEXT,          -- アルバム名
                immich_album_id TEXT,              -- Immich でのアルバム ID
                created_at TEXT NOT NULL           -- 作成日時
            )
        """
        )

        # インデックス作成（検索を高速化するため）
        # source_path での検索が多いのでインデックスを作成
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_source_path
            ON migrated_files(source_path)
        """
        )

        # status での検索も多い（失敗したファイルの一覧取得など）
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_status
            ON migrated_files(status)
        """
        )

        # 変更をデータベースに確定（コミット）
        self._conn.commit()

    def record_file(
        self,
        source_path: str,
        source_hash: Optional[str],
        source_size: int,
        source_mtime: str,
        immich_asset_id: Optional[str],
        status: FileStatus,
        error_message: Optional[str] = None,
    ) -> None:
        """
        ファイルの移行結果を記録する

        同じ source_path のレコードがすでに存在する場合は更新（UPSERT）される。
        これにより、失敗したファイルを再度移行した場合に、
        ステータスを更新できる。

        Args:
            source_path: 元ファイルのパス（例: "/photos/IMG_001.jpg"）
            source_hash: ファイルの SHA256 ハッシュ（変更検出に使用）
            source_size: ファイルサイズ（バイト）
            source_mtime: 元ファイルの更新日時（ISO 形式の文字列）
            immich_asset_id: Immich 側のアセット ID（失敗時は None）
            status: 移行ステータス（FileStatus 列挙型）
            error_message: エラーメッセージ（失敗時のみ。成功時は None）
        """
        cursor = self._conn.cursor()

        # 現在時刻を ISO 形式で取得（例: "2024-01-15T10:30:00.123456"）
        now = datetime.now().isoformat()

        # UPSERT（INSERT or UPDATE）
        # ON CONFLICT で source_path が重複した場合の動作を指定
        # excluded は「挿入しようとした値」を参照するための特殊な識別子
        cursor.execute(
            """
            INSERT INTO migrated_files
            (source_path, source_hash, source_size, source_mtime,
             immich_asset_id, migrated_at, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                source_hash = excluded.source_hash,
                source_size = excluded.source_size,
                source_mtime = excluded.source_mtime,
                immich_asset_id = excluded.immich_asset_id,
                migrated_at = excluded.migrated_at,
                status = excluded.status,
                error_message = excluded.error_message
            """,
            (
                source_path,
                source_hash,
                source_size,
                source_mtime,
                immich_asset_id,
                now,
                status.value,  # Enum の値（文字列）を取得
                error_message,
            ),
        )

        # 変更を確定
        self._conn.commit()

    def get_file(self, source_path: str) -> Optional[dict]:
        """
        指定パスのファイル情報を取得する

        Args:
            source_path: 元ファイルのパス

        Returns:
            ファイル情報の辞書。存在しない場合は None。
            辞書には以下のキーが含まれる:
            - source_path: 元ファイルのパス
            - source_hash: ファイルハッシュ
            - source_size: ファイルサイズ
            - source_mtime: 更新日時
            - immich_asset_id: Immich のアセット ID
            - migrated_at: 移行日時
            - status: 移行ステータス
        """
        cursor = self._conn.cursor()

        # プレースホルダー（?）を使ってパラメータを渡す
        # 文字列連結を使わないことで SQL インジェクションを防ぐ
        cursor.execute(
            "SELECT * FROM migrated_files WHERE source_path = ?",
            (source_path,),  # タプルで渡す（要素が1つでもカンマが必要）
        )

        # fetchone() は結果が1行だけ、または0行の場合に使う
        row = cursor.fetchone()

        # Row オブジェクトを辞書に変換して返す
        # row が None の場合（レコードが見つからない場合）は None を返す
        return dict(row) if row else None

    def is_migrated(self, source_path: str) -> bool:
        """
        ファイルが正常に移行済みかどうかを判定する

        FAILED や UNSUPPORTED ステータスのファイルは
        移行済みとは見なさない。SUCCESS のみが True を返す。

        Args:
            source_path: 元ファイルのパス

        Returns:
            True: 移行成功済み（再度移行する必要なし）
            False: 未移行、または失敗/未対応
        """
        file_info = self.get_file(source_path)

        # ファイル情報が見つからない場合は未移行
        if file_info is None:
            return False

        # SUCCESS の場合のみ True を返す
        return file_info["status"] == FileStatus.SUCCESS.value

    def get_files_by_status(self, status: FileStatus) -> list[dict]:
        """
        指定ステータスのファイル一覧を取得する

        リトライ対象（FAILED）のファイル一覧を取得したり、
        未対応形式（UNSUPPORTED）のファイルをレポートしたりするのに使う。

        結果は source_path でソートされる。これにより、
        再開可能な検証機能で常に同じ順序でファイルを取得できる。

        Args:
            status: フィルタするステータス（FileStatus 列挙型）

        Returns:
            ファイル情報の辞書のリスト（source_path でソート済み）
        """
        cursor = self._conn.cursor()

        # ORDER BY source_path で一定の順序を保証
        # 再開可能な検証機能で、同じ順序でファイルを処理するために必要
        cursor.execute(
            "SELECT * FROM migrated_files WHERE status = ? ORDER BY source_path",
            (status.value,),  # Enum の値（文字列）を使用
        )

        # fetchall() は複数行の結果を取得
        # リスト内包表記で各 Row を辞書に変換
        return [dict(row) for row in cursor.fetchall()]

    def get_statistics(self) -> dict:
        """
        移行統計を取得する

        移行の進捗状況を把握するために使用する。
        成功/失敗/未対応の件数を返す。

        Returns:
            統計情報の辞書:
            - total: 合計ファイル数
            - success: 成功ファイル数
            - failed: 失敗ファイル数
            - unsupported: 未対応ファイル数
        """
        cursor = self._conn.cursor()

        # 全件数を取得
        cursor.execute("SELECT COUNT(*) FROM migrated_files")
        total = cursor.fetchone()[0]

        # 結果を格納する辞書を初期化
        stats: dict[str, int] = {
            "total": total,
            "success": 0,
            "failed": 0,
            "unsupported": 0,
        }

        # 各ステータスの件数を取得
        for file_status in FileStatus:
            cursor.execute(
                "SELECT COUNT(*) FROM migrated_files WHERE status = ?",
                (file_status.value,),
            )
            # Enum の値（"success" など）をキーとして使用
            stats[file_status.value] = cursor.fetchone()[0]

        return stats

    def record_album(
        self,
        synology_album_id: int,
        synology_album_name: str,
        immich_album_id: str,
    ) -> None:
        """
        アルバムの移行結果を記録する

        Synology Photos のアルバムと Immich のアルバムの対応関係を
        データベースに保存する。同じ synology_album_id のレコードが
        すでに存在する場合は更新（UPSERT）される。

        Args:
            synology_album_id: Synology Photos のアルバム ID
            synology_album_name: アルバム名（例: "Vacation 2024"）
            immich_album_id: Immich 側のアルバム ID（UUID 形式の文字列）
        """
        cursor = self._conn.cursor()

        # 現在時刻を ISO 形式で取得
        now = datetime.now().isoformat()

        # UPSERT（INSERT or UPDATE）
        # ON CONFLICT で synology_album_id が重複した場合は更新する
        cursor.execute(
            """
            INSERT INTO migrated_albums
            (synology_album_id, synology_album_name, immich_album_id, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(synology_album_id) DO UPDATE SET
                synology_album_name = excluded.synology_album_name,
                immich_album_id = excluded.immich_album_id,
                created_at = excluded.created_at
            """,
            (synology_album_id, synology_album_name, immich_album_id, now),
        )

        # 変更を確定
        self._conn.commit()

    def get_album_by_synology_id(self, synology_album_id: int) -> Optional[dict]:
        """
        Synology アルバム ID でアルバム情報を取得する

        指定された Synology Photos のアルバム ID に対応する
        アルバム情報を取得する。

        Args:
            synology_album_id: Synology Photos のアルバム ID

        Returns:
            アルバム情報の辞書。存在しない場合は None。
            辞書には以下のキーが含まれる:
            - synology_album_id: Synology Photos のアルバム ID
            - synology_album_name: アルバム名
            - immich_album_id: Immich のアルバム ID
            - created_at: 作成日時
        """
        cursor = self._conn.cursor()

        # プレースホルダー（?）を使ってパラメータを渡す
        cursor.execute(
            "SELECT * FROM migrated_albums WHERE synology_album_id = ?",
            (synology_album_id,),
        )

        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_albums(self) -> list[dict]:
        """
        全アルバムを取得する

        移行済みのすべてのアルバムの情報を取得する。
        移行の進捗確認やデバッグに使用する。

        Returns:
            アルバム情報の辞書のリスト
        """
        cursor = self._conn.cursor()

        # 全アルバムを取得
        cursor.execute("SELECT * FROM migrated_albums")

        # リスト内包表記で各 Row を辞書に変換
        return [dict(row) for row in cursor.fetchall()]

    def get_failed_files_with_errors(self) -> list[dict]:
        """
        失敗したファイルとそのエラーメッセージを取得する

        エラーログのレポート生成に使用する。
        FAILED と UNSUPPORTED 両方のステータスのファイルを返す。

        Returns:
            ファイル情報の辞書のリスト。各辞書には以下のキーが含まれる:
            - source_path: 元ファイルのパス
            - status: 移行ステータス（"failed" または "unsupported"）
            - error_message: エラーメッセージ（None の場合もある）
            - migrated_at: 記録日時
        """
        cursor = self._conn.cursor()

        cursor.execute(
            """
            SELECT source_path, status, error_message, migrated_at
            FROM migrated_files
            WHERE status IN (?, ?)
            ORDER BY migrated_at DESC
            """,
            (FileStatus.FAILED.value, FileStatus.UNSUPPORTED.value),
        )

        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """
        データベース接続を閉じる

        ProgressTracker の使用が終わったら必ず呼び出すこと。
        接続を閉じないと、データベースファイルがロックされたままになる
        可能性がある。

        コンテキストマネージャ（with 文）に対応させる予定だが、
        現時点では明示的に close() を呼び出す必要がある。
        """
        self._conn.close()
