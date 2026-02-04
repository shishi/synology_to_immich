"""
アルバム検証モジュール

Synology Photos のアルバムと Immich のアルバムを比較し、
ファイル数とハッシュの一致を検証する機能を提供する。

使用例:
    from synology_to_immich.album_verify import AlbumVerifier

    verifier = AlbumVerifier(
        synology_fetcher=fetcher,
        immich_client=client,
        progress_tracker=tracker,
        file_reader=reader,
    )

    report = verifier.verify()
    if report.matched_albums == report.total_synology_albums:
        print("全アルバム一致")
"""

import base64
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from synology_to_immich.immich import ImmichClient
    from synology_to_immich.progress import ProgressTracker
    from synology_to_immich.readers.base import FileReader
    from synology_to_immich.synology_db import SynologyAlbum, SynologyAlbumFetcher


@dataclass
class AlbumComparisonResult:
    """
    1つのアルバムの比較結果

    Synology のアルバムと Immich のアルバムを比較した結果を格納する。

    Attributes:
        synology_album_name: Synology 側のアルバム名
        synology_album_id: Synology 側のアルバム ID
        immich_album_id: Immich 側のアルバム ID（マッチしない場合は None）
        immich_album_name: Immich 側のアルバム名（マッチしない場合は None）
        synology_file_count: Synology 側のファイル数
        immich_asset_count: Immich 側のアセット数
        missing_in_immich: Synology にあって Immich にないファイル
        extra_in_immich: Immich にあって Synology にないファイル
        hash_mismatches: 両方にあるがハッシュが不一致のファイル
        match_type: マッチング方法 ("name" | "id" | "both" | "unmatched")
    """

    synology_album_name: str
    synology_album_id: int
    immich_album_id: Optional[str]
    immich_album_name: Optional[str]
    synology_file_count: int
    immich_asset_count: int
    missing_in_immich: list[str] = field(default_factory=list)
    extra_in_immich: list[str] = field(default_factory=list)
    hash_mismatches: list[str] = field(default_factory=list)
    match_type: str = "unmatched"


@dataclass
class AlbumVerificationReport:
    """
    アルバム検証レポート全体

    全アルバムの検証結果をまとめたレポート。

    Attributes:
        timestamp: レポート生成日時（ISO 8601 形式）
        total_synology_albums: Synology の総アルバム数
        total_immich_albums: Immich の総アルバム数
        matched_albums: マッチしたアルバム数
        unmatched_synology_albums: マッチしなかった Synology アルバム数
        unmatched_immich_albums: マッチしなかった Immich アルバム数
        album_results: 各アルバムの比較結果
        synology_only: Synology にしかないアルバム名のリスト
        immich_only: Immich にしかないアルバム名のリスト
    """

    timestamp: str
    total_synology_albums: int
    total_immich_albums: int
    matched_albums: int
    unmatched_synology_albums: int
    unmatched_immich_albums: int
    album_results: list[AlbumComparisonResult] = field(default_factory=list)
    synology_only: list[str] = field(default_factory=list)
    immich_only: list[str] = field(default_factory=list)


class AlbumVerifier:
    """
    アルバム検証クラス

    Synology のアルバムと Immich のアルバムを比較し、
    ファイル数とハッシュの一致を検証する。

    Attributes:
        _synology_fetcher: Synology DB からアルバム情報を取得
        _immich_client: Immich API クライアント
        _progress_tracker: 移行進捗トラッカー（移行記録の取得に使用）
        _file_reader: ソースファイルを読み取る
    """

    def __init__(
        self,
        synology_fetcher: "SynologyAlbumFetcher",
        immich_client: "ImmichClient",
        progress_tracker: "ProgressTracker",
        file_reader: "FileReader",
    ):
        """
        AlbumVerifier を初期化する

        Args:
            synology_fetcher: Synology DB からアルバム情報を取得するフェッチャー
            immich_client: Immich API クライアント
            progress_tracker: 移行進捗トラッカー
            file_reader: ソースファイルを読み取るリーダー
        """
        self._synology_fetcher = synology_fetcher
        self._immich_client = immich_client
        self._progress_tracker = progress_tracker
        self._file_reader = file_reader

    def _match_by_name(
        self,
        synology_albums: list["SynologyAlbum"],
        immich_albums: list[dict],
    ) -> list[tuple["SynologyAlbum", dict]]:
        """
        名前でアルバムをマッチングする

        Args:
            synology_albums: Synology のアルバムリスト
            immich_albums: Immich のアルバムリスト

        Returns:
            マッチしたアルバムのペア（Synology, Immich）のリスト
        """
        # Immich アルバムを名前でインデックス化
        immich_by_name = {album["albumName"]: album for album in immich_albums}

        matched = []
        for synology_album in synology_albums:
            immich_album = immich_by_name.get(synology_album.name)
            if immich_album:
                matched.append((synology_album, immich_album))

        return matched

    def _match_by_migration_record(
        self,
        synology_albums: list["SynologyAlbum"],
        immich_albums: list[dict],
    ) -> list[tuple["SynologyAlbum", dict]]:
        """
        移行記録（migrated_albums テーブル）でアルバムをマッチングする

        Args:
            synology_albums: Synology のアルバムリスト
            immich_albums: Immich のアルバムリスト

        Returns:
            マッチしたアルバムのペア（Synology, Immich）のリスト
        """
        # Immich アルバムを ID でインデックス化
        immich_by_id = {album["id"]: album for album in immich_albums}

        matched = []
        for synology_album in synology_albums:
            record = self._progress_tracker.get_album_by_synology_id(synology_album.id)
            if record:
                immich_id = record.get("immich_album_id")
                immich_album = immich_by_id.get(immich_id)
                if immich_album:
                    matched.append((synology_album, immich_album))

        return matched

    def _match_albums(
        self,
        synology_albums: list["SynologyAlbum"],
        immich_albums: list[dict],
    ) -> list[tuple["SynologyAlbum", dict, str]]:
        """
        名前と移行記録の両方でアルバムをマッチングする

        Args:
            synology_albums: Synology のアルバムリスト
            immich_albums: Immich のアルバムリスト

        Returns:
            マッチしたアルバムのタプル（Synology, Immich, match_type）のリスト
            match_type: "name" | "id" | "both"
        """
        # 名前でマッチング
        name_matched = self._match_by_name(synology_albums, immich_albums)
        name_matched_set = {
            (s.id, i["id"]) for s, i in name_matched
        }

        # 移行記録でマッチング
        id_matched = self._match_by_migration_record(synology_albums, immich_albums)
        id_matched_set = {
            (s.id, i["id"]) for s, i in id_matched
        }

        # 統合
        results = []
        seen_synology_ids = set()

        # 名前でマッチしたものを処理
        for synology_album, immich_album in name_matched:
            key = (synology_album.id, immich_album["id"])
            if key in id_matched_set:
                match_type = "both"
            else:
                match_type = "name"
            results.append((synology_album, immich_album, match_type))
            seen_synology_ids.add(synology_album.id)

        # ID でのみマッチしたものを追加
        for synology_album, immich_album in id_matched:
            if synology_album.id not in seen_synology_ids:
                results.append((synology_album, immich_album, "id"))
                seen_synology_ids.add(synology_album.id)

        return results

    def _compare_album_contents(
        self,
        synology_album: "SynologyAlbum",
        immich_album: dict,
    ) -> AlbumComparisonResult:
        """
        アルバムの内容を比較する（ファイル数 + ハッシュ）

        Args:
            synology_album: Synology のアルバム
            immich_album: Immich のアルバム

        Returns:
            AlbumComparisonResult: 比較結果
        """
        # Synology のファイル一覧を取得
        synology_files = self._synology_fetcher.get_album_files(synology_album.id)

        # Immich のアセット一覧を取得
        immich_assets = self._immich_client.get_album_assets(immich_album["id"])

        # Immich のアセットをファイル名でインデックス化
        immich_by_filename = {
            asset["originalFileName"]: asset
            for asset in immich_assets
        }

        missing_in_immich = []
        hash_mismatches = []

        # Synology のファイルを1つずつチェック
        for file_path in synology_files:
            filename = os.path.basename(file_path)
            immich_asset = immich_by_filename.get(filename)

            if not immich_asset:
                # Immich に存在しない
                missing_in_immich.append(file_path)
                continue

            # ハッシュ比較
            immich_checksum = immich_asset.get("checksum")
            if immich_checksum:
                # ローカルファイルのハッシュを計算
                content = self._file_reader.read_file(file_path)
                local_hash = base64.b64encode(hashlib.sha1(content).digest()).decode()
                del content

                if local_hash != immich_checksum:
                    hash_mismatches.append(file_path)

        # Immich にあって Synology にないファイルを検出
        synology_filenames = {os.path.basename(f) for f in synology_files}
        extra_in_immich = [
            asset["originalFileName"]
            for asset in immich_assets
            if asset["originalFileName"] not in synology_filenames
        ]

        return AlbumComparisonResult(
            synology_album_name=synology_album.name,
            synology_album_id=synology_album.id,
            immich_album_id=immich_album["id"],
            immich_album_name=immich_album["albumName"],
            synology_file_count=len(synology_files),
            immich_asset_count=len(immich_assets),
            missing_in_immich=missing_in_immich,
            extra_in_immich=extra_in_immich,
            hash_mismatches=hash_mismatches,
        )

    def _compare_album_contents_batch(
        self,
        synology_album: "SynologyAlbum",
        immich_album: dict,
        batch_size: int = 100,
    ) -> AlbumComparisonResult:
        """
        アルバムの内容をバッチ処理で比較する（メモリ効率重視）

        100件ごとにファイルを読み込み、ハッシュ計算し、結果を出力してからメモリを解放する。

        Args:
            synology_album: Synology のアルバム
            immich_album: Immich のアルバム
            batch_size: バッチサイズ（デフォルト100件）

        Returns:
            AlbumComparisonResult: 比較結果
        """
        # Synology のファイル一覧を取得
        synology_files = self._synology_fetcher.get_album_files(synology_album.id)

        # Immich のアセット一覧を取得
        immich_assets = self._immich_client.get_album_assets(immich_album["id"])

        # Immich のアセットをファイル名でインデックス化（軽量なマップ）
        immich_by_filename = {
            asset["originalFileName"]: asset.get("checksum")
            for asset in immich_assets
        }

        # 結果を格納するリスト
        missing_in_immich = []
        hash_mismatches = []

        # バッチ処理
        for i in range(0, len(synology_files), batch_size):
            batch_paths = synology_files[i:i + batch_size]

            # 100件分のファイル内容をまとめて読み込み
            batch_contents = []
            for file_path in batch_paths:
                filename = os.path.basename(file_path)
                immich_checksum = immich_by_filename.get(filename)

                if immich_checksum is None:
                    # Immich に存在しない
                    missing_in_immich.append(file_path)
                else:
                    # ファイル内容を読み込み
                    content = self._file_reader.read_file(file_path)
                    batch_contents.append((file_path, content, immich_checksum))

            # 100件分のハッシュ計算 & 比較
            for file_path, content, immich_checksum in batch_contents:
                local_hash = base64.b64encode(hashlib.sha1(content).digest()).decode()
                if local_hash != immich_checksum:
                    hash_mismatches.append(file_path)

            # 100件分まとめてメモリ解放
            del batch_contents

        # Immich にあって Synology にないファイルを検出
        synology_filenames = {os.path.basename(f) for f in synology_files}
        extra_in_immich = [
            asset["originalFileName"]
            for asset in immich_assets
            if asset["originalFileName"] not in synology_filenames
        ]

        # メモリ解放
        del synology_files
        del immich_assets

        return AlbumComparisonResult(
            synology_album_name=synology_album.name,
            synology_album_id=synology_album.id,
            immich_album_id=immich_album["id"],
            immich_album_name=immich_album["albumName"],
            synology_file_count=len(synology_filenames),
            immich_asset_count=len(immich_by_filename),
            missing_in_immich=missing_in_immich,
            extra_in_immich=extra_in_immich,
            hash_mismatches=hash_mismatches,
        )

    def _load_progress(self, progress_file: str) -> set[int]:
        """
        進捗ファイルから検証済みアルバム ID を読み込む

        Args:
            progress_file: 進捗ファイルのパス

        Returns:
            検証済みアルバム ID の集合
        """
        progress_path = Path(progress_file)
        if not progress_path.exists():
            return set()

        with open(progress_path, "r") as f:
            data = json.load(f)

        return set(data.get("verified_album_ids", []))

    def _save_progress(
        self,
        progress_file: str,
        result: AlbumComparisonResult,
    ) -> None:
        """
        検証結果を進捗ファイルに追記する（JSON Lines 形式）

        Args:
            progress_file: 進捗ファイルのパス
            result: 検証結果
        """
        progress_path = Path(progress_file)

        # 結果を JSON 形式で保存
        record = {
            "synology_album_id": result.synology_album_id,
            "synology_album_name": result.synology_album_name,
            "immich_album_id": result.immich_album_id,
            "immich_album_name": result.immich_album_name,
            "synology_file_count": result.synology_file_count,
            "immich_asset_count": result.immich_asset_count,
            "missing_count": len(result.missing_in_immich),
            "extra_count": len(result.extra_in_immich),
            "mismatch_count": len(result.hash_mismatches),
            "match_type": result.match_type,
        }

        with open(progress_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _generate_json_report(
        self,
        report: AlbumVerificationReport,
        output_file: str,
    ) -> None:
        """
        JSON レポートを生成する

        設計書で定義された形式で JSON ファイルを出力する。

        Args:
            report: 検証レポート
            output_file: 出力ファイルパス
        """
        # サマリー
        perfect_match = sum(
            1 for r in report.album_results
            if len(r.missing_in_immich) == 0
            and len(r.extra_in_immich) == 0
            and len(r.hash_mismatches) == 0
        )
        with_differences = len(report.album_results) - perfect_match

        output = {
            "timestamp": report.timestamp,
            "summary": {
                "total_synology_albums": report.total_synology_albums,
                "total_immich_albums": report.total_immich_albums,
                "matched_albums": report.matched_albums,
                "perfect_match": perfect_match,
                "with_differences": with_differences,
                "synology_only": report.unmatched_synology_albums,
                "immich_only": report.unmatched_immich_albums,
            },
            "unmatched_albums": {
                "synology_only": report.synology_only,
                "immich_only": report.immich_only,
            },
            "album_comparisons": [
                {
                    "synology_name": r.synology_album_name,
                    "synology_id": r.synology_album_id,
                    "immich_name": r.immich_album_name,
                    "immich_id": r.immich_album_id,
                    "match_type": r.match_type,
                    "synology_file_count": r.synology_file_count,
                    "immich_asset_count": r.immich_asset_count,
                    "status": "perfect" if (
                        len(r.missing_in_immich) == 0
                        and len(r.extra_in_immich) == 0
                        and len(r.hash_mismatches) == 0
                    ) else "different",
                    "differences": {
                        "missing_in_immich": r.missing_in_immich,
                        "extra_in_immich": r.extra_in_immich,
                        "hash_mismatches": r.hash_mismatches,
                    },
                }
                for r in report.album_results
            ],
        }

        with open(output_file, "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    def verify(
        self,
        output_file: str = "album_verification_report.json",
        progress_file: str = "album_verification_progress.json",
        batch_size: int = 100,
    ) -> AlbumVerificationReport:
        """
        アルバム検証を実行する（メインエントリポイント）

        処理フロー:
        1. Synology からアルバム一覧を取得
        2. Immich からアルバム一覧を取得
        3. 名前と移行記録でマッチング
        4. 各マッチしたアルバムについて内容を比較（バッチ処理）
        5. 進捗を保存しながら処理（再開可能）
        6. JSON レポートを生成

        Args:
            output_file: 出力レポートファイルパス
            progress_file: 進捗ファイルパス（再開用）
            batch_size: バッチサイズ（デフォルト100件）

        Returns:
            AlbumVerificationReport: 検証レポート
        """
        from datetime import datetime

        # 検証済みアルバム ID を読み込み
        verified_ids = self._load_progress(progress_file)

        # アルバム一覧を取得
        print("  Synology からアルバム一覧を取得中...", flush=True)
        synology_albums = self._synology_fetcher.get_albums()
        print(f"  Synology アルバム数: {len(synology_albums)}", flush=True)

        print("  Immich からアルバム一覧を取得中...", flush=True)
        immich_albums = self._immich_client.get_albums()
        print(f"  Immich アルバム数: {len(immich_albums)}", flush=True)

        # マッチング
        print("  アルバムをマッチング中...", flush=True)
        matched = self._match_albums(synology_albums, immich_albums)
        print(f"  マッチしたアルバム数: {len(matched)}", flush=True)

        # マッチしなかったアルバムを特定
        matched_synology_ids = {s.id for s, _, _ in matched}
        matched_immich_ids = {i["id"] for _, i, _ in matched}

        synology_only = [
            album.name for album in synology_albums
            if album.id not in matched_synology_ids
        ]
        immich_only = [
            album["albumName"] for album in immich_albums
            if album["id"] not in matched_immich_ids
        ]

        # 各アルバムを検証
        album_results = []
        for synology_album, immich_album, match_type in matched:
            # 既に検証済みならスキップ
            if synology_album.id in verified_ids:
                print(f"  スキップ（検証済み）: {synology_album.name}", flush=True)
                continue

            print(f"  検証中: {synology_album.name}...", flush=True)

            # バッチ処理で比較
            result = self._compare_album_contents_batch(
                synology_album,
                immich_album,
                batch_size=batch_size,
            )
            result.match_type = match_type

            album_results.append(result)

            # 進捗を保存
            self._save_progress(progress_file, result)

        # レポート生成
        timestamp = datetime.now().isoformat()
        report = AlbumVerificationReport(
            timestamp=timestamp,
            total_synology_albums=len(synology_albums),
            total_immich_albums=len(immich_albums),
            matched_albums=len(matched),
            unmatched_synology_albums=len(synology_only),
            unmatched_immich_albums=len(immich_only),
            album_results=album_results,
            synology_only=synology_only,
            immich_only=immich_only,
        )

        # JSON レポート出力
        self._generate_json_report(report, output_file)
        print(f"  レポート出力: {output_file}", flush=True)

        return report
