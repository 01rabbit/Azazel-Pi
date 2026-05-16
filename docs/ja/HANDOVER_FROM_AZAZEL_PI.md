# Azazel-Pi 開発終了に伴う Azazel-Edge 引き継ぎサマリ

最終更新: 2026-05-16

## 1. 方針

- Azazel-Pi は開発終了とし、以後の実装・運用は Azazel-Edge を正系とする。
- 本書は「これまでの改修が Azazel-Edge 側へ反映済みか」を確認するための引き継ぎ記録。

## 2. 引き継ぎ済みの主要改修（要約）

### 名称・系譜整理
- `cdc4ee4`: プロジェクト名を Azazel-Pi から Azazel-Edge へ改名。
- `c46d3de`: Azazel-Zero 側の ntfy 通知連携を Azazel-Edge に取り込み。

### UI / 操作系
- `bee7910`: Azazel-Zero の WebUI を移植。
- `6f3f865`: 旧モジュラーTUIを廃止し、Azazel-Zero系 unified Textual TUI に統一。
- `6383fa8`: TUI/WebUI 統合後の API/ドキュメント挙動を最終調整。

### 検知・転送・通知
- `12d0049`: OpenCanary DNAT リダイレクトと通知重複の修正。
- `b1ac227`: AIワーカーで IPv6 イベントを不適切処理しないよう修正。
- `06dfd8d`: Docker 互換性重視で nftables から iptables 運用へ調整。

### 配備・運用基盤
- `230f152` (v3.0.0): 動的 WAN 選択とフェイルオーバを導入。
- `478b8ee` (v3.1.0): EPD 表示と WAN 状態可視化の改善。
- `78540ef` (v3.2.0): `/opt` 同期・インストーラ保護・systemd連携を強化。

## 3. 現在の引き継ぎ状態（2026-05-16 時点）

- コード/ドキュメントともに Azazel-Edge 名義へ統一済み。
- 主要な改修履歴は `CHANGELOG.md`（v3.0.0〜v3.2.0）と Git 履歴で追跡可能。
- `azazel_edge/` 配下が実装中核として維持され、CLI/TUI/WebUI/通知/運用スクリプトが接続済み。

## 4. Azazel-Edge への引き継ぎチェックリスト

以下を満たせば「実務上の引き継ぎ完了」と判断可能。

- [ ] 以後の issue / PR / release の対象リポジトリが Azazel-Edge 側に一本化されている。
- [ ] README / docs / 運用手順に Azazel-Pi 固有名称が残っていない（残件があれば置換）。
- [ ] インストーラ運用が `scripts/install_azazel_complete.sh` 基準に統一されている。
- [ ] 監視・通知（Suricata / OpenCanary / ntfy / Mattermost）の有効化手順が現行 docs と一致する。
- [ ] 実機で `azctl` の主要導線（status, menu, wan-manager）が通ることを確認済み。
- [ ] `tests/` の回帰テストを定期実行し、失敗時は Azazel-Edge 側で修正する運用になっている。

## 5. 参照先

- 変更履歴: `CHANGELOG.md`
- 日本語概要: `README_ja.md`
- アーキテクチャ: `docs/ja/ARCHITECTURE.md`
- 運用手順: `docs/ja/OPERATIONS.md`
