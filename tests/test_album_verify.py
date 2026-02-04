"""
アルバム検証機能のテスト

アルバム単位での移行検証をテストする。
Synology のアルバムと Immich のアルバムを比較し、
ファイル数とハッシュの一致を確認する。
"""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

import pytest

# これらのインポートは最初は失敗する（TDD の Red フェーズ）
from synology_to_immich.album_verify import (
    AlbumComparisonResult,
    AlbumVerificationReport,
    AlbumVerifier,
)
from synology_to_immich.synology_db import SynologyAlbum


class TestAlbumComparisonResult:
    """AlbumComparisonResult データクラスのテスト"""

    def test_album_comparison_result_creation(self):
        """
        AlbumComparisonResult が正しく作成できることを確認
        """
        # Arrange & Act
        result = AlbumComparisonResult(
            synology_album_name="家族写真",
            synology_album_id=42,
            immich_album_id="abc-123-def",
            immich_album_name="家族写真",
            synology_file_count=150,
            immich_asset_count=148,
            missing_in_immich=["path/to/file1.jpg", "path/to/file2.jpg"],
            extra_in_immich=[],
            hash_mismatches=[],
            match_type="both",
        )

        # Assert
        assert result.synology_album_name == "家族写真"
        assert result.synology_album_id == 42
        assert result.immich_album_id == "abc-123-def"
        assert result.synology_file_count == 150
        assert result.immich_asset_count == 148
        assert len(result.missing_in_immich) == 2
        assert result.match_type == "both"

    def test_album_comparison_result_perfect_match(self):
        """
        完全一致の場合の AlbumComparisonResult
        """
        result = AlbumComparisonResult(
            synology_album_name="旅行",
            synology_album_id=10,
            immich_album_id="xyz-789",
            immich_album_name="旅行",
            synology_file_count=100,
            immich_asset_count=100,
            missing_in_immich=[],
            extra_in_immich=[],
            hash_mismatches=[],
            match_type="name",
        )

        # 完全一致の場合
        assert result.synology_file_count == result.immich_asset_count
        assert len(result.missing_in_immich) == 0
        assert len(result.extra_in_immich) == 0
        assert len(result.hash_mismatches) == 0


class TestAlbumVerificationReport:
    """AlbumVerificationReport データクラスのテスト"""

    def test_album_verification_report_creation(self):
        """
        AlbumVerificationReport が正しく作成できることを確認
        """
        # Arrange
        comparison = AlbumComparisonResult(
            synology_album_name="家族写真",
            synology_album_id=42,
            immich_album_id="abc-123",
            immich_album_name="家族写真",
            synology_file_count=100,
            immich_asset_count=100,
            missing_in_immich=[],
            extra_in_immich=[],
            hash_mismatches=[],
            match_type="both",
        )

        # Act
        report = AlbumVerificationReport(
            timestamp="2026-02-05T12:34:56",
            total_synology_albums=25,
            total_immich_albums=27,
            matched_albums=23,
            unmatched_synology_albums=2,
            unmatched_immich_albums=4,
            album_results=[comparison],
            synology_only=["旅行2020", "古い写真"],
            immich_only=["手動作成1", "テスト", "Favorites", "新アルバム"],
        )

        # Assert
        assert report.timestamp == "2026-02-05T12:34:56"
        assert report.total_synology_albums == 25
        assert report.total_immich_albums == 27
        assert report.matched_albums == 23
        assert len(report.album_results) == 1
        assert len(report.synology_only) == 2
        assert len(report.immich_only) == 4


class TestAlbumVerifierMatching:
    """AlbumVerifier のマッチング機能テスト"""

    def test_match_by_name(self):
        """
        名前でマッチングできることを確認
        """
        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        synology_albums = [
            SynologyAlbum(id=1, name="家族写真", item_count=100),
            SynologyAlbum(id=2, name="旅行", item_count=50),
        ]

        immich_albums = [
            {"id": "uuid-1", "albumName": "家族写真", "assetCount": 100},
            {"id": "uuid-2", "albumName": "旅行", "assetCount": 50},
            {"id": "uuid-3", "albumName": "その他", "assetCount": 30},
        ]

        # Act
        matched = verifier._match_by_name(synology_albums, immich_albums)

        # Assert
        assert len(matched) == 2
        # 家族写真がマッチ
        assert matched[0][0].name == "家族写真"
        assert matched[0][1]["id"] == "uuid-1"
        # 旅行がマッチ
        assert matched[1][0].name == "旅行"
        assert matched[1][1]["id"] == "uuid-2"

    def test_match_by_migration_record(self):
        """
        移行記録（migrated_albums テーブル）でマッチングできることを確認
        """
        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        # 移行記録を返すように設定
        mock_progress_tracker.get_album_by_synology_id.side_effect = lambda album_id: {
            1: {"synology_album_id": 1, "immich_album_id": "uuid-1"},
            2: {"synology_album_id": 2, "immich_album_id": "uuid-2"},
        }.get(album_id)

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        synology_albums = [
            SynologyAlbum(id=1, name="家族写真", item_count=100),
            SynologyAlbum(id=2, name="旅行", item_count=50),
            SynologyAlbum(id=3, name="未移行", item_count=20),
        ]

        immich_albums = [
            {"id": "uuid-1", "albumName": "Family Photos", "assetCount": 100},
            {"id": "uuid-2", "albumName": "Trip", "assetCount": 50},
        ]

        # Act
        matched = verifier._match_by_migration_record(synology_albums, immich_albums)

        # Assert
        assert len(matched) == 2
        # ID=1 が uuid-1 にマッチ
        assert matched[0][0].id == 1
        assert matched[0][1]["id"] == "uuid-1"
        # ID=2 が uuid-2 にマッチ
        assert matched[1][0].id == 2
        assert matched[1][1]["id"] == "uuid-2"

    def test_match_combined(self):
        """
        名前マッチングと移行記録マッチングを統合できることを確認
        両方でマッチした場合は match_type = "both"
        """
        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        # 移行記録: ID=1 が uuid-1 にマッチ
        mock_progress_tracker.get_album_by_synology_id.side_effect = lambda album_id: {
            1: {"synology_album_id": 1, "immich_album_id": "uuid-1"},
        }.get(album_id)

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        synology_albums = [
            SynologyAlbum(id=1, name="家族写真", item_count=100),  # 名前+ID でマッチ
            SynologyAlbum(id=2, name="旅行", item_count=50),        # 名前のみでマッチ
        ]

        immich_albums = [
            {"id": "uuid-1", "albumName": "家族写真", "assetCount": 100},
            {"id": "uuid-2", "albumName": "旅行", "assetCount": 50},
        ]

        # Act
        results = verifier._match_albums(synology_albums, immich_albums)

        # Assert
        # 家族写真: 名前でも ID でもマッチ → match_type = "both"
        family_result = next(r for r in results if r[0].name == "家族写真")
        assert family_result[2] == "both"

        # 旅行: 名前のみでマッチ → match_type = "name"
        travel_result = next(r for r in results if r[0].name == "旅行")
        assert travel_result[2] == "name"


class TestAlbumVerifierComparison:
    """AlbumVerifier のアルバム内容比較テスト"""

    def test_compare_album_perfect_match(self):
        """
        完全一致の場合のテスト
        """
        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        # Synology のファイル一覧
        mock_synology_fetcher.get_album_files.return_value = [
            "/volume1/photo/file1.jpg",
            "/volume1/photo/file2.jpg",
        ]

        # Immich のアセット一覧
        mock_immich_client.get_album_assets.return_value = [
            {"id": "asset-1", "originalFileName": "file1.jpg", "checksum": "aGFzaDEK"},
            {"id": "asset-2", "originalFileName": "file2.jpg", "checksum": "aGFzaDIK"},
        ]

        # ファイル内容を返す（ハッシュ計算用）
        # "aGFzaDEK" は base64("hash1\n")
        # "aGFzaDIK" は base64("hash2\n")
        import base64
        import hashlib
        content1 = b"content1"
        content2 = b"content2"
        hash1 = base64.b64encode(hashlib.sha1(content1).digest()).decode()
        hash2 = base64.b64encode(hashlib.sha1(content2).digest()).decode()

        mock_file_reader.read_file.side_effect = [content1, content2]
        mock_immich_client.get_album_assets.return_value = [
            {"id": "asset-1", "originalFileName": "file1.jpg", "checksum": hash1},
            {"id": "asset-2", "originalFileName": "file2.jpg", "checksum": hash2},
        ]

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        synology_album = SynologyAlbum(id=1, name="家族写真", item_count=2)
        immich_album = {"id": "uuid-1", "albumName": "家族写真", "assetCount": 2}

        # Act
        result = verifier._compare_album_contents(synology_album, immich_album)

        # Assert
        assert result.synology_file_count == 2
        assert result.immich_asset_count == 2
        assert result.missing_in_immich == []
        assert result.extra_in_immich == []
        assert result.hash_mismatches == []

    def test_compare_album_missing_files(self):
        """
        Immich に欠損ファイルがある場合のテスト
        """
        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        mock_synology_fetcher.get_album_files.return_value = [
            "/volume1/photo/file1.jpg",
            "/volume1/photo/file2.jpg",
            "/volume1/photo/file3.jpg",  # これが Immich にない
        ]

        import base64
        import hashlib
        content1 = b"content1"
        content2 = b"content2"
        hash1 = base64.b64encode(hashlib.sha1(content1).digest()).decode()
        hash2 = base64.b64encode(hashlib.sha1(content2).digest()).decode()

        mock_immich_client.get_album_assets.return_value = [
            {"id": "asset-1", "originalFileName": "file1.jpg", "checksum": hash1},
            {"id": "asset-2", "originalFileName": "file2.jpg", "checksum": hash2},
        ]

        mock_file_reader.read_file.side_effect = [content1, content2]

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        synology_album = SynologyAlbum(id=1, name="家族写真", item_count=3)
        immich_album = {"id": "uuid-1", "albumName": "家族写真", "assetCount": 2}

        # Act
        result = verifier._compare_album_contents(synology_album, immich_album)

        # Assert
        assert result.synology_file_count == 3
        assert result.immich_asset_count == 2
        assert "/volume1/photo/file3.jpg" in result.missing_in_immich
        assert result.hash_mismatches == []

    def test_compare_album_hash_mismatch(self):
        """
        ハッシュ不一致がある場合のテスト
        """
        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        mock_synology_fetcher.get_album_files.return_value = [
            "/volume1/photo/file1.jpg",
        ]

        import base64
        import hashlib
        content_local = b"local content"
        content_immich = b"different content"
        hash_immich = base64.b64encode(hashlib.sha1(content_immich).digest()).decode()

        mock_immich_client.get_album_assets.return_value = [
            {"id": "asset-1", "originalFileName": "file1.jpg", "checksum": hash_immich},
        ]

        mock_file_reader.read_file.return_value = content_local

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        synology_album = SynologyAlbum(id=1, name="家族写真", item_count=1)
        immich_album = {"id": "uuid-1", "albumName": "家族写真", "assetCount": 1}

        # Act
        result = verifier._compare_album_contents(synology_album, immich_album)

        # Assert
        assert result.synology_file_count == 1
        assert result.immich_asset_count == 1
        assert result.missing_in_immich == []
        assert "/volume1/photo/file1.jpg" in result.hash_mismatches
