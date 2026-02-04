"""
Backfiller のテスト

backfill コマンドのロジック層をテストする。
"""

import pytest

from synology_to_immich.backfill import Backfiller
from synology_to_immich.progress import FileStatus, ProgressTracker
from synology_to_immich.readers.base import FileInfo


class TestFindUnrecordedFiles:
    """DB に記録されていないファイルを検出するテスト"""

    def test_find_unrecorded_files_returns_files_not_in_db(self, tmp_path):
        """DB に記録がないファイルを返す"""
        # Arrange
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(str(db_path))

        # DB には file1 だけ記録
        tracker.record_file(
            source_path="/photos/file1.jpg",
            source_hash=None,
            source_size=1000,
            source_mtime="2024-01-01T00:00:00",
            immich_asset_id="asset-1",
            status=FileStatus.SUCCESS,
        )

        # ソースには file1, file2, file3 がある
        source_files = [
            FileInfo(path="/photos/file1.jpg", size=1000, mtime="2024-01-01T00:00:00"),
            FileInfo(path="/photos/file2.jpg", size=2000, mtime="2024-01-02T00:00:00"),
            FileInfo(path="/photos/file3.jpg", size=3000, mtime="2024-01-03T00:00:00"),
        ]

        backfiller = Backfiller(progress_tracker=tracker)

        # Act
        unrecorded = backfiller.find_unrecorded_files(source_files)

        # Assert
        assert len(unrecorded) == 2
        paths = [f.path for f in unrecorded]
        assert "/photos/file2.jpg" in paths
        assert "/photos/file3.jpg" in paths
        assert "/photos/file1.jpg" not in paths

        tracker.close()


class TestCheckImmichExistence:
    """Immich にファイルが存在するか確認するテスト"""

    def test_check_immich_existence_categorizes_files(self, tmp_path):
        """Immich に存在するファイルと存在しないファイルを分類する"""
        # Arrange
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(str(db_path))

        # モック ImmichClient
        class MockImmichClient:
            def get_all_assets(self):
                return [
                    {"id": "asset-1", "originalFileName": "file2.jpg"},
                    {"id": "asset-2", "originalFileName": "other.jpg"},
                ]

        unrecorded_files = [
            FileInfo(path="/photos/file2.jpg", size=2000, mtime="2024-01-02T00:00:00"),
            FileInfo(path="/photos/file3.jpg", size=3000, mtime="2024-01-03T00:00:00"),
        ]

        backfiller = Backfiller(
            progress_tracker=tracker,
            immich_client=MockImmichClient(),
        )

        # Act
        existing, missing = backfiller.check_immich_existence(unrecorded_files)

        # Assert
        # file2.jpg は Immich にある
        assert len(existing) == 1
        assert existing[0]["file_info"].path == "/photos/file2.jpg"
        assert existing[0]["asset_id"] == "asset-1"

        # file3.jpg は Immich にない
        assert len(missing) == 1
        assert missing[0].path == "/photos/file3.jpg"

        tracker.close()


class TestBackfillExisting:
    """Immich に存在するファイルを DB にバックフィルするテスト"""

    def test_backfill_records_existing_asset_to_db(self, tmp_path):
        """Immich に存在するファイルを DB に記録する"""
        # Arrange
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(str(db_path))

        existing_files = [
            {
                "file_info": FileInfo(
                    path="/photos/file2.jpg", size=2000, mtime="2024-01-02T00:00:00"
                ),
                "asset_id": "asset-1",
            },
        ]

        backfiller = Backfiller(progress_tracker=tracker)

        # Act
        backfiller.backfill_existing(existing_files)

        # Assert
        record = tracker.get_file("/photos/file2.jpg")
        assert record is not None
        assert record["immich_asset_id"] == "asset-1"
        assert record["status"] == FileStatus.SUCCESS.value

        tracker.close()


class TestUploadMissing:
    """Immich に存在しないファイルをアップロードするテスト"""

    def test_upload_missing_uploads_and_records(self, tmp_path):
        """不足ファイルをアップロードして DB に記録する"""
        # Arrange
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(str(db_path))

        # アップロード結果を返すモック
        class MockUploadResult:
            success = True
            asset_id = "new-asset-1"
            error_message = None

        class MockImmichClient:
            def upload_asset(self, file_data, filename, created_at):
                return MockUploadResult()

        # ファイルを読み込むモック
        class MockFileReader:
            def read_file(self, path):
                return b"fake file content"

        missing_files = [
            FileInfo(path="/photos/file3.jpg", size=3000, mtime="2024-01-03T00:00:00"),
        ]

        backfiller = Backfiller(
            progress_tracker=tracker,
            immich_client=MockImmichClient(),
            file_reader=MockFileReader(),
        )

        # Act
        uploaded, failed = backfiller.upload_missing(missing_files)

        # Assert
        assert uploaded == 1
        assert failed == 0

        record = tracker.get_file("/photos/file3.jpg")
        assert record is not None
        assert record["immich_asset_id"] == "new-asset-1"
        assert record["status"] == FileStatus.SUCCESS.value

        tracker.close()


class TestBackfillCommand:
    """backfill CLI コマンドのテスト"""

    def test_backfill_command_exists(self):
        """backfill コマンドが存在する"""
        from click.testing import CliRunner

        from synology_to_immich.__main__ import main

        runner = CliRunner()
        result = runner.invoke(main, ["backfill", "--help"])

        assert result.exit_code == 0
        assert "backfill" in result.output.lower() or "補完" in result.output
