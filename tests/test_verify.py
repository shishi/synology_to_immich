"""
検証機能のテスト

移行結果の検証ロジックをテストする。
移行が正しく行われたかを確認するために、
ProgressTracker に記録された成功ファイルが Immich に存在するかを検証する。
"""

from unittest.mock import Mock

import pytest

from synology_to_immich.verify import VerificationResult, Verifier


class TestVerificationResult:
    """VerificationResult データクラスのテスト"""

    def test_verification_result_valid(self):
        """検証成功時の結果

        欠損ファイルとハッシュ不一致がない場合は valid
        """
        result = VerificationResult(
            local_file_count=100,
            immich_asset_count=100,
            missing_in_immich=[],
            hash_mismatches=[],
        )

        assert result.is_valid is True

    def test_verification_result_count_mismatch(self):
        """件数不一致の場合

        件数が一致しなくても missing リストが空なら valid
        """
        result = VerificationResult(
            local_file_count=100,
            immich_asset_count=95,
            missing_in_immich=[],
        )

        assert result.is_valid is True

    def test_verification_result_missing_files(self):
        """欠損ファイルがある場合

        missing_in_immich に欠損ファイルがある場合は invalid
        """
        result = VerificationResult(
            local_file_count=100,
            immich_asset_count=95,
            missing_in_immich=["/photos/missing1.jpg", "/photos/missing2.jpg"],
        )

        assert result.is_valid is False

    def test_verification_result_empty(self):
        """ファイルが0件の場合

        何も移行していない場合でも valid
        """
        result = VerificationResult(
            local_file_count=0,
            immich_asset_count=0,
            missing_in_immich=[],
        )

        assert result.is_valid is True

    def test_verification_result_not_in_db_still_valid(self):
        """not_in_db があっても valid

        progress.db に記録がないファイルは検証失敗とは見なさない
        """
        result = VerificationResult(
            local_file_count=100,
            immich_asset_count=95,
            missing_in_immich=[],
            not_in_db=["/photos/new.jpg"],
        )

        assert result.is_valid is True


class TestHashVerificationWithLocalFiles:
    """ローカルファイルリストを正として検証するテスト"""

    @pytest.fixture
    def mock_progress_tracker(self):
        """テスト用の ProgressTracker モック"""
        tracker = Mock()
        return tracker

    @pytest.fixture
    def mock_immich_client(self):
        """テスト用の ImmichClient モック"""
        client = Mock()
        return client

    @pytest.fixture
    def mock_file_reader(self):
        """テスト用の FileReader モック"""
        reader = Mock()
        return reader

    def test_verify_uses_local_file_list_as_source(
        self,
        mock_progress_tracker,
        mock_immich_client,
        mock_file_reader,
        tmp_path,
    ):
        """検証はローカルファイルリストを正として行う

        progress.db ではなく、reader.list_files() のファイルリストを
        検証対象とする。これにより progress.db が信用できなくても
        正しく検証できる。
        """
        import base64
        import hashlib
        from synology_to_immich.readers.base import FileInfo

        # ファイルの内容とチェックサム
        file_content = b"test image content"
        sha1_hash = hashlib.sha1(file_content).digest()
        checksum_base64 = base64.b64encode(sha1_hash).decode()

        # ローカルファイルリスト（これが正！）
        mock_file_reader.list_files.return_value = iter([
            FileInfo(path="/photos/a.jpg", size=100, mtime="2024-01-15"),
            FileInfo(path="/photos/b.jpg", size=200, mtime="2024-01-15"),
        ])
        mock_file_reader.read_file.return_value = file_content

        # progress.db から immich_asset_id を取得
        mock_progress_tracker.get_file.side_effect = lambda path: {
            "/photos/a.jpg": {"immich_asset_id": "asset-a"},
            "/photos/b.jpg": {"immich_asset_id": "asset-b"},
        }.get(path)

        # Immich のアセット
        mock_immich_client.get_all_assets.return_value = [
            {"id": "asset-a", "checksum": checksum_base64},
            {"id": "asset-b", "checksum": checksum_base64},
        ]

        verifier = Verifier(
            progress_tracker=mock_progress_tracker,
            immich_client=mock_immich_client,
        )

        resume_file = str(tmp_path / "test_progress.txt")
        result = verifier.verify_with_hash(file_reader=mock_file_reader, resume_file=resume_file)

        # list_files が呼ばれたことを確認
        mock_file_reader.list_files.assert_called_once()

        # 全て一致 → valid
        assert result.is_valid is True
        assert len(result.missing_in_immich) == 0
        assert len(result.hash_mismatches) == 0

    def test_verify_file_not_in_progress_db(
        self,
        mock_progress_tracker,
        mock_immich_client,
        mock_file_reader,
        tmp_path,
    ):
        """progress.db に記録がないファイルは not_in_db としてカウント

        ローカルにあるけど progress.db に記録がない場合、
        移行されていない可能性がある。
        """
        from synology_to_immich.readers.base import FileInfo

        # ローカルファイルリスト
        mock_file_reader.list_files.return_value = iter([
            FileInfo(path="/photos/new.jpg", size=100, mtime="2024-01-15"),
        ])

        # progress.db には記録がない
        mock_progress_tracker.get_file.return_value = None

        # Immich のアセット
        mock_immich_client.get_all_assets.return_value = []

        verifier = Verifier(
            progress_tracker=mock_progress_tracker,
            immich_client=mock_immich_client,
        )

        resume_file = str(tmp_path / "test_progress.txt")
        result = verifier.verify_with_hash(file_reader=mock_file_reader, resume_file=resume_file)

        # progress.db に記録がない → not_in_db
        assert result.not_in_db == ["/photos/new.jpg"]

    def test_verify_sorted_file_list_for_resume(
        self,
        mock_progress_tracker,
        mock_immich_client,
        mock_file_reader,
        tmp_path,
    ):
        """ファイルリストはソートされて一定の順序で処理される

        再開機能のため、ファイルリストは毎回同じ順序で処理される必要がある。
        """
        import base64
        import hashlib
        from synology_to_immich.readers.base import FileInfo

        file_content = b"test"
        sha1_hash = hashlib.sha1(file_content).digest()
        checksum_base64 = base64.b64encode(sha1_hash).decode()

        # 順序がバラバラなファイルリスト
        mock_file_reader.list_files.return_value = iter([
            FileInfo(path="/photos/c.jpg", size=100, mtime="2024-01-15"),
            FileInfo(path="/photos/a.jpg", size=100, mtime="2024-01-15"),
            FileInfo(path="/photos/b.jpg", size=100, mtime="2024-01-15"),
        ])
        mock_file_reader.read_file.return_value = file_content

        mock_progress_tracker.get_file.side_effect = lambda path: {
            "/photos/a.jpg": {"immich_asset_id": "asset-a"},
            "/photos/b.jpg": {"immich_asset_id": "asset-b"},
            "/photos/c.jpg": {"immich_asset_id": "asset-c"},
        }.get(path)

        mock_immich_client.get_all_assets.return_value = [
            {"id": "asset-a", "checksum": checksum_base64},
            {"id": "asset-b", "checksum": checksum_base64},
            {"id": "asset-c", "checksum": checksum_base64},
        ]

        verifier = Verifier(
            progress_tracker=mock_progress_tracker,
            immich_client=mock_immich_client,
        )

        resume_file = str(tmp_path / "test_progress.txt")
        result = verifier.verify_with_hash(file_reader=mock_file_reader, resume_file=resume_file)

        # 進捗ファイルを読んで順序を確認
        import json
        with open(resume_file) as f:
            lines = [json.loads(line) for line in f if line.strip()]

        # ソートされた順序で処理されている
        assert lines[0]["path"] == "/photos/a.jpg"
        assert lines[1]["path"] == "/photos/b.jpg"
        assert lines[2]["path"] == "/photos/c.jpg"

    def test_verify_no_checksum_is_missing(
        self,
        mock_progress_tracker,
        mock_immich_client,
        mock_file_reader,
        tmp_path,
    ):
        """checksum がない場合は missing として扱う

        Immich のアセットに checksum がない場合、
        ハッシュ検証ができないため missing として扱う。
        """
        from synology_to_immich.readers.base import FileInfo

        # ローカルファイル
        mock_file_reader.list_files.return_value = iter([
            FileInfo(path="/photos/no_checksum.jpg", size=100, mtime="2024-01-15"),
        ])

        # progress.db には記録がある
        mock_progress_tracker.get_file.return_value = {"immich_asset_id": "asset-no-checksum"}

        # Immich のアセットには checksum がない
        mock_immich_client.get_all_assets.return_value = [
            {"id": "asset-no-checksum", "checksum": None},
        ]
        mock_immich_client.get_asset_by_id.return_value = {"id": "asset-no-checksum", "checksum": None}

        verifier = Verifier(
            progress_tracker=mock_progress_tracker,
            immich_client=mock_immich_client,
        )

        resume_file = str(tmp_path / "test_progress.txt")
        result = verifier.verify_with_hash(file_reader=mock_file_reader, resume_file=resume_file)

        # checksum がない → missing として扱う → is_valid は False
        assert result.is_valid is False
        assert "/photos/no_checksum.jpg" in result.missing_in_immich
