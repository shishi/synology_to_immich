"""
Migrator（移行オーケストレーター）のテスト

各コンポーネントをモックして、オーケストレーションロジックをテストする。
Migrator は以下のコンポーネントを組み合わせて移行処理を行う:
- FileReader: ファイルスキャン
- LivePhotoPairer: Live Photo ペアリング
- ImmichClient: アップロード
- ProgressTracker: 進捗管理
- MigrationLogger: ログ出力
"""

from unittest.mock import Mock, patch

import pytest

from synology_to_immich.config import Config
from synology_to_immich.immich import ImmichUploadResult
from synology_to_immich.migrator import MigrationResult, Migrator
from synology_to_immich.readers.base import FileInfo


class TestMigrationResult:
    """MigrationResult データクラスのテスト"""

    def test_migration_result_has_required_fields(self):
        """必須フィールドが存在することを確認"""
        result = MigrationResult(
            total_files=100,
            success_count=90,
            failed_count=5,
            skipped_count=3,
            unsupported_count=2,
            elapsed_seconds=120.5,
        )

        assert result.total_files == 100
        assert result.success_count == 90
        assert result.failed_count == 5
        assert result.skipped_count == 3
        assert result.unsupported_count == 2
        assert result.elapsed_seconds == 120.5


class TestMigrator:
    """Migrator のテスト"""

    @pytest.fixture
    def mock_config(self):
        """テスト用の Config モック"""
        config = Mock(spec=Config)
        config.dry_run = False
        config.batch_size = 10
        config.batch_delay = 0.0  # テストでは待機しない
        return config

    @pytest.fixture
    def mock_reader(self):
        """テスト用の FileReader モック"""
        reader = Mock()
        reader.list_files.return_value = iter(
            [
                FileInfo(path="/photos/IMG_001.jpg", size=1000, mtime="2024-01-01"),
            ]
        )
        reader.read_file.return_value = b"fake image data"
        return reader

    @pytest.fixture
    def mock_immich_client(self):
        """テスト用の ImmichClient モック"""
        client = Mock()
        client.upload_asset.return_value = ImmichUploadResult(
            success=True,
            asset_id="asset-123",
            error_message=None,
            is_unsupported=False,
        )
        return client

    @pytest.fixture
    def mock_progress_tracker(self):
        """テスト用の ProgressTracker モック"""
        tracker = Mock()
        tracker.is_migrated.return_value = False
        return tracker

    @pytest.fixture
    def mock_logger(self):
        """テスト用の MigrationLogger モック"""
        return Mock()

    def test_run_processes_files(
        self,
        mock_config,
        mock_reader,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """ファイルが処理されることを確認"""
        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.run()

        assert result.total_files == 1
        assert result.success_count == 1
        mock_immich_client.upload_asset.assert_called_once()
        mock_progress_tracker.record_file.assert_called_once()

    def test_skips_already_migrated(
        self,
        mock_config,
        mock_reader,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """移行済みファイルはスキップされることを確認"""
        mock_progress_tracker.is_migrated.return_value = True

        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.run()

        assert result.skipped_count == 1
        assert result.success_count == 0
        mock_immich_client.upload_asset.assert_not_called()

    def test_dry_run_mode(
        self,
        mock_config,
        mock_reader,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """dry_run モードではアップロードしないことを確認"""
        mock_config.dry_run = True

        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.run()

        assert result.total_files == 1
        mock_immich_client.upload_asset.assert_not_called()
        # dry_run でも成功としてカウント（実際にはアップロードしていない）
        mock_logger.info.assert_called()

    def test_handles_upload_failure(
        self,
        mock_config,
        mock_reader,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """アップロード失敗時の処理を確認"""
        mock_immich_client.upload_asset.return_value = ImmichUploadResult(
            success=False,
            asset_id=None,
            error_message="Network error",
            is_unsupported=False,
        )

        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.run()

        assert result.failed_count == 1
        assert result.success_count == 0
        mock_logger.error.assert_called()

    def test_handles_unsupported_format(
        self,
        mock_config,
        mock_reader,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """未対応形式の処理を確認"""
        mock_immich_client.upload_asset.return_value = ImmichUploadResult(
            success=False,
            asset_id=None,
            error_message="Unsupported file type",
            is_unsupported=True,
        )

        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.run()

        assert result.unsupported_count == 1
        assert result.failed_count == 0
        mock_logger.log_unsupported.assert_called()

    def test_processes_live_photo_pair(
        self,
        mock_config,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """Live Photo ペアが正しく処理されることを確認"""
        # Live Photo ペアを返すリーダー
        mock_reader = Mock()
        mock_reader.list_files.return_value = iter(
            [
                FileInfo(path="/photos/IMG_001.HEIC", size=1000, mtime="2024-01-01"),
                FileInfo(path="/photos/IMG_001.MOV", size=2000, mtime="2024-01-01"),
            ]
        )
        mock_reader.read_file.side_effect = lambda p: b"image" if "HEIC" in p else b"video"

        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.run()

        # ペアは1つのアップロードとしてカウント
        assert result.total_files == 1
        assert result.success_count == 1

        # Immich v2.x では live_photo_data は使わない
        # 代わりに静止画と動画を別々にアップロードする
        # upload_asset が2回呼ばれる（静止画 + 動画）
        assert mock_immich_client.upload_asset.call_count == 2

        # 1回目は静止画
        first_call = mock_immich_client.upload_asset.call_args_list[0]
        first_filename = first_call.kwargs.get("filename", "")
        assert "HEIC" in first_filename, f"1回目のアップロードは HEIC であるべき: {first_filename}"

        # 2回目は動画
        second_call = mock_immich_client.upload_asset.call_args_list[1]
        second_filename = second_call.kwargs.get("filename", "")
        assert "MOV" in second_filename, f"2回目のアップロードは MOV であるべき: {second_filename}"

    def test_batch_processing(
        self,
        mock_config,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """バッチ処理が機能することを確認"""
        mock_config.batch_size = 2
        mock_config.batch_delay = 0.01  # 10ms

        # 5ファイルを返す
        mock_reader = Mock()
        mock_reader.list_files.return_value = iter(
            [
                FileInfo(path=f"/photos/IMG_{i:03d}.jpg", size=1000, mtime="2024-01-01")
                for i in range(5)
            ]
        )
        mock_reader.read_file.return_value = b"fake data"

        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        with patch("synology_to_immich.migrator.time.sleep") as mock_sleep:
            result = migrator.run()

        assert result.total_files == 5
        # バッチ2つ分の待機（5ファイル / 2バッチサイズ = 2回の待機、最後は待機なし）
        assert mock_sleep.call_count == 2

    def test_elapsed_time_recorded(
        self,
        mock_config,
        mock_reader,
        mock_immich_client,
        mock_progress_tracker,
        mock_logger,
    ):
        """処理時間が記録されることを確認"""
        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.run()

        # 処理時間が記録されている（0 以上）
        assert result.elapsed_seconds >= 0

    def test_live_photo_video_upload_failure_counts_as_failed(
        self,
        mock_config,
        mock_progress_tracker,
        mock_logger,
    ):
        """Live Photo の動画アップロード失敗時は全体が失敗になることを確認"""
        # Live Photo ペアを返すリーダー
        mock_reader = Mock()
        mock_reader.list_files.return_value = iter(
            [
                FileInfo(path="/photos/IMG_001.HEIC", size=1000, mtime="2024-01-01"),
                FileInfo(path="/photos/IMG_001.MOV", size=2000, mtime="2024-01-01"),
            ]
        )
        mock_reader.read_file.side_effect = lambda p: b"image" if "HEIC" in p else b"video"

        # 静止画は成功、動画は失敗
        mock_immich_client = Mock()
        mock_immich_client.upload_asset.side_effect = [
            ImmichUploadResult(
                success=True,
                asset_id="image-asset-123",
                error_message=None,
                is_unsupported=False,
            ),
            ImmichUploadResult(
                success=False,
                asset_id=None,
                error_message="Video upload failed",
                is_unsupported=False,
            ),
        ]

        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.run()

        # 動画アップロードが失敗したら、Live Photo 全体が失敗として扱われるべき
        assert result.failed_count == 1
        assert result.success_count == 0

    def test_live_photo_video_read_error_counts_as_failed(
        self,
        mock_config,
        mock_progress_tracker,
        mock_logger,
    ):
        """Live Photo の動画読み込みエラー時は全体が失敗になることを確認"""
        # Live Photo ペアを返すリーダー
        mock_reader = Mock()
        mock_reader.list_files.return_value = iter(
            [
                FileInfo(path="/photos/IMG_001.HEIC", size=1000, mtime="2024-01-01"),
                FileInfo(path="/photos/IMG_001.MOV", size=2000, mtime="2024-01-01"),
            ]
        )

        # 静止画は読める、動画は読み込みエラー
        def read_file_side_effect(path):
            if "HEIC" in path:
                return b"image data"
            raise IOError("Failed to read video file")

        mock_reader.read_file.side_effect = read_file_side_effect

        # 静止画アップロードは成功
        mock_immich_client = Mock()
        mock_immich_client.upload_asset.return_value = ImmichUploadResult(
            success=True,
            asset_id="image-asset-123",
            error_message=None,
            is_unsupported=False,
        )

        migrator = Migrator(
            config=mock_config,
            reader=mock_reader,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            logger=mock_logger,
        )

        result = migrator.run()

        # 動画読み込みエラー時は、Live Photo 全体が失敗として扱われるべき
        assert result.failed_count == 1
        assert result.success_count == 0
