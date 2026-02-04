"""
進捗管理（ProgressTracker）のテスト

SQLite を使った移行進捗の追跡機能をテストする。
このモジュールは、どのファイルが移行済みか、失敗したか、
未対応形式だったかを追跡するために使用される。
"""

from pathlib import Path

# テスト対象のモジュールをインポート
from synology_to_immich.progress import FileStatus, ProgressTracker


class TestProgressTracker:
    """
    ProgressTracker クラスのテスト

    ProgressTracker は SQLite データベースを使って、
    写真の移行進捗を管理するクラス。
    """

    def test_create_database(self, tmp_path: Path):
        """
        データベースが正しく作成されることを確認

        tmp_path は pytest が提供する一時ディレクトリ。
        テスト終了後に自動的にクリーンアップされる。
        """
        # Arrange（準備）: データベースファイルのパスを設定
        db_path = tmp_path / "progress.db"

        # Act（実行）: ProgressTracker を初期化
        tracker = ProgressTracker(db_path)

        # Assert（検証）: データベースファイルが作成されたことを確認
        assert db_path.exists(), "データベースファイルが作成されていない"
        tracker.close()

    def test_record_success(self, tmp_path: Path):
        """
        成功した移行を記録できることを確認

        ファイルが正常に Immich に移行された場合、
        その情報をデータベースに記録できる。
        """
        # Arrange: データベースを準備
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # Act: 移行成功を記録
        tracker.record_file(
            source_path="/photos/IMG_001.jpg",  # 元ファイルのパス
            source_hash="abc123",  # ファイルのハッシュ値
            source_size=1024,  # ファイルサイズ（バイト）
            source_mtime="2024-01-15T10:30:00",  # 元ファイルの更新日時
            immich_asset_id="asset-uuid-001",  # Immich でのアセット ID
            status=FileStatus.SUCCESS,  # 移行ステータス：成功
        )

        # Assert: 記録されたデータを確認
        result = tracker.get_file("/photos/IMG_001.jpg")
        assert result is not None, "記録されたファイルが取得できない"
        assert result["source_hash"] == "abc123", "ハッシュ値が一致しない"
        assert result["status"] == "success", "ステータスが 'success' でない"
        tracker.close()

    def test_is_migrated(self, tmp_path: Path):
        """
        ファイルが移行済みかどうかを判定できることを確認

        is_migrated() は、ファイルが SUCCESS ステータスで
        記録されているかどうかを返す。
        """
        # Arrange: データベースを準備し、1つのファイルを移行済みとして記録
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)
        tracker.record_file(
            source_path="/photos/IMG_001.jpg",
            source_hash="abc123",
            source_size=1024,
            source_mtime="2024-01-15T10:30:00",
            immich_asset_id="asset-uuid-001",
            status=FileStatus.SUCCESS,
        )

        # Act & Assert: 移行済み判定を確認
        # 記録したファイルは True を返す
        assert (
            tracker.is_migrated("/photos/IMG_001.jpg") is True
        ), "移行済みファイルが True を返さない"
        # 記録していないファイルは False を返す
        assert (
            tracker.is_migrated("/photos/IMG_002.jpg") is False
        ), "未移行ファイルが False を返さない"
        tracker.close()

    def test_get_pending_files(self, tmp_path: Path):
        """
        未移行ファイルを取得できることを確認

        get_files_by_status() で、特定のステータスのファイル一覧を
        取得できる。リトライ対象（FAILED）のファイルを抽出するのに使う。
        """
        # Arrange: 成功1件、失敗1件を記録
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # 成功したファイル
        tracker.record_file(
            source_path="/photos/success.jpg",
            source_hash="abc",
            source_size=100,
            source_mtime="2024-01-15",
            immich_asset_id="asset-1",
            status=FileStatus.SUCCESS,
        )
        # 失敗したファイル
        tracker.record_file(
            source_path="/photos/failed.jpg",
            source_hash="def",
            source_size=200,
            source_mtime="2024-01-15",
            immich_asset_id=None,  # 失敗したので Immich ID はない
            status=FileStatus.FAILED,
        )

        # Act: 失敗したファイルの一覧を取得
        failed_files = tracker.get_files_by_status(FileStatus.FAILED)

        # Assert: 失敗したファイルが1件だけ取得できる
        assert len(failed_files) == 1, "失敗ファイルの数が正しくない"
        assert (
            failed_files[0]["source_path"] == "/photos/failed.jpg"
        ), "失敗ファイルのパスが正しくない"
        tracker.close()

    def test_get_files_by_status_returns_sorted_by_source_path(self, tmp_path: Path):
        """
        get_files_by_status() は source_path でソートされた結果を返す

        再開可能な検証機能で、常に同じ順序でファイルを取得できる必要がある。
        SQLite は ORDER BY なしでは順序を保証しないため、
        source_path でソートして一定の順序を保証する。
        """
        # Arrange: 順序がバラバラになるように3つのファイルを登録
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # わざと順序をバラバラに登録
        paths = ["/photos/c.jpg", "/photos/a.jpg", "/photos/b.jpg"]
        for i, path in enumerate(paths):
            tracker.record_file(
                source_path=path,
                source_hash=f"hash-{i}",
                source_size=100,
                source_mtime="2024-01-15",
                immich_asset_id=f"asset-{i}",
                status=FileStatus.SUCCESS,
            )

        # Act
        files = tracker.get_files_by_status(FileStatus.SUCCESS)

        # Assert: source_path でソートされている
        assert len(files) == 3
        assert files[0]["source_path"] == "/photos/a.jpg"
        assert files[1]["source_path"] == "/photos/b.jpg"
        assert files[2]["source_path"] == "/photos/c.jpg"
        tracker.close()

    def test_get_statistics(self, tmp_path: Path):
        """
        統計情報を取得できることを確認

        get_statistics() で、移行全体の進捗状況を把握できる。
        """
        # Arrange: 3つのファイルを異なるステータスで記録
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # SUCCESS が2件、FAILED が1件になるようにループ
        statuses = [FileStatus.SUCCESS, FileStatus.SUCCESS, FileStatus.FAILED]
        for i, status in enumerate(statuses):
            tracker.record_file(
                source_path=f"/photos/IMG_{i}.jpg",
                source_hash=f"hash{i}",
                source_size=100,
                source_mtime="2024-01-15",
                # 成功した場合のみ Immich ID を設定
                immich_asset_id=f"asset-{i}" if status == FileStatus.SUCCESS else None,
                status=status,
            )

        # Act: 統計情報を取得
        stats = tracker.get_statistics()

        # Assert: 各統計値を確認
        assert stats["total"] == 3, "合計ファイル数が正しくない"
        assert stats["success"] == 2, "成功ファイル数が正しくない"
        assert stats["failed"] == 1, "失敗ファイル数が正しくない"
        assert stats["unsupported"] == 0, "未対応ファイル数が正しくない"
        tracker.close()


class TestProgressTrackerAlbums:
    """
    ProgressTracker のアルバム管理テスト

    Synology Photos のアルバムと Immich のアルバムの対応関係を
    追跡する機能をテストする。
    """

    def test_record_album(self, tmp_path: Path):
        """
        アルバムを記録できることを確認

        アルバムの情報（Synology ID、名前、Immich ID）を
        データベースに保存し、後で取得できることをテストする。
        """
        # Arrange（準備）: データベースを初期化
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # Act（実行）: アルバム情報を記録
        tracker.record_album(
            synology_album_id=123,  # Synology Photos でのアルバム ID
            synology_album_name="Vacation 2024",  # アルバム名
            immich_album_id="immich-album-uuid",  # Immich でのアルバム ID
        )

        # Assert（検証）: 記録されたアルバムを取得して確認
        album = tracker.get_album_by_synology_id(123)
        assert album is not None, "アルバムが取得できない"
        assert album["synology_album_name"] == "Vacation 2024", "アルバム名が一致しない"
        assert album["immich_album_id"] == "immich-album-uuid", "Immich ID が一致しない"
        tracker.close()

    def test_get_all_albums(self, tmp_path: Path):
        """
        全アルバムを取得できることを確認

        複数のアルバムを記録した後、すべてのアルバムを
        一度に取得できることをテストする。
        """
        # Arrange: データベースを準備し、2つのアルバムを記録
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)
        tracker.record_album(1, "Album A", "immich-a")  # アルバム1
        tracker.record_album(2, "Album B", "immich-b")  # アルバム2

        # Act: 全アルバムを取得
        albums = tracker.get_all_albums()

        # Assert: 2件のアルバムが取得できる
        assert len(albums) == 2, "アルバム数が正しくない"
        tracker.close()

    def test_record_album_upsert(self, tmp_path: Path):
        """
        同じアルバム ID で更新（UPSERT）できることを確認

        既に存在するアルバム ID で record_album() を呼び出した場合、
        重複エラーにならず、既存のレコードが更新される。
        これにより、アルバム名の変更や Immich ID の更新に対応できる。
        """
        # Arrange（準備）: データベースを初期化
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # Act（実行）: 同じ synology_album_id で2回記録
        # 最初の挿入
        tracker.record_album(
            synology_album_id=1,
            synology_album_name="Album A",
            immich_album_id="immich-a",
        )
        # 同じ ID で更新（UPSERT）
        tracker.record_album(
            synology_album_id=1,
            synology_album_name="Album A Updated",  # 名前を変更
            immich_album_id="immich-a-new",  # Immich ID も変更
        )

        # Assert（検証）: 更新された値が取得できる
        album = tracker.get_album_by_synology_id(1)
        assert album is not None, "アルバムが取得できない"
        assert album["synology_album_name"] == "Album A Updated", "アルバム名が更新されていない"
        assert album["immich_album_id"] == "immich-a-new", "Immich ID が更新されていない"

        # Assert: 重複が作成されていないことを確認
        all_albums = tracker.get_all_albums()
        assert len(all_albums) == 1, "重複アルバムが作成されている（1件であるべき）"

        tracker.close()


class TestProgressTrackerErrorLogging:
    """
    ProgressTracker のエラーログ機能テスト

    移行が失敗したとき、エラーメッセージが正しくデータベースに
    記録されることをテストする。これにより、後からエラー原因を
    分析することができる。
    """

    def test_record_failure_with_error_message(self, tmp_path: Path):
        """
        失敗時にエラーメッセージが記録されることを確認

        移行が失敗した場合、何が原因で失敗したかを
        error_message として記録できる。これは後で
        エラー分析やリトライの判断に使用される。
        """
        # Arrange（準備）: データベースを初期化
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # Act（実行）: 失敗を記録（エラーメッセージ付き）
        tracker.record_file(
            source_path="/photos/corrupted.jpg",
            source_hash="abc123",
            source_size=1024,
            source_mtime="2024-01-15T10:30:00",
            immich_asset_id=None,  # 失敗したので Immich ID はない
            status=FileStatus.FAILED,
            error_message="Immich API returned 400: Invalid image format",  # エラーメッセージ！
        )

        # Assert（検証）: エラーメッセージが記録されていることを確認
        result = tracker.get_file("/photos/corrupted.jpg")
        assert result is not None, "記録されたファイルが取得できない"
        assert result["status"] == "failed", "ステータスが 'failed' でない"
        assert result["error_message"] == "Immich API returned 400: Invalid image format", (
            "エラーメッセージが正しく記録されていない"
        )
        tracker.close()

    def test_record_unsupported_with_error_message(self, tmp_path: Path):
        """
        未対応形式のエラーメッセージが記録されることを確認

        Immich が対応していないファイル形式の場合も、
        その理由をエラーメッセージとして記録する。
        """
        # Arrange
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # Act: 未対応形式を記録（エラーメッセージ付き）
        tracker.record_file(
            source_path="/photos/document.pdf",
            source_hash="xyz789",
            source_size=5000,
            source_mtime="2024-01-15T10:30:00",
            immich_asset_id=None,
            status=FileStatus.UNSUPPORTED,
            error_message="Unsupported file type: application/pdf",
        )

        # Assert: エラーメッセージが記録されていることを確認
        result = tracker.get_file("/photos/document.pdf")
        assert result is not None
        assert result["status"] == "unsupported"
        assert result["error_message"] == "Unsupported file type: application/pdf"
        tracker.close()

    def test_get_failed_files_with_errors(self, tmp_path: Path):
        """
        失敗したファイルとエラーメッセージを一覧取得できることを確認

        get_failed_files_with_errors() で、失敗と未対応のファイルを
        エラーメッセージ付きで取得できる。これにより、移行後の
        エラー分析レポートを生成できる。
        """
        # Arrange: 成功1件、失敗2件（エラーメッセージ付き）を記録
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # 成功したファイル（エラーなし）
        tracker.record_file(
            source_path="/photos/success.jpg",
            source_hash="abc",
            source_size=100,
            source_mtime="2024-01-15",
            immich_asset_id="asset-1",
            status=FileStatus.SUCCESS,
        )
        # 失敗したファイル（エラーメッセージあり）
        tracker.record_file(
            source_path="/photos/failed1.jpg",
            source_hash="def",
            source_size=200,
            source_mtime="2024-01-15",
            immich_asset_id=None,
            status=FileStatus.FAILED,
            error_message="Connection timeout after 30s",
        )
        # 未対応形式のファイル（エラーメッセージあり）
        tracker.record_file(
            source_path="/photos/unsupported.raw",
            source_hash="ghi",
            source_size=300,
            source_mtime="2024-01-15",
            immich_asset_id=None,
            status=FileStatus.UNSUPPORTED,
            error_message="RAW format not supported by Immich",
        )

        # Act: 失敗したファイルの一覧を取得
        failed_files = tracker.get_failed_files_with_errors()

        # Assert: 失敗と未対応の2件が取得でき、エラーメッセージが含まれる
        assert len(failed_files) == 2, "失敗/未対応ファイルの数が正しくない"

        # パスでソートして順序を固定
        failed_files_sorted = sorted(failed_files, key=lambda x: x["source_path"])

        assert failed_files_sorted[0]["source_path"] == "/photos/failed1.jpg"
        assert failed_files_sorted[0]["error_message"] == "Connection timeout after 30s"

        assert failed_files_sorted[1]["source_path"] == "/photos/unsupported.raw"
        assert failed_files_sorted[1]["error_message"] == "RAW format not supported by Immich"

        tracker.close()

    def test_success_has_no_error_message(self, tmp_path: Path):
        """
        成功時はエラーメッセージがないことを確認

        成功した移行にはエラーメッセージがなく、
        get_failed_files_with_errors() の結果にも含まれない。
        """
        # Arrange
        db_path = tmp_path / "progress.db"
        tracker = ProgressTracker(db_path)

        # Act: 成功を記録（error_message は指定しない）
        tracker.record_file(
            source_path="/photos/good.jpg",
            source_hash="abc123",
            source_size=1024,
            source_mtime="2024-01-15T10:30:00",
            immich_asset_id="asset-uuid-001",
            status=FileStatus.SUCCESS,
        )

        # Assert: エラーメッセージが None であることを確認
        result = tracker.get_file("/photos/good.jpg")
        assert result is not None
        assert result["error_message"] is None, "成功したファイルにエラーメッセージがある"

        # Assert: 失敗ファイル一覧に含まれないことを確認
        failed_files = tracker.get_failed_files_with_errors()
        assert len(failed_files) == 0, "成功ファイルが失敗一覧に含まれている"

        tracker.close()
