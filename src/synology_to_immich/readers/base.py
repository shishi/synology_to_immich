"""
ファイルリーダーの抽象基底クラス

このモジュールは、ファイルを読み取るための抽象インターフェースを定義する。
LocalFileReader や SmbFileReader など、具体的な実装はこの基底クラスを
継承して作成する。

抽象基底クラス（ABC）とは:
- 直接インスタンス化できないクラス
- サブクラスで必ず実装すべきメソッドを定義する
- インターフェースとして機能し、異なる実装を統一的に扱える

デザインパターン:
このモジュールは「ストラテジーパターン」を採用している。
ファイルの読み取り方法（ローカル、SMB、将来的にはクラウドなど）を
抽象化し、切り替え可能にしている。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass
class FileInfo:
    """
    ファイル情報を保持するデータクラス

    ファイルのパス、サイズ、更新日時を格納する。
    dataclass デコレータにより、__init__() や __repr__() が
    自動生成される。

    Attributes:
        path: ファイルの完全パス（文字列）
              例: "/home/user/photos/IMG_001.jpg"
        size: ファイルサイズ（バイト単位の整数）
              例: 1024 (1KB)
        mtime: 更新日時（ISO 8601 形式の文字列）
               例: "2024-01-15T10:30:00"

    使用例:
        # FileInfo オブジェクトの作成
        file_info = FileInfo(
            path="/photos/IMG_001.jpg",
            size=1024000,
            mtime="2024-01-15T10:30:00"
        )

        # 属性へのアクセス
        print(f"ファイル: {file_info.path}")
        print(f"サイズ: {file_info.size} バイト")
        print(f"更新日時: {file_info.mtime}")
    """

    path: str  # ファイルの完全パス
    size: int  # ファイルサイズ（バイト）
    mtime: str  # 更新日時（ISO 8601 形式）


class FileReader(ABC):
    """
    ファイルリーダーの抽象基底クラス

    ファイルのリストアップと読み取りを行うインターフェースを定義する。
    このクラスは直接インスタンス化できない。必ずサブクラスで
    抽象メソッドを実装する必要がある。

    ABC（Abstract Base Class）を継承する理由:
    - @abstractmethod デコレータを使って抽象メソッドを定義できる
    - 抽象メソッドを実装せずにインスタンス化すると TypeError になる
    - 型ヒントで FileReader 型を指定すると、どの実装でも受け入れられる

    サブクラスで実装が必要なメソッド:
    - list_files(): ファイルを再帰的にリストアップ
    - read_file(path): ファイル内容を読み取り
    - should_exclude(path): 除外判定

    使用例:
        # LocalFileReader は FileReader を継承している
        reader: FileReader = LocalFileReader(Path("/photos"))

        # どの実装でも同じインターフェースで使える
        for file_info in reader.list_files():
            content = reader.read_file(file_info.path)
    """

    @abstractmethod
    def list_files(self) -> Iterator[FileInfo]:
        """
        ファイルを再帰的にリストアップする

        base_path 配下のすべてのファイルを再帰的に走査し、
        FileInfo オブジェクトを yield する。ディレクトリは含まない。
        should_exclude() が True を返すパスは除外される。

        Returns:
            Iterator[FileInfo]: FileInfo オブジェクトのイテレータ
                                ジェネレータとして実装することで、
                                大量のファイルでもメモリ効率が良い

        使用例:
            for file_info in reader.list_files():
                print(f"Found: {file_info.path}")

        Note:
            - Iterator（イテレータ）はジェネレータを含む
            - yield を使うとジェネレータになる
            - ジェネレータは遅延評価され、必要になるまで処理しない
        """
        pass  # pragma: no cover（カバレッジから除外）

    @abstractmethod
    def read_file(self, path: str) -> bytes:
        """
        ファイル内容を読み取る

        指定されたパスのファイルをバイト列として読み取る。
        画像ファイルなどのバイナリファイルを扱うため、
        bytes 型で返す。

        Args:
            path: 読み取るファイルのパス（文字列）
                  list_files() が返す FileInfo.path と同じ形式

        Returns:
            bytes: ファイルの内容（バイト列）

        Raises:
            FileNotFoundError: ファイルが存在しない場合
            PermissionError: ファイルを読み取る権限がない場合

        使用例:
            content = reader.read_file("/photos/IMG_001.jpg")
            print(f"Read {len(content)} bytes")
        """
        pass  # pragma: no cover

    @abstractmethod
    def should_exclude(self, path: str) -> bool:
        """
        パスを除外すべきかどうかを判定する

        Synology Photos のシステムディレクトリや、OS が生成する
        メタデータファイルを除外するために使用する。

        除外対象の例:
        - @eaDir: Synology のメタデータディレクトリ
        - .DS_Store: macOS のフォルダメタデータ
        - Thumbs.db: Windows のサムネイルキャッシュ
        - .thumbnail: Synology のサムネイルディレクトリ
        - #recycle: Synology のゴミ箱

        Args:
            path: チェックするパス（文字列）

        Returns:
            bool: True なら除外する、False なら含める

        使用例:
            if reader.should_exclude("/photos/@eaDir/thumb.jpg"):
                print("このファイルは除外されます")
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_file_info(self, path: str) -> FileInfo:
        """
        指定されたパスのファイル情報を取得する

        リトライ処理など、特定のファイルのメタデータ（サイズ、更新日時）が
        必要な場合に使用する。list_files() とは異なり、単一ファイルの
        情報のみを取得する。

        Args:
            path: ファイルのパス（文字列）
                  list_files() が返す FileInfo.path と同じ形式

        Returns:
            FileInfo: ファイル情報（path, size, mtime を含む）

        Raises:
            FileNotFoundError: ファイルが存在しない場合

        使用例:
            file_info = reader.get_file_info("/photos/IMG_001.jpg")
            print(f"Size: {file_info.size}, Modified: {file_info.mtime}")
        """
        pass  # pragma: no cover
