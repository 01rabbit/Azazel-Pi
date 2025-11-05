# Azazel-Pi Ollama統合 - 設計実装完了

## 概要
Raspberry Pi 5でOllama + Qwen2.5-1.5B-Instruct-q4_K_Mを使用した
リアルタイム脅威検知・自動対処システムの完全実装

## アーキテクチャ

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Suricata      │───▶│  Alert Handler  │───▶│  Policy Engine  │
│   EVE JSON      │    │  (AI Enhanced)  │    │  tc/nftables    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              ▼                        ▼
                    ┌─────────────────┐    ┌─────────────────┐
                    │     Ollama      │    │   Mattermost    │
                    │  Qwen2.5-1.5B   │    │  Notification   │
                    └─────────────────┘    └─────────────────┘

Host: /opt/models/qwen/*.gguf (Read-Only)
  ↓ Volume Mount
Docker: Ollama Container (推論エンジン専用)
  ↓ HTTP API (127.0.0.1:11434)
Handler: alert_handler.py (既存ai_evaluator.py活用)
  ↓ Risk Assessment & Action
System: tc/nftables + Mattermost通知
```

## ファイル構成

```
/opt/models/qwen/
├── Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf  # 1.5GB モデルファイル
├── Modelfile                                      # Ollama設定  
├── model_info.json                                # メタデータ
└── model.sha256                                   # チェックサム

/opt/azazel/
├── docker-compose.yml                 # Ollama統合版
├── alert_handler.py                   # メインハンドラ
├── policy_delay.sh                    # tc遅延制御
├── policy_block.sh                    # nftables遮断
└── .env                              # 環境設定

Azazel-Pi/
├── deploy/
│   ├── docker-compose-ollama.yml     # Docker構成
│   ├── alert_handler.py              # アラートハンドラ
│   ├── policy_*.sh                   # ポリシースクリプト
│   └── models/                       # モデル設定
├── scripts/
│   └── install_ollama.sh             # 自動インストール
├── azazel_pi/core/
│   ├── ai_config.py                  # AI設定（Ollama有効化済）
│   └── ai_evaluator.py               # 既存AI評価器（対応済）
└── configs/
    └── ai_config.json                # Ollama設定（更新済）
```

## インストール手順

### 1. モデルの事前ダウンロード（必須）
```bash
# モデルディレクトリ作成
sudo mkdir -p /opt/models/qwen
sudo chown $USER:$USER /opt/models/qwen
```

**ブラウザでダウンロード（推奨・高速）:**
1. https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF にアクセス
2. `Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf` をダウンロード
3. `/opt/models/qwen/` に配置

**コマンドラインダウンロード（時間かかる）:**
```bash
cd /opt/models/qwen
wget https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
```

### 2. 自動インストール実行
```bash
cd /home/azazel/Azazel-Pi
sudo ./scripts/install_ollama.sh
```

### 3. 手動インストール（デバッグ用）
```bash
# 1. モデルが配置されていることを確認
ls -la /opt/models/qwen/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf

# 3. 設定ファイル配置
sudo mkdir -p /opt/azazel
cd /home/azazel/Azazel-Pi
cp deploy/docker-compose-ollama.yml /opt/azazel/docker-compose.yml
cp deploy/alert_handler.py /opt/azazel/
cp deploy/policy_*.sh /opt/azazel/
cp deploy/models/* /opt/models/qwen/

# 4. 権限設定
chmod +x /opt/azazel/policy_*.sh
chmod +x /opt/azazel/alert_handler.py

# 5. サービス起動
cd /opt/azazel
docker-compose up -d ollama

# 6. モデル登録
sleep 10
docker exec azazel_ollama ollama create threatjudge -f /models/qwen/Modelfile

# 7. ハンドラ起動
docker-compose up -d threat-handler
```

## 設定

### Environment Variables (.env)
```bash
# Mattermost通知
MATTERMOST_WEBHOOK=https://your-mattermost.com/hooks/xxx

# Ollama設定
AZ_MODEL=threatjudge
OLLAMA_URL=http://127.0.0.1:11434/api/generate
LOG_LEVEL=INFO

# ネットワーク
AZ_INTERFACE=eth0
```

### Suricata設定
```yaml
outputs:
  - eve-log:
      enabled: yes
      filename: /var/log/suricata/eve.json
      types:
        - alert:
            payload: yes
            payload-printable: yes
            metadata: yes

vars:
  address-groups:
    HOME_NET: "[172.16.0.254]"  # Azazel-Pi自身のIP
```

## 動作確認

### 1. サービス状態確認
```bash
# Docker サービス
cd /opt/azazel
docker-compose ps

# Ollama モデル
docker exec azazel_ollama ollama list

# ログ監視
docker logs -f azazel_threat_handler
```

### 2. テスト実行
```bash
# ダミーアラート投入
echo '{"event_type":"alert","src_ip":"1.2.3.4","dest_ip":"172.16.0.254","proto":"tcp","dest_port":22,
"alert":{"signature":"SSH brute-force attempt"},
"payload_printable":"user: root pass: 123456"}' | sudo tee -a /var/log/suricata/eve.json

# ポリシー確認
tc -s qdisc show dev eth0
sudo nft list ruleset | grep -A2 'table inet azazel'
```

### 3. AI応答テスト
```bash
# Ollama直接テスト
docker exec -it azazel_ollama ollama run threatjudge "SSH brute-force from 1.2.3.4"
```

## 機能詳細

### リスクレベル判定
- **1-2**: ログ記録のみ
- **3**: tc遅延制御（200ms）
- **4-5**: nftables完全遮断

### AI処理フロー
1. Suricata EVE JSON解析
2. Qwen2.5-1.5B脅威評価
3. JSON形式結果解析
4. ポリシー適用
5. Mattermost通知

### フェールセーフ
- Ollama障害時は既存offline AI評価器にフォールバック
- API タイムアウト時は保守的判定
- JSON解析失敗時はデフォルトリスク=2

## 運用メンテナンス

### ログ管理
```bash
# アプリケーションログ
docker logs azazel_threat_handler

# システムログ
journalctl -u azazel-ollama.service -f

# Ollama内部ログ
docker exec azazel_ollama ollama logs
```

### ポリシー掃除
```bash
# tc ルール削除
sudo tc qdisc del dev eth0 root

# nftables テーブル削除
sudo nft delete table inet azazel
```

### モデル更新
```bash
# 1. 新モデルをブラウザダウンロード → /opt/models/qwen/
# 2. Modelfile のFROMパスを更新
# 3. モデル再作成
docker exec azazel_ollama ollama create threatjudge -f /models/qwen/Modelfile
```

### 推奨モデル
- **mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF**
- サイズ: ~1.5GB (Q4_K_M量子化)
- 特徴: セキュリティ分析に適した非検閲版
- URL: https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF

## パフォーマンス

### Pi 5想定値
- **メモリ使用量**: 2.5-3GB（モデル1.5GB + システム）
- **推論時間**: 2-5秒/アラート
- **CPU使用率**: 50-80%（推論時）
- **ディスク使用量**: 2GB（モデル + システム）

### 最適化設定
```bash
# Ollama環境変数
OLLAMA_NUM_PARALLEL=1
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_KEEP_ALIVE=24h

# Docker リソース制限
docker update --memory=3g --cpus=3 azazel_ollama
```

## トラブルシューティング

### よくある問題
1. **メモリ不足** → swap設定、並列処理制限
2. **モデル読み込み失敗** → 権限確認、ディスク容量
3. **API タイムアウト** → timeout値調整、CPU性能確認
4. **ポリシー適用失敗** → 権限確認、ネットワーク設定

### 詳細ログ有効化
```bash
# デバッグモード
export LOG_LEVEL=DEBUG
docker-compose restart threat-handler
```

---

## 実装完了 ✅

すべてのコンポーネントが実装され、ワンライン実行可能な状態です：

```bash
sudo /home/azazel/Azazel-Pi/scripts/install_ollama.sh
```