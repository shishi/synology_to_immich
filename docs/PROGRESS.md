# Synology to Immich Migration Tool - 実装進捗

> **最終更新**: 2026-01-31
> **ブランチ**: `feature/migration`
> **Worktree**: `.worktrees/feature-migration`

## 概要

Synology Photos から Immich へ写真・動画・アルバムを安全に移行する Python CLI ツール。

### 接続先情報

| サービス | URL/パス |
|---------|---------|
| NAS (SMB) | `smb://100.71.227.37/homes/shishi/Photo` |
| Synology Photos | `100.71.227.37:62081` |
| Immich | `100.71.227.37:2283` |
| Synology DB | PostgreSQL（アルバム情報用） |

---

## 完了済みタスク (Phase 1-5)

### Phase 1: プロジェクト構造とコア基盤

| Task | 内容 | 状態 |
|------|------|------|
| Task 1 | プロジェクト構造の作成 | ✅ 完了 |
| Task 2 | 設定ファイル読み込み（Config クラス） | ✅ 完了 |

### Phase 2: Progress Tracker（進捗管理）

| Task | 内容 | 状態 |
|------|------|------|
| Task 3 | ProgressTracker - 基本 CRUD | ✅ 完了 |
| Task 4 | ProgressTracker - アルバム管理 | ✅ 完了 |

### Phase 3: ファイル読み取り

| Task | 内容 | 状態 |
|------|------|------|
| Task 5 | LocalFileReader - ローカルファイルスキャン | ✅ 完了 |
| Task 6 | SmbFileReader - SMB ファイルアクセス | ✅ 完了 |

### Phase 4: Immich クライアント

| Task | 内容 | 状態 |
|------|------|------|
| Task 7 | ImmichClient - 基本アップロード | ✅ 完了 |

### Phase 5: ロギング

| Task | 内容 | 状態 |
|------|------|------|
| Task 8 | ログシステムの実装 | ✅ 完了 |

---

### Phase 6: メイン移行ロジック

| Task | 内容 | 状態 |
|------|------|------|
| Task 9 | Live Photos ペアリングロジック | ✅ 完了 |
| Task 10 | Synology PostgreSQL からのアルバム取得 | ✅ 完了 |
| Task 11 | Migrator クラス（メインオーケストレーション） | ✅ 完了 |
| Task 12 | CLI コマンド（migrate） | ✅ 完了 |
| Task 13 | CLI コマンド（verify） | ✅ 完了 |
| Task 14 | CLI コマンド（status, retry） | ✅ 完了 |
| Task 15 | 最終レポート出力 | ✅ 完了 |

---

## 🎉 実装完了！

**全 15 タスク完了、107 テスト全パス！**

---

## ファイル構造

```
.worktrees/feature-migration/
├── docs/
│   ├── plans/
│   │   ├── 2025-01-31-synology-to-immich-design.md  # 設計ドキュメント
│   │   └── 2025-01-31-implementation-plan.md       # TDD 実装プラン
│   └── PROGRESS.md                                 # この進捗ドキュメント
├── src/
│   └── synology_to_immich/
│       ├── __init__.py          # パッケージ初期化、__version__
│       ├── __main__.py          # CLI エントリーポイント (click) - migrate, verify, status, retry, report
│       ├── config.py            # Config クラス、TOML 読み込み
│       ├── progress.py          # ProgressTracker (SQLite)
│       ├── immich.py            # ImmichClient (httpx)
│       ├── logging.py           # MigrationLogger (複数ログファイル)
│       ├── live_photo.py        # LivePhotoPairer, LivePhotoGroup
│       ├── synology_db.py       # SynologyAlbumFetcher (PostgreSQL)
│       ├── migrator.py          # Migrator, MigrationResult
│       ├── verify.py            # Verifier, VerificationResult
│       ├── report.py            # ReportGenerator
│       └── readers/
│           ├── __init__.py      # FileReader エクスポート
│           ├── base.py          # FileInfo, FileReader ABC
│           ├── local.py         # LocalFileReader
│           └── smb.py           # SmbFileReader, parse_smb_url
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # pytest フィクスチャ
│   ├── test_config.py           # 5 テスト
│   ├── test_progress.py         # 8 テスト
│   ├── test_readers.py          # 16 テスト
│   ├── test_immich.py           # 14 テスト
│   ├── test_logging.py          # 3 テスト
│   ├── test_live_photo.py       # 9 テスト
│   ├── test_synology_db.py      # 8 テスト
│   ├── test_migrator.py         # 9 テスト
│   ├── test_cli.py              # 20 テスト
│   ├── test_verify.py           # 8 テスト
│   └── test_report.py           # 7 テスト
├── flake.nix                    # Nix 開発環境
├── flake.lock
├── pyproject.toml               # プロジェクト設定
└── .gitignore
```

---

## テスト状況

```
Total: 107 テスト全パス
```

| テストファイル | テスト数 | 内容 |
|--------------|---------|------|
| test_config.py | 5 | Config クラス、TOML 読み込み |
| test_progress.py | 8 | ProgressTracker (ファイル + アルバム + UPSERT) |
| test_readers.py | 16 | LocalFileReader (9) + SmbFileReader (7) |
| test_immich.py | 14 | ImmichClient (アップロード、アルバム、エラー処理) |
| test_logging.py | 3 | MigrationLogger (ログファイル作成、unsupported) |
| test_live_photo.py | 9 | LivePhotoPairer (ペアリング、大文字小文字) |
| test_synology_db.py | 8 | SynologyAlbumFetcher (PostgreSQL接続、アルバム取得) |
| test_migrator.py | 9 | Migrator (オーケストレーション、バッチ処理) |
| test_cli.py | 20 | CLI コマンド (migrate, verify, status, retry, report) |
| test_verify.py | 8 | Verifier (検証ロジック、詳細チェック) |
| test_report.py | 7 | ReportGenerator (Markdown レポート出力) |

---

## 実装済みコンポーネント詳細

### 1. Config (`config.py`)

TOML 設定ファイルの読み込みと設定管理。

```python
from synology_to_immich.config import Config, load_config

config = load_config(Path("config.toml"))
print(config.source)           # SMB URL or ローカルパス
print(config.is_smb_source)    # True if SMB URL
```

**主要フィールド:**
- `source`: 移行元パス
- `immich_url`, `immich_api_key`: Immich 接続情報
- `smb_user`, `smb_password`: SMB 認証情報
- `dry_run`, `batch_size`, `batch_delay`: 移行オプション
- `synology_db_*`: Synology PostgreSQL 接続情報

### 2. ProgressTracker (`progress.py`)

SQLite で移行進捗を追跡。

```python
from synology_to_immich.progress import ProgressTracker, FileStatus

tracker = ProgressTracker(Path("progress.db"))

# ファイル記録
tracker.record_file(
    source_path="/photos/IMG_001.jpg",
    source_hash="abc123",
    source_size=1024,
    source_mtime="2024-01-15T10:30:00",
    immich_asset_id="asset-uuid",
    status=FileStatus.SUCCESS,
)

# アルバム記録
tracker.record_album(
    synology_album_id=123,
    synology_album_name="Vacation 2024",
    immich_album_id="immich-album-uuid",
)

# 統計取得
stats = tracker.get_statistics()
# {"total": 100, "success": 95, "failed": 3, "unsupported": 2}
```

### 3. FileReader (`readers/`)

ローカルと SMB からファイルを読み取り。

```python
from synology_to_immich.readers import LocalFileReader, SmbFileReader

# ローカル
reader = LocalFileReader("/path/to/photos")
for file_info in reader.list_files():
    print(file_info.path, file_info.size, file_info.mtime)
    data = reader.read_file(file_info.path)

# SMB
reader = SmbFileReader(
    "smb://192.168.1.1/homes/user/Photo",
    username="user",
    password="pass",
)
for file_info in reader.list_files():
    # @eaDir, .DS_Store, Thumbs.db は自動除外
    data = reader.read_file(file_info.path)
```

### 4. ImmichClient (`immich.py`)

Immich API との通信。

```python
from synology_to_immich.immich import ImmichClient

client = ImmichClient(
    base_url="http://localhost:2283",
    api_key="your-api-key",
)

# アップロード
result = client.upload_asset(
    file_data=b"...",
    filename="photo.jpg",
    created_at="2024-01-15T10:30:00",
    live_photo_data=b"...",  # オプション
)
if result.success:
    print(f"Asset ID: {result.asset_id}")
elif result.is_unsupported:
    print(f"Unsupported: {result.error_message}")

# アルバム
album_id = client.create_album("Vacation 2024")
client.add_assets_to_album(album_id, ["asset-1", "asset-2"])
```

### 5. MigrationLogger (`logging.py`)

複数ログファイルへの出力。

```python
from synology_to_immich.logging import MigrationLogger
from pathlib import Path

logger = MigrationLogger(Path("./logs"))

logger.info("移行開始", total_files=1000)
logger.error("アップロード失敗", file_path="/photos/fail.jpg")
logger.log_unsupported(
    file_path="/photos/unknown.xyz",
    file_size=1024,
    mime_type="application/octet-stream",
    error_message="Unsupported file type",
)
logger.close()
```

**出力ファイル:**
- `migration_YYYYMMDD_HHMMSS.log`: 全ログ
- `errors_YYYYMMDD_HHMMSS.log`: エラーのみ
- `unsupported_YYYYMMDD_HHMMSS.log`: 未対応形式（詳細フォーマット）

---

## 開発環境のセットアップ

### 環境構成

このプロジェクトは **uv + Nix** の併用構成：

| ツール | 役割 | ファイル |
|-------|------|---------|
| **uv** | Python パッケージ管理、仮想環境 | `uv.lock`, `.venv/` |
| **Nix** | システムツール（psql など） | `flake.nix` |

```
.venv/           # uv が管理するプロジェクトローカル仮想環境
uv.lock          # 依存関係ロックファイル（再現性保証）
pyproject.toml   # プロジェクト設定
flake.nix        # Nix 開発環境（PostgreSQL クライアント等）
```

### 1. Worktree に移動

```bash
cd /home/shishi/dev/src/github.com/shishi/synology_to_immich/.worktrees/feature-migration
```

### 2. コマンド実行方法（2通り）

#### 方法 A: uv run（推奨）

```bash
# テスト実行
uv run pytest -v

# フォーマット
uv run black .

# リント
uv run ruff check .

# 型チェック
uv run mypy src/
```

#### 方法 B: Nix 開発環境

```bash
# Nix シェルに入る（psql など追加ツールが使える）
nix develop

# その後は直接コマンド実行
pytest -v
black .
```

### 3. テスト実行

```bash
# 全テスト（uv）
uv run pytest -v

# 特定のテスト
uv run pytest tests/test_config.py -v

# カバレッジ付き
uv run pytest --cov=synology_to_immich --cov-report=html
```

### 4. コード品質チェック

```bash
uv run black .          # フォーマット
uv run ruff check .     # リント
uv run mypy src/        # 型チェック
```

### 5. 依存関係の追加

```bash
# 本番依存関係を追加
uv add パッケージ名

# 開発依存関係を追加
uv add --dev パッケージ名

# 依存関係を同期
uv sync
```

---

## Git コミット履歴

```
067f568 feat: add MigrationLogger for logging system
a0eb3eb feat: add ImmichClient for Immich API communication
b325ba0 feat: add SmbFileReader for SMB file access
220fb6d feat: add LocalFileReader for recursive file scanning
5f4b9b3 test: add UPSERT test for record_album()
9187d75 feat: add album tracking to ProgressTracker
8c2ad24 feat: add ProgressTracker for SQLite-based migration progress tracking
1f2de68 feat: add Config class for loading settings from TOML files
894f013 feat: initialize project structure with pyproject.toml and test setup
d578026 docs: add detailed TDD implementation plan
cf4a968 chore: add flake.lock
92c62d6 build: add flake.nix for Python development environment
e2d551a chore: add .gitignore
0446147 docs: add Synology Photos to Immich migration tool design
```

---

## Claude への再開指示

### コピペ用テンプレート

```
synology_to_immich プロジェクトの続きをやりたい。

worktree: /home/shishi/dev/src/github.com/shishi/synology_to_immich/.worktrees/feature-migration

docs/PROGRESS.md を読んで現状を把握して、Phase 6 (Task 9〜) を続けて。
Subagent-Driven Development で進めてね。
```

### 短縮版

```
synology_to_immich の続き。docs/PROGRESS.md 見て Task 9 から再開して。
```

---

## 再開手順（人間用）

### Phase 6 の実装を続ける場合

1. この worktree に移動:
   ```bash
   cd /home/shishi/dev/src/github.com/shishi/synology_to_immich/.worktrees/feature-migration
   ```

2. 実装プランを確認:
   ```bash
   cat docs/plans/2025-01-31-implementation-plan.md
   ```

3. Task 9 (Live Photos ペアリング) から再開

4. Subagent-Driven Development を使用:
   - 各タスクごとに Implementer サブエージェントを起動
   - Spec Compliance Review → Code Quality Review の 2 段階レビュー

### 注意事項

- **タイムゾーン問題**: `datetime.fromtimestamp()` はローカル時間を使用（設計通り）
- **Live Photos**: ZIP にしない（PhotoMigrator のバグを回避）
- **@eaDir 除外**: Synology の隠しフォルダは自動的にスキップ
- **未対応形式**: 専用ログファイルに詳細出力

---

## 関連ドキュメント

- [設計ドキュメント](./plans/2025-01-31-synology-to-immich-design.md)
- [TDD 実装プラン](./plans/2025-01-31-implementation-plan.md)
