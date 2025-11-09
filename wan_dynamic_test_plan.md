# WANダイナミック制御 差分掌握とテスト計画

## 差分掌握
1. **WAN状態ストアの追加**: `azazel_pi/utils/wan_state.py` でアクティブ回線、健全性スコア、候補スナップショットを JSON に永続化する仕組みが追加され、複数コンポーネントが同じ真実のソースを共有できるようになった。
2. **WANマネージャサービス**: 新しい `azctl wan-manager` / `azazel_pi.core.network.wan_manager.WANManager` が複数インターフェースを定期プローブし、最良の回線に切り替えて `bin/azazel-traffic-init.sh`、NAT(`iptables -t nat`)、依存サービス(Suricata/azctl-unified)を再適用することで動的フェイルオーバーを実現する。`systemd/azazel-wan-manager.service` で常駐化。
3. **Suricata起動系の連携**: `systemd/suricata.service` は WAN マネージャに依存し、`azazel_pi/core/network/suricata_wrapper.py` を経由して最新の WAN インターフェースで Suricata を起動する。`azazel-traffic-init.sh` も `WAN_IF_OVERRIDE` を尊重。
4. **表示/収集の連携**: `StatusCollector` と `EPaperRenderer` が WAN state を読み、現在の WAN 名・ステータス・警告を UI に表示。網羅的なルール比較ロジックは削除され、WAN manager が選定した結果をそのまま表示する形に変更された。
5. **他コンポーネントの追従**: `TrafficControlEngine`、`azazel_pi.monitor.reset_network_config()` などが `wan_state` を参照して動的なインターフェースに追従するようになり、ドキュメント(README*) にも新機能が明記された。

## テスト計画
テストは以下の2レイヤーで管理する。表の「結果」は実行後に更新する。

### 1. 自動テスト (ローカルで即時実行可能)
| ID | 対象/目的 | 主要観点 | 手順 / コマンド | 結果 |
|----|-----------|---------|-----------------|------|
| A1 | `tests/utils/test_wan_state.py` | 状態ファイルの読書・更新、環境変数指定の動作確認 | `.venv/bin/pytest tests/utils/test_wan_state.py` | 成功 (仮想環境 `.venv` で pytest+PyYAML を導入して実行) |
| A2 | `tests/core/test_traffic_control.py` | `TrafficControlEngine` が `get_active_wan_interface` に変更されても既存ポリシー処理が壊れていないかの回帰 | `.venv/bin/pytest tests/core/test_traffic_control.py` | 成功 (A1 と同じ仮想環境で実行) |

### 2. 手動/統合テスト (実機/権限が必要)
| ID | 対象/目的 | 主要観点 | 手順 (概要) | 結果 |
|----|-----------|---------|-------------|------|
| M1 | WANマネージャ常駐運用 | `azctl wan-manager` が候補回線をプローブし、`runtime/wan_state.json` を更新、ステータス `ready` へ遷移すること | 実機で `sudo systemctl enable --now azazel-wan-manager` → `journalctl -u azazel-wan-manager` でフェイルオーバー理由とスコアを確認、`/var/run/azazel/wan_state.json` を検証 | 未実施 (仮想環境では root/実機ネットワークにアクセスできず保留) |
| M2 | フェイルオーバー経路 | アクティブ回線断時に別回線へ切替え、`bin/azazel-traffic-init.sh` と NAT 再適用が走ること | アクティブ IF を `ip link set <if> down` で落とし、ログと NAT (`iptables -t nat -S POSTROUTING`) を確認 | 未実施 (root 権限と複数物理IFが必要なため現環境で不可) |
| M3 | Suricata ラッパー | `suricata_wrapper` が state 追従し、systemd 依存関係が成立すること | `AZAZEL_WAN_STATE_PATH` をテストファイルに設定 → `sudo systemctl restart suricata` → `ps -ef | grep suricata` で引数と `journalctl` を確認 | 未実施 (systemd/Suricata へのアクセス権限なし) |
| M4 | 表示系の WAN 警告 | WAN state が `ready` 以外の時に e-paper に警告行が追加されること | 1) WAN state ファイルに `status: degraded` を書く 2) `python -m azazel_pi.core.display.renderer --dry-run` など表示ジョブを起動し、描画ログまたはスクリーンショットで `[WAN]` 行を確認 | 未実施 (e-paper 実機への描画確認が必要) |
| M5 | `azazel-traffic-init.sh` override | `WAN_IF_OVERRIDE` がスクリプト内で優先されること | `WAN_IF_OVERRIDE=eth0 ./bin/azazel-traffic-init.sh` を root で実行し、`tc qdisc show` 出力を確認 (失敗時はログに IF 名が出る) | 未実施 (root 権限で tc/iptables を弄る必要があり現環境では不可) |
| M6 | `azctl wan-manager --once` ドライラン | `--state-file` 指定で dry-run 評価のみ行い、候補スナップショットが JSON に記録されること | ネットワーク制御を避けるため `--once --state-file /tmp/... --candidate lo --services ''` などの軽量設定で実行し JSON を確認 (実行前に root で traffic/NAT 部分をモック化する) | 未実施 (dry-runでもiptables/systemctl実行が必要なため権限制約で保留) |

### 備考
- 手動テストは root 権限と実インターフェースが必要。CI では自動テスト (A1/A2) のみを必須とし、実機チェックはリリース前の運用手順に組み込む。
- `AZAZEL_WAN_STATE_PATH` を使えばローカルでも renderer/collector の確認がしやすい。
