# Synology to Immich Migration Tool

Synology Photos から Immich へ写真・動画・アルバムを安全に移行する CLI ツール。

## 機能

- **migrate** - Synology Photos → Immich への移行（SMB/ローカル対応）
- **verify** - SHA1 ハッシュで移行結果を検証（再開可能）
- **backfill** - 移行漏れを検出して補完（バックフィル＋アップロード）
- **retry** - 失敗したファイルの再試行
- **albums** - アルバム情報の移行
- **status** - 進捗状況の表示

## 必要なもの

- [Nix](https://nixos.org/download.html)（パッケージマネージャー）
- [direnv](https://direnv.net/)（推奨：自動環境切り替え）

## セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/shishi/synology_to_immich.git
cd synology_to_immich

# feature/migration ブランチに移動（または worktree を使用）
git checkout feature/migration

# direnv を有効化（初回のみ）
direnv allow

# 依存関係をインストール
uv sync
```

## 開発

### direnv を使う場合（推奨）

direnv を設定すると、ディレクトリに入るだけで自動的に Nix 環境が有効になる。

```bash
# ディレクトリに入ると自動で環境が有効化される
cd synology_to_immich

# そのままコマンド実行できる
uv run pytest -v
uv run black .
```

### direnv を使わない場合

```bash
# 手動で Nix 環境に入る
nix develop

# その中でコマンド実行
uv run pytest -v
```

### よく使うコマンド

```bash
uv run pytest -v           # テスト実行
uv run black .             # フォーマット
uv run ruff check .        # リント
uv run mypy src/           # 型チェック
```

## 使い方

### 1. 設定ファイルを作成

```toml
# config.toml
source = "smb://192.168.1.100/photos"  # または "/path/to/photos"
smb_user = "user"
smb_password = "password"

immich_url = "http://localhost:2283"
immich_api_key = "your-api-key"

progress_db_path = "progress.db"
```

### 2. 移行を実行

```bash
# 移行を実行
synology-to-immich migrate -c config.toml

# ドライランで確認
synology-to-immich migrate -c config.toml --dry-run
```

### 3. 検証

```bash
# SHA1 ハッシュで検証（再開可能）
synology-to-immich verify -c config.toml
```

### 4. 漏れがあれば補完

```bash
# 漏れを確認（ドライラン）
synology-to-immich backfill -c config.toml --dry-run

# 漏れを補完
synology-to-immich backfill -c config.toml
```

### 依存関係の追加

```bash
# 本番依存関係
uv add パッケージ名

# 開発依存関係
uv add --dev パッケージ名
```

## プロジェクト構造

```
├── src/synology_to_immich/   # メインコード
│   ├── __main__.py           # CLI エントリーポイント
│   ├── config.py             # 設定管理
│   ├── progress.py           # 進捗追跡 (SQLite)
│   ├── immich.py             # Immich API クライアント
│   ├── migrator.py           # 移行ロジック
│   ├── verify.py             # ハッシュ検証
│   ├── backfill.py           # 移行漏れ補完
│   ├── logging.py            # ロギング
│   └── readers/              # ファイル読み取り
│       ├── local.py          # ローカルファイル
│       └── smb.py            # SMB ファイル
├── tests/                    # テスト
├── docs/                     # ドキュメント
│   ├── PROGRESS.md           # 実装進捗
│   └── plans/                # 設計・実装プラン
├── flake.nix                 # Nix 開発環境
├── pyproject.toml            # プロジェクト設定
└── uv.lock                   # 依存関係ロック
```

## ドキュメント

- [実装進捗](docs/PROGRESS.md) - 完了タスクと次のステップ
- [設計ドキュメント](docs/plans/2025-01-31-synology-to-immich-design.md)
- [TDD 実装プラン](docs/plans/2025-01-31-implementation-plan.md)

## ライセンス

MIT
