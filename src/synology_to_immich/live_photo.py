"""
Live Photos ペアリングモジュール

iPhone/iPad で撮影された Live Photos を検出し、静止画と動画をペアリングする。

Live Photos とは:
- iPhone 6s 以降で撮影可能な特殊な写真形式
- 静止画（HEIC/JPG）と約3秒の動画（MOV）のペアで構成される
- Synology Photos では別々のファイルとして保存される
- Immich にアップロードする際はペアとして一緒にアップロードする必要がある

ペアリングのルール:
1. 同じディレクトリ内のファイルのみをペアとする
2. 同じベース名（拡張子を除いた部分）を持つファイルをペアとする
3. 大文字小文字を区別しない（IMG_001.HEIC と img_001.mov はペア）
4. 画像拡張子: .heic, .jpg, .jpeg
5. 動画拡張子: .mov

使用例:
    from synology_to_immich.live_photo import LivePhotoPairer
    from synology_to_immich.readers.base import FileInfo

    files = [
        FileInfo(path="/photos/IMG_001.HEIC", size=1000, mtime="2024-01-01"),
        FileInfo(path="/photos/IMG_001.MOV", size=2000, mtime="2024-01-01"),
    ]

    pairer = LivePhotoPairer(files)
    for group in pairer.pair_files():
        if group.is_live_photo:
            print(f"Live Photo: {group.image_path} + {group.video_path}")
        else:
            print(f"単独ファイル: {group.image_path}")
"""

import os
from dataclasses import dataclass
from typing import Iterator, Optional, Sequence

from synology_to_immich.readers.base import FileInfo

# Live Photos の静止画として認識する拡張子（小文字で定義）
LIVE_PHOTO_IMAGE_EXTENSIONS = {".heic", ".jpg", ".jpeg"}

# Live Photos の動画として認識する拡張子（小文字で定義）
LIVE_PHOTO_VIDEO_EXTENSIONS = {".mov"}


@dataclass
class LivePhotoGroup:
    """
    Live Photo のグループを表すデータクラス

    静止画と動画のペア、または単独のファイルを表現する。
    is_live_photo プロパティでペアかどうかを判定できる。

    Attributes:
        image_path: 静止画（またはペアがない場合の単独ファイル）のパス
        video_path: 動画のパス（ペアがない場合は None）

    使用例:
        # Live Photo ペアの場合
        group = LivePhotoGroup(
            image_path="/photos/IMG_001.HEIC",
            video_path="/photos/IMG_001.MOV"
        )
        print(group.is_live_photo)  # True

        # 単独ファイルの場合
        group = LivePhotoGroup(
            image_path="/photos/IMG_002.jpg",
            video_path=None
        )
        print(group.is_live_photo)  # False
    """

    image_path: str  # 静止画のパス（または単独ファイルのパス）
    video_path: Optional[str] = None  # 動画のパス（ペアがない場合は None）

    @property
    def is_live_photo(self) -> bool:
        """
        Live Photo かどうかを判定する

        video_path が設定されていれば Live Photo と判定する。

        Returns:
            bool: True なら Live Photo ペア、False なら単独ファイル
        """
        return self.video_path is not None


class LivePhotoPairer:
    """
    Live Photos のペアリングを行うクラス

    ファイルリストを受け取り、同じベース名を持つ静止画と動画を
    ペアとしてグループ化する。ペアが見つからないファイルは
    単独ファイルとして返す。

    Attributes:
        files: ペアリング対象のファイルリスト

    使用例:
        files = [
            FileInfo(path="/photos/IMG_001.HEIC", size=1000, mtime="2024-01-01"),
            FileInfo(path="/photos/IMG_001.MOV", size=2000, mtime="2024-01-01"),
            FileInfo(path="/photos/IMG_002.jpg", size=1500, mtime="2024-01-01"),
        ]

        pairer = LivePhotoPairer(files)
        for group in pairer.pair_files():
            print(f"Live Photo: {group.is_live_photo}")
    """

    def __init__(self, files: Sequence[FileInfo]) -> None:
        """
        LivePhotoPairer を初期化する

        Args:
            files: ペアリング対象のファイルリスト
                   FileInfo オブジェクトのシーケンス（リストやタプル）
        """
        self.files = files

    def pair_files(self) -> Iterator[LivePhotoGroup]:
        """
        ファイルをペアリングして LivePhotoGroup のイテレータを返す

        同じディレクトリ内で同じベース名を持つ静止画と動画をペアにする。
        ペアが見つからないファイルは単独の LivePhotoGroup として返す。

        Returns:
            Iterator[LivePhotoGroup]: ペアリング結果のイテレータ

        Note:
            - ファイルの順序は保証されない
            - 同じファイルが複数回返されることはない
        """
        # ディレクトリ + ベース名をキーにしてファイルを分類する
        # 例: ("/photos", "img_001") -> {"image": FileInfo, "video": FileInfo}
        groups: dict[tuple[str, str], dict[str, FileInfo]] = {}

        for file_info in self.files:
            # ファイルパスからディレクトリとファイル名を分離
            directory = os.path.dirname(file_info.path)
            filename = os.path.basename(file_info.path)

            # 拡張子とベース名を分離（大文字小文字を区別しない）
            name, ext = os.path.splitext(filename)
            ext_lower = ext.lower()
            # ベース名も小文字に統一（ペアリングのため）
            name_lower = name.lower()

            # グループキーを作成
            key = (directory, name_lower)

            # グループがなければ作成
            if key not in groups:
                groups[key] = {}

            # ファイルをカテゴリ分けして格納
            if ext_lower in LIVE_PHOTO_IMAGE_EXTENSIONS:
                # 静止画として登録
                groups[key]["image"] = file_info
            elif ext_lower in LIVE_PHOTO_VIDEO_EXTENSIONS:
                # 動画として登録
                groups[key]["video"] = file_info
            else:
                # その他のファイル（MP4 など）は単独ファイルとして扱う
                # 既存のキーと被らないようにパス全体をキーにする
                other_key = (file_info.path, "other")
                groups[other_key] = {"other": file_info}

        # グループを走査して LivePhotoGroup を生成
        for key, group in groups.items():
            if "image" in group and "video" in group:
                # 静止画と動画の両方がある場合 → Live Photo ペア
                yield LivePhotoGroup(
                    image_path=group["image"].path,
                    video_path=group["video"].path,
                )
            elif "image" in group:
                # 静止画のみ → 単独の画像ファイル
                yield LivePhotoGroup(
                    image_path=group["image"].path,
                    video_path=None,
                )
            elif "video" in group:
                # 動画のみ → 単独の動画ファイル（通常の動画として扱う）
                yield LivePhotoGroup(
                    image_path=group["video"].path,
                    video_path=None,
                )
            elif "other" in group:
                # その他のファイル → 単独ファイルとして扱う
                yield LivePhotoGroup(
                    image_path=group["other"].path,
                    video_path=None,
                )
