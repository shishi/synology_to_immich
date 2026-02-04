"""
移行オーケストレーターモジュール

このモジュールは、Synology Photos から Immich への移行処理全体を
オーケストレーション（統合管理）する。

各コンポーネントの役割:
- FileReader: ソースからファイルをスキャン
- LivePhotoPairer: Live Photo のペアリング
- ImmichClient: Immich へのアップロード
- ProgressTracker: 進捗管理（中断再開に対応）
- MigrationLogger: ログ出力

処理フロー:
1. FileReader でファイル一覧を取得
2. LivePhotoPairer でペアリング
3. 各グループについて:
   - ProgressTracker で移行済みか確認 → 済みならスキップ
   - dry_run モードなら実際のアップロードをスキップ
   - ImmichClient でアップロード
   - 結果を ProgressTracker に記録
   - ログ出力
4. バッチ処理: batch_size ごとに batch_delay 秒待機
5. MigrationResult を返す

使用例:
    from synology_to_immich.migrator import Migrator
    from synology_to_immich.config import load_config

    config = load_config(Path("config.toml"))
    reader = LocalFileReader(Path(config.source))
    client = ImmichClient(config.immich_url, config.immich_api_key)
    tracker = ProgressTracker(config.progress_db_path)
    logger = MigrationLogger(Path("./logs"))

    migrator = Migrator(config, reader, client, tracker, logger)
    result = migrator.run()
    print(f"成功: {result.success_count}, 失敗: {result.failed_count}")
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from synology_to_immich.config import Config
from synology_to_immich.immich import ImmichClient
from synology_to_immich.live_photo import LivePhotoGroup, LivePhotoPairer
from synology_to_immich.logging import MigrationLogger
from synology_to_immich.progress import FileStatus, ProgressTracker
from synology_to_immich.readers.base import FileReader


@dataclass
class MigrationResult:
    """
    移行結果を保持するデータクラス

    run() メソッドの戻り値として使用される。
    移行の成功/失敗/スキップの統計情報を含む。

    Attributes:
        total_files: 処理対象となったファイル/ペアの総数
        success_count: アップロードに成功した数
        failed_count: アップロードに失敗した数（リトライ可能なエラー）
        skipped_count: スキップした数（既に移行済み）
        unsupported_count: 未対応形式の数（Immich が対応していない形式）
        elapsed_seconds: 処理にかかった時間（秒）

    使用例:
        result = migrator.run()
        print(f"合計: {result.total_files}")
        print(f"成功: {result.success_count}")
        print(f"失敗: {result.failed_count}")
        print(f"スキップ: {result.skipped_count}")
        print(f"未対応: {result.unsupported_count}")
        print(f"処理時間: {result.elapsed_seconds:.1f}秒")
    """

    total_files: int  # 処理対象ファイル/ペア数
    success_count: int  # 成功数
    failed_count: int  # 失敗数
    skipped_count: int  # スキップ数（既に移行済み）
    unsupported_count: int  # 未対応形式数
    elapsed_seconds: float  # 処理時間（秒）


class Migrator:
    """
    移行オーケストレータークラス

    各コンポーネントを統合して移行処理を実行する。
    増分移行（前回の続きから再開）をサポートし、
    Live Photo のペアリングも自動で行う。

    Attributes:
        config: 設定オブジェクト
        reader: ファイルリーダー（LocalFileReader または SmbFileReader）
        immich_client: Immich API クライアント
        progress_tracker: 進捗トラッカー
        logger: ログ出力用オブジェクト

    使用例:
        migrator = Migrator(
            config=config,
            reader=reader,
            immich_client=client,
            progress_tracker=tracker,
            logger=logger,
        )
        result = migrator.run()
    """

    def __init__(
        self,
        config: Config,
        reader: FileReader,
        immich_client: ImmichClient,
        progress_tracker: ProgressTracker,
        logger: MigrationLogger,
    ) -> None:
        """
        Migrator を初期化する

        Args:
            config: 設定オブジェクト（dry_run, batch_size, batch_delay など）
            reader: ファイルリーダー（ファイルスキャンとデータ読み込み）
            immich_client: Immich API クライアント（アップロード処理）
            progress_tracker: 進捗トラッカー（移行済みファイルの管理）
            logger: ログ出力用オブジェクト
        """
        self.config = config
        self.reader = reader
        self.immich_client = immich_client
        self.progress_tracker = progress_tracker
        self.logger = logger

    def run(self) -> MigrationResult:
        """
        移行を実行して結果を返す

        処理フロー:
        1. ファイル一覧を取得
        2. Live Photo ペアリング
        3. 各グループを処理（スキップ/アップロード）
        4. バッチごとに待機
        5. 結果を返す

        Returns:
            MigrationResult: 移行結果の統計情報
        """
        # 処理開始時刻を記録
        start_time = time.time()

        # カウンターを初期化
        total_files = 0
        success_count = 0
        failed_count = 0
        skipped_count = 0
        unsupported_count = 0

        # 1. ファイル一覧を取得
        # list_files() はジェネレータなので、list() で実体化
        files = list(self.reader.list_files())
        self.logger.info(f"ファイルスキャン完了: {len(files)} ファイル")

        # 2. Live Photo ペアリング
        pairer = LivePhotoPairer(files)
        groups = list(pairer.pair_files())
        self.logger.info(f"ペアリング完了: {len(groups)} グループ")

        # 3. 各グループを処理
        processed_in_batch = 0  # 現在のバッチで処理した数

        for group in groups:
            total_files += 1

            # 移行済みか確認
            if self._is_group_migrated(group):
                skipped_count += 1
                self.logger.debug(
                    f"スキップ（移行済み）: {group.image_path}",
                    file_path=group.image_path,
                )
                continue

            # ファイルを処理
            result = self._process_group(group)

            # 結果をカウント
            if result == "success":
                success_count += 1
            elif result == "failed":
                failed_count += 1
            elif result == "unsupported":
                unsupported_count += 1

            # バッチ処理
            processed_in_batch += 1
            if processed_in_batch >= self.config.batch_size and self.config.batch_delay > 0:
                # バッチサイズに達したら待機
                self.logger.debug(f"バッチ待機: {self.config.batch_delay}秒")
                time.sleep(self.config.batch_delay)
                processed_in_batch = 0

        # 処理終了時刻を記録
        elapsed_seconds = time.time() - start_time

        # 4. 結果をログ出力
        self.logger.info(
            f"移行完了: 成功={success_count}, 失敗={failed_count}, "
            f"スキップ={skipped_count}, 未対応={unsupported_count}, "
            f"処理時間={elapsed_seconds:.1f}秒"
        )

        # 5. 結果を返す
        return MigrationResult(
            total_files=total_files,
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            unsupported_count=unsupported_count,
            elapsed_seconds=elapsed_seconds,
        )

    def _is_group_migrated(self, group: LivePhotoGroup) -> bool:
        """
        グループが移行済みかどうかを判定する

        Live Photo ペアの場合、画像ファイルが移行済みなら
        グループ全体が移行済みと判定する。

        Args:
            group: 判定対象の LivePhotoGroup

        Returns:
            bool: 移行済みなら True
        """
        return self.progress_tracker.is_migrated(group.image_path)

    def _process_group(self, group: LivePhotoGroup) -> str:
        """
        1つのグループ（ファイルまたはペア）を処理する

        Args:
            group: 処理対象の LivePhotoGroup

        Returns:
            str: 処理結果（"success", "failed", "unsupported"）
        """
        # ファイルパスからファイル名を取得
        filename = os.path.basename(group.image_path)

        # dry_run モードの場合
        if self.config.dry_run:
            self.logger.info(
                f"[DRY RUN] アップロード対象: {filename}",
                file_path=group.image_path,
                is_live_photo=group.is_live_photo,
            )
            return "success"

        # ファイルデータを読み込む
        try:
            file_data = self.reader.read_file(group.image_path)
        except Exception as e:
            self.logger.error(
                f"ファイル読み込みエラー: {filename}",
                file_path=group.image_path,
                error=str(e),
            )
            self._record_failure(group, f"ファイル読み込みエラー: {e}")
            return "failed"

        # Immich にアップロード（静止画）
        # TODO: mtime から created_at を取得（現状は仮の値）
        upload_result = self.immich_client.upload_asset(
            file_data=file_data,
            filename=filename,
            created_at="2024-01-01T00:00:00",  # TODO: 実際の日時を取得
        )

        # Live Photo の場合、動画も別途アップロード
        # Immich v2.x では livePhotoData フィールドが廃止されたため、
        # 写真と動画を別々にアップロードする（Immich が自動でペアリング）
        if group.is_live_photo and group.video_path and upload_result.success:
            try:
                live_photo_data = self.reader.read_file(group.video_path)
                video_filename = Path(group.video_path).name
                video_result = self.immich_client.upload_asset(
                    file_data=live_photo_data,
                    filename=video_filename,
                    created_at="2024-01-01T00:00:00",  # TODO: 実際の日時を取得
                )
                if video_result.success:
                    # 動画の成功も DB に記録（完全な検証を可能にする）
                    self.progress_tracker.record_file(
                        source_path=group.video_path,
                        source_hash=None,
                        source_size=len(live_photo_data),
                        source_mtime="",
                        immich_asset_id=video_result.asset_id,
                        status=FileStatus.SUCCESS,
                    )
                else:
                    error_msg = f"Live Photo 動画アップロード失敗: {video_result.error_message}"
                    self.logger.warning(
                        f"Live Photo 動画アップロード失敗（静止画は成功）: {video_filename}",
                        file_path=group.video_path,
                        error=video_result.error_message,
                    )
                    # 動画の失敗も DB に記録（後から追跡可能にする）
                    self.progress_tracker.record_file(
                        source_path=group.video_path,
                        source_hash=None,
                        source_size=len(live_photo_data),
                        source_mtime="",
                        immich_asset_id=None,
                        status=FileStatus.FAILED,
                        error_message=error_msg,
                    )
            except Exception as e:
                error_msg = f"Live Photo 動画読み込みエラー: {e}"
                self.logger.warning(
                    f"Live Photo 動画読み込みエラー（静止画は成功）: {group.video_path}",
                    file_path=group.video_path,
                    error=str(e),
                )
                # 動画の失敗も DB に記録（後から追跡可能にする）
                self.progress_tracker.record_file(
                    source_path=group.video_path,
                    source_hash=None,
                    source_size=0,
                    source_mtime="",
                    immich_asset_id=None,
                    status=FileStatus.FAILED,
                    error_message=error_msg,
                )

        # 結果を処理
        if upload_result.success:
            self.logger.info(
                f"アップロード成功: {filename}",
                file_path=group.image_path,
                asset_id=upload_result.asset_id,
            )
            self._record_success(group, upload_result.asset_id)
            return "success"
        elif upload_result.is_unsupported:
            self.logger.log_unsupported(
                file_path=group.image_path,
                file_size=len(file_data),
                mime_type="unknown",  # TODO: MIME タイプを取得
                error_message=upload_result.error_message or "Unknown error",
            )
            self._record_unsupported(group, upload_result.error_message)
            return "unsupported"
        else:
            self.logger.error(
                f"アップロード失敗: {filename}",
                file_path=group.image_path,
                error=upload_result.error_message,
            )
            self._record_failure(group, upload_result.error_message)
            return "failed"

    def _record_success(self, group: LivePhotoGroup, asset_id: Optional[str]) -> None:
        """
        成功を進捗トラッカーに記録する

        Args:
            group: 処理対象のグループ
            asset_id: Immich のアセット ID
        """
        self.progress_tracker.record_file(
            source_path=group.image_path,
            source_hash=None,  # TODO: ハッシュを計算
            source_size=0,  # TODO: サイズを取得
            source_mtime="",  # TODO: mtime を取得
            immich_asset_id=asset_id,
            status=FileStatus.SUCCESS,
        )

    def _record_failure(self, group: LivePhotoGroup, error_message: Optional[str]) -> None:
        """
        失敗を進捗トラッカーに記録する

        Args:
            group: 処理対象のグループ
            error_message: エラーメッセージ
        """
        self.progress_tracker.record_file(
            source_path=group.image_path,
            source_hash=None,
            source_size=0,
            source_mtime="",
            immich_asset_id=None,
            status=FileStatus.FAILED,
            error_message=error_message,  # エラーメッセージを記録
        )

    def _record_unsupported(self, group: LivePhotoGroup, error_message: Optional[str]) -> None:
        """
        未対応形式を進捗トラッカーに記録する

        Args:
            group: 処理対象のグループ
            error_message: エラーメッセージ
        """
        self.progress_tracker.record_file(
            source_path=group.image_path,
            source_hash=None,
            source_size=0,
            source_mtime="",
            immich_asset_id=None,
            status=FileStatus.UNSUPPORTED,
            error_message=error_message,  # エラーメッセージを記録
        )
