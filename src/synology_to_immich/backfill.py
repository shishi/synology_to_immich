"""
Backfiller - 移行漏れを補完するモジュール

移行時に漏れたファイル（DB に記録がないファイル）を検出し、
Immich に存在すれば DB にバックフィル、存在しなければアップロードする。

使用例:
    backfiller = Backfiller(progress_tracker=tracker, immich_client=client)

    # DB に記録がないファイルを検出
    unrecorded = backfiller.find_unrecorded_files(source_files)

    # Immich に存在するか確認
    existing, missing = backfiller.check_immich_existence(unrecorded)
"""

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from synology_to_immich.progress import FileStatus, ProgressTracker
from synology_to_immich.readers.base import FileInfo

if TYPE_CHECKING:
    from synology_to_immich.immich import ImmichClient
    from synology_to_immich.readers.base import FileReader


class ExistingFile(TypedDict):
    """Immich に存在するファイルの情報"""

    file_info: FileInfo
    asset_id: str


class Backfiller:
    """
    移行漏れを補完するクラス

    Attributes:
        _progress_tracker: ProgressTracker インスタンス
        _immich_client: ImmichClient インスタンス（オプション）
    """

    def __init__(
        self,
        progress_tracker: ProgressTracker,
        immich_client: "ImmichClient | None" = None,
        file_reader: "FileReader | None" = None,
    ):
        """
        Backfiller を初期化する

        Args:
            progress_tracker: ProgressTracker インスタンス
            immich_client: ImmichClient インスタンス（オプション）
            file_reader: FileReader インスタンス（オプション）
        """
        self._progress_tracker = progress_tracker
        self._immich_client = immich_client
        self._file_reader = file_reader

    def find_unrecorded_files(self, source_files: list[FileInfo]) -> list[FileInfo]:
        """
        DB に記録されていないファイルを検出する

        Args:
            source_files: ソースファイルのリスト

        Returns:
            DB に記録がないファイルのリスト
        """
        unrecorded = []
        for file_info in source_files:
            record = self._progress_tracker.get_file(file_info.path)
            if not record:
                unrecorded.append(file_info)
        return unrecorded

    def check_immich_existence(
        self, files: list[FileInfo]
    ) -> tuple[list[ExistingFile], list[FileInfo]]:
        """
        ファイルが Immich に存在するか確認する

        ファイル名で Immich のアセットと照合し、存在するものと
        存在しないものに分類する。

        Args:
            files: 確認対象のファイルリスト

        Returns:
            (existing, missing) のタプル
            - existing: Immich に存在するファイル（asset_id 付き）
            - missing: Immich に存在しないファイル
        """
        if not self._immich_client:
            raise ValueError("immich_client が設定されていません")

        # Immich から全アセットを取得
        assets = self._immich_client.get_all_assets()

        # ファイル名 → アセット ID のマップを作成
        # assets は大量のメモリを使う可能性があるので、マップ作成後に解放
        filename_to_asset: dict[str, str] = {}
        for asset in assets:
            filename = asset.get("originalFileName", "")
            if filename:
                filename_to_asset[filename] = asset["id"]

        # メモリを解放（アセット数が多い場合に重要）
        del assets

        existing: list[ExistingFile] = []
        missing: list[FileInfo] = []

        for file_info in files:
            filename = Path(file_info.path).name
            if filename in filename_to_asset:
                existing.append(
                    ExistingFile(
                        file_info=file_info,
                        asset_id=filename_to_asset[filename],
                    )
                )
            else:
                missing.append(file_info)

        return existing, missing

    def backfill_existing(self, existing_files: list[ExistingFile]) -> int:
        """
        Immich に存在するファイルを DB にバックフィルする

        ファイルのアップロードは行わず、DB への記録のみ行う。

        Args:
            existing_files: Immich に存在するファイルのリスト

        Returns:
            バックフィルした件数
        """
        count = 0
        for item in existing_files:
            file_info = item["file_info"]
            asset_id = item["asset_id"]

            self._progress_tracker.record_file(
                source_path=file_info.path,
                source_hash=None,
                source_size=file_info.size,
                source_mtime=file_info.mtime,
                immich_asset_id=asset_id,
                status=FileStatus.SUCCESS,
            )
            count += 1

        return count

    def upload_missing(self, missing_files: list[FileInfo]) -> tuple[int, int]:
        """
        Immich に存在しないファイルをアップロードして DB に記録する

        Args:
            missing_files: アップロード対象のファイルリスト

        Returns:
            (uploaded, failed) のタプル
            - uploaded: アップロード成功件数
            - failed: アップロード失敗件数
        """
        if not self._immich_client:
            raise ValueError("immich_client が設定されていません")
        if not self._file_reader:
            raise ValueError("file_reader が設定されていません")

        uploaded = 0
        failed = 0

        for file_info in missing_files:
            try:
                # ファイルを読み込む
                file_data = self._file_reader.read_file(file_info.path)
                filename = Path(file_info.path).name

                # アップロード
                result = self._immich_client.upload_asset(
                    file_data=file_data,
                    filename=filename,
                    created_at=file_info.mtime,
                )

                # メモリを解放（大きなファイルでメモリを使い切らないように）
                del file_data

                if result.success:
                    # DB に記録
                    self._progress_tracker.record_file(
                        source_path=file_info.path,
                        source_hash=None,
                        source_size=file_info.size,
                        source_mtime=file_info.mtime,
                        immich_asset_id=result.asset_id,
                        status=FileStatus.SUCCESS,
                    )
                    uploaded += 1
                else:
                    # 失敗を記録
                    self._progress_tracker.record_file(
                        source_path=file_info.path,
                        source_hash=None,
                        source_size=file_info.size,
                        source_mtime=file_info.mtime,
                        immich_asset_id=None,
                        status=FileStatus.FAILED,
                        error_message=result.error_message,
                    )
                    failed += 1

            except Exception as e:
                # エラーを記録
                self._progress_tracker.record_file(
                    source_path=file_info.path,
                    source_hash=None,
                    source_size=file_info.size,
                    source_mtime=file_info.mtime,
                    immich_asset_id=None,
                    status=FileStatus.FAILED,
                    error_message=str(e),
                )
                failed += 1

        return uploaded, failed
