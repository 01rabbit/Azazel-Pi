## Azazel-Pi E2E デモ: Suricata EVE リプレイで検出→評価→遷移→通知を再現する

このドキュメントは E2E デモ用に特化しています。目的は以下のとおりです。

- Suricata EVE イベントをリプレイして、監視パイプラインが検出→AI 評価→モード遷移→enforcer/通知 を通して動く様子を示す。
- デモで使う通知は `configs/monitoring/notify_demo.yaml`（テスト webhook）を使い、本番構成に影響を与えない。
- 最小の操作で自動的に `scan → brute → exploit → ddos` のシーケンスが発生し、最終的に lockdown 相当のモードに到達できることを確認する。

前提と注意
- この手順はローカルのデモ環境を想定します。実際の enforcer (nft/tc) は root 権限で実行されるとネットワークに影響を与えます。デモでは root を使わないか、ネットワークに影響しないテスト環境で実行してください。
-- いくつかのコマンドは azctl の CLI 引数に依存します。実際のサブコマンドは次のオプションをサポートします（`python3 -m azctl.cli <subcommand> --help` を実行して詳細を確認してください）。

   - `serve` の主なオプション:
      - `--config CONFIG`        : 初期化用の設定 YAML
      - `--decisions-log PATH`   : decisions.log 出力先（任意）
      - `--suricata-eve PATH`    : Suricata eve.json のパス（デフォルトは設定から読み取る）
      - `--lan-if IF` / `--wan-if IF`: インターフェース指定

   - `menu` の主なオプション:
      - `--decisions-log PATH`   : decisions.log を指定して表示させる（任意）
      - `--lan-if IF` / `--wan-if IF` : インターフェース指定

   上の例では `--suricata-eve` と `--decisions-log` を使っていますが、環境に合わせて `--help` を参照のうえ適宜置き換えてください。

必要なファイル（このリポジトリで追加済み）
- `scripts/eve_replay.py` — EVE JSON を指定ファイルに周期的に追記してリプレイするスクリプト
- `configs/monitoring/notify_demo.yaml` — デモ用の Mattermost/webhook 設定（安全なテスト先を設定してください）
- `scripts/install_demo_notify.sh` — 既存の `configs/notify.yaml` をバックアップしてデモ用設定をインストールする補助スクリプト
- `scripts/restore_notify.sh` — 既存の notify 設定を復元するスクリプト（デモ後に実行）

準備手順
1) 必要 Python ライブラリをインストール

```bash
pip3 install --user rich requests
```

2) デモ用の notify 設定をインストール（安全のためバックアップされます）

```bash
bash scripts/install_demo_notify.sh
# 成功すると configs/notify.yaml が demo 設定に置き換わります
```

3) EVE リプレイ先ファイルの準備（デフォルトの場所）

```bash
mkdir -p runtime
: > runtime/demo_eve.json   # 空ファイルを作る
```

E2E デモ手順（実行順）
以下は一例の最小オペレーションです。別のターミナルでそれぞれ実行してください。

1. 監視デーモンを起動（Suricata EVE を監視させる）

   想定コマンド（CLI がこれらのオプションを受け取る場合）:

```bash
# 例: decisions.log をカレントに、Suricata EVE を runtime/demo_eve.json に設定
python3 -m azctl.cli serve --suricata-eve runtime/demo_eve.json --decisions-log ./decisions.log
```

   注: `azctl.cli serve` のオプションが異なる場合は、`main_suricata.py` を直接起動して `runtime/demo_eve.json` を監視するようにしてください。目的は監視プロセスが `runtime/demo_eve.json` の追記を読み、評価→enforce→notify を実行することです。

2. TUI（状態表示）を起動

```bash
python3 -m azctl.cli menu --decisions-log ./decisions.log
```

   TUI は decisions.log / 状態を表示します。これで観客に現在モードや決定の遷移を見せられます。

3. EVE リプレイを開始（攻撃シーケンスの注入）

```bash
python3 scripts/eve_replay.py --file runtime/demo_eve.json --interval 5 --loop
```

   - `--interval 5` はイベント間隔（秒）です。`--loop` を付けるとシーケンスを繰り返します。
   - このスクリプトは段階的に検出シグネチャ（scan → brute → exploit → ddos）に見立てた EVE JSON を追加します。

4. 監視の動作観察

- TUI にスコア／モード遷移が表示されることを確認します。
- decisions.log を別ターミナルで tail して、該当の決定（JSON ライン）が追記されることを確認します:

```bash
tail -f ./decisions.log
```

- 通知: `configs/monitoring/notify_demo.yaml` に設定したテスト webhook（例: RequestBin）にポストが届くことを確認します。

期待される流れ（デフォルトデモ）
- EVE シーケンスにより最初は軽度のスキャン検出が入り、AI 評価が一定閾値を越えると警告モードに移行。
- 攻撃シーケンスが進むとスコアが上がり、最終的に lockdown 相当のモードが適用され、enforcer が適切なアクションを実行（実環境では nft/tc を適用）します。

<!-- 追加ツールは削除済み: E2E デモは上記ファイルだけで実行します -->

安全とロールバック
- デモ後は必ず notify 設定を復元してください:

```bash
bash scripts/restore_notify.sh
```

- decisions.log、runtime/demo_eve.json、runtime/demo_mode.json などのデモ生成ファイルは削除して構いません。
- 実際に enforcer を動かす（nft/tc を適用する）場合は root 権限が必要です。本番ネットワークに影響を与えないテスト環境で行ってください。

トラブルシュート
- 何も起きない場合:
  - 監視プロセスが runtime/demo_eve.json を見ていることを確認。パスやオプションが異なる可能性あり。
  - `decisions.log` が別の場所に出力されていないか確認（`azctl.cli` のオプションや `azctl/daemon.py` の設定を確認）。
  - Ollama を使う評価を見せたい場合はローカル Ollama サービスが稼働していること（デフォルト: http://127.0.0.1:11434）を確認。

期待検証チェックリスト（すぐ使える）
- [ ] `scripts/install_demo_notify.sh` を実行してデモ通知を有効にした
- [ ] `python3 -m azctl.cli serve --suricata-eve runtime/demo_eve.json --decisions-log ./decisions.log` を起動した
- [ ] `python3 -m azctl.cli menu --decisions-log ./decisions.log` を起動した
- [ ] `python3 scripts/eve_replay.py --file runtime/demo_eve.json --interval 5 --loop` を起動した
- [ ] TUI と decisions.log に検出・スコア・モード遷移が表示された
- [ ] notify_demo の webhook に通知が届いた

補足（実行環境に応じた微調整）
- `azctl.cli` の `serve`／`menu` の引数名は実装により異なることがあります。もし上記コマンドが通らない場合は `python3 -m azctl.cli --help` でオプションを確認し、`--suricata-eve` や `--decisions-log` に相当するオプションを指定してください。

