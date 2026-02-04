"""
Synology Photos PostgreSQL データベースからアルバム情報を取得するモジュール

Synology Photos は synofoto という PostgreSQL データベースにアルバム情報を保存している。
このモジュールは、そのデータベースからアルバムとその写真のマッピングを取得する。

注意: 実際のDBスキーマは Synology の環境によって異なる可能性があるため、
クエリは後で調整が必要になる場合がある。
"""

from dataclasses import dataclass
from typing import Optional

import psycopg2


@dataclass
class SynologyAlbum:
    """
    Synology Photos のアルバムを表すデータクラス

    Attributes:
        id: アルバムの一意識別子（DBの主キー）
        name: アルバム名（ユーザーが付けた名前）
        item_count: アルバムに含まれるアイテム数
    """

    id: int
    name: str
    item_count: int


class SynologyAlbumFetcher:
    """
    Synology Photos の PostgreSQL データベースからアルバム情報を取得するクラス

    使用例:
        # 通常の使用方法
        fetcher = SynologyAlbumFetcher(
            host="192.168.1.1",
            port=5432,
            user="synofoto",
            password="password",
            database="synofoto",
        )
        fetcher.connect()
        try:
            albums = fetcher.get_albums()
            for album in albums:
                files = fetcher.get_album_files(album.id)
                print(f"{album.name}: {len(files)} files")
        finally:
            fetcher.close()

        # コンテキストマネージャーを使用する方法（推奨）
        with SynologyAlbumFetcher(...) as fetcher:
            albums = fetcher.get_albums()
    """

    # アルバム一覧を取得するSQLクエリ
    # Synology Photos の実際のスキーマに基づく
    # - normal_album: アルバム情報（通常のユーザー作成アルバム）
    # - type=0 は通常のアルバム（条件付きアルバムではない）
    QUERY_GET_ALBUMS = """
        SELECT id, name, item_count
        FROM normal_album
        WHERE type = 0
        ORDER BY name
    """

    # アルバム内のファイルパスを取得するSQLクエリ
    # Synology Photos の実際のスキーマに基づく
    # - many_item_has_many_normal_album: アルバムと item の紐付け
    # - unit: ファイル情報（filename, id_folder）
    # - folder: フォルダパス（name フィールドにフルパス）
    # - item と unit は id_item で紐付け
    QUERY_GET_ALBUM_FILES = """
        SELECT CONCAT(f.name, '/', u.filename) as full_path
        FROM many_item_has_many_normal_album ma
        JOIN unit u ON ma.id_item = u.id_item
        JOIN folder f ON u.id_folder = f.id
        WHERE ma.id_normal_album = %s
        ORDER BY full_path
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
    ):
        """
        SynologyAlbumFetcher を初期化する

        Args:
            host: PostgreSQL サーバーのホスト名またはIPアドレス
            port: PostgreSQL サーバーのポート番号（通常は5432）
            user: データベースユーザー名
            password: データベースパスワード
            database: データベース名（通常は synofoto）
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self._conn: Optional[psycopg2.extensions.connection] = None

    def connect(self) -> None:
        """
        データベースに接続する

        Raises:
            psycopg2.Error: 接続に失敗した場合
        """
        self._conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
        )

    def close(self) -> None:
        """
        データベース接続を閉じる

        接続が存在しない場合は何もしない
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SynologyAlbumFetcher":
        """
        コンテキストマネージャーのエントリポイント

        自動的に connect() を呼び出す
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        コンテキストマネージャーの終了処理

        自動的に close() を呼び出す
        """
        self.close()

    def get_albums(self) -> list[SynologyAlbum]:
        """
        全アルバムの一覧を取得する

        Returns:
            SynologyAlbum のリスト。アルバムがない場合は空リスト

        Raises:
            RuntimeError: 接続が確立されていない場合
            psycopg2.Error: クエリ実行に失敗した場合
        """
        if self._conn is None:
            raise RuntimeError(
                "データベースに接続されていません。connect() を先に呼び出してください。"
            )

        albums: list[SynologyAlbum] = []

        with self._conn.cursor() as cursor:
            cursor.execute(self.QUERY_GET_ALBUMS)
            rows = cursor.fetchall()

            for row in rows:
                album = SynologyAlbum(
                    id=row[0],
                    name=row[1],
                    item_count=row[2],
                )
                albums.append(album)

        return albums

    def get_album_files(self, album_id: int) -> list[str]:
        """
        指定したアルバムに含まれるファイルのパスを取得する

        Args:
            album_id: アルバムのID

        Returns:
            ファイルパスのリスト。ファイルがない場合は空リスト

        Raises:
            RuntimeError: 接続が確立されていない場合
            psycopg2.Error: クエリ実行に失敗した場合
        """
        if self._conn is None:
            raise RuntimeError(
                "データベースに接続されていません。connect() を先に呼び出してください。"
            )

        files: list[str] = []

        with self._conn.cursor() as cursor:
            cursor.execute(self.QUERY_GET_ALBUM_FILES, (album_id,))
            rows = cursor.fetchall()

            for row in rows:
                files.append(row[0])

        return files
