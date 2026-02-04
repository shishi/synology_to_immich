"""
CLI コマンドのテスト

click.testing.CliRunner を使用してコマンドをテストする。

click は Python でコマンドラインインターフェース（CLI）を作成するための
ライブラリで、CliRunner を使うことでコマンドを実際に実行せずにテストできる。
"""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from synology_to_immich.__main__ import main
from synology_to_immich.immich import ImmichUploadResult
from synology_to_immich.migrator import MigrationResult
from synology_to_immich.verify import VerificationResult


class TestMainCli:
    """メイン CLI のテスト"""

    def test_main_shows_help(self):
        """--help でヘルプが表示されることを確認"""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "Synology Photos" in result.output

    def test_main_shows_version(self):
        """--version でバージョンが表示されることを確認"""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestMigrateCommand:
    """migrate コマンドのテスト"""

    def test_migrate_requires_config(self):
        """--config が必須であることを確認"""
        runner = CliRunner()
        result = runner.invoke(main, ["migrate"])

        # config オプションが必須なので、エラー終了すること
        assert result.exit_code != 0
        assert "config" in result.output.lower() or "missing" in result.output.lower()

    def test_migrate_config_not_found(self):
        """設定ファイルが存在しない場合のエラー"""
        runner = CliRunner()
        result = runner.invoke(main, ["migrate", "-c", "/nonexistent/config.toml"])

        # ファイルが見つからないのでエラー終了
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "見つかりません" in result.output

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.Migrator")
    @patch("synology_to_immich.__main__.LocalFileReader")
    @patch("synology_to_immich.__main__.ImmichClient")
    @patch("synology_to_immich.__main__.ProgressTracker")
    @patch("synology_to_immich.__main__.MigrationLogger")
    def test_migrate_success(
        self,
        mock_logger_class,
        mock_tracker_class,
        mock_immich_class,
        mock_reader_class,
        mock_migrator_class,
        mock_load_config,
        tmp_path,
    ):
        """migrate コマンドが正常に実行されることを確認"""
        # 設定ファイルを作成
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        # モックの設定
        mock_config = Mock()
        mock_config.source = "/photos"
        mock_config.is_smb_source = False
        mock_config.immich_url = "http://localhost:2283"
        mock_config.immich_api_key = "test-key"
        mock_config.dry_run = False
        mock_config.batch_size = 100
        mock_config.batch_delay = 1.0
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        # Migrator の戻り値
        mock_migrator = Mock()
        mock_migrator.run.return_value = MigrationResult(
            total_files=10,
            success_count=8,
            failed_count=1,
            skipped_count=1,
            unsupported_count=0,
            elapsed_seconds=5.0,
        )
        mock_migrator_class.return_value = mock_migrator

        runner = CliRunner()
        result = runner.invoke(main, ["migrate", "-c", str(config_file)])

        assert result.exit_code == 0
        mock_migrator.run.assert_called_once()

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.Migrator")
    @patch("synology_to_immich.__main__.LocalFileReader")
    @patch("synology_to_immich.__main__.ImmichClient")
    @patch("synology_to_immich.__main__.ProgressTracker")
    @patch("synology_to_immich.__main__.MigrationLogger")
    def test_migrate_dry_run(
        self,
        mock_logger_class,
        mock_tracker_class,
        mock_immich_class,
        mock_reader_class,
        mock_migrator_class,
        mock_load_config,
        tmp_path,
    ):
        """--dry-run オプションが機能することを確認"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.source = "/photos"
        mock_config.is_smb_source = False
        mock_config.immich_url = "http://localhost:2283"
        mock_config.immich_api_key = "test-key"
        mock_config.dry_run = False  # 初期値
        mock_config.batch_size = 100
        mock_config.batch_delay = 1.0
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        mock_migrator = Mock()
        mock_migrator.run.return_value = MigrationResult(
            total_files=10,
            success_count=10,
            failed_count=0,
            skipped_count=0,
            unsupported_count=0,
            elapsed_seconds=1.0,
        )
        mock_migrator_class.return_value = mock_migrator

        runner = CliRunner()
        result = runner.invoke(main, ["migrate", "-c", str(config_file), "--dry-run"])

        assert result.exit_code == 0
        # dry_run フラグが設定されていることを確認
        assert mock_config.dry_run is True

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.Migrator")
    @patch("synology_to_immich.__main__.SmbFileReader")
    @patch("synology_to_immich.__main__.ImmichClient")
    @patch("synology_to_immich.__main__.ProgressTracker")
    @patch("synology_to_immich.__main__.MigrationLogger")
    def test_migrate_with_smb_source(
        self,
        mock_logger_class,
        mock_tracker_class,
        mock_immich_class,
        mock_reader_class,
        mock_migrator_class,
        mock_load_config,
        tmp_path,
    ):
        """SMB ソースの場合に SmbFileReader が使われることを確認"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "smb://192.168.1.1/photos"
smb_user = "user"
smb_password = "pass"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.source = "smb://192.168.1.1/photos"
        mock_config.is_smb_source = True
        mock_config.smb_user = "user"
        mock_config.smb_password = "pass"
        mock_config.immich_url = "http://localhost:2283"
        mock_config.immich_api_key = "test-key"
        mock_config.dry_run = False
        mock_config.batch_size = 100
        mock_config.batch_delay = 1.0
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        mock_migrator = Mock()
        mock_migrator.run.return_value = MigrationResult(
            total_files=5,
            success_count=5,
            failed_count=0,
            skipped_count=0,
            unsupported_count=0,
            elapsed_seconds=2.0,
        )
        mock_migrator_class.return_value = mock_migrator

        runner = CliRunner()
        result = runner.invoke(main, ["migrate", "-c", str(config_file)])

        assert result.exit_code == 0
        # SmbFileReader が使われていることを確認
        mock_reader_class.assert_called_once()


class TestVerifyCommand:
    """verify コマンドのテスト

    移行結果の検証コマンドをテストする。
    verify コマンドは verify_with_hash() を使用してハッシュ検証を行う。
    """

    def test_verify_requires_config(self):
        """--config が必須であることを確認"""
        runner = CliRunner()
        result = runner.invoke(main, ["verify"])

        # config オプションが必須なので、エラー終了すること
        assert result.exit_code != 0

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.Verifier")
    @patch("synology_to_immich.__main__.LocalFileReader")
    @patch("synology_to_immich.__main__.ImmichClient")
    @patch("synology_to_immich.__main__.ProgressTracker")
    def test_verify_success(
        self,
        mock_tracker_class,
        mock_immich_class,
        mock_reader_class,
        mock_verifier_class,
        mock_load_config,
        tmp_path,
    ):
        """verify コマンドが正常に実行されることを確認

        検証成功時に exit code 0 で終了することを確認
        """
        # 設定ファイルを作成
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        # モックの設定
        mock_config = Mock()
        mock_config.source = "/photos"
        mock_config.is_smb_source = False
        mock_config.immich_url = "http://localhost:2283"
        mock_config.immich_api_key = "test-key"
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        # Verifier の戻り値（verify_with_hash を使用）
        mock_verifier = Mock()
        mock_verifier.verify_with_hash.return_value = VerificationResult(
            local_file_count=100,
            immich_asset_count=100,
            missing_in_immich=[],
        )
        mock_verifier_class.return_value = mock_verifier

        runner = CliRunner()
        result = runner.invoke(main, ["verify", "-c", str(config_file)])

        assert result.exit_code == 0
        mock_verifier.verify_with_hash.assert_called_once()

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.Verifier")
    @patch("synology_to_immich.__main__.LocalFileReader")
    @patch("synology_to_immich.__main__.ImmichClient")
    @patch("synology_to_immich.__main__.ProgressTracker")
    def test_verify_with_missing_files(
        self,
        mock_tracker_class,
        mock_immich_class,
        mock_reader_class,
        mock_verifier_class,
        mock_load_config,
        tmp_path,
    ):
        """欠損ファイルがある場合

        検証失敗時に exit code 1 で終了することを確認
        """
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.source = "/photos"
        mock_config.is_smb_source = False
        mock_config.immich_url = "http://localhost:2283"
        mock_config.immich_api_key = "test-key"
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        # 欠損ファイルがある場合
        mock_verifier = Mock()
        mock_verifier.verify_with_hash.return_value = VerificationResult(
            local_file_count=100,
            immich_asset_count=95,
            missing_in_immich=["/photos/missing1.jpg", "/photos/missing2.jpg"],
        )
        mock_verifier_class.return_value = mock_verifier

        runner = CliRunner()
        result = runner.invoke(main, ["verify", "-c", str(config_file)])

        # 検証失敗なので exit code 1
        assert result.exit_code == 1

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.Verifier")
    @patch("synology_to_immich.__main__.LocalFileReader")
    @patch("synology_to_immich.__main__.ImmichClient")
    @patch("synology_to_immich.__main__.ProgressTracker")
    def test_verify_verbose(
        self,
        mock_tracker_class,
        mock_immich_class,
        mock_reader_class,
        mock_verifier_class,
        mock_load_config,
        tmp_path,
    ):
        """--verbose オプションのテスト

        詳細出力モードで追加情報が表示されることを確認
        """
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.source = "/photos"
        mock_config.is_smb_source = False
        mock_config.immich_url = "http://localhost:2283"
        mock_config.immich_api_key = "test-key"
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        mock_verifier = Mock()
        mock_verifier.verify_with_hash.return_value = VerificationResult(
            local_file_count=100,
            immich_asset_count=100,
            missing_in_immich=[],
        )
        mock_verifier_class.return_value = mock_verifier

        runner = CliRunner()
        result = runner.invoke(main, ["verify", "-c", str(config_file), "--verbose"])

        assert result.exit_code == 0
        # verbose モードで追加情報が出力されることを確認
        assert "100" in result.output


class TestStatusCommand:
    """status コマンドのテスト

    移行の現在の状態を表示するコマンドをテストする
    """

    def test_status_requires_config(self):
        """--config が必須であることを確認"""
        runner = CliRunner()
        result = runner.invoke(main, ["status"])

        assert result.exit_code != 0

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.ProgressTracker")
    def test_status_shows_statistics(
        self,
        mock_tracker_class,
        mock_load_config,
        tmp_path,
    ):
        """統計情報が表示されることを確認"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        mock_tracker = Mock()
        mock_tracker.get_statistics.return_value = {
            "total": 100,
            "success": 90,
            "failed": 8,
            "unsupported": 2,
        }
        mock_tracker_class.return_value = mock_tracker

        runner = CliRunner()
        result = runner.invoke(main, ["status", "-c", str(config_file)])

        assert result.exit_code == 0
        assert "100" in result.output  # total
        assert "90" in result.output  # success

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.ProgressTracker")
    def test_status_verbose_shows_failed_files(
        self,
        mock_tracker_class,
        mock_load_config,
        tmp_path,
    ):
        """--verbose で失敗ファイルが表示されることを確認"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        mock_tracker = Mock()
        mock_tracker.get_statistics.return_value = {
            "total": 10,
            "success": 8,
            "failed": 2,
            "unsupported": 0,
        }
        mock_tracker.get_files_by_status.return_value = [
            {"source_path": "/photos/failed1.jpg"},
            {"source_path": "/photos/failed2.jpg"},
        ]
        mock_tracker_class.return_value = mock_tracker

        runner = CliRunner()
        result = runner.invoke(main, ["status", "-c", str(config_file), "-v"])

        assert result.exit_code == 0
        assert "failed1.jpg" in result.output
        assert "failed2.jpg" in result.output


class TestRetryCommand:
    """retry コマンドのテスト

    失敗したファイルの再移行を試みるコマンドをテストする
    """

    def test_retry_requires_config(self):
        """--config が必須であることを確認"""
        runner = CliRunner()
        result = runner.invoke(main, ["retry"])

        assert result.exit_code != 0

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.ProgressTracker")
    @patch("synology_to_immich.__main__.ImmichClient")
    @patch("synology_to_immich.__main__.LocalFileReader")
    @patch("synology_to_immich.__main__.MigrationLogger")
    def test_retry_processes_failed_files(
        self,
        mock_logger_class,
        mock_reader_class,
        mock_immich_class,
        mock_tracker_class,
        mock_load_config,
        tmp_path,
    ):
        """失敗ファイルが再処理されることを確認"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.source = "/photos"
        mock_config.is_smb_source = False
        mock_config.immich_url = "http://localhost:2283"
        mock_config.immich_api_key = "test-key"
        mock_config.dry_run = False
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        # 失敗ファイルを2つ返す
        mock_tracker = Mock()
        mock_tracker.get_files_by_status.return_value = [
            {
                "source_path": "/photos/failed1.jpg",
                "source_size": 1000,
                "source_mtime": "2024-01-01",
            },
            {
                "source_path": "/photos/failed2.jpg",
                "source_size": 2000,
                "source_mtime": "2024-01-01",
            },
        ]
        mock_tracker_class.return_value = mock_tracker

        # リーダーのモック
        mock_reader = Mock()
        mock_reader.read_file.return_value = b"fake data"
        mock_reader_class.return_value = mock_reader

        # Immich クライアントのモック
        mock_immich = Mock()
        mock_immich.upload_asset.return_value = ImmichUploadResult(
            success=True,
            asset_id="new-asset-id",
            error_message=None,
            is_unsupported=False,
        )
        mock_immich_class.return_value = mock_immich

        runner = CliRunner()
        result = runner.invoke(main, ["retry", "-c", str(config_file)])

        assert result.exit_code == 0
        # 2回アップロードが呼ばれる
        assert mock_immich.upload_asset.call_count == 2

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.ProgressTracker")
    def test_retry_no_failed_files(
        self,
        mock_tracker_class,
        mock_load_config,
        tmp_path,
    ):
        """失敗ファイルがない場合のメッセージ"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        mock_tracker = Mock()
        mock_tracker.get_files_by_status.return_value = []
        mock_tracker_class.return_value = mock_tracker

        runner = CliRunner()
        result = runner.invoke(main, ["retry", "-c", str(config_file)])

        assert result.exit_code == 0
        assert "0" in result.output or "なし" in result.output or "no" in result.output.lower()


class TestReportCommand:
    """report コマンドのテスト

    移行結果のレポートを生成するコマンドをテストする
    """

    def test_report_requires_config(self):
        """--config が必須であることを確認"""
        runner = CliRunner()
        result = runner.invoke(main, ["report"])

        # config オプションが必須なので、エラー終了すること
        assert result.exit_code != 0

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.ProgressTracker")
    @patch("synology_to_immich.__main__.ReportGenerator")
    def test_report_generates_file(
        self,
        mock_generator_class,
        mock_tracker_class,
        mock_load_config,
        tmp_path,
    ):
        """レポートファイルが生成されることを確認"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        runner = CliRunner()
        result = runner.invoke(
            main, ["report", "-c", str(config_file), "-o", str(tmp_path / "report.md")]
        )

        assert result.exit_code == 0
        mock_generator_class.return_value.generate.assert_called_once()

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.ProgressTracker")
    @patch("synology_to_immich.__main__.ReportGenerator")
    def test_report_default_output(
        self,
        mock_generator_class,
        mock_tracker_class,
        mock_load_config,
        tmp_path,
    ):
        """デフォルトの出力ファイル名を使用"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"
"""
        )

        mock_config = Mock()
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_load_config.return_value = mock_config

        runner = CliRunner()
        result = runner.invoke(main, ["report", "-c", str(config_file)])

        assert result.exit_code == 0
        # デフォルトで migration_report.md に出力されることを確認
        mock_generator_class.return_value.generate.assert_called_once()
        call_args = mock_generator_class.return_value.generate.call_args
        assert "migration_report.md" in str(call_args)


class TestVerifyAlbumsCommand:
    """verify-albums コマンドのテスト

    アルバム単位での移行検証をテストする
    """

    def test_verify_albums_requires_config(self):
        """--config が必須であることを確認"""
        runner = CliRunner()
        result = runner.invoke(main, ["verify-albums"])

        # config オプションが必須なので、エラー終了すること
        assert result.exit_code != 0

    @patch("synology_to_immich.__main__.load_config")
    @patch("synology_to_immich.__main__.SynologyAlbumFetcher")
    @patch("synology_to_immich.__main__.ImmichClient")
    @patch("synology_to_immich.__main__.ProgressTracker")
    @patch("synology_to_immich.__main__.LocalFileReader")
    @patch("synology_to_immich.__main__.AlbumVerifier")
    def test_verify_albums_success(
        self,
        mock_verifier_class,
        mock_reader_class,
        mock_tracker_class,
        mock_immich_class,
        mock_fetcher_class,
        mock_load_config,
        tmp_path,
    ):
        """verify-albums コマンドが正常に実行されることを確認"""
        from synology_to_immich.album_verify import AlbumVerificationReport

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[source]
path = "/photos"

[immich]
url = "http://localhost:2283"
api_key = "test-key"

[synology_db]
host = "192.168.1.1"
port = 5432
user = "synofoto"
password = "password"
database = "synofoto"
"""
        )

        mock_config = Mock()
        mock_config.source = "/photos"
        mock_config.is_smb_source = False
        mock_config.immich_url = "http://localhost:2283"
        mock_config.immich_api_key = "test-key"
        mock_config.progress_db_path = tmp_path / "progress.db"
        mock_config.synology_db_host = "192.168.1.1"
        mock_config.synology_db_port = 5432
        mock_config.synology_db_user = "synofoto"
        mock_config.synology_db_password = "password"
        mock_config.synology_db_name = "synofoto"
        mock_load_config.return_value = mock_config

        # モックの verify が AlbumVerificationReport を返す
        mock_report = AlbumVerificationReport(
            timestamp="2026-02-05T12:00:00",
            total_synology_albums=10,
            total_immich_albums=12,
            matched_albums=10,
            unmatched_synology_albums=0,
            unmatched_immich_albums=2,
            album_results=[],
            synology_only=[],
            immich_only=["手動作成1", "手動作成2"],
        )
        mock_verifier_class.return_value.verify.return_value = mock_report

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["verify-albums", "-c", str(config_file), "-o", str(tmp_path / "report.json")],
        )

        assert result.exit_code == 0
        mock_verifier_class.return_value.verify.assert_called_once()
