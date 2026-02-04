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
import os
from dataclasses import dataclass, field
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
