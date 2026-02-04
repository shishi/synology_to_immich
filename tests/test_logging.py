"""
ログシステム（MigrationLogger）のテスト

移行ツールのログ出力機能をテストする。
このモジュールは以下のログファイルを管理する:
- migration_*.log: すべてのログ（DEBUG以上）
- errors_*.log: エラーログのみ
- unsupported_*.log: 未対応ファイルの詳細ログ
"""

from pathlib import Path

# テスト対象のモジュールをインポート
from synology_to_immich.logging import MigrationLogger


class TestMigrationLogger:
    """
    MigrationLogger クラスのテスト

    MigrationLogger は複数のログファイルに出力するロガーで、
    移行の進捗やエラー、未対応ファイルを記録する。
    """

    def test_creates_log_files(self, tmp_path: Path):
        """
        ログファイルが正しく作成されることを確認

        MigrationLogger を初期化すると、3つのログファイルが
        作成されることを確認する:
        - migration_*.log: 全ログ
        - errors_*.log: エラーログ
        - unsupported_*.log: 未対応ファイルログ
        """
        # Arrange（準備）: ログディレクトリのパスを設定
        log_dir = tmp_path / "logs"

        # Act（実行）: MigrationLogger を初期化
        logger = MigrationLogger(log_dir)

        # Assert（検証）: ディレクトリが作成されたことを確認
        assert log_dir.exists(), "ログディレクトリが作成されていない"

        # Assert: 3つのログファイルが作成されたことを確認
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) == 3, f"ログファイルが3つでない（{len(log_files)}個）"

        # Assert: 各ログファイルの種類を確認
        file_names = [f.name for f in log_files]
        assert any("migration_" in name for name in file_names), "migration_*.log が見つからない"
        assert any("errors_" in name for name in file_names), "errors_*.log が見つからない"
        assert any(
            "unsupported_" in name for name in file_names
        ), "unsupported_*.log が見つからない"

        # クリーンアップ
        logger.close()

    def test_logs_unsupported_format(self, tmp_path: Path):
        """
        未対応形式のログが正しく出力されることを確認

        log_unsupported() メソッドは、Immich が対応していない
        ファイル形式を検出した際に詳細情報を記録する。
        ログにはファイルパスとサイズが含まれることを確認する。
        """
        # Arrange（準備）: ロガーを初期化
        log_dir = tmp_path / "logs"
        logger = MigrationLogger(log_dir)

        # Act（実行）: 未対応ファイルをログに記録
        logger.log_unsupported(
            file_path="/photos/test.xyz",  # 未対応のファイルパス
            file_size=1024,  # 1 KB
            mime_type="application/octet-stream",  # MIMEタイプ
            error_message="Unsupported file type",  # エラーメッセージ
        )

        # ログファイルを閉じてフラッシュ
        logger.close()

        # Assert（検証）: unsupported_*.log の内容を確認
        unsupported_files = list(log_dir.glob("unsupported_*.log"))
        assert len(unsupported_files) == 1, "unsupported_*.log が見つからない"

        # ログファイルの内容を読み取る
        content = unsupported_files[0].read_text()

        # ファイルパスが含まれることを確認
        assert "/photos/test.xyz" in content, "ファイルパスがログに含まれていない"

        # サイズ（人間が読める形式）が含まれることを確認
        assert "1.0 KB" in content, "ファイルサイズがログに含まれていない"

    def test_logs_error(self, tmp_path: Path):
        """
        エラーログが正しく出力されることを確認

        error() メソッドは、エラーメッセージを errors_*.log に
        出力する。ログにはメッセージと file_path が含まれることを確認。
        """
        # Arrange（準備）: ロガーを初期化
        log_dir = tmp_path / "logs"
        logger = MigrationLogger(log_dir)

        # Act（実行）: エラーをログに記録
        logger.error(
            "Upload failed",  # エラーメッセージ
            file_path="/photos/broken.jpg",  # 関連するファイルパス
        )

        # ログファイルを閉じてフラッシュ
        logger.close()

        # Assert（検証）: errors_*.log の内容を確認
        error_files = list(log_dir.glob("errors_*.log"))
        assert len(error_files) == 1, "errors_*.log が見つからない"

        # ログファイルの内容を読み取る
        content = error_files[0].read_text()

        # エラーメッセージが含まれることを確認
        assert "Upload failed" in content, "エラーメッセージがログに含まれていない"

        # ファイルパスが含まれることを確認
        assert "/photos/broken.jpg" in content, "file_path がログに含まれていない"
