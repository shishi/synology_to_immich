"""
Synology Photos PostgreSQL からのアルバム取得テスト

psycopg2 を使用した PostgreSQL 接続をモックでテストする
"""

from unittest.mock import MagicMock, Mock, patch

from synology_to_immich.synology_db import SynologyAlbum, SynologyAlbumFetcher


class TestSynologyAlbum:
    """SynologyAlbum データクラスのテスト"""

    def test_synology_album_has_required_fields(self):
        """必須フィールドが存在することを確認"""
        album = SynologyAlbum(id=1, name="Vacation 2024", item_count=100)

        assert album.id == 1
        assert album.name == "Vacation 2024"
        assert album.item_count == 100


class TestSynologyAlbumFetcher:
    """SynologyAlbumFetcher のテスト（モック使用）"""

    def test_initialization(self):
        """初期化時にDB接続情報が保存されることを確認"""
        fetcher = SynologyAlbumFetcher(
            host="192.168.1.1",
            port=5432,
            user="synofoto",
            password="secret",
            database="synofoto",
        )

        assert fetcher.host == "192.168.1.1"
        assert fetcher.port == 5432
        assert fetcher.database == "synofoto"

    @patch("synology_to_immich.synology_db.psycopg2.connect")
    def test_connect(self, mock_connect):
        """データベースに接続できることを確認"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        fetcher = SynologyAlbumFetcher(
            host="localhost",
            port=5432,
            user="user",
            password="pass",
            database="synofoto",
        )
        fetcher.connect()

        mock_connect.assert_called_once_with(
            host="localhost",
            port=5432,
            user="user",
            password="pass",
            database="synofoto",
        )

    @patch("synology_to_immich.synology_db.psycopg2.connect")
    def test_close(self, mock_connect):
        """接続を閉じられることを確認"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        fetcher = SynologyAlbumFetcher(
            host="localhost",
            port=5432,
            user="user",
            password="pass",
            database="synofoto",
        )
        fetcher.connect()
        fetcher.close()

        mock_conn.close.assert_called_once()

    @patch("synology_to_immich.synology_db.psycopg2.connect")
    def test_get_albums(self, mock_connect):
        """アルバム一覧を取得できることを確認"""
        # モックのセットアップ
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        # クエリ結果をモック
        mock_cursor.fetchall.return_value = [
            (1, "Vacation 2024", 50),
            (2, "Birthday Party", 30),
        ]

        fetcher = SynologyAlbumFetcher(
            host="localhost",
            port=5432,
            user="user",
            password="pass",
            database="synofoto",
        )
        fetcher.connect()
        albums = fetcher.get_albums()

        assert len(albums) == 2
        assert albums[0].name == "Vacation 2024"
        assert albums[0].item_count == 50
        assert albums[1].name == "Birthday Party"

    @patch("synology_to_immich.synology_db.psycopg2.connect")
    def test_get_album_files(self, mock_connect):
        """アルバム内のファイルパスを取得できることを確認"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        # クエリ結果をモック
        mock_cursor.fetchall.return_value = [
            ("/Photo/2024/IMG_001.jpg",),
            ("/Photo/2024/IMG_002.heic",),
            ("/Photo/2024/IMG_002.mov",),
        ]

        fetcher = SynologyAlbumFetcher(
            host="localhost",
            port=5432,
            user="user",
            password="pass",
            database="synofoto",
        )
        fetcher.connect()
        files = fetcher.get_album_files(album_id=1)

        assert len(files) == 3
        assert "/Photo/2024/IMG_001.jpg" in files
        assert "/Photo/2024/IMG_002.heic" in files

    @patch("synology_to_immich.synology_db.psycopg2.connect")
    def test_get_albums_empty(self, mock_connect):
        """アルバムがない場合は空リストを返す"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        mock_cursor.fetchall.return_value = []

        fetcher = SynologyAlbumFetcher(
            host="localhost",
            port=5432,
            user="user",
            password="pass",
            database="synofoto",
        )
        fetcher.connect()
        albums = fetcher.get_albums()

        assert albums == []

    @patch("synology_to_immich.synology_db.psycopg2.connect")
    def test_context_manager(self, mock_connect):
        """コンテキストマネージャーとして使えることを確認"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with SynologyAlbumFetcher(
            host="localhost",
            port=5432,
            user="user",
            password="pass",
            database="synofoto",
        ) as fetcher:
            assert fetcher._conn is not None

        mock_conn.close.assert_called_once()
