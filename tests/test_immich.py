"""
Immich クライアントのテスト

Immich API との通信をテストする。
実際の Immich サーバーには接続せず、モック（模擬オブジェクト）を使用する。

TDD の流れ:
1. このテストファイルを先に書く（Red: テストは失敗する）
2. immich.py を実装する（Green: テストが通る）
3. 必要に応じてリファクタリング（Refactor）

モック (mock) とは:
- 実際のオブジェクトの代わりに使う模擬オブジェクト
- 外部サービス（API サーバーなど）に依存せずテストできる
- unittest.mock モジュールで提供される
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

# このインポートは最初は失敗する（immich.py がまだ実装されていないため）
# これが TDD の「Red」フェーズ
from synology_to_immich.immich import ImmichClient, ImmichUploadResult


class TestImmichUploadResult:
    """
    ImmichUploadResult データクラスのテスト

    アップロード結果を表すシンプルなデータクラス。
    成功/失敗/未対応形式の3つの状態を表現できる。
    """

    def test_upload_result_success(self):
        """
        成功結果を正しく表現できることを確認

        成功時:
        - success = True
        - asset_id = Immich が返すアセット ID
        - error_message = None
        - is_unsupported = False
        """
        # Arrange & Act（準備と実行）
        result = ImmichUploadResult(
            success=True,
            asset_id="asset-uuid-123",
            error_message=None,
            is_unsupported=False,
        )

        # Assert（検証）
        assert result.success is True
        assert result.asset_id == "asset-uuid-123"
        assert result.error_message is None
        assert result.is_unsupported is False

    def test_upload_result_failure(self):
        """
        失敗結果を正しく表現できることを確認

        失敗時:
        - success = False
        - asset_id = None
        - error_message = エラーメッセージ
        - is_unsupported = False（通常のエラー）
        """
        # Arrange & Act
        result = ImmichUploadResult(
            success=False,
            asset_id=None,
            error_message="Connection refused",
            is_unsupported=False,
        )

        # Assert
        assert result.success is False
        assert result.asset_id is None
        assert result.error_message == "Connection refused"
        assert result.is_unsupported is False

    def test_upload_result_unsupported(self):
        """
        未対応形式の結果を正しく表現できることを確認

        未対応形式の場合:
        - success = False
        - asset_id = None
        - error_message = エラーメッセージ（通常は Immich からの応答）
        - is_unsupported = True（リトライ不要を示す）
        """
        # Arrange & Act
        result = ImmichUploadResult(
            success=False,
            asset_id=None,
            error_message="Unsupported file type",
            is_unsupported=True,
        )

        # Assert
        assert result.success is False
        assert result.asset_id is None
        assert result.error_message == "Unsupported file type"
        assert result.is_unsupported is True


class TestImmichClient:
    """
    ImmichClient クラスのテスト

    Immich API への HTTP リクエストをモックしてテストする。
    実際のサーバーには接続しないため、ネットワーク環境に依存しない。
    """

    def test_client_initialization(self):
        """
        クライアントの初期化が正しく行われることを確認

        ImmichClient は以下を受け取る:
        - base_url: Immich サーバーの URL（例: "http://localhost:2283"）
        - api_key: Immich API キー（認証に使用）

        内部的に以下のヘッダーを設定する:
        - x-api-key: API キー
        - Accept: application/json
        """
        # Arrange & Act
        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key-123",
        )

        # Assert
        # ベース URL が正しく設定されていることを確認
        assert client._base_url == "http://localhost:2283"
        # ヘッダーが正しく設定されていることを確認
        assert client._headers["x-api-key"] == "test-api-key-123"
        assert client._headers["Accept"] == "application/json"

    @patch("synology_to_immich.immich.httpx.Client")
    def test_upload_asset_success(self, mock_client_class: MagicMock):
        """
        アセットのアップロードが成功した場合のテスト

        Immich API の /api/assets エンドポイントに POST リクエストを送信し、
        201 Created レスポンスを受け取った場合の動作をテスト。

        @patch デコレータについて:
        - 指定したオブジェクト（ここでは httpx.Client）をモックに置き換える
        - テスト関数の引数として渡される（mock_client_class）
        - テスト終了後に自動的に元に戻る
        """
        # Arrange（準備）
        # モックレスポンスを設定
        mock_response = MagicMock()
        mock_response.status_code = 201  # Created
        mock_response.json.return_value = {
            "id": "asset-uuid-from-immich",
            "status": "created",
        }

        # httpx.Client のモックを設定
        # with ステートメントで使われるため、__enter__ と __exit__ を設定
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        # ImmichClient を作成
        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act（実行）
        # テスト用の画像データ
        file_data = b"fake image data"
        result = client.upload_asset(
            file_data=file_data,
            filename="test.jpg",
            created_at="2024-01-15T10:30:00",
        )

        # Assert（検証）
        assert result.success is True
        assert result.asset_id == "asset-uuid-from-immich"
        assert result.error_message is None
        assert result.is_unsupported is False

        # POST リクエストが正しいエンドポイントに送信されたことを確認
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert "/api/assets" in call_args[0][0]

    @patch("synology_to_immich.immich.httpx.Client")
    def test_upload_asset_unsupported_format(self, mock_client_class: MagicMock):
        """
        未対応形式でアップロードが拒否された場合のテスト

        Immich が 400 Bad Request を返し、レスポンスに "unsupported" が含まれる場合、
        is_unsupported = True を設定する。

        これにより、リトライ不要なファイルを識別できる。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 400  # Bad Request
        mock_response.json.return_value = {
            "message": "Unsupported file type",
            "error": "Bad Request",
        }
        # text プロパティも設定（エラーメッセージの検出に使用）
        mock_response.text = "Unsupported file type"

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        result = client.upload_asset(
            file_data=b"fake data",
            filename="test.xyz",  # 未対応の拡張子
            created_at="2024-01-15T10:30:00",
        )

        # Assert
        assert result.success is False
        assert result.asset_id is None
        assert result.is_unsupported is True
        assert result.error_message is not None

    def test_upload_asset_with_live_photo_raises_error(self):
        """
        live_photo_data を渡すと ValueError が発生することを確認

        Immich v2.x では livePhotoData フィールドが廃止されたため、
        Live Photo は静止画と動画を別々にアップロードする必要がある。
        呼び出し元のバグを早期発見するため、live_photo_data が渡されたら
        例外を raise する。
        """
        # Arrange
        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            client.upload_asset(
                file_data=b"fake image data",
                filename="IMG_001.HEIC",
                created_at="2024-01-15T10:30:00",
                live_photo_data=b"fake video data",  # これが渡されるとエラー
            )

        # エラーメッセージを確認
        assert "live_photo_data は廃止されました" in str(exc_info.value)
        assert "Immich v2.x" in str(exc_info.value)

    @patch("synology_to_immich.immich.httpx.Client")
    def test_create_album(self, mock_client_class: MagicMock):
        """
        アルバム作成のテスト

        POST /api/albums でアルバムを作成し、
        作成されたアルバムの ID を返す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 201  # Created
        mock_response.json.return_value = {
            "id": "album-uuid-from-immich",
            "albumName": "Vacation 2024",
        }

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        album_id = client.create_album("Vacation 2024")

        # Assert
        assert album_id == "album-uuid-from-immich"

        # POST リクエストが正しいエンドポイントに送信されたことを確認
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert "/api/albums" in call_args[0][0]

    @patch("synology_to_immich.immich.httpx.Client")
    def test_create_album_failure(self, mock_client_class: MagicMock):
        """
        アルバム作成が失敗した場合のテスト

        サーバーエラーなどで失敗した場合、None を返す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 500  # Internal Server Error
        mock_response.json.return_value = {
            "message": "Internal server error",
        }

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        album_id = client.create_album("Test Album")

        # Assert
        assert album_id is None

    @patch("synology_to_immich.immich.httpx.Client")
    def test_add_assets_to_album(self, mock_client_class: MagicMock):
        """
        アルバムへのアセット追加テスト

        PUT /api/albums/{album_id}/assets でアセットをアルバムに追加する。
        成功時は True を返す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200  # OK
        mock_response.json.return_value = [
            {"id": "asset-1", "success": True},
            {"id": "asset-2", "success": True},
        ]

        mock_client_instance = MagicMock()
        mock_client_instance.put.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        result = client.add_assets_to_album(
            album_id="album-uuid",
            asset_ids=["asset-1", "asset-2"],
        )

        # Assert
        assert result is True

        # PUT リクエストが正しいエンドポイントに送信されたことを確認
        mock_client_instance.put.assert_called_once()
        call_args = mock_client_instance.put.call_args
        assert "/api/albums/album-uuid/assets" in call_args[0][0]

    @patch("synology_to_immich.immich.httpx.Client")
    def test_add_assets_to_album_failure(self, mock_client_class: MagicMock):
        """
        アルバムへのアセット追加が失敗した場合のテスト

        サーバーエラーなどで失敗した場合、False を返す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 404  # Not Found (album doesn't exist)

        mock_client_instance = MagicMock()
        mock_client_instance.put.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        result = client.add_assets_to_album(
            album_id="nonexistent-album",
            asset_ids=["asset-1"],
        )

        # Assert
        assert result is False

    @patch("synology_to_immich.immich.httpx.Client")
    def test_get_all_assets(self, mock_client_class: MagicMock):
        """
        全アセット取得のテスト

        POST /api/search/metadata でページネーションを処理しながら全アセットを取得する。
        Immich v2.x では GET /api/assets は非推奨となり、
        POST /api/search/metadata を使用する必要がある。
        """
        # Arrange
        # 2ページ分のレスポンスをシミュレート
        # search/metadata は {"assets": {"items": [...]}} 形式で返す
        mock_response_page1 = MagicMock()
        mock_response_page1.status_code = 200
        mock_response_page1.json.return_value = {
            "assets": {
                "items": [
                    {"id": "asset-1", "originalFileName": "photo1.jpg"},
                    {"id": "asset-2", "originalFileName": "photo2.jpg"},
                ]
            }
        }

        mock_response_page2 = MagicMock()
        mock_response_page2.status_code = 200
        mock_response_page2.json.return_value = {
            "assets": {"items": []}  # 空のページで終了
        }

        mock_client_instance = MagicMock()
        # side_effect で複数回の呼び出しに対して異なる値を返す
        # search/metadata は POST リクエスト
        mock_client_instance.post.side_effect = [mock_response_page1, mock_response_page2]
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        assets = client.get_all_assets()

        # Assert
        assert len(assets) == 2
        assert assets[0]["id"] == "asset-1"
        assert assets[1]["id"] == "asset-2"

        # POST が search/metadata エンドポイントに送信されたことを確認
        call_args = mock_client_instance.post.call_args_list[0]
        assert "/api/search/metadata" in call_args[0][0]

    @patch("synology_to_immich.immich.httpx.Client")
    def test_upload_asset_server_error(self, mock_client_class: MagicMock):
        """
        サーバーエラー時のテスト

        500 Internal Server Error の場合、
        success=False でエラーメッセージを含む結果を返す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        result = client.upload_asset(
            file_data=b"fake data",
            filename="test.jpg",
            created_at="2024-01-15T10:30:00",
        )

        # Assert
        assert result.success is False
        assert result.asset_id is None
        assert result.is_unsupported is False  # 500 エラーはリトライ可能
        assert "500" in result.error_message or "error" in result.error_message.lower()

    @patch("synology_to_immich.immich.httpx.Client")
    def test_upload_asset_network_error(self, mock_client_class: MagicMock):
        """
        ネットワークエラー時のテスト（接続失敗など）

        httpx.ConnectError などのネットワーク例外が発生した場合、
        success=False でエラーメッセージを含む結果を返す。
        """
        # Arrange
        mock_client_instance = MagicMock()
        mock_client_instance.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        result = client.upload_asset(
            file_data=b"data",
            filename="test.jpg",
            created_at="2024-01-15",
        )

        # Assert
        assert result.success is False
        assert result.error_message is not None
        assert result.is_unsupported is False

    @patch("synology_to_immich.immich.httpx.Client")
    def test_get_asset_by_id_success(self, mock_client_class: MagicMock):
        """
        アセット ID で単一アセットを取得するテスト

        /api/assets/{id} エンドポイントから特定のアセット情報を取得する。
        Live Photo の MOV ファイルなど、search/metadata API で
        取得できないアセットの checksum を取得するために使用する。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "asset-uuid-123",
            "originalFileName": "IMG_1234.MOV",
            "checksum": "base64-checksum-here",
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        result = client.get_asset_by_id("asset-uuid-123")

        # Assert
        assert result is not None
        assert result["id"] == "asset-uuid-123"
        assert result["checksum"] == "base64-checksum-here"

        # GET リクエストが正しいエンドポイントに送信されたことを確認
        mock_client_instance.get.assert_called_once()
        call_args = mock_client_instance.get.call_args
        assert "/api/assets/asset-uuid-123" in call_args[0][0]

    @patch("synology_to_immich.immich.httpx.Client")
    def test_get_asset_by_id_not_found(self, mock_client_class: MagicMock):
        """
        存在しないアセット ID の場合は None を返す

        404 Not Found の場合、例外を投げずに None を返す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        result = client.get_asset_by_id("non-existent-id")

        # Assert
        assert result is None

    @patch("synology_to_immich.immich.httpx.Client")
    def test_get_albums(self, mock_client_class: MagicMock):
        """
        アルバム一覧取得のテスト

        GET /api/albums で全アルバムを取得する。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "album-uuid-1",
                "albumName": "家族写真",
                "assetCount": 150,
            },
            {
                "id": "album-uuid-2",
                "albumName": "旅行2024",
                "assetCount": 80,
            },
        ]

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        albums = client.get_albums()

        # Assert
        assert len(albums) == 2
        assert albums[0]["id"] == "album-uuid-1"
        assert albums[0]["albumName"] == "家族写真"
        assert albums[0]["assetCount"] == 150
        assert albums[1]["id"] == "album-uuid-2"

        # GET リクエストが正しいエンドポイントに送信されたことを確認
        mock_client_instance.get.assert_called_once()
        call_args = mock_client_instance.get.call_args
        assert "/api/albums" in call_args[0][0]

    @patch("synology_to_immich.immich.httpx.Client")
    def test_get_albums_empty(self, mock_client_class: MagicMock):
        """
        アルバムがない場合は空リストを返す
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        albums = client.get_albums()

        # Assert
        assert albums == []

    @patch("synology_to_immich.immich.httpx.Client")
    def test_get_album_assets(self, mock_client_class: MagicMock):
        """
        アルバム内のアセット一覧取得テスト

        GET /api/albums/{id} でアルバム詳細を取得し、
        assets フィールドからアセット一覧を返す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "album-uuid-1",
            "albumName": "家族写真",
            "assets": [
                {
                    "id": "asset-1",
                    "originalFileName": "photo1.jpg",
                    "checksum": "base64-checksum-1",
                },
                {
                    "id": "asset-2",
                    "originalFileName": "photo2.jpg",
                    "checksum": "base64-checksum-2",
                },
            ],
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        assets = client.get_album_assets("album-uuid-1")

        # Assert
        assert len(assets) == 2
        assert assets[0]["id"] == "asset-1"
        assert assets[0]["originalFileName"] == "photo1.jpg"
        assert assets[0]["checksum"] == "base64-checksum-1"

        # GET リクエストが正しいエンドポイントに送信されたことを確認
        mock_client_instance.get.assert_called_once()
        call_args = mock_client_instance.get.call_args
        assert "/api/albums/album-uuid-1" in call_args[0][0]

    @patch("synology_to_immich.immich.httpx.Client")
    def test_get_album_assets_not_found(self, mock_client_class: MagicMock):
        """
        アルバムが見つからない場合は空リストを返す
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="test-api-key",
        )

        # Act
        assets = client.get_album_assets("non-existent-album")

        # Assert
        assert assets == []
