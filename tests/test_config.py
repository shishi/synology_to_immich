"""
設定ファイル読み込みのテスト

config.toml からの設定読み込みと、コマンドライン引数のマージをテストする。

TDD の流れ:
1. このテストファイルを先に書く（Red: テストは失敗する）
2. config.py を実装する（Green: テストが通る）
3. 必要に応じてリファクタリング（Refactor）
"""

from pathlib import Path

import pytest

# このインポートは最初は失敗する（config.py がまだ実装されていないため）
# これが TDD の「Red」フェーズ
from synology_to_immich.config import Config, load_config


class TestConfig:
    """
    Config クラスのテスト

    Config クラスは設定値を保持するデータクラス。
    必須フィールドとオプションフィールド（デフォルト値あり）を持つ。
    """

    def test_config_has_required_fields(self):
        """
        設定に必須フィールドが存在することを確認

        Config クラスには以下の必須フィールドがある:
        - source: 移行元のパス（SMB URL またはローカルパス）
        - immich_url: Immich サーバーの URL
        - immich_api_key: Immich API キー
        """
        # Arrange & Act（準備と実行）
        # Config オブジェクトを必須フィールドのみで作成
        config = Config(
            source="smb://localhost/share",
            immich_url="http://localhost:2283",
            immich_api_key="test-key",
        )

        # Assert（検証）
        # 設定した値が正しく保持されていることを確認
        assert config.source == "smb://localhost/share"
        assert config.immich_url == "http://localhost:2283"
        assert config.immich_api_key == "test-key"

    def test_config_default_values(self):
        """
        デフォルト値が正しく設定されることを確認

        オプションフィールドには以下のデフォルト値がある:
        - dry_run: False（実際にアップロードを行う）
        - batch_size: 100（一度に100ファイルを処理）
        - batch_delay: 1.0（バッチ間に1秒待機）
        - smb_user: None（SMB認証なし）
        - smb_password: None（SMB認証なし）
        """
        # Arrange & Act
        # 必須フィールドのみ指定し、オプションフィールドはデフォルト値を使用
        config = Config(
            source="/path/to/photos",
            immich_url="http://localhost:2283",
            immich_api_key="test-key",
        )

        # Assert
        # デフォルト値が正しく設定されていることを確認
        assert config.dry_run is False  # デフォルトは実際にアップロードする
        assert config.batch_size == 100  # デフォルトは100ファイルずつ
        assert config.batch_delay == 1.0  # デフォルトは1秒待機
        assert config.smb_user is None  # SMBユーザーは未設定
        assert config.smb_password is None  # SMBパスワードは未設定

    def test_config_detects_smb_source(self):
        """
        SMB URL を正しく検出できることを確認

        is_smb_source プロパティは:
        - source が "smb://" で始まる場合: True
        - それ以外（ローカルパスなど）: False
        """
        # Arrange（準備）
        # SMB URL を使用する設定
        smb_config = Config(
            source="smb://192.168.1.1/photos",
            immich_url="http://localhost:2283",
            immich_api_key="test-key",
        )
        # ローカルパスを使用する設定
        local_config = Config(
            source="/mnt/photos",
            immich_url="http://localhost:2283",
            immich_api_key="test-key",
        )

        # Act & Assert（実行と検証を同時に）
        assert smb_config.is_smb_source is True  # SMB URL なので True
        assert local_config.is_smb_source is False  # ローカルパスなので False


class TestLoadConfig:
    """
    設定ファイル読み込みのテスト

    load_config 関数は TOML ファイルから設定を読み込み、
    Config オブジェクトを返す。
    """

    def test_load_config_from_toml(self, tmp_path: Path):
        """
        TOML ファイルから設定を読み込めることを確認

        tmp_path は pytest が提供する一時ディレクトリ。
        テスト終了後に自動的に削除される。

        Args:
            tmp_path: pytest が提供する一時ディレクトリ（fixture）
        """
        # Arrange（準備）
        # 一時ディレクトリにテスト用の設定ファイルを作成
        config_file = tmp_path / "config.toml"
        # TOML 形式で設定を書き込む
        config_file.write_text(
            """
[source]
path = "smb://192.168.1.1/homes/user/Photo"
smb_user = "testuser"

[immich]
url = "http://localhost:2283"
api_key = "my-api-key"

[migration]
dry_run = true
batch_size = 50
"""
        )

        # Act（実行）
        # 設定ファイルを読み込む
        config = load_config(config_file)

        # Assert（検証）
        # TOML ファイルの値が正しく読み込まれていることを確認
        assert config.source == "smb://192.168.1.1/homes/user/Photo"
        assert config.smb_user == "testuser"
        assert config.immich_url == "http://localhost:2283"
        assert config.immich_api_key == "my-api-key"
        assert config.dry_run is True
        assert config.batch_size == 50

    def test_load_config_file_not_found(self, tmp_path: Path):
        """
        存在しない設定ファイルでエラーになることを確認

        FileNotFoundError が発生することを期待する。

        Args:
            tmp_path: pytest が提供する一時ディレクトリ（fixture）
        """
        # Arrange（準備）
        # 存在しないファイルのパス
        config_file = tmp_path / "nonexistent.toml"

        # Act & Assert（実行と検証）
        # pytest.raises を使って例外の発生を確認
        with pytest.raises(FileNotFoundError):
            load_config(config_file)
