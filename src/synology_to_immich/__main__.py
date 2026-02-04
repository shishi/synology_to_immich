"""
メインエントリーポイント

python -m synology_to_immich で実行可能にする

このファイルは Python がパッケージをモジュールとして実行するときに
呼び出されるエントリーポイントです。
例: python -m synology_to_immich

click ライブラリを使用してコマンドラインインターフェース (CLI) を構築しています。
click は Python で CLI を作成するための人気のあるライブラリで、
デコレータを使って簡潔にコマンドを定義できます。
"""

from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

# 自作モジュールのインポート
from synology_to_immich.album import AlbumMigrationResult, AlbumMigrator
from synology_to_immich.backfill import Backfiller
from synology_to_immich.config import load_config
from synology_to_immich.immich import ImmichClient
from synology_to_immich.logging import MigrationLogger
from synology_to_immich.migrator import MigrationResult, Migrator
from synology_to_immich.progress import FileStatus, ProgressTracker
from synology_to_immich.readers.local import LocalFileReader
from synology_to_immich.readers.smb import SmbFileReader
from synology_to_immich.report import ReportGenerator
from synology_to_immich.synology_db import SynologyAlbumFetcher
from synology_to_immich.album_verify import AlbumVerifier
from synology_to_immich.verify import VerificationResult, Verifier

# rich の Console オブジェクト（見やすい出力用）
console = Console()


# @click.group() デコレータは、このコマンドが
# サブコマンドを持つグループコマンドであることを示します
# 例: synology-to-immich migrate, synology-to-immich verify など
@click.group()
@click.version_option()  # --version オプションを自動追加
def main():
    """Synology Photos から Immich へ写真・動画を移行するツール"""
    # グループコマンドのメイン関数は通常何もしない
    # 実際の処理はサブコマンドで行う
    pass


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    required=True,
    type=click.Path(exists=False),
    help="設定ファイル（TOML）のパス",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="実際にはアップロードせずに実行をシミュレート",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="詳細な出力を表示",
)
def migrate(config_path: str, dry_run: bool, verbose: bool) -> None:
    """
    Synology Photos から Immich へファイルを移行する

    設定ファイルを指定して移行を実行します。
    --dry-run オプションで実際のアップロードをスキップしてテストできます。

    使用例:
        synology-to-immich migrate -c config.toml
        synology-to-immich migrate -c config.toml --dry-run
        synology-to-immich migrate -c config.toml --verbose
    """
    # 設定ファイルの存在確認
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]エラー: 設定ファイルが見つかりません: {config_path}[/red]")
        raise SystemExit(1)

    # 設定を読み込む
    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[red]エラー: 設定ファイルの読み込みに失敗しました: {e}[/red]")
        raise SystemExit(1)

    # --dry-run オプションが指定された場合、設定に反映
    if dry_run:
        config.dry_run = True

    # 開始メッセージを表示
    console.print("[bold blue]移行を開始します...[/bold blue]")
    if config.dry_run:
        console.print("[yellow]DRY RUN モード: 実際のアップロードは行いません[/yellow]")
    if verbose:
        console.print(f"  ソース: {config.source}")
        console.print(f"  Immich URL: {config.immich_url}")

    # 各コンポーネントを初期化
    # ファイルリーダー: SMB かローカルかで分岐
    if config.is_smb_source:
        reader = SmbFileReader(
            smb_url=config.source,
            username=config.smb_user,
            password=config.smb_password,
        )
    else:
        reader = LocalFileReader(Path(config.source))

    # Immich クライアント
    immich_client = ImmichClient(
        base_url=config.immich_url,
        api_key=config.immich_api_key,
    )

    # 進捗トラッカー
    progress_tracker = ProgressTracker(config.progress_db_path)

    # ログ出力（ログディレクトリは設定ファイルと同じディレクトリ）
    log_dir = config_file.parent / "logs"
    migration_logger = MigrationLogger(log_dir)

    # Migrator を作成して実行
    migrator = Migrator(
        config=config,
        reader=reader,
        immich_client=immich_client,
        progress_tracker=progress_tracker,
        logger=migration_logger,
    )

    # 移行を実行
    result = migrator.run()

    # 結果を表示
    _print_result(result, verbose)


def _print_result(result: MigrationResult, verbose: bool) -> None:
    """
    移行結果を表示する

    Args:
        result: MigrationResult オブジェクト
        verbose: 詳細表示モードかどうか
    """
    console.print()
    console.print("[bold green]移行完了[/bold green]")
    console.print()

    # サマリーを表示
    console.print(f"  処理対象: {result.total_files} ファイル")
    console.print(f"  [green]成功: {result.success_count}[/green]")

    # 失敗やスキップがあれば色付きで表示
    if result.failed_count > 0:
        console.print(f"  [red]失敗: {result.failed_count}[/red]")
    else:
        console.print(f"  失敗: {result.failed_count}")

    if result.skipped_count > 0:
        console.print(f"  [yellow]スキップ（移行済み）: {result.skipped_count}[/yellow]")
    else:
        console.print(f"  スキップ: {result.skipped_count}")

    if result.unsupported_count > 0:
        console.print(f"  [yellow]未対応形式: {result.unsupported_count}[/yellow]")
    else:
        console.print(f"  未対応形式: {result.unsupported_count}")

    # 処理時間
    console.print(f"  処理時間: {result.elapsed_seconds:.1f} 秒")


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    required=True,
    type=click.Path(exists=False),
    help="設定ファイル（TOML）のパス",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="詳細な出力を表示",
)
def verify(config_path: str, verbose: bool) -> None:
    """
    移行結果を検証する

    ローカルファイルを正として、Immich に正しく移行されているかを
    SHA1 ハッシュで検証します。再開可能。

    使用例:
        synology-to-immich verify -c config.toml
        synology-to-immich verify -c config.toml --verbose
    """
    # 設定ファイルの存在確認
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]エラー: 設定ファイルが見つかりません: {config_path}[/red]")
        raise SystemExit(1)

    # 設定を読み込む
    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[red]エラー: 設定ファイルの読み込みに失敗しました: {e}[/red]")
        raise SystemExit(1)

    # 開始メッセージを表示
    console.print("[bold blue]検証を開始します...[/bold blue]")
    if verbose:
        console.print(f"  Immich URL: {config.immich_url}")

    # 各コンポーネントを初期化
    immich_client = ImmichClient(
        base_url=config.immich_url,
        api_key=config.immich_api_key,
    )

    progress_tracker = ProgressTracker(config.progress_db_path)

    # FileReader を初期化（migrate コマンドと同じロジック）
    if config.is_smb_source:
        file_reader = SmbFileReader(
            smb_url=config.source,
            username=config.smb_user,
            password=config.smb_password,
        )
    else:
        file_reader = LocalFileReader(Path(config.source))

    # Verifier を作成して検証を実行
    verifier = Verifier(
        progress_tracker=progress_tracker,
        immich_client=immich_client,
    )

    result = verifier.verify_with_hash(file_reader=file_reader)

    # 結果を表示
    _print_verification_result(result, verbose)

    # 検証失敗の場合は exit code 1
    if not result.is_valid:
        raise SystemExit(1)


def _print_verification_result(result: VerificationResult, verbose: bool) -> None:
    """
    検証結果を表示する

    Args:
        result: VerificationResult オブジェクト
        verbose: 詳細表示モードかどうか
    """
    console.print()

    if result.is_valid:
        console.print("[bold green]検証成功[/bold green]")
    else:
        console.print("[bold red]検証失敗[/bold red]")

    console.print()

    # サマリーを表示
    console.print(f"  ローカルファイル数: {result.local_file_count}")
    console.print(f"  Immich アセット数: {result.immich_asset_count}")

    # 欠損ファイルがある場合
    if result.missing_in_immich:
        console.print(f"  [red]欠損ファイル数: {len(result.missing_in_immich)}[/red]")

        # verbose モードの場合は欠損ファイルの詳細を表示
        if verbose:
            console.print()
            console.print("[yellow]欠損ファイル一覧:[/yellow]")
            for path in result.missing_in_immich[:10]:  # 最大10件まで表示
                console.print(f"    {path}")
            if len(result.missing_in_immich) > 10:
                console.print(f"    ... 他 {len(result.missing_in_immich) - 10} 件")

    # ハッシュ不一致ファイルがある場合
    if result.hash_mismatches:
        console.print(f"  [red]ハッシュ不一致数: {len(result.hash_mismatches)}[/red]")

        # verbose モードの場合はハッシュ不一致ファイルの詳細を表示
        if verbose:
            console.print()
            console.print("[yellow]ハッシュ不一致ファイル一覧:[/yellow]")
            for path in result.hash_mismatches[:10]:  # 最大10件まで表示
                console.print(f"    {path}")
            if len(result.hash_mismatches) > 10:
                console.print(f"    ... 他 {len(result.hash_mismatches) - 10} 件")

    # progress.db に記録がないファイルがある場合
    if result.not_in_db:
        console.print(f"  [yellow]DB未記録数: {len(result.not_in_db)}[/yellow]")

        if verbose:
            console.print()
            console.print("[yellow]DB未記録ファイル一覧:[/yellow]")
            for path in result.not_in_db[:10]:
                console.print(f"    {path}")
            if len(result.not_in_db) > 10:
                console.print(f"    ... 他 {len(result.not_in_db) - 10} 件")


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    required=True,
    type=click.Path(exists=False),
    help="設定ファイル（TOML）のパス",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="詳細な出力を表示（失敗ファイルの一覧など）",
)
def status(config_path: str, verbose: bool) -> None:
    """
    移行の現在の状態を表示する

    ProgressTracker から統計を取得して、成功/失敗/未対応の件数を表示します。
    --verbose オプションで失敗ファイルの詳細も表示できます。

    使用例:
        synology-to-immich status -c config.toml
        synology-to-immich status -c config.toml --verbose
    """
    # 設定ファイルの存在確認
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]エラー: 設定ファイルが見つかりません: {config_path}[/red]")
        raise SystemExit(1)

    # 設定を読み込む
    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[red]エラー: 設定ファイルの読み込みに失敗しました: {e}[/red]")
        raise SystemExit(1)

    # 進捗トラッカーを初期化
    progress_tracker = ProgressTracker(config.progress_db_path)

    # 統計を取得
    stats = progress_tracker.get_statistics()

    # 統計情報を表示（rich の Table を使って見やすく）
    _print_status(stats, verbose, progress_tracker)

    # リソースを解放
    progress_tracker.close()


def _print_status(stats: dict, verbose: bool, progress_tracker: ProgressTracker) -> None:
    """
    統計情報を表示する

    Args:
        stats: 統計情報の辞書
        verbose: 詳細表示モードかどうか
        progress_tracker: ProgressTracker インスタンス（失敗ファイル取得用）
    """
    console.print()
    console.print("[bold blue]移行状態[/bold blue]")
    console.print()

    # rich の Table を使って見やすく表示
    table = Table(show_header=True, header_style="bold")
    table.add_column("項目", style="cyan")
    table.add_column("件数", justify="right")

    # 各ステータスの件数を追加
    table.add_row("合計", str(stats["total"]))
    table.add_row("[green]成功[/green]", str(stats["success"]))
    table.add_row("[red]失敗[/red]", str(stats["failed"]))
    table.add_row("[yellow]未対応形式[/yellow]", str(stats["unsupported"]))

    console.print(table)

    # verbose モードの場合、失敗ファイルの一覧を表示
    if verbose and stats["failed"] > 0:
        console.print()
        console.print("[bold yellow]失敗ファイル一覧:[/bold yellow]")

        # FAILED ステータスのファイルを取得
        failed_files = progress_tracker.get_files_by_status(FileStatus.FAILED)

        # 最大 20 件まで表示
        for file_info in failed_files[:20]:
            console.print(f"  {file_info['source_path']}")

        if len(failed_files) > 20:
            console.print(f"  ... 他 {len(failed_files) - 20} 件")


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    required=True,
    type=click.Path(exists=False),
    help="設定ファイル（TOML）のパス",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="実際にはアップロードせずに実行をシミュレート",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="詳細な出力を表示",
)
def retry(config_path: str, dry_run: bool, verbose: bool) -> None:
    """
    失敗したファイルの再移行を試みる

    FAILED ステータスのファイルのみを再処理します。
    UNSUPPORTED（未対応形式）のファイルはリトライしても意味がないため、
    対象外となります。

    使用例:
        synology-to-immich retry -c config.toml
        synology-to-immich retry -c config.toml --dry-run
        synology-to-immich retry -c config.toml --verbose
    """
    # 設定ファイルの存在確認
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]エラー: 設定ファイルが見つかりません: {config_path}[/red]")
        raise SystemExit(1)

    # 設定を読み込む
    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[red]エラー: 設定ファイルの読み込みに失敗しました: {e}[/red]")
        raise SystemExit(1)

    # 進捗トラッカーを初期化
    progress_tracker = ProgressTracker(config.progress_db_path)

    # 失敗ファイルを取得（UNSUPPORTED は対象外）
    failed_files = progress_tracker.get_files_by_status(FileStatus.FAILED)

    # 失敗ファイルがない場合は終了
    if not failed_files:
        console.print("[green]再処理対象のファイルがありません（0 件）[/green]")
        progress_tracker.close()
        return

    # 開始メッセージを表示
    console.print(f"[bold blue]再処理を開始します... ({len(failed_files)} 件)[/bold blue]")
    if dry_run:
        console.print("[yellow]DRY RUN モード: 実際のアップロードは行いません[/yellow]")

    # 各コンポーネントを初期化
    # ファイルリーダー: SMB かローカルかで分岐
    if config.is_smb_source:
        reader = SmbFileReader(
            smb_url=config.source,
            username=config.smb_user,
            password=config.smb_password,
        )
    else:
        reader = LocalFileReader(Path(config.source))

    # Immich クライアント
    immich_client = ImmichClient(
        base_url=config.immich_url,
        api_key=config.immich_api_key,
    )

    # ログ出力（ログディレクトリは設定ファイルと同じディレクトリ）
    log_dir = config_file.parent / "logs"
    migration_logger = MigrationLogger(log_dir)

    # リトライ結果のカウンター
    success_count = 0
    failed_count = 0

    # 各失敗ファイルを再処理
    for file_info in failed_files:
        source_path = file_info["source_path"]
        source_mtime = file_info["source_mtime"]

        # source_mtime が空や無効な場合はファイルから直接取得する
        # progress.db に mtime が記録されていない場合のフォールバック
        if not source_mtime or source_mtime.strip() == "":
            try:
                actual_file_info = reader.get_file_info(source_path)
                source_mtime = actual_file_info.mtime
            except Exception as e:
                # ファイル情報の取得に失敗した場合はエラーとして記録
                migration_logger.error(
                    f"ファイル情報の取得に失敗: {source_path}",
                    error=str(e),
                )
                failed_count += 1
                continue

        if verbose:
            console.print(f"  処理中: {source_path}")

        # DRY RUN モードの場合はスキップ
        if dry_run:
            success_count += 1
            continue

        # ファイルを読み込んでアップロード
        try:
            file_data = reader.read_file(source_path)

            # アップロード
            result = immich_client.upload_asset(
                file_data=file_data,
                filename=Path(source_path).name,
                created_at=source_mtime,
            )

            if result.success:
                # 成功を記録
                progress_tracker.record_file(
                    source_path=source_path,
                    source_hash=file_info.get("source_hash"),
                    source_size=file_info["source_size"],
                    source_mtime=source_mtime,
                    immich_asset_id=result.asset_id,
                    status=FileStatus.SUCCESS,
                )
                success_count += 1
                migration_logger.info(
                    f"リトライ成功: {source_path}",
                    asset_id=result.asset_id or "",
                )
            else:
                # 再度失敗
                failed_count += 1
                migration_logger.error(
                    f"リトライ失敗: {source_path}",
                    error=result.error_message or "Unknown error",
                )

        except Exception as e:
            # エラーが発生した場合
            failed_count += 1
            migration_logger.error(
                f"リトライ中にエラー: {source_path}",
                error=str(e),
            )

    # 結果を表示
    console.print()
    console.print("[bold green]再処理完了[/bold green]")
    console.print(f"  成功: {success_count}")
    console.print(f"  失敗: {failed_count}")

    # リソースを解放
    progress_tracker.close()


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    required=True,
    type=click.Path(exists=False),
    help="設定ファイル（TOML）のパス",
)
@click.option(
    "--output",
    "-o",
    "output_path",
    default="migration_report.md",
    type=click.Path(),
    help="出力ファイルのパス（デフォルト: migration_report.md）",
)
def report(config_path: str, output_path: str) -> None:
    """
    移行結果のレポートを生成する

    ProgressTracker から移行結果を取得して、
    Markdown 形式のレポートファイルを生成します。

    レポートには以下の内容が含まれます：
    - 処理件数と成功率
    - 失敗ファイルのリスト
    - 未対応形式のリスト
    - アルバム移行状況

    使用例:
        synology-to-immich report -c config.toml
        synology-to-immich report -c config.toml -o my_report.md
    """
    # 設定ファイルの存在確認
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]エラー: 設定ファイルが見つかりません: {config_path}[/red]")
        raise SystemExit(1)

    # 設定を読み込む
    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[red]エラー: 設定ファイルの読み込みに失敗しました: {e}[/red]")
        raise SystemExit(1)

    # 進捗トラッカーを初期化
    progress_tracker = ProgressTracker(config.progress_db_path)

    # レポート生成
    console.print("[bold blue]レポートを生成しています...[/bold blue]")

    generator = ReportGenerator(progress_tracker=progress_tracker)
    output = Path(output_path)
    generator.generate(output)

    # 完了メッセージ
    console.print(f"[green]レポートを生成しました: {output}[/green]")

    # リソースを解放
    progress_tracker.close()


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    required=True,
    type=click.Path(exists=False),
    help="設定ファイル（TOML）のパス",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="実際にはアルバムを作成せずに実行をシミュレート",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="詳細な出力を表示",
)
def albums(config_path: str, dry_run: bool, verbose: bool) -> None:
    """
    アルバムを Synology Photos から Immich に移行する

    Synology Photos のデータベースからアルバム情報を取得し、
    Immich にアルバムを作成してアセットを追加します。

    前提条件:
    - 写真/動画の移行（migrate コマンド）が完了していること
    - Synology Photos の PostgreSQL データベースにアクセスできること

    使用例:
        synology-to-immich albums -c config.toml
        synology-to-immich albums -c config.toml --dry-run
        synology-to-immich albums -c config.toml --verbose
    """
    # 設定ファイルの存在確認
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]エラー: 設定ファイルが見つかりません: {config_path}[/red]")
        raise SystemExit(1)

    # 設定を読み込む
    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[red]エラー: 設定ファイルの読み込みに失敗しました: {e}[/red]")
        raise SystemExit(1)

    # Synology DB の設定がない場合はエラー
    if not config.synology_db_host:
        console.print(
            "[red]エラー: Synology DB の設定がありません。"
            "config.toml に [synology_db] セクションを追加してください。[/red]"
        )
        raise SystemExit(1)

    # 開始メッセージを表示
    console.print("[bold blue]アルバム移行を開始します...[/bold blue]")
    if dry_run:
        console.print("[yellow]DRY RUN モード: 実際のアルバム作成は行いません[/yellow]")
    if verbose:
        console.print(f"  Synology DB: {config.synology_db_host}:{config.synology_db_port}")
        console.print(f"  Immich URL: {config.immich_url}")

    # 各コンポーネントを初期化
    # Synology Photos データベースフェッチャー
    synology_fetcher = SynologyAlbumFetcher(
        host=config.synology_db_host,
        port=config.synology_db_port,
        user=config.synology_db_user,
        password=config.synology_db_password,
        database=config.synology_db_name,
    )

    # Immich クライアント
    immich_client = ImmichClient(
        base_url=config.immich_url,
        api_key=config.immich_api_key,
    )

    # 進捗トラッカー
    progress_tracker = ProgressTracker(config.progress_db_path)

    # ログ出力（ログディレクトリは設定ファイルと同じディレクトリ）
    log_dir = config_file.parent / "logs"
    migration_logger = MigrationLogger(log_dir)

    # AlbumMigrator を作成
    migrator = AlbumMigrator(
        synology_fetcher=synology_fetcher,
        immich_client=immich_client,
        progress_tracker=progress_tracker,
        logger=migration_logger,
        dry_run=dry_run,
    )

    # Synology DB に接続してアルバム移行を実行
    try:
        synology_fetcher.connect()
        result = migrator.migrate_albums()
    finally:
        synology_fetcher.close()
        progress_tracker.close()
        migration_logger.close()

    # 結果を表示
    _print_album_result(result, verbose)


def _print_album_result(result: AlbumMigrationResult, verbose: bool) -> None:
    """
    アルバム移行結果を表示する

    Args:
        result: AlbumMigrationResult オブジェクト
        verbose: 詳細表示モードかどうか
    """
    console.print()
    console.print("[bold green]アルバム移行完了[/bold green]")
    console.print()

    # サマリーを表示
    console.print(f"  処理対象: {result.total_albums} アルバム")
    console.print(f"  [green]成功: {result.success_count}[/green]")

    # 失敗やスキップがあれば色付きで表示
    if result.failed_count > 0:
        console.print(f"  [red]失敗: {result.failed_count}[/red]")
    else:
        console.print(f"  失敗: {result.failed_count}")

    if result.skipped_count > 0:
        console.print(f"  [yellow]スキップ（移行済み）: {result.skipped_count}[/yellow]")
    else:
        console.print(f"  スキップ: {result.skipped_count}")


# =============================================================================
# backfill コマンド
# =============================================================================


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True),
    help="設定ファイルのパス",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="実際のアップロードを行わず、対象ファイルを表示するのみ",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="詳細な出力を表示",
)
def backfill(config_path: str, dry_run: bool, verbose: bool) -> None:
    """
    移行漏れを補完する

    DB に記録がないファイルを検出し、Immich に存在すれば
    DB にバックフィル、存在しなければアップロードします。

    使用例:
        synology-to-immich backfill -c config.toml
        synology-to-immich backfill -c config.toml --dry-run
        synology-to-immich backfill -c config.toml --verbose
    """
    # 設定ファイルの存在確認
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]エラー: 設定ファイルが見つかりません: {config_path}[/red]")
        raise SystemExit(1)

    # 設定を読み込む
    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[red]エラー: 設定ファイルの読み込みに失敗しました: {e}[/red]")
        raise SystemExit(1)

    # 各コンポーネントを初期化
    progress_tracker = ProgressTracker(config.progress_db_path)

    # FileReader を初期化
    if config.is_smb_source:
        file_reader = SmbFileReader(
            smb_url=config.source,
            username=config.smb_user,
            password=config.smb_password,
        )
    else:
        file_reader = LocalFileReader(Path(config.source))

    # Immich クライアントを初期化
    immich_client = ImmichClient(
        base_url=config.immich_url,
        api_key=config.immich_api_key,
    )

    # Backfiller を初期化
    backfiller = Backfiller(
        progress_tracker=progress_tracker,
        immich_client=immich_client,
        file_reader=file_reader,
    )

    console.print("[bold blue]移行漏れの補完を開始します...[/bold blue]")
    if dry_run:
        console.print("[yellow]DRY RUN モード: 実際のアップロードは行いません[/yellow]")

    # 1. ソースファイルを取得
    console.print("\n[bold]1. ソースファイルを取得中...[/bold]")
    source_files = list(file_reader.list_files())
    console.print(f"  ソースファイル数: {len(source_files)}")

    # 2. DB に記録がないファイルを検出
    console.print("\n[bold]2. DB 未記録ファイルを検出中...[/bold]")
    unrecorded = backfiller.find_unrecorded_files(source_files)
    console.print(f"  未記録ファイル数: {len(unrecorded)}")

    # source_files はもう不要なのでメモリを解放
    del source_files

    if not unrecorded:
        console.print("\n[green]補完対象のファイルがありません。すべて記録済みです。[/green]")
        progress_tracker.close()
        return

    # 3. Immich に存在するか確認
    console.print("\n[bold]3. Immich 存在確認中...[/bold]")
    existing, missing = backfiller.check_immich_existence(unrecorded)
    console.print(f"  Immich に存在（バックフィル対象）: {len(existing)}")
    console.print(f"  Immich に不存在（アップロード対象）: {len(missing)}")

    # unrecorded はもう不要なのでメモリを解放
    del unrecorded

    if verbose:
        if existing:
            console.print("\n[cyan]バックフィル対象ファイル:[/cyan]")
            for item in existing[:10]:
                console.print(f"    {item['file_info'].path}")
            if len(existing) > 10:
                console.print(f"    ... 他 {len(existing) - 10} 件")

        if missing:
            console.print("\n[yellow]アップロード対象ファイル:[/yellow]")
            for f in missing[:10]:
                console.print(f"    {f.path}")
            if len(missing) > 10:
                console.print(f"    ... 他 {len(missing) - 10} 件")

    if dry_run:
        console.print("\n[yellow]DRY RUN 完了。実際の処理は行いませんでした。[/yellow]")
        progress_tracker.close()
        return

    # 4. バックフィル実行
    if existing:
        console.print("\n[bold]4. バックフィル実行中...[/bold]")
        backfill_count = backfiller.backfill_existing(existing)
        console.print(f"  [green]バックフィル完了: {backfill_count} 件[/green]")

    # 5. アップロード実行
    if missing:
        console.print("\n[bold]5. アップロード実行中...[/bold]")
        uploaded, failed = backfiller.upload_missing(missing)
        console.print(f"  [green]アップロード成功: {uploaded} 件[/green]")
        if failed > 0:
            console.print(f"  [red]アップロード失敗: {failed} 件[/red]")

    # 結果サマリー
    console.print("\n[bold green]補完完了！[/bold green]")

    progress_tracker.close()


# =============================================================================
# verify-albums コマンド
# =============================================================================


@main.command("verify-albums")
@click.option(
    "-c",
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True),
    help="設定ファイルのパス",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    default="album_verification_report.json",
    type=click.Path(),
    help="出力 JSON ファイルのパス（デフォルト: album_verification_report.json）",
)
@click.option(
    "--progress-file",
    "progress_file",
    default="album_verification_progress.json",
    type=click.Path(),
    help="進捗ファイルのパス（再開用）",
)
@click.option(
    "--batch-size",
    "batch_size",
    default=100,
    type=int,
    help="バッチサイズ（デフォルト: 100）",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="詳細な出力を表示",
)
def verify_albums(
    config_path: str,
    output_path: str,
    progress_file: str,
    batch_size: int,
    verbose: bool,
) -> None:
    """
    アルバム単位で移行結果を検証する

    Synology Photos のアルバムと Immich のアルバムを比較し、
    ファイル数とハッシュが一致しているかを検証します。
    再開可能。

    出力は JSON 形式のレポートファイルです。

    使用例:
        synology-to-immich verify-albums -c config.toml
        synology-to-immich verify-albums -c config.toml -o report.json
        synology-to-immich verify-albums -c config.toml --verbose
    """
    # 設定ファイルの存在確認
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]エラー: 設定ファイルが見つかりません: {config_path}[/red]")
        raise SystemExit(1)

    # 設定を読み込む
    try:
        config = load_config(config_file)
    except Exception as e:
        console.print(f"[red]エラー: 設定ファイルの読み込みに失敗しました: {e}[/red]")
        raise SystemExit(1)

    # Synology DB の設定がない場合はエラー
    if not config.synology_db_host:
        console.print(
            "[red]エラー: Synology DB の設定がありません。"
            "config.toml に [synology_db] セクションを追加してください。[/red]"
        )
        raise SystemExit(1)

    # 開始メッセージを表示
    console.print("[bold blue]アルバム検証を開始します...[/bold blue]")
    if verbose:
        console.print(f"  Synology DB: {config.synology_db_host}:{config.synology_db_port}")
        console.print(f"  Immich URL: {config.immich_url}")
        console.print(f"  バッチサイズ: {batch_size}")

    # 各コンポーネントを初期化
    # Synology Photos データベースフェッチャー
    synology_fetcher = SynologyAlbumFetcher(
        host=config.synology_db_host,
        port=config.synology_db_port,
        user=config.synology_db_user,
        password=config.synology_db_password,
        database=config.synology_db_name,
    )

    # Immich クライアント
    immich_client = ImmichClient(
        base_url=config.immich_url,
        api_key=config.immich_api_key,
    )

    # 進捗トラッカー
    progress_tracker = ProgressTracker(config.progress_db_path)

    # FileReader を初期化（ハッシュ計算用）
    if config.is_smb_source:
        file_reader = SmbFileReader(
            smb_url=config.source,
            username=config.smb_user,
            password=config.smb_password,
        )
    else:
        file_reader = LocalFileReader(Path(config.source))

    # AlbumVerifier を作成
    verifier = AlbumVerifier(
        synology_fetcher=synology_fetcher,
        immich_client=immich_client,
        progress_tracker=progress_tracker,
        file_reader=file_reader,
    )

    # Synology DB に接続して検証を実行
    try:
        synology_fetcher.connect()
        report = verifier.verify(
            output_file=output_path,
            progress_file=progress_file,
            batch_size=batch_size,
        )
    finally:
        synology_fetcher.close()
        progress_tracker.close()

    # 結果を表示
    _print_album_verification_result(report, verbose)


def _print_album_verification_result(report, verbose: bool) -> None:
    """
    アルバム検証結果を表示する
    """
    console.print()
    console.print("[bold green]アルバム検証完了[/bold green]")
    console.print()

    # サマリーを表示
    console.print(f"  Synology アルバム数: {report.total_synology_albums}")
    console.print(f"  Immich アルバム数: {report.total_immich_albums}")
    console.print(f"  [green]マッチしたアルバム: {report.matched_albums}[/green]")

    if report.unmatched_synology_albums > 0:
        console.print(f"  [yellow]Synology のみ: {report.unmatched_synology_albums}[/yellow]")
    if report.unmatched_immich_albums > 0:
        console.print(f"  [yellow]Immich のみ: {report.unmatched_immich_albums}[/yellow]")

    # 差分があるアルバムの数
    with_differences = sum(
        1 for r in report.album_results
        if r.missing_in_immich or r.extra_in_immich or r.hash_mismatches
    )
    if with_differences > 0:
        console.print(f"  [red]差分があるアルバム: {with_differences}[/red]")

    if verbose:
        # Synology のみのアルバム
        if report.synology_only:
            console.print()
            console.print("[yellow]Synology のみのアルバム:[/yellow]")
            for name in report.synology_only[:10]:
                console.print(f"    {name}")
            if len(report.synology_only) > 10:
                console.print(f"    ... 他 {len(report.synology_only) - 10} 件")

        # Immich のみのアルバム
        if report.immich_only:
            console.print()
            console.print("[yellow]Immich のみのアルバム:[/yellow]")
            for name in report.immich_only[:10]:
                console.print(f"    {name}")
            if len(report.immich_only) > 10:
                console.print(f"    ... 他 {len(report.immich_only) - 10} 件")


# このファイルが直接実行された場合 (python __main__.py)
# または python -m synology_to_immich で実行された場合に
# main() 関数を呼び出す
if __name__ == "__main__":
    main()
