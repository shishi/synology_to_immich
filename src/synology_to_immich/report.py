"""
レポート生成モジュール

移行結果のレポートを Markdown 形式で出力する。
このモジュールは以下の機能を提供する：

- 移行サマリーの生成
- 失敗ファイルのリスト出力
- 未対応形式のリスト出力
- アルバム移行状況の出力

レポートは後で見返しやすいように Markdown 形式で出力される。
"""

from datetime import datetime
from pathlib import Path

from synology_to_immich.progress import FileStatus, ProgressTracker


class ReportGenerator:
    """
    移行結果のレポートを生成するクラス

    ProgressTracker から統計情報とファイル一覧を取得して、
    Markdown 形式のレポートファイルを生成する。

    使用例:
        # ProgressTracker を初期化
        tracker = ProgressTracker(Path("progress.db"))

        # レポートを生成
        generator = ReportGenerator(progress_tracker=tracker)
        generator.generate(Path("migration_report.md"))

        # 結果: migration_report.md が作成される

    Attributes:
        progress_tracker: 進捗情報を保持する ProgressTracker インスタンス
    """

    def __init__(self, progress_tracker: ProgressTracker) -> None:
        """
        ReportGenerator を初期化する

        Args:
            progress_tracker: 移行進捗を管理する ProgressTracker インスタンス
        """
        self._progress_tracker = progress_tracker

    def generate(self, output_path: Path) -> None:
        """
        レポートをファイルに出力する

        指定されたパスに Markdown 形式のレポートファイルを生成する。
        レポートには以下のセクションが含まれる：
        - タイトルと生成日時
        - サマリー（処理件数と成功率）
        - 失敗ファイルのリスト
        - 未対応形式のリスト

        Args:
            output_path: 出力ファイルのパス
        """
        # 各セクションを生成
        sections = [
            self._generate_header(),
            self._generate_summary(),
            self._generate_failed_list(),
            self._generate_unsupported_list(),
            self._generate_album_list(),
        ]

        # セクションを結合してファイルに書き込み
        content = "\n".join(sections)
        output_path.write_text(content, encoding="utf-8")

    def _generate_header(self) -> str:
        """
        レポートのヘッダーを生成する

        タイトルと生成日時を含む。

        Returns:
            ヘッダーの Markdown 文字列
        """
        # 現在日時を ISO 形式で取得
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return f"""# Synology to Immich 移行レポート

生成日時: {now}
"""

    def _generate_summary(self) -> str:
        """
        サマリーセクションを生成する

        処理件数と成功率をテーブル形式で表示する。

        Returns:
            サマリーの Markdown 文字列
        """
        # 統計情報を取得
        stats = self._progress_tracker.get_statistics()

        total = stats["total"]
        success = stats["success"]
        failed = stats["failed"]
        unsupported = stats["unsupported"]

        # 成功率を計算（ゼロ除算を避ける）
        if total > 0:
            success_rate = (success / total) * 100
        else:
            success_rate = 0.0

        return f"""## サマリー

| 項目 | 件数 |
|------|------|
| 処理対象 | {total} |
| 成功 | {success} |
| 失敗 | {failed} |
| 未対応 | {unsupported} |

成功率: {success_rate:.1f}%
"""

    def _generate_failed_list(self) -> str:
        """
        失敗ファイルリストセクションを生成する

        失敗したファイルのパスとエラーメッセージをテーブル形式で表示する。

        Returns:
            失敗リストの Markdown 文字列
        """
        # 失敗ファイルを取得
        failed_files = self._progress_tracker.get_files_by_status(FileStatus.FAILED)

        # ヘッダー
        lines = ["## 失敗ファイル", ""]

        # 失敗がない場合
        if not failed_files:
            lines.append("失敗したファイルはありません。")
            return "\n".join(lines)

        # テーブルヘッダー
        lines.append("| ファイル | エラー |")
        lines.append("|----------|--------|")

        # 各ファイルの行を追加
        for file_info in failed_files:
            source_path = file_info.get("source_path", "")
            error_message = file_info.get("error_message", "")
            # エラーメッセージがない場合は「不明」と表示
            if not error_message:
                error_message = "不明"
            # パイプ文字をエスケープ（テーブルが崩れないように）
            error_message = error_message.replace("|", "\\|")
            lines.append(f"| {source_path} | {error_message} |")

        lines.append("")  # 空行を追加
        return "\n".join(lines)

    def _generate_unsupported_list(self) -> str:
        """
        未対応形式リストセクションを生成する

        未対応形式のファイルパスと MIME タイプをテーブル形式で表示する。

        Returns:
            未対応リストの Markdown 文字列
        """
        # 未対応ファイルを取得
        unsupported_files = self._progress_tracker.get_files_by_status(FileStatus.UNSUPPORTED)

        # ヘッダー
        lines = ["## 未対応形式", ""]

        # 未対応がない場合
        if not unsupported_files:
            lines.append("未対応形式のファイルはありません。")
            return "\n".join(lines)

        # テーブルヘッダー
        lines.append("| ファイル | MIME タイプ |")
        lines.append("|----------|-------------|")

        # 各ファイルの行を追加
        for file_info in unsupported_files:
            source_path = file_info.get("source_path", "")
            mime_type = file_info.get("mime_type", "不明")
            if not mime_type:
                mime_type = "不明"
            lines.append(f"| {source_path} | {mime_type} |")

        lines.append("")  # 空行を追加
        return "\n".join(lines)

    def _generate_album_list(self) -> str:
        """
        アルバム移行状況セクションを生成する

        移行したアルバムの一覧をテーブル形式で表示する。

        Returns:
            アルバムリストの Markdown 文字列
        """
        # アルバム情報を取得
        albums = self._progress_tracker.get_all_albums()

        # ヘッダー
        lines = ["## アルバム移行状況", ""]

        # アルバムがない場合
        if not albums:
            lines.append("移行したアルバムはありません。")
            return "\n".join(lines)

        # テーブルヘッダー
        lines.append("| Synology ID | アルバム名 | Immich ID |")
        lines.append("|-------------|------------|-----------|")

        # 各アルバムの行を追加
        for album in albums:
            synology_id = album.get("synology_album_id", "")
            album_name = album.get("synology_album_name", "")
            immich_id = album.get("immich_album_id", "")
            lines.append(f"| {synology_id} | {album_name} | {immich_id} |")

        lines.append("")  # 空行を追加
        return "\n".join(lines)
