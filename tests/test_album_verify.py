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


class TestAlbumVerifierBatchProcessing:
    """AlbumVerifier のバッチ処理テスト"""

    def test_batch_processing(self):
        """
        100件ごとのバッチ処理が正しく動作することを確認

        250件のファイルを処理する場合:
        - バッチ1: 1-100
        - バッチ2: 101-200
        - バッチ3: 201-250

        各バッチ処理後にメモリが解放されることを間接的に確認
        （read_file の呼び出し回数で検証）
        """
        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        # 250件のファイル
        num_files = 250
        synology_files = [f"/volume1/photo/file{i}.jpg" for i in range(num_files)]
        mock_synology_fetcher.get_album_files.return_value = synology_files

        # 対応する Immich アセット（全て一致）
        import base64
        import hashlib

        def make_content(i):
            return f"content{i}".encode()

        def make_hash(i):
            return base64.b64encode(hashlib.sha1(make_content(i)).digest()).decode()

        immich_assets = [
            {"id": f"asset-{i}", "originalFileName": f"file{i}.jpg", "checksum": make_hash(i)}
            for i in range(num_files)
        ]
        mock_immich_client.get_album_assets.return_value = immich_assets

        # read_file が呼ばれるたびに対応するコンテンツを返す
        call_count = [0]
        def read_file_side_effect(path):
            idx = call_count[0]
            call_count[0] += 1
            return make_content(idx)

        mock_file_reader.read_file.side_effect = read_file_side_effect

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        synology_album = SynologyAlbum(id=1, name="大量写真", item_count=num_files)
        immich_album = {"id": "uuid-1", "albumName": "大量写真", "assetCount": num_files}

        # Act
        result = verifier._compare_album_contents_batch(
            synology_album,
            immich_album,
            batch_size=100,
        )

        # Assert
        assert result.synology_file_count == num_files
        assert result.immich_asset_count == num_files
        assert result.missing_in_immich == []
        assert result.hash_mismatches == []

        # read_file が 250 回呼ばれたことを確認
        assert mock_file_reader.read_file.call_count == num_files


class TestAlbumVerifierResume:
    """AlbumVerifier の再開機能テスト"""

    def test_resume_from_progress_file(self, tmp_path):
        """
        進捗ファイルから再開できることを確認
        """
        import json

        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        # 進捗ファイルを作成（アルバムID=1は検証済み）
        progress_file = tmp_path / "album_verification_progress.json"
        with open(progress_file, "w") as f:
            f.write(json.dumps({
                "verified_album_ids": [1],
                "results": [
                    {
                        "synology_album_id": 1,
                        "synology_album_name": "検証済みアルバム",
                        "status": "ok",
                    }
                ]
            }))

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        # Act
        verified_ids = verifier._load_progress(str(progress_file))

        # Assert
        assert 1 in verified_ids
        assert len(verified_ids) == 1

    def test_save_progress(self, tmp_path):
        """
        進捗を保存できることを確認
        """
        import json

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

        progress_file = tmp_path / "album_verification_progress.json"

        result = AlbumComparisonResult(
            synology_album_name="テストアルバム",
            synology_album_id=42,
            immich_album_id="uuid-42",
            immich_album_name="テストアルバム",
            synology_file_count=10,
            immich_asset_count=10,
            missing_in_immich=[],
            extra_in_immich=[],
            hash_mismatches=[],
            match_type="both",
        )

        # Act
        verifier._save_progress(str(progress_file), result)

        # Assert
        with open(progress_file, "r") as f:
            saved = json.loads(f.read())

        assert saved["synology_album_id"] == 42
        assert saved["synology_album_name"] == "テストアルバム"


class TestAlbumVerifierReport:
    """AlbumVerifier のレポート出力テスト"""

    def test_generate_json_report(self, tmp_path):
        """
        JSON レポートを生成できることを確認
        """
        import json

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

        # レポートデータ
        report = AlbumVerificationReport(
            timestamp="2026-02-05T12:34:56",
            total_synology_albums=25,
            total_immich_albums=27,
            matched_albums=23,
            unmatched_synology_albums=2,
            unmatched_immich_albums=4,
            album_results=[
                AlbumComparisonResult(
                    synology_album_name="家族写真",
                    synology_album_id=1,
                    immich_album_id="uuid-1",
                    immich_album_name="家族写真",
                    synology_file_count=100,
                    immich_asset_count=98,
                    missing_in_immich=["file1.jpg", "file2.jpg"],
                    extra_in_immich=[],
                    hash_mismatches=[],
                    match_type="both",
                ),
            ],
            synology_only=["旅行2020"],
            immich_only=["手動作成"],
        )

        output_file = tmp_path / "report.json"

        # Act
        verifier._generate_json_report(report, str(output_file))

        # Assert
        with open(output_file, "r") as f:
            saved = json.load(f)

        assert saved["timestamp"] == "2026-02-05T12:34:56"
        assert saved["summary"]["total_synology_albums"] == 25
        assert saved["summary"]["total_immich_albums"] == 27
        assert saved["summary"]["matched_albums"] == 23
        assert len(saved["album_comparisons"]) == 1
        assert saved["album_comparisons"][0]["synology_name"] == "家族写真"
        assert saved["unmatched_albums"]["synology_only"] == ["旅行2020"]
        assert saved["unmatched_albums"]["immich_only"] == ["手動作成"]


class TestAlbumVerifierVerify:
    """AlbumVerifier.verify() メソッドのテスト"""

    def test_verify_full_workflow(self, tmp_path):
        """
        verify() メソッドが全体のワークフローを実行できることを確認
        """
        import base64
        import hashlib

        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        # Synology アルバム
        mock_synology_fetcher.get_albums.return_value = [
            SynologyAlbum(id=1, name="家族写真", item_count=2),
            SynologyAlbum(id=2, name="旅行", item_count=1),
        ]

        # Immich アルバム
        mock_immich_client.get_albums.return_value = [
            {"id": "uuid-1", "albumName": "家族写真", "assetCount": 2},
            {"id": "uuid-2", "albumName": "旅行", "assetCount": 1},
            {"id": "uuid-3", "albumName": "手動作成", "assetCount": 5},
        ]

        # 移行記録なし
        mock_progress_tracker.get_album_by_synology_id.return_value = None

        # ファイル一覧
        mock_synology_fetcher.get_album_files.side_effect = [
            ["/vol/file1.jpg", "/vol/file2.jpg"],  # 家族写真
            ["/vol/trip.jpg"],                       # 旅行
        ]

        # Immich アセット
        content1 = b"content1"
        content2 = b"content2"
        content3 = b"content3"
        hash1 = base64.b64encode(hashlib.sha1(content1).digest()).decode()
        hash2 = base64.b64encode(hashlib.sha1(content2).digest()).decode()
        hash3 = base64.b64encode(hashlib.sha1(content3).digest()).decode()

        mock_immich_client.get_album_assets.side_effect = [
            [
                {"id": "a1", "originalFileName": "file1.jpg", "checksum": hash1},
                {"id": "a2", "originalFileName": "file2.jpg", "checksum": hash2},
            ],
            [
                {"id": "a3", "originalFileName": "trip.jpg", "checksum": hash3},
            ],
        ]

        mock_file_reader.read_file.side_effect = [content1, content2, content3]

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        output_file = tmp_path / "report.json"
        progress_file = tmp_path / "progress.json"

        # Act
        report = verifier.verify(
            output_file=str(output_file),
            progress_file=str(progress_file),
            batch_size=100,
        )

        # Assert
        assert report.total_synology_albums == 2
        assert report.total_immich_albums == 3
        assert report.matched_albums == 2
        assert len(report.album_results) == 2
        assert report.immich_only == ["手動作成"]

        # JSON レポートが生成されていること
        assert output_file.exists()


class TestAlbumVerifierPathConversion:
    """AlbumVerifier のパス変換機能テスト"""

    def test_convert_db_path_to_smb_path(self):
        """
        DB パス（/PhotoLibrary/...）を SMB UNC パスに変換できることを確認

        Synology DB から取得したパス（例: /PhotoLibrary/2024/photo.jpg）を
        SMB リーダーが期待する UNC パス形式に変換する。

        例:
        - DB パス: /PhotoLibrary/2024/photo.jpg
        - SMB ベース: \\\\192.168.1.1\\homes\\shishi\\Photos
        - 結果: \\\\192.168.1.1\\homes\\shishi\\Photos\\2024\\photo.jpg
        """
        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        # SMB リーダーの smb_base_path を設定
        mock_file_reader.smb_base_path = "\\\\192.168.1.1\\homes\\shishi\\Photos"

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        # Act
        db_path = "/PhotoLibrary/2024/family/photo.jpg"
        smb_path = verifier._convert_db_path_to_smb_path(db_path)

        # Assert
        expected = "\\\\192.168.1.1\\homes\\shishi\\Photos\\2024\\family\\photo.jpg"
        assert smb_path == expected

    def test_convert_db_path_preserves_nested_folders(self):
        """
        ネストされたフォルダ構造が保持されることを確認
        """
        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        mock_file_reader.smb_base_path = "\\\\nas\\share\\photos"

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        # Act
        db_path = "/PhotoLibrary/2024/01/01/subfolder/image.heic"
        smb_path = verifier._convert_db_path_to_smb_path(db_path)

        # Assert
        expected = "\\\\nas\\share\\photos\\2024\\01\\01\\subfolder\\image.heic"
        assert smb_path == expected

    def test_compare_album_uses_converted_paths(self):
        """
        _compare_album_contents_batch がパス変換を使用することを確認
        """
        import base64
        import hashlib

        # Arrange
        mock_synology_fetcher = MagicMock()
        mock_immich_client = MagicMock()
        mock_progress_tracker = MagicMock()
        mock_file_reader = MagicMock()

        # SMB リーダーの設定
        mock_file_reader.smb_base_path = "\\\\192.168.1.1\\homes\\shishi\\Photos"

        # DB から返されるパス（/PhotoLibrary/... 形式）
        mock_synology_fetcher.get_album_files.return_value = [
            "/PhotoLibrary/2024/photo1.jpg",
        ]

        # ファイル内容とハッシュ
        content = b"test content"
        checksum = base64.b64encode(hashlib.sha1(content).digest()).decode()

        mock_immich_client.get_album_assets.return_value = [
            {"id": "a1", "originalFileName": "photo1.jpg", "checksum": checksum},
        ]

        mock_file_reader.read_file.return_value = content

        verifier = AlbumVerifier(
            synology_fetcher=mock_synology_fetcher,
            immich_client=mock_immich_client,
            progress_tracker=mock_progress_tracker,
            file_reader=mock_file_reader,
        )

        synology_album = SynologyAlbum(id=1, name="テスト", item_count=1)
        immich_album = {"id": "uuid-1", "albumName": "テスト", "assetCount": 1}

        # Act
        result = verifier._compare_album_contents_batch(
            synology_album,
            immich_album,
            batch_size=100,
        )

        # Assert
        # read_file が変換後の SMB パスで呼ばれていること
        expected_smb_path = "\\\\192.168.1.1\\homes\\shishi\\Photos\\2024\\photo1.jpg"
        mock_file_reader.read_file.assert_called_once_with(expected_smb_path)
