# アルバム検証機能 実装計画 (TDD)

## Phase 1: Immich API 拡張 (immich.py)

### Test 1.1: get_albums() - アルバム一覧取得
- [x] `test_get_albums` - 正常系: アルバム一覧を取得できる
- [x] `test_get_albums_empty` - 空の場合も空リストを返す

### Test 1.2: get_album_assets() - アルバム内アセット取得
- [x] `test_get_album_assets` - 正常系: アセット一覧を取得できる
- [x] `test_get_album_assets_not_found` - アルバムが見つからない場合は空リスト

## Phase 2: AlbumVerifier クラス (album_verify.py)

### Test 2.1: データクラス
- [x] `test_album_comparison_result_creation` - AlbumComparisonResult の作成
- [x] `test_album_verification_report_creation` - AlbumVerificationReport の作成

### Test 2.2: アルバムマッチング
- [x] `test_match_by_name` - 名前でマッチング
- [x] `test_match_by_migration_record` - 移行記録でマッチング
- [x] `test_match_combined` - 両方でマッチング（名前 + ID）

### Test 2.3: アルバム内容比較
- [x] `test_compare_album_perfect_match` - 完全一致
- [x] `test_compare_album_missing_files` - Immich に欠損ファイルあり
- [x] `test_compare_album_extra_files` - Immich に余分なファイルあり（missing_files で一緒にテスト済み）
- [x] `test_compare_album_hash_mismatch` - ハッシュ不一致

### Test 2.4: バッチ処理
- [x] `test_batch_processing` - 100件ごとのバッチ処理

### Test 2.5: 再開機能
- [x] `test_resume_from_progress_file` - 進捗ファイルから再開
- [x] `test_save_progress` - 進捗を保存

### Test 2.6: レポート出力
- [x] `test_generate_json_report` - JSON レポート生成

## Phase 3: CLI コマンド (__main__.py)

### Test 3.1: verify-albums コマンド
- [x] `test_verify_albums_command` - コマンド実行（モック）

## Phase 4: パス変換機能追加（バグ修正）

### Test 4.1: DB パスから SMB パスへの変換
- [x] `test_convert_db_path_to_smb_path` - DB パス（/PhotoLibrary/...）を SMB UNC パスに変換
- [x] `test_convert_db_path_preserves_nested_folders` - ネストされたフォルダ構造が保持される
- [x] `test_compare_album_uses_converted_paths` - 比較処理でパス変換が使われる

## 完了！🎉
