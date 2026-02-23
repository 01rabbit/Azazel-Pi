Azazel-Edge: E2E 実行アーティファクト

このディレクトリに保存される典型的なアーティファクトと実行メモ:

- e2e_decisions.log
  - 実機実行で出力された decisions.log の抜粋（JSON 行）
- nft_snapshot.before.txt, nft_snapshot.after.txt, nft_snapshot.cleanup.txt
  - `nft list ruleset` の実行結果（実行前/実行後/クリーンアップ後）
- tc_snapshot.before.txt, tc_snapshot.after.txt, tc_snapshot.cleanup.txt
  - `tc qdisc show dev <iface>` の実行結果（実行前/実行後/クリーンアップ後）
- nft_diff.txt, tc_diff.correct.txt
  - before/after の差分（`diff -u` 出力）

安全な手順（要 root）:

1. 実行前スナップショットを取得
   - sudo nft list ruleset > runtime/nft_snapshot.before.txt
   - sudo tc qdisc show dev <iface> > runtime/tc_snapshot.before.txt
2. テスト用イベントを AzazelDaemon に注入して `process_event()` を呼ぶ
3. decisions.log（runtime/e2e_decisions.log）を確認
4. cleanup: ルールを削除して復旧を確認
   - engine.remove_rules_for_ip(<test_ip>) を呼ぶ
5. 実行後スナップショットを取得して差分を確認

注意事項:
- `nft` / `tc` による変更は即時にネットワークに影響します。必ず実行環境の許可を得てください。
- 実行前にインターフェース名（例: wlan1, eth0）を正しく指定してください。
- 本 README は実行ログを含みません。実際に行った操作は runtime/ 以下のファイルで確認できます。
