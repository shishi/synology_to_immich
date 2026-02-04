"""
アルバム移行機能のテスト

AlbumMigrator クラスのテストを行う。
Synology Photos のアルバムを Immich に移行する機能をテストする。
"""

from unittest.mock import Mock

import pytest

from synology_to_immich.album import AlbumMigrationResult, AlbumMigrator
from synology_to_immich.synology_db import SynologyAlbum


class TestAlbumMigrationResult:
    """AlbumMigrationResult データクラスのテスト"""

    def test_result_has_required_fields(self):
        """必須フィールドが存在することを確認"""
        result = AlbumMigrationResult(
            total_albums=10,
            success_count=8,
            failed_count=1,
            skipped_count=1,
        )
        assert result.total_albums == 10
        assert result.success_count == 8
        assert result.failed_count == 1
        assert result.skipped_count == 1


class TestAlbumMigrator:
    """AlbumMigrator のテスト"""

    @pytest.fixture
    def mock_synology_fetcher(self):
        """SynologyAlbumFetcher のモック"""
        fetcher = Mock()
        fetcher.get_albums.return_value = [
            SynologyAlbum(id=1, name="Vacation 2024", item_count=10),
            SynologyAlbum(id=2, name="Birthday", item_count=5),
        ]
        fetcher.get_album_files.side_effect = lambda album_id: {
            1: ["/Photos/vacation/IMG_001.jpg", "/Photos/vacation/IMG_002.jpg"],
            2: ["/Photos/birthday/IMG_001.jpg"],
        }.get(album_id, [])
        return fetcher

    @pytest.fixture
    def mock_immich_client(self):
        """ImmichClient のモック"""
        client = Mock()
        client.create_album.return_value = "immich-album-uuid"
        client.add_assets_to_album.return_value = True
        return client

    @pytest.fixture
    def mock_progress_tracker(self):
        """ProgressTracker のモック"""
        tracker = Mock()
        tracker.get_album_by_synology_id.return_value = None  # 未移行
        # ファイルパスから Immich アセット ID を返す
        tracker.get_file.side_effect = lambda path: {
            "/Photos/vacation/IMG_001.jpg": {"immich_asset_id": "asset-1", "status": "success"},
            "/Photos/vacation/IMG_002.jpg": {"immich_asset_id": "asset-2", "status": "success"},
            "/Photos/birthday/IMG_001.jpg": {"immich_asset_id": "asset-3", "status": "success"},
        }.get(path)
        return tracker

    @pytest.fixture
    def mock_logger(self):
        """MigrationLogger のモック"""
        return Mock()

    def test_migrate_albums_success(
        self,
        mock_synology_fetcher,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """アルバム移行が成功することを確認"""
        migrator = AlbumMigrator(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.migrate_albums()

        assert result.total_albums == 2
        assert result.success_count == 2
        assert result.failed_count == 0
        # Immich にアルバムが作成される
        assert mock_immich_client.create_album.call_count == 2
        # ProgressTracker にアルバムが記録される
        assert mock_progress_tracker.record_album.call_count == 2

    def test_skips_already_migrated_albums(
        self,
        mock_synology_fetcher,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """移行済みアルバムはスキップされることを確認"""
        # アルバム ID=1 は移行済み
        mock_progress_tracker.get_album_by_synology_id.side_effect = lambda id: {
            1: {"synology_album_id": 1, "immich_album_id": "existing-album"},
        }.get(id)

        migrator = AlbumMigrator(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.migrate_albums()

        assert result.skipped_count == 1
        assert result.success_count == 1
        # 1つだけアルバムが作成される
        assert mock_immich_client.create_album.call_count == 1

    def test_handles_missing_assets(
        self,
        mock_synology_fetcher,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """ファイルが Immich に存在しない場合も処理できることを確認"""
        # 一部のファイルが見つからない
        mock_progress_tracker.get_file.side_effect = lambda path: {
            "/Photos/vacation/IMG_001.jpg": {"immich_asset_id": "asset-1", "status": "success"},
            # IMG_002.jpg は None（見つからない）
        }.get(path)

        migrator = AlbumMigrator(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.migrate_albums()

        # アルバムは作成されるが、一部のアセットのみ
        assert result.success_count >= 1

    def test_dry_run_mode(
        self,
        mock_synology_fetcher,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """dry_run モードでは実際に作成しないことを確認"""
        migrator = AlbumMigrator(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
            dry_run=True,
        )

        result = migrator.migrate_albums()

        # Immich にはアルバムが作成されない
        mock_immich_client.create_album.assert_not_called()
        # でも処理はされる
        assert result.total_albums == 2

    def test_handles_album_creation_failure(
        self,
        mock_synology_fetcher,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """アルバム作成に失敗した場合の処理を確認"""
        # アルバム作成が失敗する
        mock_immich_client.create_album.return_value = None

        migrator = AlbumMigrator(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.migrate_albums()

        # 失敗としてカウントされる
        assert result.failed_count == 2
        assert result.success_count == 0
        # ProgressTracker には記録されない
        mock_progress_tracker.record_album.assert_not_called()
