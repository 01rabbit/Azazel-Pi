# 実機 E2E 実行手順（概要）

このドキュメントは、管理者が許可した実機環境で Azazel-Edge の E2E を安全に実行するための簡潔な手順を示します。

前提条件:
- 実行ユーザーが sudo 権限を持っていること
- テストに使う IP が影響範囲の少ない、許可済みのアドレスであること（例: 10.0.0.250）

手順:

1. スナップショット取得（実行前）

```bash
sudo nft list ruleset > runtime/nft_snapshot.before.txt
sudo tc qdisc show dev <iface> > runtime/tc_snapshot.before.txt
```

2. テストイベント注入（AzazelDaemon を利用）

- 既存の `runtime/e2e_run.py` スクリプトを利用して、AzazelDaemon.process_event() を呼び出します。
- PYTHONPATH が必要な場合は `sudo env PYTHONPATH=$(pwd) python3 runtime/e2e_run.py` のように実行します。

3. decisions ログの確認

```bash
# 実行結果を確認
cat runtime/e2e_decisions.log
```

4. クリーンアップ

```bash
sudo env PYTHONPATH=$(pwd) python3 runtime/e2e_cleanup.py
```

5. スナップショット取得（実行後）と差分確認

```bash
sudo nft list ruleset > runtime/nft_snapshot.after.txt
sudo tc qdisc show dev <iface> > runtime/tc_snapshot.after.txt
# 差分
diff -u runtime/nft_snapshot.before.txt runtime/nft_snapshot.after.txt > runtime/nft_diff.txt || true
diff -u runtime/tc_snapshot.before.txt runtime/tc_snapshot.after.txt > runtime/tc_diff.txt || true
```

注意:
- `tc`/`nft` のコマンドはシステムに依存します。特に `tc` の場合はインターフェース名の扱いに注意してください。
- 実行前にバックアップを取り、必要であれば手動でのリストア手順を用意してください。
