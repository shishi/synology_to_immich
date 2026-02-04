"""
SMB 共有用のファイルリーダー

このモジュールは、SMB（Windows ファイル共有）経由でファイルを読み取る
SmbFileReader クラスを提供する。Synology NAS の SMB 共有にリモート接続
する場合に使用する。

SMB（Server Message Block）とは:
- Windows で標準的に使用されるファイル共有プロトコル
- Synology NAS は SMB でファイル共有を提供している
- ネットワーク経由でファイルを読み書きできる

主な機能:
- SMB URL のパース（smb://host:port/share/path 形式）
- 認証付きの SMB 接続
- ディレクトリ内のファイルを再帰的にリストアップ
- システムファイルや不要なディレクトリの除外
- ファイル内容の読み取り

依存ライブラリ:
- smbprotocol: Python 用の SMB クライアントライブラリ
- smbclient: smbprotocol のハイレベル API

使用例:
    from synology_to_immich.readers.smb import SmbFileReader

    # 認証なしで接続（ゲストアクセス）
    reader = SmbFileReader("smb://192.168.1.1/photo/photos")

    # 認証付きで接続
    reader = SmbFileReader(
        "smb://192.168.1.1/photo/photos",
        username="admin",
        password="secret"
    )

    # ファイルをリストアップ
    for file_info in reader.list_files():
        print(f"Found: {file_info.path} ({file_info.size} bytes)")
        content = reader.read_file(file_info.path)
"""

from datetime import datetime
from typing import Any, Iterator
from urllib.parse import urlparse

import smbclient  # type: ignore[import-untyped]

from synology_to_immich.readers.base import FileInfo, FileReader


def parse_smb_url(url: str) -> dict[str, Any]:
    """
    SMB URL をパースして各部分を辞書として返す

    SMB URL の形式:
        smb://host:port/share/path/to/folder

    各部分の意味:
    - host: SMB サーバーのホスト名または IP アドレス
    - port: ポート番号（省略時は None、通常は 445）
    - share: 共有名（SMB 共有の名前）
    - path: 共有内のパス（省略時は空文字列）

    Args:
        url: SMB URL 文字列
             例: "smb://192.168.1.1:445/photo/album/2024"

    Returns:
        dict: パース結果を含む辞書
            - host (str): ホスト名または IP アドレス
            - port (int | None): ポート番号またはNone
            - share (str): 共有名
            - path (str): 共有内のパス（ルートの場合は空文字列）

    使用例:
        >>> result = parse_smb_url("smb://192.168.1.1/photo/album")
        >>> print(result)
        {'host': '192.168.1.1', 'port': None, 'share': 'photo', 'path': 'album'}

    Note:
        urlparse は Python 標準ライブラリの URL パーサー。
        smb:// スキーム以外の URL も技術的にはパースできるが、
        この関数は SMB URL を前提としている。
    """
    # urlparse で URL をパース
    # ParseResult オブジェクトが返される
    # 例: ParseResult(scheme='smb', netloc='192.168.1.1:445', path='/photo/album')
    parsed = urlparse(url)

    # ホスト名を取得（hostname はポート番号を除いた部分）
    host = parsed.hostname or ""

    # ポート番号を取得（省略時は None）
    port = parsed.port

    # パスから共有名とサブパスを分離
    # parsed.path は "/share/path/to/folder" のような形式
    # "/" で分割して先頭の空文字を除去
    path_parts = parsed.path.strip("/").split("/")

    # 最初の部分が共有名
    share = path_parts[0] if path_parts else ""

    # 残りがサブパス（共有内のパス）
    # 例: ["photo", "album", "2024"] -> "album/2024"
    sub_path = "/".join(path_parts[1:]) if len(path_parts) > 1 else ""

    return {
        "host": host,
        "port": port,
        "share": share,
        "path": sub_path,
    }


class SmbFileReader(FileReader):
    """
    SMB 共有用のファイルリーダー

    FileReader 抽象基底クラスを継承し、SMB（Windows ファイル共有）に
    特化した実装を提供する。smbclient ライブラリを使用して SMB 共有に
    接続し、ファイルの読み取りを行う。

    除外されるパターン（LocalFileReader と同じ）:
    - @eaDir: Synology のメタデータディレクトリ
    - .DS_Store: macOS のフォルダメタデータファイル
    - Thumbs.db: Windows のサムネイルキャッシュファイル
    - .thumbnail: Synology のサムネイルディレクトリ
    - #recycle: Synology のゴミ箱

    Attributes:
        host: SMB サーバーのホスト名または IP アドレス
        port: SMB ポート番号（None の場合はデフォルト）
        share: SMB 共有名
        base_path: 共有内のベースパス
        smb_base_path: UNC 形式のベースパス（\\\\host\\share\\path）

    UNC（Universal Naming Convention）パスとは:
        Windows で使用されるネットワークパスの形式
        形式: ``\\\\server\\share\\path\\to\\file``
        Python では ``\\`` を ``\\\\`` と書く必要がある（エスケープ）

    使用例:
        # 基本的な使い方
        reader = SmbFileReader("smb://192.168.1.1/photo/photos")
        for file_info in reader.list_files():
            print(f"Found: {file_info.path}")

        # 認証付き
        reader = SmbFileReader(
            "smb://nas.local/photo",
            username="admin",
            password="secret"
        )
    """

    # 除外するディレクトリ名のセット（LocalFileReader と同じ）
    # frozenset を使う理由: イミュータブル（変更不可）でクラス変数に適切
    EXCLUDED_DIRS: frozenset[str] = frozenset(
        {
            "@eaDir",  # Synology のメタデータディレクトリ
            ".thumbnail",  # Synology のサムネイルディレクトリ
            "#recycle",  # Synology のゴミ箱
        }
    )

    # 除外するファイル名のセット（LocalFileReader と同じ）
    EXCLUDED_FILES: frozenset[str] = frozenset(
        {
            ".DS_Store",  # macOS のフォルダメタデータ
            "Thumbs.db",  # Windows のサムネイルキャッシュ
        }
    )

    def __init__(
        self,
        smb_url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """
        SmbFileReader を初期化する

        SMB URL をパースしてサーバー情報を取得し、認証情報が提供
        された場合は SMB セッションを登録する。

        Args:
            smb_url: SMB URL 文字列
                     形式: smb://host:port/share/path
                     例: "smb://192.168.1.1/photo/photos"
            username: 認証用ユーザー名（省略可、ゲストアクセスの場合は None）
            password: 認証用パスワード（省略可、ゲストアクセスの場合は None）

        Note:
            smbclient.register_session() は SMB サーバーへの接続情報を
            グローバルに登録する。一度登録すると、同じホストへの接続で
            再利用される。
        """
        # SMB URL をパース
        parsed = parse_smb_url(smb_url)

        # パース結果を保存
        self.host: str = parsed["host"]
        self.port: int | None = parsed["port"]
        self.share: str = parsed["share"]
        self.base_path: str = parsed["path"]

        # UNC 形式のベースパスを構築
        # 形式: \\\\host\\share\\path
        # 例: \\\\192.168.1.1\\photo\\photos
        # パス内の / を \\ に変換する
        if self.base_path:
            # パス内のスラッシュをバックスラッシュに変換
            normalized_path = self.base_path.replace("/", "\\")
            self.smb_base_path = f"\\\\{self.host}\\{self.share}\\{normalized_path}"
        else:
            self.smb_base_path = f"\\\\{self.host}\\{self.share}"

        # 認証情報が提供された場合、セッションを登録
        # これにより、後続の smbclient 操作で認証が自動的に使用される
        if username is not None or password is not None:
            # register_session のキーワード引数を構築
            session_kwargs: dict = {
                "username": username,
                "password": password,
            }
            # ポートが指定されている場合のみ追加（None だとエラーになる）
            if self.port is not None:
                session_kwargs["port"] = self.port

            smbclient.register_session(self.host, **session_kwargs)

    def list_files(self) -> Iterator[FileInfo]:
        """
        ファイルを再帰的にリストアップする

        smb_base_path 配下のすべてのファイルを再帰的に走査し、
        FileInfo オブジェクトを yield する。除外対象のディレクトリや
        ファイルはスキップされる。

        Returns:
            Iterator[FileInfo]: FileInfo オブジェクトのイテレータ

        Note:
            - yield を使っているのでジェネレータとして動作する
            - 再帰的に _scan_directory() を呼び出す
            - smbclient.scandir() はコンテキストマネージャとして使用
        """
        # ベースディレクトリから再帰的にスキャン
        yield from self._scan_directory(self.smb_base_path)

    def _scan_directory(self, path: str) -> Iterator[FileInfo]:
        """
        指定されたディレクトリを再帰的にスキャンする

        ディレクトリ内のエントリを走査し、ファイルは FileInfo として yield し、
        サブディレクトリは再帰的にスキャンする。

        Args:
            path: スキャンするディレクトリの UNC パス

        Yields:
            FileInfo: ファイル情報

        Note:
            このメソッドはプライベート（_scan_directory）であり、
            クラス内部でのみ使用される。
        """
        # smbclient.scandir() でディレクトリをスキャン
        # scandir() は直接イテレータを返す（コンテキストマネージャではない）
        for entry in smbclient.scandir(path):
            # 除外対象かどうかをチェック
            if self.should_exclude(entry.path):
                continue

            # ディレクトリの場合は再帰的にスキャン
            if entry.is_dir():
                yield from self._scan_directory(entry.path)
            else:
                # ファイルの場合は FileInfo を作成して yield
                yield self._create_file_info(entry)

    def read_file(self, path: str) -> bytes:
        """
        ファイル内容を読み取る

        SMB 共有上のファイルをバイナリモードで読み取り、
        内容をバイト列として返す。

        Args:
            path: 読み取るファイルの UNC パス
                  例: "\\\\192.168.1.1\\photo\\IMG_001.jpg"

        Returns:
            bytes: ファイルの内容（バイト列）

        使用例:
            content = reader.read_file(r"\\\\192.168.1.1\\photo\\photo.jpg")

        Note:
            smbclient.open_file() は Python の open() に似た API を持つ。
            mode="rb" はバイナリ読み取りモード。
        """
        # smbclient.open_file() でファイルを開く
        # "rb" はバイナリ読み取りモード（read binary）
        with smbclient.open_file(path, mode="rb") as f:
            return f.read()

    def should_exclude(self, path: str) -> bool:
        """
        パスを除外すべきかどうかを判定する

        パスに除外対象のディレクトリ名やファイル名が含まれているか
        チェックする。LocalFileReader と同じロジックを使用する。

        Args:
            path: チェックするパス（UNC 形式）
                  例: "\\\\192.168.1.1\\photo\\@eaDir\\thumb.jpg"

        Returns:
            bool: True なら除外する、False なら含める

        判定ロジック:
        1. パスをバックスラッシュで分割
        2. 各部分が除外ディレクトリ名に一致するかチェック
        3. ファイル名が除外ファイル名に一致するかチェック

        Note:
            UNC パスはバックスラッシュ（\\）を使用するため、
            split("\\") で分割する。
        """
        # UNC パスをバックスラッシュで分割
        # 例: "\\\\host\\share\\@eaDir\\file.jpg" -> ["", "", "host", "share", "@eaDir", "file.jpg"]
        parts = path.split("\\")

        # 各部分をチェック
        for part in parts:
            # 除外ディレクトリに一致するかチェック
            if part in self.EXCLUDED_DIRS:
                return True

        # ファイル名（最後の部分）をチェック
        # 空でない最後の部分を取得
        filename = parts[-1] if parts else ""
        if filename in self.EXCLUDED_FILES:
            return True

        # 除外対象ではない
        return False

    def _create_file_info(self, entry: Any) -> FileInfo:
        """
        scandir エントリから FileInfo を作成する

        smbclient.scandir() が返すエントリオブジェクトから
        ファイル情報を取得し、FileInfo オブジェクトを作成する。

        Args:
            entry: smbclient.scandir() が返すエントリオブジェクト
                   entry.path, entry.stat() などのメソッドを持つ

        Returns:
            FileInfo: ファイル情報を格納したオブジェクト

        Note:
            entry.stat() は os.stat() と同様の結果を返す。
            st_size はファイルサイズ、st_mtime は更新日時。
        """
        # stat() でファイル情報を取得
        stat = entry.stat()

        # サイズを取得（バイト単位）
        size = stat.st_size

        # 更新日時を ISO 8601 形式に変換
        # st_mtime は Unix タイムスタンプ（1970年1月1日からの秒数）
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()

        # FileInfo オブジェクトを作成して返す
        return FileInfo(
            path=entry.path,
            size=size,
            mtime=mtime,
        )

    def get_file_info(self, path: str) -> FileInfo:
        """
        指定されたパスのファイル情報を取得する

        リトライ処理など、特定のファイルのメタデータが必要な場合に使用する。
        smbclient.stat() を使用してファイル情報を取得する。

        Args:
            path: ファイルの UNC パス
                  例: "\\\\192.168.1.1\\share\\photo.jpg"

        Returns:
            FileInfo: ファイル情報（path, size, mtime を含む）

        Raises:
            FileNotFoundError: ファイルが存在しない場合
        """
        # smbclient.stat() でファイル情報を取得
        stat = smbclient.stat(path)

        # サイズを取得（バイト単位）
        size = stat.st_size

        # 更新日時を ISO 8601 形式に変換
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()

        # FileInfo オブジェクトを作成して返す
        return FileInfo(
            path=path,
            size=size,
            mtime=mtime,
        )
