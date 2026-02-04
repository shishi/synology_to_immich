"""
アルバム移行モジュール

Synology Photos のアルバムを Immich に移行する機能を提供する。

主要コンポーネント:
- AlbumMigrationResult: 移行結果を表すデータクラス
- AlbumMigrator: アルバム移行を実行するクラス

使用例:
    # 各コンポーネントを初期化
    synology_fetcher = SynologyAlbumFetcher(...)
    immich_client = ImmichClient(...)
    progress_tracker = ProgressTracker(...)
    logger = MigrationLogger(...)

    # AlbumMigrator を作成して移行を実行
    migrator = AlbumMigrator(
        synology_fetcher=synology_fetcher,
        immich_client=immich_client,
        progress_tracker=progress_tracker,
        logger=logger,
    )
    result = migrator.migrate_albums()

    print(f"成功: {result.success_count}, 失敗: {result.failed_count}")
"""

from dataclasses import dataclass

from synology_to_immich.immich import ImmichClient
from synology_to_immich.logging import MigrationLogger
from synology_to_immich.progress import ProgressTracker
from synology_to_immich.synology_db import SynologyAlbum, SynologyAlbumFetcher


@dataclass
class AlbumMigrationResult:
    """
    アルバム移行の結果を表すデータクラス

    migrate_albums() メソッドの戻り値として使用される。
    移行処理の統計情報を提供する。

    Attributes:
        total_albums: 処理対象のアルバム総数
        success_count: 正常に移行できたアルバム数
        failed_count: 移行に失敗したアルバム数
        skipped_count: スキップされたアルバム数（既に移行済み）
    """

    total_albums: int  # 処理対象アルバム数
    success_count: int  # 成功数
    failed_count: int  # 失敗数
    skipped_count: int  # スキップ数（既に移行済み）


class AlbumMigrator:
    """
    Synology Photos のアルバムを Immich に移行するクラス

    処理フロー:
    1. SynologyAlbumFetcher で全アルバムを取得
    2. 各アルバムについて:
       - ProgressTracker で移行済みか確認 → 済みならスキップ
       - SynologyAlbumFetcher でアルバム内のファイルパスを取得
       - ProgressTracker でファイルパスから Immich アセット ID を検索
       - ImmichClient でアルバムを作成
       - ImmichClient でアセットをアルバムに追加
       - ProgressTracker にアルバムを記録
    3. AlbumMigrationResult を返す

    Attributes:
        _synology_fetcher: Synology Photos からアルバム情報を取得するクラス
        _immich_client: Immich API クライアント
        _progress_tracker: 進捗管理クラス
        _logger: ログ出力クラス
        _dry_run: True の場合、実際には作成しない
    """

    def __init__(
        self,
        synology_fetcher: SynologyAlbumFetcher,
        immich_client: ImmichClient,
        progress_tracker: ProgressTracker,
        logger: MigrationLogger,
        dry_run: bool = False,
    ):
        """
        AlbumMigrator を初期化する

        Args:
            synology_fetcher: Synology Photos からアルバム情報を取得するクラス
            immich_client: Immich API クライアント
            progress_tracker: 進捗管理クラス
            logger: ログ出力クラス
            dry_run: True の場合、実際には Immich にアルバムを作成しない
        """
        self._synology_fetcher = synology_fetcher
        self._immich_client = immich_client
        self._progress_tracker = progress_tracker
        self._logger = logger
        self._dry_run = dry_run

    def migrate_albums(self) -> AlbumMigrationResult:
        """
        全アルバムを Immich に移行する

        Synology Photos のアルバムを取得し、各アルバムを Immich に作成する。
        既に移行済みのアルバムはスキップされる。

        Returns:
            AlbumMigrationResult: 移行結果の統計情報

        Notes:
            - dry_run モードの場合、実際には Immich にアルバムは作成されない
            - 失敗したアルバムも含めて全て処理される（途中で止まらない）
        """
        # Synology Photos から全アルバムを取得
        albums = self._synology_fetcher.get_albums()

        # 統計カウンター
        success_count = 0
        failed_count = 0
        skipped_count = 0

        # 各アルバムを処理
        for album in albums:
            # 移行済みかどうかを確認
            existing_album = self._progress_tracker.get_album_by_synology_id(album.id)
            if existing_album is not None:
                # 既に移行済みの場合はスキップ
                self._logger.info(
                    f"アルバムをスキップ（移行済み）: {album.name}",
                    synology_album_id=album.id,
                )
                skipped_count += 1
                continue

            # アルバムを移行
            if self._migrate_single_album(album):
                success_count += 1
            else:
                failed_count += 1

        # 結果を返す
        return AlbumMigrationResult(
            total_albums=len(albums),
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
        )

    def _migrate_single_album(self, album: SynologyAlbum) -> bool:
        """
        1つのアルバムを Immich に移行する

        Args:
            album: 移行対象の Synology アルバム

        Returns:
            bool: 移行成功の場合 True、失敗の場合 False
        """
        self._logger.info(
            f"アルバムを移行中: {album.name}",
            synology_album_id=album.id,
            item_count=album.item_count,
        )

        # アルバム内のファイルパスを取得
        file_paths = self._synology_fetcher.get_album_files(album.id)

        # ファイルパスから Immich アセット ID を検索
        asset_ids = self._find_immich_asset_ids(file_paths)

        # dry_run モードの場合はここで終了
        if self._dry_run:
            self._logger.info(
                f"[DRY RUN] アルバムをスキップ: {album.name}",
                synology_album_id=album.id,
                asset_count=len(asset_ids),
            )
            return True  # dry_run では成功として扱う

        # Immich にアルバムを作成
        immich_album_id = self._immich_client.create_album(album.name)
        if immich_album_id is None:
            self._logger.error(
                f"アルバムの作成に失敗: {album.name}",
                synology_album_id=album.id,
            )
            return False

        # アセットをアルバムに追加（アセットがある場合のみ）
        if asset_ids:
            success = self._immich_client.add_assets_to_album(immich_album_id, asset_ids)
            if not success:
                self._logger.warning(
                    f"アセットの追加に失敗: {album.name}",
                    synology_album_id=album.id,
                    asset_count=len(asset_ids),
                )
                # アセット追加の失敗はアルバム作成自体は成功しているので
                # 警告だけで続行する

        # ProgressTracker にアルバムを記録
        self._progress_tracker.record_album(
            synology_album_id=album.id,
            synology_album_name=album.name,
            immich_album_id=immich_album_id,
        )

        self._logger.info(
            f"アルバム移行完了: {album.name}",
            synology_album_id=album.id,
            immich_album_id=immich_album_id,
            asset_count=len(asset_ids),
        )

        return True

    def _find_immich_asset_ids(self, file_paths: list[str]) -> list[str]:
        """
        ファイルパスから Immich アセット ID を検索する

        ProgressTracker を使って、各ファイルパスに対応する
        Immich アセット ID を検索する。

        Args:
            file_paths: Synology Photos のファイルパスのリスト

        Returns:
            Immich アセット ID のリスト（見つからなかったファイルは除外）

        Notes:
            - 見つからなかったファイルは警告ログを出力してスキップ
            - status が "success" でないファイルもスキップ
        """
        asset_ids: list[str] = []

        for path in file_paths:
            # ProgressTracker でファイル情報を取得
            file_info = self._progress_tracker.get_file(path)

            if file_info is None:
                # ファイルが見つからない場合はスキップ
                self._logger.warning(
                    f"アセットが見つかりません: {path}",
                )
                continue

            # status が success でない場合はスキップ
            if file_info.get("status") != "success":
                self._logger.warning(
                    f"アセットの移行ステータスが success ではありません: {path}",
                    status=file_info.get("status"),
                )
                continue

            # Immich アセット ID を取得
            asset_id = file_info.get("immich_asset_id")
            if asset_id is None:
                self._logger.warning(
                    f"Immich アセット ID が見つかりません: {path}",
                )
                continue

            asset_ids.append(asset_id)

        return asset_ids
