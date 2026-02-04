"""
移行検証モジュール

移行が正しく行われたかを検証する機能を提供する。
以下のチェックを行う:

- ProgressTracker に記録された成功ファイルが Immich に存在するか
- ファイル数の一致確認
- ハッシュレベルでの内容一致確認（SHA1）
- エラーや不整合のレポート

使用例:
    from synology_to_immich.verify import Verifier, VerificationResult
    from synology_to_immich.progress import ProgressTracker
    from synology_to_immich.immich import ImmichClient

    # 各コンポーネントを初期化
    tracker = ProgressTracker(Path("progress.db"))
    client = ImmichClient("http://localhost:2283", "api-key")

    # Verifier を作成して検証
    verifier = Verifier(
        progress_tracker=tracker,
        immich_client=client,
    )

    # 検証を実行
    result = verifier.verify()

    if result.is_valid:
        print("検証成功")
    else:
        print(f"欠損ファイル: {result.missing_in_immich}")

    # ハッシュレベルで検証
    hash_result = verifier.verify_with_hash(file_reader=reader)
    if hash_result.is_valid:
        print("ハッシュ検証成功")
    else:
        print(f"ハッシュ不一致: {hash_result.hash_mismatches}")
"""

import base64
import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from synology_to_immich.immich import ImmichClient
from synology_to_immich.progress import ProgressTracker

if TYPE_CHECKING:
    from synology_to_immich.readers.base import FileReader


@dataclass
class VerificationResult:
    """
    検証結果を表すデータクラス

    検証の結果を格納する。is_valid プロパティで
    検証が成功したかどうかを判定できる。

    Attributes:
        progress_success_count: ProgressTracker に記録された成功ファイル数
        immich_asset_count: Immich に存在するアセット数
        missing_in_immich: Immich に見つからないファイルのリスト
                          （ソースパスのリスト）

    使用例:
        result = VerificationResult(
            progress_success_count=100,
            immich_asset_count=100,
            missing_in_immich=[],
        )

        if result.is_valid:
            print("検証成功")
    """

    local_file_count: int  # ローカルファイル数
    immich_asset_count: int  # Immich のアセット数
    missing_in_immich: list[str] = field(default_factory=list)  # Immich に欠損
    hash_mismatches: list[str] = field(default_factory=list)  # ハッシュ不一致
    not_in_db: list[str] = field(default_factory=list)  # progress.db に記録なし

    @property
    def is_valid(self) -> bool:
        """
        検証が成功したかどうかを判定する

        欠損ファイルとハッシュ不一致がない場合に True を返す。
        not_in_db は検証失敗とは見なさない（移行前のファイルの可能性）。

        Returns:
            bool: 検証成功なら True、失敗なら False
        """
        return len(self.missing_in_immich) == 0 and len(self.hash_mismatches) == 0


class Verifier:
    """
    移行結果の検証クラス

    ローカルファイルを正として、Immich に正しく移行されているかを
    SHA1 ハッシュで検証する。

    Attributes:
        _progress_tracker: ProgressTracker インスタンス（immich_asset_id 取得用）
        _immich_client: ImmichClient インスタンス

    使用例:
        verifier = Verifier(
            progress_tracker=tracker,
            immich_client=client,
        )

        result = verifier.verify_with_hash(file_reader=reader)
        if result.is_valid:
            print("全ファイルのハッシュが一致")
    """

    def __init__(
        self,
        progress_tracker: ProgressTracker,
        immich_client: ImmichClient,
    ):
        """
        Verifier を初期化する

        Args:
            progress_tracker: ProgressTracker インスタンス
            immich_client: ImmichClient インスタンス
        """
        self._progress_tracker = progress_tracker
        self._immich_client = immich_client

    def verify_with_hash(
        self,
        file_reader: "FileReader",
        resume_file: str = "hash_verification_progress.txt",
    ) -> VerificationResult:
        """
        ハッシュレベルで移行結果を検証する（再開可能）

        ローカルファイルリストを正として、各ファイルが Immich に
        正しく移行されているかを SHA1 ハッシュで検証する。

        検証フロー:
        1. file_reader.list_files() でローカルファイルリストを取得
        2. パスでソートして一定の順序を保証（再開機能のため）
        3. 各ファイルについて:
           - progress.db から immich_asset_id を取得
           - Immich のチェックサムと比較
           - 結果を resume_file に記録

        途中で落ちても再開可能。検証済みファイルは resume_file に保存される。

        Args:
            file_reader: ソースファイルを読み取るための FileReader
            resume_file: 検証進捗を保存するファイルパス

        Returns:
            VerificationResult: 検証結果
        """
        import json
        from pathlib import Path

        # Immich から全アセットを取得
        print("  Immich からアセット情報を取得中...", flush=True)
        assets = self._immich_client.get_all_assets()
        immich_count = len(assets)
        print(f"  Immich アセット数: {immich_count}", flush=True)

        # アセット ID → checksum のマップを作成
        asset_checksums = {asset["id"]: asset.get("checksum") for asset in assets}
        del assets

        # ローカルファイルリストを取得してソート（再開のため順序を保証）
        print("  ローカルファイルリストを取得中...", flush=True)
        local_files = sorted(file_reader.list_files(), key=lambda f: f.path)
        total_files = len(local_files)
        print(f"  ローカルファイル数: {total_files}", flush=True)

        # 検証済みファイルを読み込み（再開用）
        resume_path = Path(resume_file)
        verified_paths: set[str] = set()
        missing_files: list[str] = []
        hash_mismatches: list[str] = []
        not_in_db: list[str] = []

        if resume_path.exists():
            print(f"  既存の進捗を読み込み中: {resume_file}", flush=True)
            with open(resume_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        path = record.get("path", "")
                        status = record.get("status", "")
                        verified_paths.add(path)
                        if status == "missing":
                            missing_files.append(path)
                        elif status == "mismatch":
                            hash_mismatches.append(path)
                        elif status == "not_in_db":
                            not_in_db.append(path)
                    except json.JSONDecodeError:
                        pass
            print(f"  検証済み: {len(verified_paths)} 件", flush=True)

        # 未検証のファイルだけ抽出
        to_verify = [f for f in local_files if f.path not in verified_paths]
        skip_count = total_files - len(to_verify)
        del local_files

        print(f"  ハッシュ検証開始: {total_files} 件中 {len(to_verify)} 件を検証", flush=True)
        if skip_count > 0:
            print(f"  スキップ（検証済み）: {skip_count} 件", flush=True)

        # 進捗ファイルを追記モードで開く
        with open(resume_path, "a") as out:
            for i, file_info in enumerate(to_verify):
                source_path = file_info.path

                # 進捗表示（100件ごと）
                if (i + 1) % 100 == 0:
                    print(
                        f"  進捗: {skip_count + i + 1}/{total_files} 件 "
                        f"(missing={len(missing_files)}, mismatch={len(hash_mismatches)}, not_in_db={len(not_in_db)})",
                        flush=True,
                    )

                # progress.db から immich_asset_id を取得
                db_record = self._progress_tracker.get_file(source_path)
                if not db_record:
                    not_in_db.append(source_path)
                    out.write(json.dumps({"path": source_path, "status": "not_in_db"}) + "\n")
                    out.flush()
                    continue

                asset_id = db_record.get("immich_asset_id")
                if not asset_id:
                    missing_files.append(source_path)
                    out.write(json.dumps({"path": source_path, "status": "missing"}) + "\n")
                    out.flush()
                    continue

                # Immich のチェックサムを取得
                immich_checksum = asset_checksums.get(asset_id)

                # search API で見つからない場合は直接 API でフォールバック
                if not immich_checksum:
                    direct_asset = self._immich_client.get_asset_by_id(asset_id)
                    if direct_asset:
                        immich_checksum = direct_asset.get("checksum")
                    else:
                        missing_files.append(source_path)
                        out.write(json.dumps({"path": source_path, "status": "missing"}) + "\n")
                        out.flush()
                        continue

                # チェックサムがない場合は missing（検証不可）
                if not immich_checksum:
                    missing_files.append(source_path)
                    out.write(json.dumps({"path": source_path, "status": "missing", "reason": "no_checksum"}) + "\n")
                    out.flush()
                    continue

                # ソースファイルを読み込んで SHA1 を計算
                try:
                    file_content = file_reader.read_file(source_path)
                    source_sha1 = hashlib.sha1(file_content).digest()
                    source_checksum = base64.b64encode(source_sha1).decode()
                    del file_content

                    if source_checksum != immich_checksum:
                        hash_mismatches.append(source_path)
                        out.write(json.dumps({"path": source_path, "status": "mismatch"}) + "\n")
                    else:
                        out.write(json.dumps({"path": source_path, "status": "ok"}) + "\n")
                    out.flush()
                except Exception as e:
                    missing_files.append(source_path)
                    out.write(json.dumps({"path": source_path, "status": "error", "error": str(e)}) + "\n")
                    out.flush()

        print(f"  ハッシュ検証完了: {total_files} 件", flush=True)

        return VerificationResult(
            local_file_count=total_files,
            immich_asset_count=immich_count,
            missing_in_immich=missing_files,
            hash_mismatches=hash_mismatches,
            not_in_db=not_in_db,
        )
