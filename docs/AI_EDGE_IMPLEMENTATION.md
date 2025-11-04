# Azazel-Pi AI Edge Computing Implementation（現行実装）

## 概要

本実装は「オフラインAI + ルールベース」を統合したハイブリッド脅威評価システムです。Docker/Ollama は廃止し、デバイス単体で安定動作する軽量な評価エンジンに置き換えました。Suricataアラートを解析し、AI強化スコアに基づき tc/nftables の複合制御（DNAT/遅延/帯域制限）を適用します。

## 実装コンポーネント

### 1) ハイブリッド脅威評価 (`azazel_pi/core/hybrid_threat_evaluator.py`)
- Legacyルール評価とオフラインAI（Mock LLM含む）を統合
- 統合重み: Legacy 60% + Mock LLM 40%
- カテゴリ別の最低スコア保証（例: exploit/malware/sqliは最低60点）
- 正常トラフィックの上書き判定（benign override）
- 返却詳細に components（legacy_score/mock_llm_score/weights）を含む

### 2) オフラインAI評価器 (`azazel_pi/core/offline_ai_evaluator.py`)
- 特徴量: シグネチャ/ペイロード複雑度/対象サービス重要度/レピュテーション/時間的頻度/プロトコル異常
- レピュテーション: `ipaddress` によるRFC1918・loopback・link-local・無効アドレスの厳密分類
- モデル依存なし。Mock LLMを併用する場合も擬似決定論（プロンプトハッシュで乱数シード）
- リスクは1-5で出力し、統合側で0-100に換算

### 3) Suricataモニタ (`azazel_pi/monitor/main_suricata.py`)
- `parse_alert` のカテゴリ正規化（大文字/小文字/アンダースコア差を吸収）
- 設定の allow/deny カテゴリを `configs/network/azazel.yaml` の `soc.allowed_categories` / `soc.denied_categories` から読み込み（未設定時は既定リスト）
- 独立した頻度カウンタ（signature×src_ipの時系列）で集中攻撃を安定検知
- リスク起点の制御発動: threat_score >= t1（しきい値）で複合制御適用
- 通知クールダウンと制御発動を分離（通知抑止でも制御は実施）
- `state_machine.apply_score()` による移動平均反映とモード遷移
- 10分ごとの期限切れルールのクリーンアップ呼び出し

### 4) 状態機械 (`azazel_pi/core/state_machine.py`)
- portal/shield/lockdown の3モード + ユーザ一時モード
- しきい値・アンロック遅延を YAML から読込。パス探索のフォールバックに `configs/network/azazel.yaml` を追加
- 移動平均ウィンドウで遷移判定、ユーザモードタイムアウトに対応

### 5) 統合トラフィック制御 (`azazel_pi/core/enforcer/traffic_control.py`)
- 複合制御: DNAT→OpenCanary + suspect QoS + netem遅延 + HTBシェーピング
- 冪等性: 同一IPへの同種ルール再適用を抑止、削除時は保持した `prio` で正確にフィルタ除去
- 期限切れクリーンアップAPIと統計取得API

### 6) ラッパー互換 (`azazel_pi/utils/delay_action.py`)
- 旧APIから統合エンジンへ橋渡し。レガシーフォールバックは非推奨

## 設定

`configs/network/azazel.yaml` を使用します。主なキー:

```
actions:
   portal:   { delay_ms: 100, shape_kbps: null, block: false }
   shield:   { delay_ms: 200, shape_kbps: 128,  block: false }
   lockdown: { delay_ms: 300, shape_kbps: 64,   block: true  }
thresholds:
   t1_shield: 50
   t2_lockdown: 80
   unlock_wait_secs: { shield: 600, portal: 1800 }
soc:
   allowed_categories: ["Malware", "Exploit", "SCAN", "Web Specific Apps"]  # 任意
   denied_categories:  ["DNS", "POP3"]                                       # 任意
```

allow/deny が未設定の場合は、既定の主要カテゴリを通します（取りこぼし防止）。denyはallowより優先されます。

## 動作フロー（現行）

```
Suricataアラート → Hybrid Evaluator → スコア(0-100) → 状態遷移 → 複合制御(tc/nft) → Mattermost通知
       ↓                 ↓                    ↓            ↓                    ↓
   eve.json         offline+mock        moving average   DNAT/遅延/帯域     webhook
```

## インストール/テスト（Docker不要）

1) 仮想環境の準備とテスト実行
```bash
python3 -m venv .venv
source .venv/bin/activate
pytest -q
```

2) 運用スモークテスト（例: SQLi/HTTPSなど数種）
```bash
python3 - << 'PY'
from azazel_pi.monitor.main_suricata import calculate_threat_score
tests = [
   {
      'signature': 'ET WEB_SPECIFIC_APPS SQL Injection Attack',
      'src_ip': '203.0.113.44','dest_ip': '192.168.1.10','dest_port': 80,
      'proto': 'TCP','severity': 1,
      'payload_printable': "GET /admin.php?id=1' UNION SELECT user,pass FROM admin--",
      'details': {'metadata': {'attack_target': 'web_application'}}
   },
   {
      'signature': 'ET INFO HTTPS request to legitimate CDN',
      'src_ip': '192.168.1.50','dest_ip': '151.101.1.140','dest_port': 443,
      'proto': 'TCP','severity': 4,'payload_printable': 'TLS 1.3 handshake','details': {}
   }
]
for a in tests:
   score, detail = calculate_threat_score(a, a['signature'], use_ai=True)
   print(a['signature'][:50], '->', score, detail.get('category'), detail.get('evaluation_method'))
PY
```

## 監視・運用

- サービス（例）
   - `systemd/azctl-unified.service`（統合制御）
   - `systemd/suricata.service`（Suricata）
- ログ
   - `/var/log/azazel/`（設定に依存）
   - `journalctl -f -u azctl-unified.service` など

## トラブルシューティング（現行）

1) アラートが取り込まれない
- `parse_alert` のカテゴリ正規化と allow/deny 設定を確認
- `configs/network/azazel.yaml` のパスが読めているか（フォールバック有）

2) 制御が何度も適用される
- エンジンは冪等化済。`get_active_rules()` で適用状況を確認

3) スコアが過大/過小に見える
- `thresholds.t1_shield`/`t2_lockdown` とカテゴリ最低保証の関係を調整
- 監視環境に応じて `soc.allowed_categories/denied_categories` を調整

## 既存ドキュメントからの変更点（要約）

- Docker/Ollama 依存を撤廃。すべてオフライン/ローカルで完結
- `ai_evaluator.py` は存在せず、`offline_ai_evaluator.py`+`hybrid_threat_evaluator.py` に集約
- main_suricata はリスク起点の制御発動、独立頻度カウンタ、カテゴリ正規化、定期クリーンアップに対応
- トラフィック制御は冪等性とクリーンアップを強化

## 将来的な拡張

1) 観測性の拡充（メトリクス出力/可視化）
2) 追加特徴量（フロー持続時間/方向性/サイズ分布）
3) 署名以外のベイズ統合・ファジィロジック適用
4) 低電力NPU活用の高速推論（任意）

---

本ドキュメントは現行ブランチ（edge-ai-verification）の実装に基づいて更新済みです。