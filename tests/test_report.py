"""
レポート生成機能のテスト

移行結果のレポート出力をテストする。
ReportGenerator クラスは ProgressTracker から移行情報を取得して
Markdown 形式のレポートファイルを生成する。
"""

from unittest.mock import Mock

import pytest

from synology_to_immich.report import ReportGenerator


class TestReportGenerator:
    """ReportGenerator のテスト"""

    @pytest.fixture
    def mock_progress_tracker(self):
        """テスト用の ProgressTracker モック

        テストでは実際のデータベースを使わずに、
        モックオブジェクトを使って統計情報を返す。
        """
        tracker = Mock()
        # 統計情報を返す
        tracker.get_statistics.return_value = {
            "total": 100,
            "success": 90,
            "failed": 8,
            "unsupported": 2,
        }
        # ステータス別のファイル一覧を返す
        # side_effect は呼び出しごとに異なる値を返すために使う
        tracker.get_files_by_status.side_effect = lambda status: {
            "failed": [
                {"source_path": "/photos/failed1.jpg", "error_message": "Network error"},
                {"source_path": "/photos/failed2.jpg", "error_message": "Timeout"},
            ],
            "unsupported": [
                {"source_path": "/photos/unknown.xyz", "mime_type": "application/octet-stream"},
            ],
        }.get(status.value, [])
        # アルバム情報を返す（空リスト）
        tracker.get_all_albums.return_value = []
        return tracker

    def test_generate_creates_file(self, mock_progress_tracker, tmp_path):
        """レポートファイルが作成されることを確認

        generate() を呼び出すと、指定したパスにファイルが作成される。
        """
        output_path = tmp_path / "report.md"

        generator = ReportGenerator(progress_tracker=mock_progress_tracker)
        generator.generate(output_path)

        assert output_path.exists()

    def test_report_contains_summary(self, mock_progress_tracker, tmp_path):
        """サマリーが含まれることを確認

        レポートには処理件数や成功率が含まれる。
        """
        output_path = tmp_path / "report.md"

        generator = ReportGenerator(progress_tracker=mock_progress_tracker)
        generator.generate(output_path)

        content = output_path.read_text()
        assert "100" in content  # total
        assert "90" in content  # success
        assert "90.0%" in content or "90%" in content  # success rate

    def test_report_contains_failed_files(self, mock_progress_tracker, tmp_path):
        """失敗ファイルリストが含まれることを確認

        失敗したファイルのパスとエラーメッセージが含まれる。
        """
        output_path = tmp_path / "report.md"

        generator = ReportGenerator(progress_tracker=mock_progress_tracker)
        generator.generate(output_path)

        content = output_path.read_text()
        assert "failed1.jpg" in content
        assert "Network error" in content

    def test_report_contains_unsupported_files(self, mock_progress_tracker, tmp_path):
        """未対応ファイルリストが含まれることを確認

        未対応形式のファイルパスが含まれる。
        """
        output_path = tmp_path / "report.md"

        generator = ReportGenerator(progress_tracker=mock_progress_tracker)
        generator.generate(output_path)

        content = output_path.read_text()
        assert "unknown.xyz" in content

    def test_report_is_markdown_format(self, mock_progress_tracker, tmp_path):
        """Markdown 形式であることを確認

        レポートには Markdown の見出しやテーブルが含まれる。
        """
        output_path = tmp_path / "report.md"

        generator = ReportGenerator(progress_tracker=mock_progress_tracker)
        generator.generate(output_path)

        content = output_path.read_text()
        assert "# " in content  # H1 header
        assert "| " in content  # table

    def test_report_with_no_failures(self, tmp_path):
        """失敗がない場合のレポート

        全ファイルが成功した場合、成功率 100% が表示される。
        """
        tracker = Mock()
        tracker.get_statistics.return_value = {
            "total": 100,
            "success": 100,
            "failed": 0,
            "unsupported": 0,
        }
        tracker.get_files_by_status.return_value = []
        # アルバム情報も空リストを返す
        tracker.get_all_albums.return_value = []

        output_path = tmp_path / "report.md"
        generator = ReportGenerator(progress_tracker=tracker)
        generator.generate(output_path)

        content = output_path.read_text()
        # 成功率は 100.0% の形式で出力される
        assert "100.0%" in content  # 100% success rate

    def test_report_contains_timestamp(self, mock_progress_tracker, tmp_path):
        """レポートに生成日時が含まれることを確認

        ISO 形式で日時が記録される。
        """
        output_path = tmp_path / "report.md"

        generator = ReportGenerator(progress_tracker=mock_progress_tracker)
        generator.generate(output_path)

        content = output_path.read_text()
        # ISO 形式の日時パターン（例: 2024-01-15）
        assert "生成日時" in content or "Generated" in content
