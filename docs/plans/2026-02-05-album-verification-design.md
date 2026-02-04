# アルバム検証機能 設計書

## 概要

Synology Photos のアルバムと Immich のアルバムを比較し、
ファイル数とハッシュが一致しているかを検証する機能。

## 要件

| 項目 | 内容 |
|------|------|
| 検証内容 | ファイル数 + SHA1 ハッシュ |
| 出力形式 | JSON |
| マッチング方法 | 名前ベース + 移行記録ベース 両方 |
| 再開機能 | あり |
| メモリ管理 | 100件ごとにバッチ処理・解放 |

## アーキテクチャ

```
┌─────────────────┐     ┌──────────────────┐
│  Synology DB    │     │    Immich API    │
│  (PostgreSQL)   │     │                  │
└────────┬────────┘     └────────┬─────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌──────────────────┐
│ SynologyAlbum   │     │ get_albums()     │ ← 新規追加
│ Fetcher         │     │ get_album_assets │ ← 新規追加
└────────┬────────┘     └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │   AlbumVerifier       │ ← 新規作成
         │   (album_verify.py)   │
         └───────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌──────────────────┐
│ 名前マッチング  │     │ ID マッチング    │
│ 結果            │     │ 結果             │
└────────┬────────┘     └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │   JSON レポート出力   │
         └───────────────────────┘
```

## Immich API 拡張

`immich.py` に追加するメソッド:

### get_albums()

```python
def get_albums(self) -> list[dict]:
    """
    全アルバムを取得する

    Returns:
        list[dict]: アルバム情報のリスト
            - id: アルバム ID (UUID)
            - albumName: アルバム名
            - assetCount: アセット数
    """
    # GET /api/albums
```

### get_album_assets()

```python
def get_album_assets(self, album_id: str) -> list[dict]:
    """
    アルバム内のアセット一覧を取得する

    Returns:
        list[dict]: アセット情報のリスト
            - id: アセット ID
            - originalFileName: ファイル名
            - checksum: SHA1 (base64)
    """
    # GET /api/albums/{album_id}
```

## データクラス

```python
@dataclass
class AlbumComparisonResult:
    """1つのアルバムの比較結果"""
    synology_album_name: str
    synology_album_id: int
    immich_album_id: Optional[str]
    immich_album_name: Optional[str]

    synology_file_count: int
    immich_asset_count: int

    missing_in_immich: list[str]
    extra_in_immich: list[str]
    hash_mismatches: list[str]

    match_type: str  # "name" | "id" | "both" | "unmatched"

@dataclass
class AlbumVerificationReport:
    """検証レポート全体"""
    timestamp: str

    total_synology_albums: int
    total_immich_albums: int
    matched_albums: int
    unmatched_synology_albums: int
    unmatched_immich_albums: int

    album_results: list[AlbumComparisonResult]
    synology_only: list[str]
    immich_only: list[str]
```

## JSON レポート形式

```json
{
  "timestamp": "2026-02-05T12:34:56",
  "summary": {
    "total_synology_albums": 25,
    "total_immich_albums": 27,
    "matched_albums": 23,
    "perfect_match": 20,
    "with_differences": 3,
    "synology_only": 2,
    "immich_only": 4
  },
  "unmatched_albums": {
    "synology_only": ["旅行2020", "古い写真"],
    "immich_only": ["手動作成1", "テスト", "Favorites", "新アルバム"]
  },
  "album_comparisons": [
    {
      "synology_name": "家族写真",
      "synology_id": 42,
      "immich_name": "家族写真",
      "immich_id": "abc-123-def",
      "match_type": "both",
      "synology_file_count": 150,
      "immich_asset_count": 148,
      "status": "different",
      "differences": {
        "missing_in_immich": ["path/to/file1.jpg", "path/to/file2.jpg"],
        "extra_in_immich": [],
        "hash_mismatches": []
      }
    }
  ]
}
```

## メモリ管理

100件ごとにバッチ処理:

```python
for i in range(0, len(synology_files), batch_size):
    batch_paths = synology_files[i:i + batch_size]

    # 100件分のファイル内容をまとめて読み込み
    batch_contents = []
    for file_path in batch_paths:
        content = self._file_reader.read_file(file_path)
        batch_contents.append((file_path, content))

    # 100件分のハッシュ計算 & 比較
    batch_results = []
    for file_path, content in batch_contents:
        source_hash = self._compute_hash(content)
        result = self._compare(file_path, source_hash, asset_checksums)
        batch_results.append(result)

    # 100件分の結果を書き出し
    self._write_batch_results(batch_results)

    # 100件分まとめて解放
    del batch_contents
    del batch_results
```

## CLI コマンド

```bash
uv run python -m synology_to_immich verify-albums \
  --db-host 192.168.1.100 \
  --db-user synofoto \
  --db-password xxx \
  --immich-url http://immich:2283 \
  --immich-api-key xxx \
  --source-path /volume1/photo \
  --output report.json
```

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `immich.py` | `get_albums()`, `get_album_assets()` 追加 |
| `album_verify.py` | 新規作成（AlbumVerifier クラス） |
| `__main__.py` | `verify-albums` コマンド追加 |
