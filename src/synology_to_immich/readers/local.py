"""
ローカルファイルシステム用のファイルリーダー

このモジュールは、ローカルファイルシステムからファイルを読み取る
LocalFileReader クラスを提供する。Synology NAS を直接マウント
している場合や、ローカルにコピーした写真を移行する場合に使用する。

主な機能:
- ディレクトリ内のファイルを再帰的にリストアップ
- システムファイルや不要なディレクトリの除外
- ファイル内容の読み取り
- ファイルメタデータ（サイズ、更新日時）の取得

使用例:
    from pathlib import Path
    from synology_to_immich.readers.local import LocalFileReader

    # リーダーを初期化
    reader = LocalFileReader(Path("/mnt/photos"))

    # ファイルをリストアップ
    for file_info in reader.list_files():
        print(f"Found: {file_info.path} ({file_info.size} bytes)")

        # ファイル内容を読み取る
        content = reader.read_file(file_info.path)
"""

from datetime import datetime
from pathlib import Path
from typing import Iterator

from synology_to_immich.readers.base import FileInfo, FileReader


class LocalFileReader(FileReader):
    """
    ローカルファイルシステム用のファイルリーダー

    FileReader 抽象基底クラスを継承し、ローカルファイルシステムに
    特化した実装を提供する。

    除外されるパターン:
    - @eaDir: Synology のメタデータディレクトリ
    - .DS_Store: macOS のフォルダメタデータファイル
    - Thumbs.db: Windows のサムネイルキャッシュファイル
    - .thumbnail: Synology のサムネイルディレクトリ
    - #recycle: Synology のゴミ箱

    Attributes:
        base_path: 読み取り対象のベースディレクトリ（Path オブジェクト）

    使用例:
        reader = LocalFileReader(Path("/mnt/photos"))
        for file_info in reader.list_files():
            print(f"Found: {file_info.path}")
    """

    # 除外するディレクトリ名のセット
    # set を使う理由: in 演算子での検索が O(1) で高速
    # frozenset を使う理由: イミュータブル（変更不可）でクラス変数に適切
    EXCLUDED_DIRS: frozenset[str] = frozenset(
        {
            "@eaDir",  # Synology のメタデータディレクトリ
            ".thumbnail",  # Synology のサムネイルディレクトリ
            "#recycle",  # Synology のゴミ箱
        }
    )

    # 除外するファイル名のセット
    EXCLUDED_FILES: frozenset[str] = frozenset(
        {
            ".DS_Store",  # macOS のフォルダメタデータ
            "Thumbs.db",  # Windows のサムネイルキャッシュ
        }
    )

    def __init__(self, base_path: Path) -> None:
        """
        LocalFileReader を初期化する

        Args:
            base_path: 読み取り対象のベースディレクトリ
                       Path オブジェクトまたは文字列で指定可能

        使用例:
            # Path オブジェクトで指定
            reader = LocalFileReader(Path("/mnt/photos"))

            # 文字列でも可（Path に自動変換される）
            reader = LocalFileReader("/mnt/photos")
        """
        # Path オブジェクトとして保存
        # 文字列が渡された場合は Path に変換される
        self.base_path = Path(base_path)

    def list_files(self) -> Iterator[FileInfo]:
        """
        ファイルを再帰的にリストアップする

        base_path 配下のすべてのファイルを再帰的に走査し、
        FileInfo オブジェクトを yield する。除外対象のディレクトリや
        ファイルはスキップされる。

        Returns:
            Iterator[FileInfo]: FileInfo オブジェクトのイテレータ

        Note:
            - yield を使っているのでジェネレータとして動作する
            - 大量のファイルがあってもメモリを消費しない
            - rglob("*") は再帰的に全ファイル/ディレクトリを走査する
        """
        # rglob("*") は再帰的にすべてのファイルとディレクトリを返す
        # "**/*" と同等だが、rglob の方が簡潔
        for path in self.base_path.rglob("*"):
            # ディレクトリはスキップ（ファイルのみを対象）
            # is_file() は通常ファイルかどうかをチェック
            if not path.is_file():
                continue

            # 除外対象かどうかをチェック
            if self.should_exclude(str(path)):
                continue

            # ファイル情報を取得して yield
            # yield することでジェネレータになる
            yield self._create_file_info(path)

    def read_file(self, path: str) -> bytes:
        """
        ファイル内容を読み取る

        Args:
            path: 読み取るファイルのパス（文字列）

        Returns:
            bytes: ファイルの内容（バイト列）

        Raises:
            FileNotFoundError: ファイルが存在しない場合
        """
        # Path オブジェクトに変換してバイナリモードで読み取り
        # read_bytes() はファイル全体をバイト列として返す
        return Path(path).read_bytes()

    def should_exclude(self, path: str) -> bool:
        """
        パスを除外すべきかどうかを判定する

        パスに除外対象のディレクトリ名やファイル名が含まれているか
        チェックする。パスの各部分（親ディレクトリ、ファイル名）を
        順番に確認する。

        Args:
            path: チェックするパス（文字列）

        Returns:
            bool: True なら除外する、False なら含める

        判定ロジック:
        1. パスを Path オブジェクトに変換
        2. パスの各部分（parts）をチェック
        3. 除外ディレクトリ名が含まれていたら True
        4. ファイル名が除外ファイル名に一致したら True
        5. いずれにも該当しなければ False
        """
        # Path オブジェクトに変換
        path_obj = Path(path)

        # パスの各部分をチェック
        # parts は ("home", "user", "photos", "@eaDir", "thumb.jpg") のようなタプル
        for part in path_obj.parts:
            # 除外ディレクトリに一致するかチェック
            if part in self.EXCLUDED_DIRS:
                return True

        # ファイル名を取得してチェック
        # name はパスの最後の部分（ファイル名）を返す
        filename = path_obj.name
        if filename in self.EXCLUDED_FILES:
            return True

        # 除外対象ではない
        return False

    def _create_file_info(self, path: Path) -> FileInfo:
        """
        Path オブジェクトから FileInfo を作成する

        ファイルのサイズと更新日時を取得し、FileInfo オブジェクトを
        作成して返す。

        Args:
            path: ファイルの Path オブジェクト

        Returns:
            FileInfo: ファイル情報を格納したオブジェクト

        Note:
            メソッド名がアンダースコアで始まる（_create_file_info）のは、
            このメソッドがクラス内部でのみ使用される「プライベート」
            メソッドであることを示す Python の慣習。
        """
        # stat() でファイルの情報を取得
        # stat_result には st_size（サイズ）、st_mtime（更新時刻）などが含まれる
        stat = path.stat()

        # サイズを取得（バイト単位）
        size = stat.st_size

        # 更新日時を ISO 8601 形式に変換
        # st_mtime は Unix タイムスタンプ（1970年1月1日からの秒数）
        # fromtimestamp() で datetime オブジェクトに変換
        # isoformat() で "2024-01-15T10:30:00" 形式の文字列に変換
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()

        # FileInfo オブジェクトを作成して返す
        # str(path) で Path オブジェクトを文字列に変換
        return FileInfo(
            path=str(path),
            size=size,
            mtime=mtime,
        )

    def get_file_info(self, path: str) -> FileInfo:
        """
        指定されたパスのファイル情報を取得する

        リトライ処理など、特定のファイルのメタデータが必要な場合に使用する。

        Args:
            path: ファイルのパス（文字列）

        Returns:
            FileInfo: ファイル情報（path, size, mtime を含む）

        Raises:
            FileNotFoundError: ファイルが存在しない場合
        """
        # 文字列を Path オブジェクトに変換して _create_file_info を再利用
        return self._create_file_info(Path(path))
