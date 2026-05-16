# Azazel-Pi EOL / Archive Checklist

このチェックリストは、Azazel-Pi を正式に開発終了し、Azazel-Edge へ完全移行するための運用手順です。

基準日: 2026-05-16

## 1. リポジトリ内整備（実施済み確認）

- [ ] `README.md` / `README_ja.md` に EOL 宣言と移行先を明記
- [ ] `CONTRIBUTING.md` を EOL 方針に更新
- [ ] `SECURITY.md` を EOL 方針に更新
- [ ] `.github/ISSUE_TEMPLATE/config.yml` で Issue を Azazel-Edge 側へ誘導
- [ ] `.github/pull_request_template.md` で PR を Azazel-Edge 側へ誘導
- [ ] `CHANGELOG.md` に EOL エントリを追加

## 2. 最終リリース固定

- [ ] 最終タグを作成（例: `azazel-pi-eol-2026-05-16`）
- [ ] GitHub Release を作成し、以下を記載:
  - 開発終了日: 2026-05-16
  - 継承先: Azazel-Edge
  - 以後の修正受付先: Azazel-Edge

## 3. GitHub運用設定

- [ ] Openな Issue をクローズ（最終アナウンスコメントを残す）
- [ ] Openな PR をクローズ（Azazel-Edge への再提出を案内）
- [ ] 必要なら Discussions に固定投稿で移行案内
- [ ] リポジトリ Description に「EOL / Moved to Azazel-Edge」を追記
- [ ] Website 欄を Azazel-Edge へ設定

## 4. アーカイブ実施

- [ ] GitHub Repository Settings から Archive を実行
- [ ] Archive 後、読み取り専用状態であることを確認
- [ ] Issue / PR 新規作成不可を確認

## 5. 移行後の監査ポイント

- [ ] Azazel-Pi への新規問い合わせが Azazel-Edge へ流れている
- [ ] セキュリティ報告が Azazel-Edge 側に集約されている
- [ ] 外部資料・発表スライド・ブログのリンク先が Azazel-Edge に更新済み
