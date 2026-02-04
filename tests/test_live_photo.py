"""
Live Photos ペアリングのテスト

iPhone の Live Photos（静止画 + 動画のペア）を検出するロジックをテストする。

Live Photos とは:
- iPhone で撮影された特殊な写真形式
- 静止画（HEIC/JPG）と短い動画（MOV）のペアで構成される
- Synology Photos では別々のファイルとして保存される
- Immich にアップロードする際はペアとして一緒にアップロードする必要がある
"""

from synology_to_immich.live_photo import LivePhotoGroup, LivePhotoPairer
from synology_to_immich.readers.base import FileInfo


class TestLivePhotoGroup:
    """LivePhotoGroup データクラスのテスト"""

    def test_live_photo_group_with_pair(self):
        """ペアがある場合の LivePhotoGroup は is_live_photo が True"""
        group = LivePhotoGroup(
            image_path="/photos/IMG_001.HEIC",
            video_path="/photos/IMG_001.MOV",
        )
        assert group.is_live_photo is True

    def test_live_photo_group_without_pair(self):
        """ペアがない場合の LivePhotoGroup は is_live_photo が False"""
        group = LivePhotoGroup(
            image_path="/photos/IMG_002.jpg",
            video_path=None,
        )
        assert group.is_live_photo is False


class TestLivePhotoPairer:
    """LivePhotoPairer のテスト"""

    def test_pairs_heic_and_mov(self):
        """HEIC と MOV がペアになることを確認"""
        files = [
            FileInfo(path="/photos/IMG_001.HEIC", size=1000, mtime="2024-01-01"),
            FileInfo(path="/photos/IMG_001.MOV", size=2000, mtime="2024-01-01"),
        ]
        pairer = LivePhotoPairer(files)
        groups = list(pairer.pair_files())

        assert len(groups) == 1
        assert groups[0].image_path == "/photos/IMG_001.HEIC"
        assert groups[0].video_path == "/photos/IMG_001.MOV"
        assert groups[0].is_live_photo is True

    def test_pairs_case_insensitive(self):
        """大文字小文字を区別しないでペアリング"""
        files = [
            FileInfo(path="/photos/IMG_001.heic", size=1000, mtime="2024-01-01"),
            FileInfo(path="/photos/img_001.MOV", size=2000, mtime="2024-01-01"),
        ]
        pairer = LivePhotoPairer(files)
        groups = list(pairer.pair_files())

        assert len(groups) == 1
        assert groups[0].is_live_photo is True

    def test_unpaired_image_returned_alone(self):
        """ペアがない画像は単独で返される"""
        files = [
            FileInfo(path="/photos/IMG_001.jpg", size=1000, mtime="2024-01-01"),
        ]
        pairer = LivePhotoPairer(files)
        groups = list(pairer.pair_files())

        assert len(groups) == 1
        assert groups[0].image_path == "/photos/IMG_001.jpg"
        assert groups[0].video_path is None
        assert groups[0].is_live_photo is False

    def test_unpaired_mov_returned_alone(self):
        """ペアがない MOV は単独で返される（通常の動画として）"""
        files = [
            FileInfo(path="/photos/video_001.MOV", size=5000, mtime="2024-01-01"),
        ]
        pairer = LivePhotoPairer(files)
        groups = list(pairer.pair_files())

        assert len(groups) == 1
        # ペアがない MOV は image_path に入る（単独ファイルとして扱う）
        assert groups[0].image_path == "/photos/video_001.MOV"
        assert groups[0].video_path is None
        assert groups[0].is_live_photo is False

    def test_different_directories_not_paired(self):
        """異なるディレクトリのファイルはペアにならない"""
        files = [
            FileInfo(path="/photos/2024/IMG_001.HEIC", size=1000, mtime="2024-01-01"),
            FileInfo(path="/photos/2025/IMG_001.MOV", size=2000, mtime="2024-01-01"),
        ]
        pairer = LivePhotoPairer(files)
        groups = list(pairer.pair_files())

        assert len(groups) == 2
        assert all(not g.is_live_photo for g in groups)

    def test_jpg_pairs_with_mov(self):
        """JPG も MOV とペアになる"""
        files = [
            FileInfo(path="/photos/IMG_001.jpg", size=1000, mtime="2024-01-01"),
            FileInfo(path="/photos/IMG_001.mov", size=2000, mtime="2024-01-01"),
        ]
        pairer = LivePhotoPairer(files)
        groups = list(pairer.pair_files())

        assert len(groups) == 1
        assert groups[0].is_live_photo is True

    def test_multiple_files_mixed(self):
        """複数ファイルの混在ケース"""
        files = [
            # Live Photo ペア 1
            FileInfo(path="/photos/IMG_001.HEIC", size=1000, mtime="2024-01-01"),
            FileInfo(path="/photos/IMG_001.MOV", size=2000, mtime="2024-01-01"),
            # 通常の写真
            FileInfo(path="/photos/IMG_002.jpg", size=1500, mtime="2024-01-01"),
            # 通常の動画
            FileInfo(path="/photos/video.mp4", size=5000, mtime="2024-01-01"),
            # Live Photo ペア 2
            FileInfo(path="/photos/IMG_003.jpeg", size=1000, mtime="2024-01-01"),
            FileInfo(path="/photos/IMG_003.MOV", size=2000, mtime="2024-01-01"),
        ]
        pairer = LivePhotoPairer(files)
        groups = list(pairer.pair_files())

        # 4グループ: 2つの Live Photo ペア + 通常写真 + 通常動画
        assert len(groups) == 4

        live_photos = [g for g in groups if g.is_live_photo]
        assert len(live_photos) == 2

        non_live = [g for g in groups if not g.is_live_photo]
        assert len(non_live) == 2
