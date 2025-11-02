# Azazel-Pi アーキテクチャ

Azazel-PiはSOC/NOC制御プレーンを自己完結型リポジトリにパッケージ化しています。クリーンなRaspberry Piイメージがタグ付きリリースを取得して、アドホックな設定なしに運用可能になるように設計されています。

## システム概要

Azazel-Piは、ネットワークセキュリティ監視および自動応答システムとして機能します。侵入検知、脅威スコアリング、適応的防御対応を統合し、Raspberry Piハードウェア上で効率的に動作します。

### 基本アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│                    Azazel-Pi System                    │
├─────────────────────┬───────────────────────────────────┤
│   Control Plane     │         Data Plane               │
│                     │                                   │
│  ┌─────────────┐   │  ┌─────────────┐  ┌─────────────┐ │
│  │State Machine│   │  │  Suricata   │  │ OpenCanary  │ │
│  │   (azctl)   │   │  │    IDS      │  │  Honeypot   │ │
│  └─────────────┘   │  └─────────────┘  └─────────────┘ │
│          │          │          │               │        │
│  ┌─────────────┐   │  ┌─────────────┐  ┌─────────────┐ │
│  │   Scorer    │   │  │   Vector    │  │    nftables │ │
│  │  Engine     │   │  │  Log Proc   │  │  Firewall   │ │
│  └─────────────┘   │  └─────────────┘  └─────────────┘ │
│          │          │          │               │        │
│  ┌─────────────┐   │  ┌─────────────┐  ┌─────────────┐ │
│  │E-Paper Disp │   │  │     TC      │  │ Mattermost  │ │
│  │  Status     │   │  │Traffic Ctrl │  │   Alerts    │ │
│  └─────────────┘   │  └─────────────┘  └─────────────┘ │
└─────────────────────┴───────────────────────────────────┘
```

## コアサービス

| コンポーネント | 目的 | 実装場所 |
|---------------|------|----------|
| `azazel_pi/core/state_machine.py` | 防御態勢間の遷移を制御 | コア状態管理 |
| `azazel_pi/core/actions/` | tc/nftables操作をべき等プランとしてモデル化 | ネットワーク制御 |
| `azazel_pi/core/ingest/` | SuricataのEVEログとOpenCanaryイベントを解析 | データ取り込み |
| `azazel_pi/core/display/` | E-Paperステータス表示とレンダリング | 物理インターフェース |
| `azazel_pi/core/qos/` | プロファイルをQoS実行クラスにマッピング | 帯域制御 |
| `azctl/` | systemdで使用される軽量CLI/デーモンインターフェース | システム統合 |
| `configs/` | スキーマ検証を含む宣言的設定セット | 設定管理 |
| `scripts/install_azazel.sh` | ランタイムと依存関係をステージングするプロビジョニングスクリプト | 導入支援 |
| `systemd/` | Azazelサービススタックを構成するユニットとターゲット | サービス管理 |

## 状態マシン詳細

状態マシンは、受信アラートから計算されたスコアに基づいて防御態勢を昇格または降格させます。3つのステージがモデル化されています：

### 防御モード

#### 1. Portal モード（基本監視）
- **説明**: デフォルト状態、最小限の制限
- **特徴**: 
  - 基本的な監視とログ記録
  - 遅延: 100ms
  - 帯域制限: なし
  - ファイアウォール: 基本ルール
- **適用条件**: スコア平均 < T1閾値

#### 2. Shield モード（強化監視）
- **説明**: 高度な監視、トラフィックシェーピング適用
- **特徴**:
  - 詳細ログ記録と分析
  - 遅延: 200ms
  - 帯域制限: 128kbps
  - トラフィックシェーピング有効
- **適用条件**: T1閾値 ≤ スコア平均 < T2閾値

#### 3. Lockdown モード（完全封じ込め）
- **説明**: 高スコアによってトリガーされる最高セキュリティ段階
- **特徴**:
  - 最大遅延: 300ms
  - 厳格な帯域制限: 64kbps
  - nftablesルールによる信頼範囲への制限
  - 医療・緊急FQDNへのアクセス維持
- **適用条件**: スコア平均 ≥ T2閾値

### 状態遷移メカニズム

```python
# 状態遷移の実装例
@dataclass
class StateMachine:
    def dispatch(self, event: Event) -> State:
        """イベントを処理し、適用可能な場合は状態マシンを進める"""
        for transition in self._transition_map.get(self.current_state.name, []):
            if transition.condition(event):
                previous = self.current_state
                self.current_state = transition.target
                self._handle_transition(previous, self.current_state)
                return self.current_state
        return self.current_state

    def apply_score(self, severity: int) -> Dict[str, Any]:
        """スコアウィンドウを評価し、適切なモードに遷移"""
        evaluation = self.evaluate_window(severity)
        desired_mode = evaluation["desired_mode"]
        
        # アンロック時間を考慮したターゲットモード決定
        target_mode = self._resolve_target_mode(desired_mode)
        
        if target_mode != self.current_state.name:
            self.dispatch(Event(name=target_mode, severity=severity))
            
        return evaluation
```

## スコアリングシステム

脅威スコアリングロジックは`azazel_pi/core/scorer.py`に実装され、`tests/`配下のユニットテストで検証されています。

### ScoreEvaluator クラス

```python
@dataclass
class ScoreEvaluator:
    """複数のイベントからスコアを集約"""
    
    baseline: int = 0
    
    def evaluate(self, events: Iterable[Event]) -> int:
        """累積重要度スコアを計算"""
        score = self.baseline
        for event in events:
            score += max(event.severity, 0)
        return score
    
    def classify(self, score: int) -> str:
        """スコアのテキスト分類を返す"""
        if score >= 80: return "critical"
        if score >= 50: return "elevated" 
        if score >= 20: return "guarded"
        return "normal"
```

### スコア分類

| 分類 | スコア範囲 | 説明 | 対応アクション |
|------|------------|------|----------------|
| normal | 0-19 | 通常状態 | Portal モード維持 |
| guarded | 20-49 | 警戒状態 | 監視強化 |
| elevated | 50-79 | 高警戒状態 | Shield モード移行 |
| critical | 80+ | 危機状態 | Lockdown モード移行 |

## データフロー

### イベント処理パイプライン

```
外部イベント → インジェスト → スコアリング → 状態評価 → アクション実行
     ↓              ↓            ↓           ↓            ↓
┌─────────────┐ ┌─────────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐
│Suricata EVE │ │SuricataTail │ │ Scorer   │ │ State   │ │ Actions  │
│OpenCanary   │ │CanaryTail   │ │Evaluator │ │Machine  │ │tc/nftable│
│Events       │ │Parsers      │ │          │ │         │ │          │
└─────────────┘ └─────────────┘ └──────────┘ └─────────┘ └──────────┘
     ↓              ↓            ↓           ↓            ↓
    ログ          Event        Score      State        Network
   ファイル       オブジェクト    数値      変更        制御実行
```

### 設定管理フロー

```
YAML設定 → スキーマ検証 → 設定キャッシュ → ランタイム適用
    ↓           ↓             ↓            ↓
┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│azazel.  │ │ JSON     │ │Config    │ │Component │
│yaml     │ │Schema    │ │Cache     │ │Runtime   │
└─────────┘ └──────────┘ └──────────┘ └──────────┘
```

## コンポーネント詳細

### 1. イベント取り込み（Ingest）

#### SuricataTail
```python
class SuricataTail:
    """SuricataのEVEログをリアルタイムで監視"""
    
    def tail_events(self) -> Iterator[Event]:
        """ログファイルを追跡しEventオブジェクトを生成"""
        # ファイル監視とJSON解析
        # イベント正規化とフィルタリング
```

#### CanaryTail
```python
class CanaryTail:
    """OpenCanaryハニーポットイベントを処理"""
    
    def parse_canary_event(self, raw_event: str) -> Event:
        """生ログからEventオブジェクトを生成"""
        # ハニーポットイベント解析
        # 重要度スコア計算
```

### 2. アクションシステム

アクションはべき等性を保証し、計画と実行を分離します：

```python
@dataclass  
class Action:
    """ネットワーク制御アクションの基底クラス"""
    
    def plan(self, target: str) -> Iterator[ActionResult]:
        """実行計画を生成（副作用なし）"""
        raise NotImplementedError
        
    def execute(self, target: str) -> List[ActionResult]:
        """計画を実際に実行"""
        return list(self.plan(target))
```

#### 実装済みアクション

| アクション | 目的 | 実装 |
|------------|------|------|
| DelayAction | パケット遅延注入 | tc netem規則 |
| ShapeAction | 帯域制限適用 | tc tbf/htb規則 |
| BlockAction | IPアドレスブロック | nftables reject規則 |
| RedirectAction | トラフィック転送 | nftables dnat規則 |

### 3. E-Paper表示システム

#### StatusCollector
```python
class StatusCollector:
    """システム状況情報を収集"""
    
    def collect(self) -> SystemStatus:
        """現在のシステム状態を収集"""
        return SystemStatus(
            hostname=self._get_hostname(),
            network=self._get_network_status(),
            security=self._get_security_status(),
            uptime_seconds=self._get_uptime(),
        )
```

#### EPaperRenderer
```python
class EPaperRenderer:
    """E-Paperディスプレイへの描画"""
    
    def render_status(self, status: SystemStatus) -> None:
        """システム状態をE-Paperに描画"""
        # レイアウト計算とフォントレンダリング
        # ディスプレイドライバー呼び出し
```

### 4. HTTP API

最小限のHTTPインターフェースを提供：

```python
class APIServer:
    """軽量HTTPサーバー"""
    
    def add_health_route(self, version: str) -> None:
        """ヘルスチェックエンドポイントを追加"""
        @self.app.route('/v1/health')
        def health():
            return HealthResponse(
                status="healthy",
                version=version,
                uptime=time.time() - self.start_time
            )
```

## 設定システム

すべてのランタイムパラメータは`configs/azazel.yaml`に格納されます。JSON Schemaが`configs/azazel.schema.json`で公開され、CIで検証されます。

### 設定構造

```yaml
# メイン設定ファイル例
system:
  hostname: "azazel-gateway"
  log_level: "INFO"

network:
  interface: "eth0"
  home_net: "192.168.1.0/24"
  
security:
  modes:
    portal:
      delay_ms: 100
      bandwidth_kbps: null
      firewall_policy: "monitor"
    shield:
      delay_ms: 200  
      bandwidth_kbps: 128
      firewall_policy: "restrict"
    lockdown:
      delay_ms: 300
      bandwidth_kbps: 64
      firewall_policy: "lockdown"
      
  thresholds:
    t1: 25  # Portal → Shield
    t2: 75  # Shield → Lockdown
    
  unlock_windows:
    shield_unlock_seconds: 300
    lockdown_unlock_seconds: 900
```

### スキーマ検証

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "security": {
      "type": "object",
      "properties": {
        "thresholds": {
          "type": "object",
          "properties": {
            "t1": {"type": "number", "minimum": 0},
            "t2": {"type": "number", "minimum": 0}
          },
          "required": ["t1", "t2"]
        }
      }
    }
  }
}
```

## パッケージング目標

`install_azazel.sh`は以下を実行します：

1. **ファイル配置**: Azazelを`/opt/azazel`にインストール
2. **設定コピー**: 設定ファイルをシステム場所にコピー
3. **systemdユニット**: サービス定義を適切な場所に配置
4. **依存関係確認**: 必要なDebian パッケージの存在確認

リポジトリレイアウトはステージングされたファイルシステムを反映し、リリースの再現性を保証します。コミットのタグ付けにより、エアギャップインストール用の全ペイロードを含む`azazel-installer-<tag>.tar.gz`を構築するリリースワークフローがトリガーされます。

### インストールフロー

```
Git Repository → Release Build → Tarball → Target System
      ↓              ↓           ↓           ↓
┌─────────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐
│Source Code  │ │CI/CD     │ │Installer│ │Production│
│Tags         │ │Pipeline  │ │Package  │ │Deployment│
└─────────────┘ └──────────┘ └─────────┘ └──────────┘
```

## サービス統合

### systemd統合

Azazelは統合された`azctl.target`を通じてすべてのサービスを管理：

```ini
# azctl.target
[Unit]
Description=Azazel Control System
Documentation=https://github.com/01rabbit/Azazel-Pi
Wants=azctl-serve.service mattermost.service nginx.service
After=multi-user.target network-online.target

[Install]
WantedBy=multi-user.target
```

### 依存関係管理

| サービス | 依存関係 | 説明 |
|----------|----------|------|
| azctl-serve.service | ネットワーク | メインコントローラー |
| suricata.service | ネットワーク | IDS/IPS |
| opencanary.service | なし | ハニーポット |
| vector.service | ログディレクトリ | ログ処理 |
| mattermost.service | データベース | アラート通知 |
| nginx.service | mattermost | リバースプロキシ |

## 監視とログ

### ログ階層

```
/var/log/azazel/
├── decisions.log      # 状態遷移とスコア決定
├── events.json        # 正規化されたセキュリティイベント
├── actions.log        # 実行されたネットワークアクション
└── health.log         # システムヘルスチェック
```

### メトリクス収集

```python
class MetricsCollector:
    """システムメトリクスを収集"""
    
    def collect_metrics(self) -> Dict[str, Any]:
        return {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "network_io": psutil.net_io_counters(),
            "active_connections": len(psutil.net_connections()),
        }
```

## セキュリティ考慮事項

### アクセス制御

- systemdサービスは最小権限で実行
- 設定ファイルは適切な権限設定
- ネットワークインターフェースへの制限アクセス

### ログ管理

- 機密情報のマスキング
- ログローテーションの実装
- 改ざん検知のためのハッシュ化

### 通信セキュリティ

- TLS暗号化（HTTPS/WSS）
- 証明書検証
- セキュアな認証機構

## 拡張性と保守性

### プラグインアーキテクチャ

新しいイベントソースやアクションタイプを追加可能：

```python
# カスタムイベントソース
class CustomEventSource:
    def tail_events(self) -> Iterator[Event]:
        # カスタムログ解析ロジック
        pass

# カスタムアクション
class CustomAction(Action):
    def plan(self, target: str) -> Iterator[ActionResult]:
        # カスタム制御ロジック
        pass
```

### テスト戦略

- ユニットテスト: 個別コンポーネントの動作確認
- 統合テスト: コンポーネント間の相互作用テスト
- システムテスト: エンドツーエンドのシナリオテスト

### ドキュメント

- APIリファレンス: 詳細な関数・クラス文書
- 運用ガイド: 日常的な運用手順
- トラブルシューティング: 問題解決手順

## パフォーマンス特性

### リソース使用量

| コンポーネント | CPU使用率 | メモリ使用量 | ディスクI/O |
|---------------|-----------|-------------|-------------|
| azctl-serve | < 5% | ~50MB | 低 |
| suricata | 10-30% | ~200MB | 中 |
| vector | < 5% | ~30MB | 中 |
| mattermost | < 10% | ~150MB | 低 |

### スケーラビリティ

- イベント処理: 1000イベント/秒まで対応
- 同時接続: 100接続まで対応
- ログ保持: デフォルト30日間

## 関連ドキュメント

- [`API_REFERENCE_ja.md`](API_REFERENCE_ja.md) - PythonモジュールとHTTPエンドポイント詳細
- [`OPERATIONS_ja.md`](OPERATIONS_ja.md) - 運用とメンテナンス手順
- [`INSTALLATION_ja.md`](INSTALLATION_ja.md) - インストールと初期設定
- [`NETWORK_SETUP_ja.md`](NETWORK_SETUP_ja.md) - ネットワーク設定詳細
- [`TROUBLESHOOTING_ja.md`](TROUBLESHOOTING_ja.md) - 問題解決ガイド

---

*Azazel-Piアーキテクチャの詳細については、[公式リポジトリ](https://github.com/01rabbit/Azazel-Pi)のソースコードとドキュメントを参照してください。*