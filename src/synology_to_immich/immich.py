"""
Immich API クライアントモジュール

Immich サーバーとの通信を担当するモジュール。
以下の機能を提供する:

- 写真/動画のアップロード
- アルバムの作成
- アルバムへのアセット追加
- 全アセットの取得（検証用）

HTTP クライアントには httpx を使用。httpx は requests ライブラリの
後継として設計されており、以下の特徴がある:
- 同期/非同期の両方をサポート
- HTTP/2 対応
- タイムアウトの明示的な設定が必要（安全）
- 型ヒントが充実

Immich API のエンドポイント:
- POST /api/assets: アセットのアップロード
- POST /api/albums: アルバムの作成
- PUT /api/albums/{id}/assets: アルバムへのアセット追加
- GET /api/assets: 全アセットの取得
"""

import mimetypes
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class ImmichUploadResult:
    """
    アップロード結果を表すデータクラス

    アップロードの成功/失敗/未対応形式を表現する。
    進捗トラッカー (ProgressTracker) と連携して、
    移行状態を記録するために使用される。

    Attributes:
        success: アップロードが成功したかどうか
                 True: 成功（asset_id が設定される）
                 False: 失敗または未対応形式
        asset_id: Immich でのアセット ID（UUID 形式の文字列）
                  成功時のみ設定される。失敗時は None。
        error_message: エラーメッセージ
                       失敗時のみ設定される。成功時は None。
        is_unsupported: Immich が未対応と判断した形式かどうか
                        True の場合、リトライしても意味がない。
                        例: 特殊な RAW 形式、破損したファイルなど。

    使用例:
        # 成功時
        result = ImmichUploadResult(
            success=True,
            asset_id="abc-123-def",
            error_message=None,
            is_unsupported=False
        )

        # 失敗時（リトライ可能）
        result = ImmichUploadResult(
            success=False,
            asset_id=None,
            error_message="Connection timeout",
            is_unsupported=False
        )

        # 未対応形式（リトライ不要）
        result = ImmichUploadResult(
            success=False,
            asset_id=None,
            error_message="Unsupported file type",
            is_unsupported=True
        )
    """

    success: bool  # アップロード成功フラグ
    asset_id: Optional[str]  # Immich アセット ID（成功時のみ）
    error_message: Optional[str]  # エラーメッセージ（失敗時のみ）
    is_unsupported: bool  # 未対応形式フラグ


class ImmichClient:
    """
    Immich API クライアント

    Immich サーバーへの HTTP リクエストを送信するクラス。
    認証ヘッダーの管理、エンドポイントへのリクエスト、
    レスポンスの解析を行う。

    Attributes:
        _base_url: Immich サーバーのベース URL（例: "http://localhost:2283"）
        _headers: HTTP リクエストヘッダー（API キーを含む）

    使用例:
        # クライアントを作成
        client = ImmichClient(
            base_url="http://localhost:2283",
            api_key="your-api-key"
        )

        # アセットをアップロード
        with open("photo.jpg", "rb") as f:
            result = client.upload_asset(
                file_data=f.read(),
                filename="photo.jpg",
                created_at="2024-01-15T10:30:00"
            )

        if result.success:
            print(f"アップロード成功: {result.asset_id}")
        else:
            print(f"アップロード失敗: {result.error_message}")
    """

    # HTTP リクエストのタイムアウト（秒）
    # 大きなファイルのアップロードに時間がかかることがあるため、
    # デフォルトより長めに設定（Live Photo の MOV は特に大きい）
    DEFAULT_TIMEOUT = 600.0  # 10分（大きなファイルのアップロード対応）

    # ページネーションのデフォルトサイズ
    # get_all_assets で使用
    DEFAULT_PAGE_SIZE = 100

    def __init__(self, base_url: str, api_key: str):
        """
        ImmichClient を初期化する

        Args:
            base_url: Immich サーバーの URL
                      例: "http://localhost:2283"
                      末尾のスラッシュは不要（あっても動作する）
            api_key: Immich API キー
                     Immich の管理画面 > API Keys で取得できる
        """
        # 末尾のスラッシュを削除（一貫性のため）
        # "http://localhost:2283/" -> "http://localhost:2283"
        self._base_url = base_url.rstrip("/")

        # API 認証用のヘッダーを設定
        # x-api-key: Immich の認証ヘッダー
        # Accept: レスポンス形式の指定
        self._headers = {
            "x-api-key": api_key,
            "Accept": "application/json",
        }

    def upload_asset(
        self,
        file_data: bytes,
        filename: str,
        created_at: str,
        live_photo_data: Optional[bytes] = None,
    ) -> ImmichUploadResult:
        """
        アセット（写真/動画）をアップロードする

        Immich の /api/assets エンドポイントに multipart/form-data で
        ファイルを送信する。

        Args:
            file_data: ファイルのバイナリデータ
            filename: ファイル名（拡張子を含む）
                      例: "IMG_001.jpg", "vacation.heic"
            created_at: ファイルの作成日時（ISO 8601 形式）
                        例: "2024-01-15T10:30:00"
            live_photo_data: Live Photo の動画部分（オプション）
                             iPhone の Live Photo は静止画と動画で構成される

        Returns:
            ImmichUploadResult: アップロード結果

        Notes:
            - 201 Created: 成功
            - 400 Bad Request + "unsupported": 未対応形式
            - その他のエラー: 一般的な失敗（リトライ可能）
        """
        # アップロード先の URL
        url = f"{self._base_url}/api/assets"

        # MIME タイプを推測
        # mimetypes.guess_type() はファイル名から MIME タイプを推測する
        # 例: "photo.jpg" -> "image/jpeg"
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type is None:
            # 推測できない場合はバイナリとして扱う
            mime_type = "application/octet-stream"

        # multipart/form-data の files パラメータ
        # 形式: {"フィールド名": (ファイル名, データ, MIMEタイプ)}
        files = {
            "assetData": (filename, file_data, mime_type),
        }

        # 注意: Immich v2.x では livePhotoData フィールドは廃止された
        # Live Photos は写真と動画を別々にアップロードすると、
        # Immich が自動的にペアリングしてくれる
        # このコードパスは実行されるべきではない - 呼び出し元のバグ
        if live_photo_data is not None:
            raise ValueError(
                "live_photo_data は廃止されました。"
                "Live Photos は写真と動画を別々にアップロードしてください。"
                "Immich v2.x では livePhotoData フィールドはサポートされていません。"
            )

        # フォームデータ（メタデータ）
        # deviceAssetId: デバイス上での識別子（重複チェックに使用）
        # deviceId: デバイスの識別子（移行ツールを識別）
        # fileCreatedAt/fileModifiedAt: ファイルの日時情報
        data = {
            "deviceAssetId": filename,
            "deviceId": "synology-to-immich",
            "fileCreatedAt": created_at,
            "fileModifiedAt": created_at,
        }

        # HTTP リクエストを送信
        # with ステートメントで httpx.Client を使うことで、
        # リクエスト完了後に自動的にリソースが解放される
        try:
            with httpx.Client(timeout=self.DEFAULT_TIMEOUT) as client:
                response = client.post(
                    url,
                    headers=self._headers,
                    files=files,
                    data=data,
                )
            # レスポンスを解析
            return self._parse_upload_response(response)
        except httpx.HTTPError as e:
            # ネットワークエラー（接続失敗、タイムアウトなど）
            return ImmichUploadResult(
                success=False,
                asset_id=None,
                error_message=f"ネットワークエラー: {str(e)}",
                is_unsupported=False,
            )

    def _parse_upload_response(self, response: httpx.Response) -> ImmichUploadResult:
        """
        アップロードレスポンスを解析する

        内部メソッド（アンダースコアで始まる）。
        upload_asset から呼び出される。

        Args:
            response: httpx のレスポンスオブジェクト

        Returns:
            ImmichUploadResult: 解析結果
        """
        # 成功（201 Created）または重複（200 OK with status: duplicate）
        if response.status_code == 201:
            # JSON レスポンスからアセット ID を取得
            response_data = response.json()
            return ImmichUploadResult(
                success=True,
                asset_id=response_data.get("id"),
                error_message=None,
                is_unsupported=False,
            )

        # 重複ファイル（200 OK with status: duplicate）
        # Immich v2.x では既存ファイルの場合、200 で id を返す
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "duplicate":
                # 重複でも成功として扱う（既存の asset_id を返す）
                return ImmichUploadResult(
                    success=True,
                    asset_id=response_data.get("id"),
                    error_message=None,
                    is_unsupported=False,
                )

        # 未対応形式（400 Bad Request + "unsupported"）
        if response.status_code == 400:
            # レスポンステキストに "unsupported" が含まれるか確認
            # 大文字小文字を無視して検索
            is_unsupported = "unsupported" in response.text.lower()
            return ImmichUploadResult(
                success=False,
                asset_id=None,
                error_message=response.text,
                is_unsupported=is_unsupported,
            )

        # その他のエラー
        return ImmichUploadResult(
            success=False,
            asset_id=None,
            error_message=f"HTTP {response.status_code}: {response.text}",
            is_unsupported=False,
        )

    def create_album(self, album_name: str) -> Optional[str]:
        """
        アルバムを作成する

        Immich の /api/albums エンドポイントに POST リクエストを送信し、
        新しいアルバムを作成する。

        Args:
            album_name: アルバム名
                        例: "Vacation 2024", "Family Photos"

        Returns:
            str: 作成されたアルバムの ID（UUID 形式）
            None: 作成に失敗した場合

        Notes:
            同じ名前のアルバムが既に存在していても、
            新しいアルバムが作成される（名前の重複は許可される）。
        """
        url = f"{self._base_url}/api/albums"

        # JSON ボディでアルバム名を送信
        json_data = {
            "albumName": album_name,
        }

        with httpx.Client(timeout=self.DEFAULT_TIMEOUT) as client:
            response = client.post(
                url,
                headers=self._headers,
                json=json_data,  # json パラメータで自動的に JSON 形式に変換
            )

        # 成功（201 Created）
        if response.status_code == 201:
            response_data = response.json()
            return response_data.get("id")

        # 失敗
        return None

    def add_assets_to_album(self, album_id: str, asset_ids: list[str]) -> bool:
        """
        アセットをアルバムに追加する

        Immich の /api/albums/{album_id}/assets エンドポイントに
        PUT リクエストを送信し、アセットをアルバムに追加する。

        Args:
            album_id: アルバムの ID（UUID 形式）
            asset_ids: 追加するアセットの ID リスト

        Returns:
            bool: 追加に成功した場合は True、失敗した場合は False

        Notes:
            - 既にアルバムに含まれているアセットは無視される
            - 存在しないアセット ID は無視される
        """
        url = f"{self._base_url}/api/albums/{album_id}/assets"

        # JSON ボディでアセット ID のリストを送信
        json_data = {
            "ids": asset_ids,
        }

        with httpx.Client(timeout=self.DEFAULT_TIMEOUT) as client:
            response = client.put(
                url,
                headers=self._headers,
                json=json_data,
            )

        # 成功（200 OK）
        return response.status_code == 200

    def get_all_assets(self) -> list[dict]:
        """
        全アセットを取得する

        Immich の /api/search/metadata エンドポイントからページネーションを
        処理しながら全アセットを取得する。

        Immich v2.x では /api/assets GET は非推奨となり、
        /api/search/metadata POST を使用する必要がある。

        Returns:
            list[dict]: アセット情報の辞書のリスト
                        各辞書には以下のキーが含まれる:
                        - id: アセット ID
                        - originalFileName: 元のファイル名
                        - checksum: SHA1 チェックサム（base64エンコード）
                        - その他 Immich が返すメタデータ

        Notes:
            アセット数が多い場合、この操作は時間がかかる。
            検証用途やデバッグに使用することを想定している。
        """
        # 全アセットを格納するリスト
        all_assets: list[dict] = []

        # ページネーション用の変数
        page = 1
        page_size = 1000  # 検索APIはより大きなページサイズをサポート

        with httpx.Client(timeout=self.DEFAULT_TIMEOUT) as client:
            while True:
                # search/metadata API を使用（Immich v2.x 対応）
                url = f"{self._base_url}/api/search/metadata"

                response = client.post(
                    url,
                    headers=self._headers,
                    json={"size": page_size, "page": page},
                )

                # エラーの場合は現在までの結果を返す
                if response.status_code != 200:
                    break

                # レスポンスを解析
                # search/metadata は {"assets": {"items": [...]}} の形式で返す
                data = response.json()
                assets = data.get("assets", {}).get("items", [])

                # 空のページに到達したら終了
                if not assets:
                    break

                # 結果を追加
                all_assets.extend(assets)

                # ページサイズ未満なら最後のページ
                if len(assets) < page_size:
                    break

                # 次のページへ
                page += 1

        return all_assets

    def get_asset_by_id(self, asset_id: str) -> Optional[dict]:
        """
        アセット ID で単一のアセット情報を取得する

        /api/assets/{id} エンドポイントから特定のアセット情報を取得する。
        get_all_assets() で使用する search/metadata API では
        Live Photo の MOV ファイルなど一部のアセットが取得できないため、
        直接 ID を指定して取得する必要がある場合に使用する。

        Args:
            asset_id: 取得するアセットの ID（UUID 形式）

        Returns:
            dict: アセット情報（id, originalFileName, checksum など）
            None: アセットが見つからない場合（404）

        使用例:
            client = ImmichClient(base_url, api_key)
            asset = client.get_asset_by_id("asset-uuid-123")
            if asset:
                print(f"Checksum: {asset.get('checksum')}")
        """
        with httpx.Client(timeout=self.DEFAULT_TIMEOUT) as client:
            url = f"{self._base_url}/api/assets/{asset_id}"

            response = client.get(
                url,
                headers=self._headers,
            )

            # 見つからない場合は None を返す
            if response.status_code != 200:
                return None

            return response.json()
