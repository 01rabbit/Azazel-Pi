# Ollama統合ガイド（Docker Compose版）

## 概要

Azazel-Edgeは、既知の脅威にはMock LLM（高速・軽量）を使用し、未知の脅威にはOllama（深堀り分析）を使用するハイブリッドAIシステムです。

OllamaはDocker Composeで管理され、PostgreSQL/Mattermostと統合されています。

## アーキテクチャ

```
Suricataアラート
    ↓
┌─────────────────────────────────┐
│ ハイブリッド脅威評価システム      │
├─────────────────────────────────┤
│ 1. Legacy Rules (基礎評価)       │
│ 2. Mock LLM (高速AI、<50ms)      │
│    ├→ 信頼度 ≥ 0.7: 確定        │
│    └→ 信頼度 < 0.7: 未知の脅威? │
│                                 │
│ 3. Ollama (深堀り分析、2-5秒)    │
│    └→ 未知の脅威を詳細分析       │
└─────────────────────────────────┘
    ↓
リスクスコア → ポリシー適用
```

## Docker Compose構成

`deploy/docker-compose.yml`:

```yaml
services:
  postgres:      # Mattermost用データベース
  ollama:        # AI脅威分析エンジン
```

両サービスを一元管理できます。

## インストール

### 1. モデルのダウンロード（初回のみ）

```bash
# ダウンロード先ディレクトリ作成
sudo mkdir -p /opt/models/qwen
sudo chown $USER:$USER /opt/models/qwen
cd /opt/models/qwen

# モデルダウンロード
# URL: https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF
# ファイル: Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
# サイズ: ~1.1GB

# 例: wgetでダウンロード
wget https://huggingface.co/mradermacher/Qwen2.5-1.5B-Instruct-uncensored-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-uncensored.Q4_K_M.gguf
```

### 2. Ollamaのセットアップ

```bash
# 自動セットアップスクリプト実行
sudo /home/azazel/Azazel-Edge/scripts/setup_ollama.sh
```

このスクリプトは以下を実行します：
1. モデルファイルの確認
2. Modelfileの作成
3. Docker Composeでコンテナ起動
4. threatjudgeモデルの作成
5. 動作テスト

## 管理コマンド

### Docker Composeでの操作

```bash
cd /home/azazel/Azazel-Edge/deploy

# 全サービス起動（PostgreSQL + Ollama）
docker compose up -d

# Ollamaのみ起動
docker compose up -d ollama

# Ollamaのみ停止
docker compose stop ollama

# Ollama再起動
docker compose restart ollama

# サービス状態確認
docker compose ps

# ログ確認
docker logs -f azazel_ollama
```

### 個別コマンド

```bash
# モデル一覧
docker exec azazel_ollama ollama list

# モデルテスト
docker exec azazel_ollama ollama run threatjudge "テスト"

# コンテナ内でシェル起動
docker exec -it azazel_ollama /bin/bash
```


## 設定

`configs/ai_config.json`:

```json
{
  "ai": {
    "ollama_url": "http://127.0.0.1:11434/api/generate",
    "model": "threatjudge",
    "timeout": 30,
    "unknown_threat_detection": {
      "enabled": true,
      "confidence_threshold": 0.7
    }
  }
}
```

## 未知の脅威検出トリガー

以下の条件でOllamaによる深堀り分析が実行されます：

1. **信頼度が低い**: Mock LLMの信頼度 < 0.7
2. **カテゴリが不明**: `unknown` または `benign` カテゴリ
3. **低リスクだが不確実**: リスクレベル ≤ 2

## 動作確認

### Docker Composeステータス確認

```bash
cd /home/azazel/Azazel-Edge/deploy
docker compose ps
```

期待される出力:
```
NAME              IMAGE                  STATUS
azazel_ollama     ollama/ollama:latest   Up (healthy)
azazel_postgres   postgres:15            Up
```

### APIテスト

```bash
curl -X POST http://127.0.0.1:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "threatjudge",
    "prompt": "Analyze: ET SCAN Suspicious port scan",
    "stream": false
  }'
```

### 統合テスト

```python
from azazel_edge.core.hybrid_threat_evaluator import evaluate_with_hybrid_system

# テストアラート（未知の脅威）
alert = {
    'signature': 'ET INFO Unknown suspicious activity',
    'src_ip': '192.168.1.100',
    'dest_ip': '10.0.0.1',
    'dest_port': 8888,
    'proto': 'TCP',
    'severity': 3,
    'payload_printable': 'strange binary data...'
}

# 評価実行
result = evaluate_with_hybrid_system(alert)
print(f"Risk: {result['risk']}/5")
print(f"Category: {result['category']}")
print(f"Method: {result['evaluation_method']}")  # "ollama_unknown_threat" が表示されるはず
print(f"Reason: {result['reason']}")
```

## パフォーマンス

| 評価方法 | 処理時間 | 使用ケース |
|---------|---------|-----------|
| Mock LLM | <50ms | 既知の脅威（大部分） |
| Ollama | 2-5秒 | 未知の脅威（少数） |

**実運用での割合**:
- Mock LLMのみ: ~80-90%（高速処理）
- Ollama補完: ~10-20%（深堀り分析）

## トラブルシューティング

### Ollamaコンテナが起動しない

```bash
# ログ確認
docker logs azazel_ollama

# 再起動
cd /home/azazel/Azazel-Edge/deploy
docker compose restart ollama
```

### モデルが見つからない

```bash
# モデル一覧確認
docker exec azazel_ollama ollama list

# モデル再作成
docker exec azazel_ollama ollama create threatjudge -f /models/qwen/Modelfile
```

### ヘルスチェックが失敗する

```bash
# コンテナ内で手動確認
docker exec azazel_ollama ollama ps

# ポートが開いているか確認
curl http://127.0.0.1:11434/api/tags
```

### タイムアウトエラー

`configs/ai_config.json`でタイムアウトを調整：

```json
{
  "ai": {
    "timeout": 60
  }
}
```

## システム起動時の自動起動

Docker Composeの再起動ポリシーにより、システム再起動時に自動的にOllamaが起動します。

手動で設定する場合：

```bash
# Docker サービスの自動起動有効化
sudo systemctl enable docker

# 起動時にコンテナを自動起動
cd /home/azazel/Azazel-Edge/deploy
docker compose up -d
```

## リソース使用量

### メモリ
- **コンテナ常駐**: ~100MB（Ollamaサービス）
- **推論時**: ~2-3GB（モデル読み込み時）
- **推奨メモリ**: 4GB以上

### ディスク
- **モデルファイル**: ~1.1GB
- **Dockerボリューム**: ~500MB（キャッシュ等）
- **合計**: ~2GB

### CPU
- **推論時**: 50-80%（1コア）
- **アイドル時**: <5%

## まとめ

- ✅ **統合管理**: PostgreSQLと一緒にDocker Composeで管理
- ✅ **高速**: 大部分の脅威はMock LLMで即座に処理
- ✅ **正確**: 未知の脅威はOllamaで深堀り分析
- ✅ **効率的**: 必要な時だけOllamaを使用
- ✅ **オフライン**: 完全にローカルで動作
- ✅ **自動起動**: システム再起動時も自動起動

---

**クイックスタート**: 
1. モデルをダウンロード
2. `sudo scripts/setup_ollama.sh` を実行
3. 完了！

