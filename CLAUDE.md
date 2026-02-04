# Claude への指示

このプロジェクトで作業する際の注意事項。

## プロジェクト概要

Synology Photos → Immich 移行ツール。

主要コマンド:
- `migrate` - 移行実行
- `verify` - SHA1 ハッシュ検証（再開可能）
- `backfill` - 移行漏れ補完
- `retry` - 失敗ファイルの再試行

## 開発環境

**重要: このプロジェクトは Nix + uv で管理されている。**

### コマンド実行

```bash
# direnv が有効なら直接実行可能
uv run pytest -v
uv run black .
uv run ruff check .

# または nix develop -c を使う
nix develop -c uv run pytest -v
```

### 依存関係の追加

```bash
uv add パッケージ名
uv add --dev パッケージ名
```

### やってはいけないこと

- `python` や `pytest` を直接実行しない（Nix 環境外の Python を使ってしまう）
- `pip install` を使わない（uv で管理）
- `.venv` を手動で作成しない（uv が管理）

## プロジェクト構造

```
src/synology_to_immich/
├── __main__.py    # CLI
├── config.py      # 設定
├── progress.py    # 進捗 DB (SQLite)
├── immich.py      # Immich API
├── migrator.py    # 移行ロジック
├── verify.py      # ハッシュ検証
├── backfill.py    # 移行漏れ補完
└── readers/       # ファイル読み取り
```

## TDD

Kent Beck の TDD に従う：
1. Red: 失敗するテストを書く
2. Green: テストを通す最小限のコードを書く
3. Refactor: リファクタリング

## メモリ管理

大量ファイル処理時は `del` で明示的にメモリを解放：
- ファイルデータは使用後すぐに `del`
- 中間リストも不要になったら `del`

## コミット

- 構造変更と振る舞い変更を分ける
- 全テストがパスしてからコミット
- Conventional Commits 形式（feat:, fix:, chore: など）
