# Azazel-Pi AI Edge Computing Implementation（現行実装）

## 概要

本実装は「オフラインAI + ルールベース + Ollama（未知の脅威用）」を統合したハイブリッド脅威評価システムです。Suricataアラートを解析し、AI強化スコアに基づき tc/nftables の複合制御（DNAT/遅延/帯域制限）を適用します。

### 3層評価アーキテクチャ

```
1. Legacy Rules (基礎評価)      - 高速 (<10ms)
   ↓
2. Mock LLM (既知の脅威)        - 高速 (<50ms) - メイン評価エンジン
   ├→ 信頼度 ≥ 0.7: 確定
   └→ 信頼度 < 0.7: 未知の脅威?
       ↓
3. Ollama (未知の脅威の深堀り)  - 詳細 (2-5秒) - オプション補完
```

**処理割合**:
- Mock LLM のみ: ~80-90%（高速処理）
- Ollama 補完: ~10-20%（深堀り分析）

## 実装コンポーネント

### 1) ハイブリッド脅威評価 (`azazel_pi/core/hybrid_threat_evaluator.py`)
- Legacyルール評価とオフラインAI（Mock LLM含む）を統合
- **Ollama統合**: 未知の脅威検出時に深堀り分析を実行
  - トリガー条件: 信頼度 < 0.7、unknownカテゴリ、低リスクだが不確実
- 統合重み: 
  - 既知の脅威: Legacy 60% + Mock LLM 40%
  - 未知の脅威: Ollama 70% + Mock LLM 30%
- カテゴリ別の最低スコア保証（例: exploit/malware/sqliは最低60点）
- 正常トラフィックの上書き判定（benign override）
- 返却詳細に components（legacy_score/mock_llm_score/weights）を含む

### 2) AI評価器 (`azazel_pi/core/ai_evaluator.py`)
- **Ollama LLM評価器**: 未知の脅威に対する深堀り分析
- APIエンドポイント: `http://127.0.0.1:11434/api/generate`
- モデル: threatjudge (Qwen2.5-1.5B-Instruct-uncensored)
- タイムアウト: 30秒（設定可能）
- フォールバック機能: Ollama利用不可時は自動的にMock LLMへ

### 3) オフラインAI評価器 (`azazel_pi/core/offline_ai_evaluator.py`)
- 特徴量: シグネチャ/ペイロード複雑度/対象サービス重要度/レピュテーション/時間的頻度/プロトコル異常
- レピュテーション: `ipaddress` によるRFC1918・loopback・link-local・無効アドレスの厳密分類
- モデル依存なし。Mock LLMを併用する場合も擬似決定論（プロンプトハッシュで乱数シード）
- リスクは1-5で出力し、統合側で0-100に換算

### 4) Suricataモニタ (`azazel_pi/monitor/main_suricata.py`)
- `parse_alert` のカテゴリ正規化（大文字/小文字/アンダースコア差を吸収）
- 設定の allow/deny カテゴリを `configs/network/azazel.yaml` の `soc.allowed_categories` / `soc.denied_categories` から読み込み（未設定時は既定リスト）
- 独立した頻度カウンタ（signature×src_ipの時系列）で集中攻撃を安定検知
- リスク起点の制御発動: threat_score >= t1（しきい値）で複合制御適用
- 通知クールダウンと制御発動を分離（通知抑止でも制御は実施）
- `state_machine.apply_score()` による移動平均反映とモード遷移
- 10分ごとの期限切れルールのクリーンアップ呼び出し

### 5) 状態機械 (`azazel_pi/core/state_machine.py`)
- portal/shield/lockdown の3モード + ユーザ一時モード
- しきい値・アンロック遅延を YAML から読込。パス探索のフォールバックに `configs/network/azazel.yaml` を追加
- 移動平均ウィンドウで遷移判定、ユーザモードタイムアウトに対応

### 6) 統合トラフィック制御 (`azazel_pi/core/enforcer/traffic_control.py`)
- 複合制御: DNAT→OpenCanary + suspect QoS + netem遅延 + HTBシェーピング
- 冪等性: 同一IPへの同種ルール再適用を抑止、削除時は保持した `prio` で正確にフィルタ除去
- 期限切れクリーンアップAPIと統計取得API

### 7) ラッパー互換 (`azazel_pi/utils/delay_action.py`)
- 旧APIから統合エンジンへ橋渡し。レガシーフォールバックは非推奨

## 設定

### AI設定 (`configs/ai_config.json`)

```json
{
  "ai": {
    "ollama_url": "http://127.0.0.1:11434/api/generate",
    "model": "threatjudge",
    "timeout": 30,
    "max_payload_chars": 400,
    "unknown_threat_detection": {
      "enabled": true,
      "confidence_threshold": 0.7,
      "trigger_categories": ["unknown", "benign"],
      "trigger_low_risk": true
    }
  },
  "hybrid": {
    "legacy_weight": 0.6,
    "mock_llm_weight": 0.4,
    "ollama_weight": 0.7,
    "unknown_detection_enabled": true
  }
}
```

### ネットワーク設定 (`configs/network/azazel.yaml`)

主なキー:

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
   eve.json      Legacy+Mock LLM        moving average   DNAT/遅延/帯域     webhook
                      ↓
                 (信頼度 < 0.7)
                      ↓
                 Ollama深堀り分析
```

### 評価フロー詳細

1. **高速評価** (大部分のアラート)
   - Legacy Rules + Mock LLM
   - 処理時間: <50ms
   - 信頼度が高い場合は即座に確定

2. **深堀り評価** (未知の脅威)
   - Ollamaによる詳細分析
   - 処理時間: 2-5秒
   - 低信頼度、unknownカテゴリ、不確実な低リスクアラート

## Docker Compose統合

Ollamaは既存のMattermost/PostgreSQL環境と統合されています。

### サービス構成 (`deploy/docker-compose.yml`)

```yaml
services:
  postgres:      # Mattermost用データベース
  ollama:        # AI脅威分析エンジン
```

### 管理コマンド

```bash
cd /home/azazel/Azazel-Pi/deploy

# 全サービス起動
docker compose up -d

# Ollamaのみ起動
docker compose up -d ollama

# 状態確認
docker compose ps

# ログ確認
docker logs -f azazel_ollama
```

## インストール/セットアップ

### 1. Ollamaセットアップ

```bash
# 自動セットアップスクリプト実行
sudo /home/azazel/Azazel-Pi/scripts/setup_ollama.sh
```

事前にモデルファイルをダウンロード:
- URL: https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF
- ファイル: Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
- 配置先: /opt/models/qwen/

### 2. テスト実行
```bash
python3 -m venv .venv
source .venv/bin/activate
pytest -q
```

### 3. 統合テスト
```bash
python3 - << 'PY'
from azazel_pi.monitor.main_suricata import calculate_threat_score

# 既知の脅威テスト (Mock LLM)
print("=== 既知の脅威: SQLi ===")
alert1 = {
   'signature': 'ET WEB_SPECIFIC_APPS SQL Injection Attack',
   'src_ip': '203.0.113.44','dest_ip': '192.168.1.10','dest_port': 80,
   'proto': 'TCP','severity': 1,
   'payload_printable': "GET /admin.php?id=1' UNION SELECT user,pass FROM admin--",
   'details': {'metadata': {'attack_target': 'web_application'}}
}
score, detail = calculate_threat_score(alert1, alert1['signature'], use_ai=True)
print(f"  Score: {score}, Category: {detail.get('category')}, Method: {detail.get('evaluation_method')}")

# 未知の脅威テスト (Ollama)
print("\n=== 未知の脅威: 不明なアクティビティ ===")
alert2 = {
   'signature': 'ET INFO Unknown suspicious activity',
   'src_ip': '192.168.1.100','dest_ip': '10.0.0.1','dest_port': 8888,
   'proto': 'TCP','severity': 3,'payload_printable': 'strange binary data'
}
score, detail = calculate_threat_score(alert2, alert2['signature'], use_ai=True)
print(f"  Score: {score}, Category: {detail.get('category')}, Method: {detail.get('evaluation_method')}")
# evaluation_method が "ollama_unknown_threat" になることを確認
PY
```

期待される出力:
```
=== 既知の脅威: SQLi ===
  Score: 60-80, Category: sqli, Method: hybrid_integration

=== 未知の脅威: 不明なアクティビティ ===
  Score: 20-40, Category: unknown, Method: ollama_unknown_threat
```

## 監視・運用

- サービス（例）
   - `systemd/azctl-unified.service`（統合制御）
   - `systemd/suricata.service`（Suricata）
- ログ
   - `/var/log/azazel/`（設定に依存）
   - `journalctl -f -u azctl-unified.service` など

## トラブルシューティング（現行）

### 1) アラートが取り込まれない
- `parse_alert` のカテゴリ正規化と allow/deny 設定を確認
- `configs/network/azazel.yaml` のパスが読めているか（フォールバック有）

### 2) 制御が何度も適用される
- エンジンは冪等化済。`get_active_rules()` で適用状況を確認

### 3) スコアが過大/過小に見える
- `thresholds.t1_shield`/`t2_lockdown` とカテゴリ最低保証の関係を調整
- 監視環境に応じて `soc.allowed_categories/denied_categories` を調整

### 4) Ollamaが応答しない
```bash
# サービス状態確認
docker logs azazel_ollama

# 再起動
cd /home/azazel/Azazel-Pi/deploy
docker compose restart ollama

# ヘルスチェック
docker exec azazel_ollama ollama ps
curl http://127.0.0.1:11434/api/tags
```

### 5) タイムアウトエラーが多い
`configs/ai_config.json`でタイムアウトを調整:
```json
{
  "ai": {
    "timeout": 60
  }
}
```

## パフォーマンス特性

| 評価方法 | 処理時間 | メモリ使用量 | 使用割合 | 用途 |
|---------|---------|------------|---------|------|
| Legacy Rules | <10ms | <1MB | フォールバック | 基礎評価 |
| Mock LLM | <50ms | <10MB | 80-90% | 既知の脅威（メイン） |
| Ollama | 2-5秒 | 2-3GB | 10-20% | 未知の脅威（補完） |

### リソース要件

- **最小メモリ**: 2GB（Mock LLMのみ）
- **推奨メモリ**: 4GB以上（Ollama使用時）
- **ディスク**: ~2GB（Ollamaモデル含む）
- **CPU**: 4コア推奨（Raspberry Pi 5で動作確認済み）

## 既存ドキュメントからの変更点（要約）

- **Ollama統合**: Docker Composeで管理、未知の脅威の深堀り分析に使用
- **3層評価**: Legacy → Mock LLM → Ollama のカスケード評価
- `ai_evaluator.py` を活用: Ollama LLM評価器として機能
- `hybrid_threat_evaluator.py` を更新: 未知の脅威検出ロジックを追加
- Docker統合: PostgreSQL/Mattermostと統合管理
- main_suricata はリスク起点の制御発動、独立頻度カウンタ、カテゴリ正規化、定期クリーンアップに対応
- トラフィック制御は冪等性とクリーンアップを強化

## 将来的な拡張

1. 観測性の拡充（メトリクス出力/可視化）
2. 追加特徴量（フロー持続時間/方向性/サイズ分布）
3. 署名以外のベイズ統合・ファジィロジック適用
4. より大規模なLLMモデルの選択的使用（重要アラート限定）
5. オンライン学習による脅威パターンの自動更新

## 関連ドキュメント

- **Ollamaセットアップ詳細**: [OLLAMA_SETUP.md](OLLAMA_SETUP.md)
- **Mock LLM設計思想**: [MOCK_LLM_DESIGN.md](MOCK_LLM_DESIGN.md)
- **アーキテクチャ**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **運用ガイド**: [OPERATIONS.md](OPERATIONS.md)

---

本ドキュメントは現行ブランチ（edge-ai-verification）の実装に基づいて更新済みです。
最終更新: 2025-11-05 - Ollama統合、Docker Compose管理、未知の脅威検出機能追加