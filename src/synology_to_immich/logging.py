"""
ログシステムモジュール

移行ツール用のログ管理機能を提供する。
以下の3種類のログファイルを出力する:
- migration_YYYYMMDD_HHMMSS.log: すべてのログ（DEBUG以上）
- errors_YYYYMMDD_HHMMSS.log: エラーログのみ
- unsupported_YYYYMMDD_HHMMSS.log: 未対応ファイルの詳細ログ

使用例:
    from synology_to_immich.logging import MigrationLogger

    logger = MigrationLogger(Path("./logs"))
    logger.info("移行を開始します")
    logger.error("アップロード失敗", file_path="/photos/test.jpg")
    logger.log_unsupported("/photos/test.xyz", 1024, "application/octet-stream", "Unsupported")
    logger.close()
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any


class MigrationLogger:
    """
    移行ツール用のロガークラス

    このクラスは Python の標準 logging モジュールを使用して、
    複数のログファイルに同時に出力する機能を提供する。

    属性:
        log_dir (Path): ログファイルを保存するディレクトリ
        timestamp (str): ログファイル名に使用するタイムスタンプ
        logger (logging.Logger): メインのロガーオブジェクト
    """

    def __init__(self, log_dir: Path) -> None:
        """
        MigrationLogger を初期化する

        引数:
            log_dir: ログファイルを保存するディレクトリのパス
                     存在しない場合は自動的に作成される
        """
        # ログディレクトリを Path オブジェクトに変換（念のため）
        self.log_dir = Path(log_dir)

        # ディレクトリが存在しない場合は作成
        # parents=True: 親ディレクトリも含めて作成
        # exist_ok=True: 既に存在していてもエラーにしない
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # タイムスタンプを生成（ファイル名に使用）
        # 例: "20240115_103000"
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ロガーを設定
        self._setup_loggers()

    def _setup_loggers(self) -> None:
        """
        ロガーとファイルハンドラを設定する

        内部メソッド（_ で始まるのは Python の慣習で「プライベート」を意味する）
        """
        # メインのロガーを作成
        # __name__ を使わず、固有の名前を使用して他のロガーと衝突を避ける
        self.logger = logging.getLogger(f"migration_{self.timestamp}")
        self.logger.setLevel(logging.DEBUG)  # DEBUG 以上のすべてのログを処理

        # 既存のハンドラをクリア（再初期化時の重複を防ぐ）
        self.logger.handlers.clear()

        # ログのフォーマットを設定
        # %(asctime)s: タイムスタンプ
        # %(levelname)s: ログレベル（DEBUG, INFO, WARNING, ERROR）
        # %(message)s: ログメッセージ
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",  # 日付フォーマット
        )

        # === 1. migration_*.log: 全ログ用ハンドラ ===
        self.migration_log_path = self.log_dir / f"migration_{self.timestamp}.log"
        self.migration_handler = logging.FileHandler(
            self.migration_log_path,
            encoding="utf-8",  # 日本語対応
        )
        self.migration_handler.setLevel(logging.DEBUG)  # DEBUG 以上すべて
        self.migration_handler.setFormatter(formatter)
        self.logger.addHandler(self.migration_handler)

        # === 2. errors_*.log: エラー専用ハンドラ ===
        self.errors_log_path = self.log_dir / f"errors_{self.timestamp}.log"
        self.errors_handler = logging.FileHandler(
            self.errors_log_path,
            encoding="utf-8",
        )
        self.errors_handler.setLevel(logging.ERROR)  # ERROR 以上のみ
        self.errors_handler.setFormatter(formatter)
        self.logger.addHandler(self.errors_handler)

        # === 3. unsupported_*.log: 未対応ファイル用（直接ファイル書き込み） ===
        self.unsupported_log_path = self.log_dir / f"unsupported_{self.timestamp}.log"
        # 未対応ファイルログは特殊フォーマットなので、直接ファイルを開く
        self.unsupported_file = open(
            self.unsupported_log_path,
            "w",
            encoding="utf-8",
        )

    def _format_size(self, size_bytes: int) -> str:
        """
        バイト数を人間が読みやすい形式に変換する

        引数:
            size_bytes: ファイルサイズ（バイト単位）

        戻り値:
            人間が読みやすい形式の文字列（例: "1.5 MB"）

        例:
            _format_size(1024) -> "1.0 KB"
            _format_size(1048576) -> "1.0 MB"
            _format_size(500) -> "500 B"
        """
        # サイズの単位を定義
        # 1 KB = 1024 bytes, 1 MB = 1024 KB, ...
        units = ["B", "KB", "MB", "GB", "TB"]

        size = float(size_bytes)
        unit_index = 0

        # サイズが 1024 以上の場合、次の単位に変換
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        # バイト単位の場合は整数で表示、それ以外は小数点1桁
        if unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        else:
            return f"{size:.1f} {units[unit_index]}"

    def _format_message(self, message: str, **kwargs: Any) -> str:
        """
        ログメッセージをフォーマットする

        追加のキーワード引数があれば、メッセージに追記する。

        引数:
            message: 基本のログメッセージ
            **kwargs: 追加情報（例: file_path="/path/to/file"）

        戻り値:
            フォーマットされたメッセージ
        """
        if not kwargs:
            return message

        # 追加情報を "key=value" 形式で結合
        extras = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        return f"{message} | {extras}"

    def debug(self, message: str, **kwargs: Any) -> None:
        """
        DEBUG レベルのログを出力する

        開発時のデバッグ情報を記録するために使用。
        migration_*.log にのみ出力される。

        引数:
            message: ログメッセージ
            **kwargs: 追加情報（例: file_path="/path/to/file"）
        """
        self.logger.debug(self._format_message(message, **kwargs))

    def info(self, message: str, **kwargs: Any) -> None:
        """
        INFO レベルのログを出力する

        一般的な情報を記録するために使用。
        例: ファイルのアップロード開始、完了など。

        引数:
            message: ログメッセージ
            **kwargs: 追加情報
        """
        self.logger.info(self._format_message(message, **kwargs))

    def warning(self, message: str, **kwargs: Any) -> None:
        """
        WARNING レベルのログを出力する

        警告（エラーではないが注意が必要な状況）を記録する。
        例: ファイルのスキップ、リトライなど。

        引数:
            message: ログメッセージ
            **kwargs: 追加情報
        """
        self.logger.warning(self._format_message(message, **kwargs))

    def error(self, message: str, **kwargs: Any) -> None:
        """
        ERROR レベルのログを出力する

        エラーを記録する。migration_*.log と errors_*.log の
        両方に出力される。

        引数:
            message: エラーメッセージ
            **kwargs: 追加情報（例: file_path="/path/to/file"）
        """
        self.logger.error(self._format_message(message, **kwargs))

    def log_unsupported(
        self,
        file_path: str,
        file_size: int,
        mime_type: str,
        error_message: str,
    ) -> None:
        """
        未対応ファイルの詳細情報をログに記録する

        Immich が対応していないファイル形式を検出した際に、
        詳細情報を unsupported_*.log に記録する。

        引数:
            file_path: ファイルのパス
            file_size: ファイルサイズ（バイト単位）
            mime_type: 試行した MIME タイプ
            error_message: Immich からのエラーメッセージ

        出力例:
            ============================================================
            ⚠️  UNSUPPORTED FORMAT DETECTED
            ============================================================
            File: /photos/test.xyz
            Size: 1.0 KB
            Attempted MIME: application/octet-stream
            Immich Response: "Unsupported file type"
            Timestamp: 2024-01-15 10:30:00
            ============================================================
        """
        # 現在時刻を取得
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 人間が読みやすいサイズに変換
        readable_size = self._format_size(file_size)

        # 詳細フォーマットでログを出力
        separator = "=" * 60
        log_entry = f"""
{separator}
⚠️  UNSUPPORTED FORMAT DETECTED
{separator}
File: {file_path}
Size: {readable_size}
Attempted MIME: {mime_type}
Immich Response: "{error_message}"
Timestamp: {current_time}
{separator}
"""
        # unsupported_*.log に書き込み
        self.unsupported_file.write(log_entry)
        self.unsupported_file.flush()  # 即座にファイルに書き込む

        # migration_*.log にも WARNING として記録
        self.warning(
            "Unsupported file format",
            file_path=file_path,
            mime_type=mime_type,
        )

    def close(self) -> None:
        """
        すべてのファイルハンドラを閉じる

        ログ出力が完了したら、このメソッドを呼び出して
        リソースを解放する。with 文を使わない場合は必須。
        """
        # ロガーのハンドラを閉じる
        for handler in self.logger.handlers[:]:  # [:] でコピーを作成
            handler.close()
            self.logger.removeHandler(handler)

        # unsupported_*.log を閉じる
        if hasattr(self, "unsupported_file") and self.unsupported_file:
            self.unsupported_file.close()
