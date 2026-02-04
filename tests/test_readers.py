"""
ファイルリーダーのテスト

ローカルファイルシステムからファイルを読み取る機能をテストする。
このモジュールは以下の機能を提供する:

- ディレクトリ内のファイルを再帰的にリストアップ
- システムファイル（@eaDir、.DS_Store など）の除外
- ファイル内容の読み取り
- ファイルメタデータ（サイズ、更新日時）の取得

TDD の流れ:
1. このテストファイルを先に書く（Red: テストは失敗する）
2. readers/base.py と readers/local.py を実装する（Green: テストが通る）
3. 必要に応じてリファクタリング（Refactor）
"""

from pathlib import Path

import pytest

# テスト対象のモジュールをインポート
# 最初は存在しないのでエラーになる（TDD の Red フェーズ）
from synology_to_immich.readers.base import FileInfo, FileReader
from synology_to_immich.readers.local import LocalFileReader


class TestFileInfo:
    """
    FileInfo データクラスのテスト

    FileInfo はファイルの情報を保持するデータクラス。
    パス、サイズ、更新日時の情報を持つ。
    """

    def test_file_info_has_required_fields(self):
        """
        FileInfo に必須フィールドが存在することを確認

        FileInfo には以下のフィールドが必要:
        - path: ファイルパス（文字列）
        - size: ファイルサイズ（バイト）
        - mtime: 更新日時（ISO 8601 形式の文字列）
        """
        # Arrange & Act: FileInfo オブジェクトを作成
        file_info = FileInfo(
            path="/photos/IMG_001.jpg",
            size=1024,
            mtime="2024-01-15T10:30:00",
        )

        # Assert: フィールドの値を確認
        assert file_info.path == "/photos/IMG_001.jpg"
        assert file_info.size == 1024
        assert file_info.mtime == "2024-01-15T10:30:00"


class TestLocalFileReader:
    """
    LocalFileReader クラスのテスト

    LocalFileReader はローカルファイルシステムからファイルを
    読み取るためのクラス。ディレクトリ内のファイルを再帰的に
    リストアップし、システムファイルを除外する。
    """

    def test_list_files(self, tmp_path: Path):
        """
        ファイルが再帰的にリストアップされることを確認

        サブディレクトリ内のファイルも含めて、すべてのファイルが
        リストアップされることをテストする。

        ディレクトリ構造:
            tmp_path/
            ├── file1.jpg
            └── subdir/
                └── file2.jpg

        Args:
            tmp_path: pytest が提供する一時ディレクトリ
        """
        # Arrange（準備）: テスト用のファイル構造を作成
        # ルートディレクトリにファイルを作成
        (tmp_path / "file1.jpg").write_bytes(b"test content 1")

        # サブディレクトリを作成してファイルを追加
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file2.jpg").write_bytes(b"test content 2")

        # Act（実行）: LocalFileReader でファイルをリストアップ
        reader = LocalFileReader(tmp_path)
        # list_files() はジェネレータなので、list() で全て取得
        files = list(reader.list_files())

        # Assert（検証）: 2つのファイルがリストアップされる
        assert len(files) == 2, "ファイル数が2件でない"

        # ファイルパスを取得（順序は不定なのでセットで比較）
        paths = {f.path for f in files}
        expected_paths = {
            str(tmp_path / "file1.jpg"),
            str(tmp_path / "subdir" / "file2.jpg"),
        }
        assert paths == expected_paths, "リストアップされたファイルパスが正しくない"

    def test_excludes_eadir(self, tmp_path: Path):
        """
        @eaDir ディレクトリが除外されることを確認

        @eaDir は Synology NAS が自動生成するメタデータディレクトリ。
        このディレクトリとその中身は移行対象から除外する必要がある。

        ディレクトリ構造:
            tmp_path/
            ├── photo.jpg
            └── @eaDir/
                └── thumbnail.jpg  <- 除外される

        Args:
            tmp_path: pytest が提供する一時ディレクトリ
        """
        # Arrange: 通常のファイルと @eaDir を作成
        (tmp_path / "photo.jpg").write_bytes(b"photo content")

        # @eaDir ディレクトリを作成（Synology のメタデータディレクトリ）
        eadir = tmp_path / "@eaDir"
        eadir.mkdir()
        (eadir / "thumbnail.jpg").write_bytes(b"thumbnail content")

        # Act: ファイルをリストアップ
        reader = LocalFileReader(tmp_path)
        files = list(reader.list_files())

        # Assert: @eaDir 内のファイルは含まれない
        assert len(files) == 1, "@eaDir が除外されていない"
        assert files[0].path == str(tmp_path / "photo.jpg"), "photo.jpg が見つからない"

    def test_excludes_system_files(self, tmp_path: Path):
        """
        システムファイル（.DS_Store、Thumbs.db）が除外されることを確認

        これらはOS が自動生成するファイルで、移行対象から除外する:
        - .DS_Store: macOS が作成するフォルダメタデータ
        - Thumbs.db: Windows が作成するサムネイルキャッシュ

        ディレクトリ構造:
            tmp_path/
            ├── photo.jpg
            ├── .DS_Store       <- 除外される
            └── Thumbs.db       <- 除外される

        Args:
            tmp_path: pytest が提供する一時ディレクトリ
        """
        # Arrange: 通常のファイルとシステムファイルを作成
        (tmp_path / "photo.jpg").write_bytes(b"photo content")
        (tmp_path / ".DS_Store").write_bytes(b"ds store content")
        (tmp_path / "Thumbs.db").write_bytes(b"thumbs db content")

        # Act: ファイルをリストアップ
        reader = LocalFileReader(tmp_path)
        files = list(reader.list_files())

        # Assert: システムファイルは含まれない
        assert len(files) == 1, "システムファイルが除外されていない"
        assert files[0].path == str(tmp_path / "photo.jpg"), "photo.jpg が見つからない"

    def test_excludes_thumbnail_directory(self, tmp_path: Path):
        """
        .thumbnail ディレクトリが除外されることを確認

        .thumbnail は Synology Photos がサムネイルを保存するディレクトリ。
        移行対象から除外する必要がある。

        ディレクトリ構造:
            tmp_path/
            ├── photo.jpg
            └── .thumbnail/
                └── thumb.jpg  <- 除外される

        Args:
            tmp_path: pytest が提供する一時ディレクトリ
        """
        # Arrange: 通常のファイルと .thumbnail ディレクトリを作成
        (tmp_path / "photo.jpg").write_bytes(b"photo content")

        thumbnail_dir = tmp_path / ".thumbnail"
        thumbnail_dir.mkdir()
        (thumbnail_dir / "thumb.jpg").write_bytes(b"thumbnail content")

        # Act: ファイルをリストアップ
        reader = LocalFileReader(tmp_path)
        files = list(reader.list_files())

        # Assert: .thumbnail 内のファイルは含まれない
        assert len(files) == 1, ".thumbnail が除外されていない"
        assert files[0].path == str(tmp_path / "photo.jpg"), "photo.jpg が見つからない"

    def test_excludes_recycle_directory(self, tmp_path: Path):
        """
        #recycle ディレクトリが除外されることを確認

        #recycle は Synology NAS のゴミ箱ディレクトリ。
        削除されたファイルが含まれるため、移行対象から除外する。

        ディレクトリ構造:
            tmp_path/
            ├── photo.jpg
            └── #recycle/
                └── deleted.jpg  <- 除外される

        Args:
            tmp_path: pytest が提供する一時ディレクトリ
        """
        # Arrange: 通常のファイルと #recycle ディレクトリを作成
        (tmp_path / "photo.jpg").write_bytes(b"photo content")

        recycle_dir = tmp_path / "#recycle"
        recycle_dir.mkdir()
        (recycle_dir / "deleted.jpg").write_bytes(b"deleted content")

        # Act: ファイルをリストアップ
        reader = LocalFileReader(tmp_path)
        files = list(reader.list_files())

        # Assert: #recycle 内のファイルは含まれない
        assert len(files) == 1, "#recycle が除外されていない"
        assert files[0].path == str(tmp_path / "photo.jpg"), "photo.jpg が見つからない"

    def test_read_file(self, tmp_path: Path):
        """
        ファイル内容を読み取れることを確認

        read_file() メソッドで、指定されたパスのファイル内容を
        バイト列として取得できることをテストする。

        Args:
            tmp_path: pytest が提供する一時ディレクトリ
        """
        # Arrange: テスト用のファイルを作成
        test_content = b"test image content"
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(test_content)

        # Act: ファイル内容を読み取る
        reader = LocalFileReader(tmp_path)
        content = reader.read_file(str(test_file))

        # Assert: 内容が正しいことを確認
        assert content == test_content, "ファイル内容が一致しない"

    def test_file_info_includes_metadata(self, tmp_path: Path):
        """
        FileInfo にサイズと更新日時が含まれることを確認

        list_files() が返す FileInfo オブジェクトには、
        ファイルサイズと更新日時（ISO 8601 形式）が含まれる。

        Args:
            tmp_path: pytest が提供する一時ディレクトリ
        """
        # Arrange: テスト用のファイルを作成
        test_content = b"test content with known size"
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(test_content)

        # Act: ファイルをリストアップ
        reader = LocalFileReader(tmp_path)
        files = list(reader.list_files())

        # Assert: メタデータが正しいことを確認
        assert len(files) == 1, "ファイル数が1件でない"
        file_info = files[0]

        # サイズの確認
        assert file_info.size == len(test_content), "ファイルサイズが正しくない"

        # 更新日時の形式を確認（ISO 8601 形式: YYYY-MM-DDTHH:MM:SS）
        # 例: "2024-01-15T10:30:00"
        assert "T" in file_info.mtime, "更新日時が ISO 8601 形式でない"
        # 年月日が含まれていることを確認
        assert len(file_info.mtime) >= 19, "更新日時の形式が不正"

    def test_get_file_info_returns_file_metadata(self, tmp_path: Path):
        """
        get_file_info() がファイルのメタデータを返すことを確認

        リトライ処理でファイルの mtime が必要だが、progress.db に記録されていない
        場合がある。そのため、パスを指定して直接ファイル情報を取得できる必要がある。

        Args:
            tmp_path: pytest が提供する一時ディレクトリ
        """
        # Arrange: テスト用のファイルを作成
        test_content = b"test content for get_file_info"
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(test_content)

        # Act: get_file_info() を呼び出す
        reader = LocalFileReader(tmp_path)
        file_info = reader.get_file_info(str(test_file))

        # Assert: FileInfo が正しい値を持つことを確認
        assert file_info.path == str(test_file)
        assert file_info.size == len(test_content)
        assert "T" in file_info.mtime  # ISO 8601 形式


class TestFileReaderAbstract:
    """
    FileReader 抽象基底クラスのテスト

    FileReader は抽象基底クラス（ABC）で、直接インスタンス化できない。
    サブクラスで list_files(), read_file(), should_exclude() を
    実装する必要がある。
    """

    def test_cannot_instantiate_abstract_class(self):
        """
        FileReader を直接インスタンス化できないことを確認

        抽象基底クラスは直接インスタンス化すると TypeError が発生する。
        これにより、必ずサブクラスで実装することを強制できる。
        """
        # Act & Assert: インスタンス化すると TypeError が発生
        with pytest.raises(TypeError):
            FileReader()  # type: ignore


# =============================================================================
# SMB URL パーサーと SmbFileReader のテスト
# =============================================================================


class TestParseSmbUrl:
    """
    SMB URL パーサーのテスト

    SMB URL を解析して、ホスト、ポート、共有名、パスに分解する機能をテストする。
    SMB URL の形式: smb://host:port/share/path/to/folder

    SMB とは:
    - Server Message Block の略
    - Windows のファイル共有プロトコル
    - Synology NAS は SMB でファイル共有を提供している
    """

    def test_parse_basic_url(self):
        """
        基本的な SMB URL をパースできることを確認

        入力: smb://192.168.1.1/share/path/to/photos
        期待される出力:
        - host: 192.168.1.1
        - port: None（デフォルト）
        - share: share
        - path: path/to/photos
        """
        # テスト対象をインポート
        from synology_to_immich.readers.smb import parse_smb_url

        # Arrange（準備）: テスト用の URL
        url = "smb://192.168.1.1/share/path/to/photos"

        # Act（実行）: URL をパース
        result = parse_smb_url(url)

        # Assert（検証）: 各フィールドが正しいことを確認
        assert result["host"] == "192.168.1.1", "ホストが正しくない"
        assert result["port"] is None, "ポートはデフォルトで None"
        assert result["share"] == "share", "共有名が正しくない"
        assert result["path"] == "path/to/photos", "パスが正しくない"

    def test_parse_url_with_port(self):
        """
        ポート番号付きの SMB URL をパースできることを確認

        入力: smb://192.168.1.1:445/share/photos
        期待される出力:
        - host: 192.168.1.1
        - port: 445（SMB のデフォルトポート）
        - share: share
        - path: photos

        Note:
            445 は SMB の標準ポート番号
        """
        from synology_to_immich.readers.smb import parse_smb_url

        # Arrange: ポート番号付きの URL
        url = "smb://192.168.1.1:445/share/photos"

        # Act: URL をパース
        result = parse_smb_url(url)

        # Assert: ポート番号が正しくパースされることを確認
        assert result["host"] == "192.168.1.1", "ホストが正しくない"
        assert result["port"] == 445, "ポート番号が正しくない"
        assert result["share"] == "share", "共有名が正しくない"
        assert result["path"] == "photos", "パスが正しくない"

    def test_parse_url_minimal(self):
        """
        最小構成の SMB URL をパースできることを確認

        入力: smb://localhost/homes
        期待される出力:
        - host: localhost
        - port: None
        - share: homes
        - path: ""（空文字、共有のルート）

        Note:
            パスがない場合は空文字列になる
        """
        from synology_to_immich.readers.smb import parse_smb_url

        # Arrange: 最小構成の URL（共有名のみ、パスなし）
        url = "smb://localhost/homes"

        # Act: URL をパース
        result = parse_smb_url(url)

        # Assert: 最小構成でも正しくパースされることを確認
        assert result["host"] == "localhost", "ホストが正しくない"
        assert result["port"] is None, "ポートは None"
        assert result["share"] == "homes", "共有名が正しくない"
        assert result["path"] == "", "パスは空文字列"


class TestSmbFileReader:
    """
    SmbFileReader クラスのテスト

    SMB（Windows ファイル共有）経由でファイルを読み取る機能をテストする。
    実際の SMB サーバーには接続せず、smbclient ライブラリをモックしてテストする。

    モックとは:
    - テスト用の偽物オブジェクト
    - 外部サービス（SMB サーバー）への依存を排除できる
    - 特定の戻り値を設定してテストできる
    """

    def test_list_files_mock(self):
        """
        smbclient.scandir をモックしてファイルリストが取得できることを確認

        実際の SMB サーバーに接続せずに、smbclient ライブラリの動作を
        モックしてテストする。

        テストシナリオ:
        1. SMB 共有に 2 つのファイルがある
        2. list_files() を呼び出す
        3. 2 つの FileInfo が返される
        """
        from unittest.mock import MagicMock, patch

        from synology_to_immich.readers.smb import SmbFileReader

        # Arrange（準備）: モックの設定

        # ファイルエントリのモックを作成
        # scandir が返すエントリオブジェクトをシミュレート
        mock_file1 = MagicMock()
        mock_file1.name = "photo1.jpg"
        mock_file1.path = r"\\192.168.1.1\share\photos\photo1.jpg"
        mock_file1.is_dir.return_value = False
        # stat() の戻り値をモック
        mock_stat1 = MagicMock()
        mock_stat1.st_size = 1024
        mock_stat1.st_mtime = 1704067200.0  # 2024-01-01 00:00:00 UTC
        mock_file1.stat.return_value = mock_stat1

        mock_file2 = MagicMock()
        mock_file2.name = "photo2.jpg"
        mock_file2.path = r"\\192.168.1.1\share\photos\photo2.jpg"
        mock_file2.is_dir.return_value = False
        mock_stat2 = MagicMock()
        mock_stat2.st_size = 2048
        mock_stat2.st_mtime = 1704153600.0  # 2024-01-02 00:00:00 UTC
        mock_file2.stat.return_value = mock_stat2

        # smbclient.scandir をモック
        # patch はコンテキストマネージャとして使用
        with patch("synology_to_immich.readers.smb.smbclient") as mock_smbclient:
            # scandir が直接イテレータを返すように設定
            mock_smbclient.scandir.return_value = iter([mock_file1, mock_file2])

            # Act（実行）: SmbFileReader でファイルをリストアップ
            reader = SmbFileReader("smb://192.168.1.1/share/photos")
            files = list(reader.list_files())

            # Assert（検証）: 2つのファイルがリストアップされる
            assert len(files) == 2, "ファイル数が2件でない"

            # ファイルパスを確認
            paths = {f.path for f in files}
            expected_paths = {
                r"\\192.168.1.1\share\photos\photo1.jpg",
                r"\\192.168.1.1\share\photos\photo2.jpg",
            }
            assert paths == expected_paths, "ファイルパスが正しくない"

    def test_excludes_eadir_in_smb(self):
        """
        SMB 経由でも @eaDir ディレクトリが除外されることを確認

        LocalFileReader と同様に、Synology のメタデータディレクトリは
        除外される必要がある。
        """
        from unittest.mock import MagicMock, patch

        from synology_to_immich.readers.smb import SmbFileReader

        # Arrange: @eaDir 内のファイルを含むモックを作成
        mock_photo = MagicMock()
        mock_photo.name = "photo.jpg"
        mock_photo.path = r"\\192.168.1.1\share\photo.jpg"
        mock_photo.is_dir.return_value = False
        mock_stat = MagicMock()
        mock_stat.st_size = 1024
        mock_stat.st_mtime = 1704067200.0
        mock_photo.stat.return_value = mock_stat

        # @eaDir 内のファイル（除外対象）
        mock_eadir_file = MagicMock()
        mock_eadir_file.name = "thumb.jpg"
        mock_eadir_file.path = r"\\192.168.1.1\share\@eaDir\thumb.jpg"
        mock_eadir_file.is_dir.return_value = False

        with patch("synology_to_immich.readers.smb.smbclient") as mock_smbclient:
            # scandir が直接イテレータを返すように設定
            mock_smbclient.scandir.return_value = iter([mock_photo, mock_eadir_file])

            # Act: ファイルをリストアップ
            reader = SmbFileReader("smb://192.168.1.1/share")
            files = list(reader.list_files())

            # Assert: @eaDir 内のファイルは除外される
            assert len(files) == 1, "@eaDir が除外されていない"
            assert "photo.jpg" in files[0].path, "photo.jpg が見つからない"

    def test_read_file_mock(self):
        """
        smbclient.open_file をモックしてファイル内容を読み取れることを確認
        """
        from unittest.mock import MagicMock, patch

        from synology_to_immich.readers.smb import SmbFileReader

        # Arrange: open_file のモックを設定
        test_content = b"test image content"

        with patch("synology_to_immich.readers.smb.smbclient") as mock_smbclient:
            # open_file がコンテキストマネージャとして動作するようにモック
            mock_file = MagicMock()
            mock_file.read.return_value = test_content
            mock_smbclient.open_file.return_value.__enter__.return_value = mock_file

            # Act: ファイル内容を読み取る
            reader = SmbFileReader("smb://192.168.1.1/share/photos")
            content = reader.read_file(r"\\192.168.1.1\share\photos\test.jpg")

            # Assert: 内容が正しいことを確認
            assert content == test_content, "ファイル内容が一致しない"

    def test_registers_session_with_credentials(self):
        """
        認証情報が提供された場合、smbclient.register_session が呼ばれることを確認

        SMB サーバーに接続するには認証が必要な場合がある。
        ユーザー名とパスワードが提供された場合、セッションを登録する。
        """
        from unittest.mock import patch

        from synology_to_immich.readers.smb import SmbFileReader

        with patch("synology_to_immich.readers.smb.smbclient") as mock_smbclient:
            # Act: 認証情報付きで SmbFileReader を作成
            SmbFileReader(
                "smb://192.168.1.1/share/photos",
                username="testuser",
                password="testpass",
            )

            # Assert: register_session が正しい引数で呼ばれることを確認
            # port が指定されていない場合は port パラメータを渡さない
            mock_smbclient.register_session.assert_called_once_with(
                "192.168.1.1", username="testuser", password="testpass"
            )

    def test_get_file_info_returns_file_metadata(self):
        """
        get_file_info() がファイルのメタデータを返すことを確認

        リトライ処理でファイルの mtime が必要だが、progress.db に記録されていない
        場合がある。そのため、パスを指定して直接ファイル情報を取得できる必要がある。

        戻り値:
            FileInfo: path, size, mtime を含むオブジェクト
        """
        from unittest.mock import MagicMock, patch

        from synology_to_immich.readers.smb import SmbFileReader

        # Arrange: stat() のモックを設定
        with patch("synology_to_immich.readers.smb.smbclient") as mock_smbclient:
            mock_stat = MagicMock()
            mock_stat.st_size = 4096
            mock_stat.st_mtime = 1704067200.0  # 2024-01-01 00:00:00 UTC
            mock_smbclient.stat.return_value = mock_stat

            # Act: get_file_info() を呼び出す
            reader = SmbFileReader("smb://192.168.1.1/share/photos")
            file_info = reader.get_file_info(r"\\192.168.1.1\share\photos\test.jpg")

            # Assert: FileInfo が正しい値を持つことを確認
            assert file_info.path == r"\\192.168.1.1\share\photos\test.jpg"
            assert file_info.size == 4096
            assert "2024-01-01" in file_info.mtime  # ISO 8601 形式の日付を含む
