# Synology to Immich Migration Tool

A CLI tool for safely migrating photos, videos, and albums from Synology Photos to Immich.

## Features

- **migrate** - Transfer files from Synology Photos to Immich (SMB/local supported)
- **verify** - Verify migration results with SHA1 hash (resumable)
- **verify-albums** - Verify album contents with SHA1 hash (resumable, reports in JSON/Markdown)
- **backfill** - Detect and recover missing migrations
- **retry** - Retry failed uploads
- **albums** - Migrate album information
- **status** - View migration progress

## Requirements

- [Nix](https://nixos.org/download.html) (package manager)
- [direnv](https://direnv.net/) (recommended: automatic environment switching)

## Setup

```bash
git clone https://github.com/shishi/synology_to_immich.git
cd synology_to_immich
direnv allow
uv sync
```

## Usage

### 1. Create config file

```bash
cp config.toml.example config.toml
# Edit config.toml with your settings
```

### 2. Run migration

```bash
# Run migration
synology-to-immich migrate -c config.toml

# Dry run (no actual upload)
synology-to-immich migrate -c config.toml --dry-run
```

### 3. Verify files

```bash
synology-to-immich verify -c config.toml
```

### 4. Verify albums

```bash
# Verify all album contents with SHA1 hash
synology-to-immich verify-albums -c config.toml

# Output: album_verification_report.json, album_verification_report.md
```

### 5. Backfill if needed

```bash
# Check missing files (dry run)
synology-to-immich backfill -c config.toml --dry-run

# Backfill missing files
synology-to-immich backfill -c config.toml
```

## Disclaimer

- **No Warranty**: This tool is provided AS-IS. We are not responsible for any data loss or damage.
- **Use at Your Own Risk**: Always backup your data before migration.
- **Limited Testing**: Only tested in the author's environment. No guarantee of working in other environments.

## License

MIT

---

# 日本語

Synology Photos から Immich へ写真・動画・アルバムを安全に移行する CLI ツール。

## 機能

- **migrate** - Synology Photos → Immich への移行（SMB/ローカル対応）
- **verify** - SHA1 ハッシュで移行結果を検証（再開可能）
- **verify-albums** - アルバム内容を SHA1 ハッシュで検証（再開可能、JSON/Markdown レポート出力）
- **backfill** - 移行漏れを検出して補完
- **retry** - 失敗したファイルの再試行
- **albums** - アルバム情報の移行
- **status** - 進捗状況の表示

## 必要なもの

- [Nix](https://nixos.org/download.html)（パッケージマネージャー）
- [direnv](https://direnv.net/)（推奨：自動環境切り替え）

## セットアップ

```bash
git clone https://github.com/shishi/synology_to_immich.git
cd synology_to_immich
direnv allow
uv sync
```

## 使い方

### 1. 設定ファイルを作成

```bash
cp config.toml.example config.toml
# config.toml を編集
```

### 2. 移行を実行

```bash
# 移行を実行
synology-to-immich migrate -c config.toml

# ドライラン（実際のアップロードなし）
synology-to-immich migrate -c config.toml --dry-run
```

### 3. ファイル検証

```bash
synology-to-immich verify -c config.toml
```

### 4. アルバム検証

```bash
# 全アルバムの内容を SHA1 ハッシュで検証
synology-to-immich verify-albums -c config.toml

# 出力: album_verification_report.json, album_verification_report.md
```

### 5. 漏れがあれば補完

```bash
# 漏れを確認（ドライラン）
synology-to-immich backfill -c config.toml --dry-run

# 漏れを補完
synology-to-immich backfill -c config.toml
```

## 注意事項

- **無保証**: このツールは AS-IS（現状有姿）で提供されます。データ損失等いかなる損害についても責任を負いません。
- **自己責任**: 必ず移行前にバックアップを取得してください。
- **テスト環境**: 作者の環境でのみテストしています。他の環境での動作は保証しません。

## ライセンス

MIT
