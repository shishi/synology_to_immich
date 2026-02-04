"""
ファイルリーダーモジュール

このパッケージはファイルの読み取り機能を提供する。
ローカルファイルシステムや SMB 共有からファイルを読み取る
抽象化レイヤーを提供する。

モジュール構成:
- base.py: 抽象基底クラス（FileReader）とデータクラス（FileInfo）
- local.py: ローカルファイルシステム用の実装（LocalFileReader）
- smb.py: SMB 共有用の実装（SmbFileReader、parse_smb_url）

使用例:
    # ローカルファイルシステムの場合
    from synology_to_immich.readers import LocalFileReader

    reader = LocalFileReader(Path("/path/to/photos"))
    for file_info in reader.list_files():
        print(f"Found: {file_info.path} ({file_info.size} bytes)")
        content = reader.read_file(file_info.path)

    # SMB 共有の場合
    from synology_to_immich.readers import SmbFileReader

    reader = SmbFileReader(
        "smb://192.168.1.1/photo/photos",
        username="admin",
        password="secret"
    )
    for file_info in reader.list_files():
        print(f"Found: {file_info.path}")
"""

# 主要なクラスをパッケージレベルでエクスポート
# これにより、以下のようにインポートできる:
# from synology_to_immich.readers import FileReader, FileInfo, LocalFileReader, SmbFileReader
from synology_to_immich.readers.base import FileInfo, FileReader
from synology_to_immich.readers.local import LocalFileReader
from synology_to_immich.readers.smb import SmbFileReader, parse_smb_url

# __all__ はモジュールをインポートした際に公開されるシンボルを定義
# from synology_to_immich.readers import * としたときにエクスポートされる
__all__ = [
    "FileReader",
    "FileInfo",
    "LocalFileReader",
    "SmbFileReader",
    "parse_smb_url",
]
