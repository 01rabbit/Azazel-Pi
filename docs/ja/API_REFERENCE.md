# API リファレンス

このリファレンスでは、Azazel制御プレーンを構成するPythonモジュールについて文書化しています。運用者がテスト中に動作を拡張またはモック化するのに十分なコンテキストを提供することを目的としています。

## `azazel_pi.core.state_machine`

### 基本クラス

#### `State(name: str, description: str = "")`
防御システムの名前付き状態を表現します。

**パラメータ:**
- `name`: 状態の一意識別子（"portal", "shield", "lockdown"）
- `description`: 状態の説明文

**使用例:**
```python
portal = State(name="portal", description="通常運用")
shield = State(name="shield", description="強化監視")
lockdown = State(name="lockdown", description="完全封じ込めモード")
```

#### `Event(name: str, severity: int = 0)`
状態遷移をトリガーする可能性のある外部イベントです。

**パラメータ:**
- `name`: イベント名（状態名と対応）
- `severity`: 重要度スコア（0以上の整数）

**使用例:**
```python
event = Event(name="shield", severity=25)
critical_event = Event(name="lockdown", severity=85)
```

#### `Transition(source, target, condition, action=None)`
イベントによってトリガーされる状態間の遷移です。

**パラメータ:**
- `source`: 遷移元の状態オブジェクト
- `target`: 遷移先の状態オブジェクト  
- `condition`: 遷移条件を評価する関数
- `action`: 遷移時に実行されるアクション（オプション）

**使用例:**
```python
transition = Transition(
    source=portal,
    target=shield,
    condition=lambda event: event.name == "shield"
)
```

### StateMachine クラス

#### `StateMachine(initial_state, config_path=None, window_size=5)`
YAML設定に基づくモード対応状態マシンです。

**パラメータ:**
- `initial_state`: 初期状態オブジェクト
- `config_path`: 設定ファイルのパス（デフォルト: `/etc/azazel/azazel.yaml`）
- `window_size`: スコア移動平均のウィンドウサイズ

#### メソッド

##### `add_transition(transition)`
新しい遷移を登録します。

**パラメータ:**
- `transition`: Transitionオブジェクト

**使用例:**
```python
machine = StateMachine(initial_state=portal)
machine.add_transition(Transition(
    source=portal,
    target=shield,
    condition=lambda event: event.name == "shield"
))
```

##### `dispatch(event)`
現在の状態から遷移を評価します。

**パラメータ:**
- `event`: 処理するEventオブジェクト

**戻り値:**
- 遷移後の状態オブジェクト

**使用例:**
```python
new_state = machine.dispatch(Event(name="shield", severity=30))
print(f"新しい状態: {new_state.name}")
```

##### `reset()`
初期状態に戻り、スコア履歴をクリアします。

**使用例:**
```python
machine.reset()
print(f"リセット後の状態: {machine.current_state.name}")
```

##### `summary()`
API応答に適した辞書を返します。

**戻り値:**
- 状態情報を含む辞書

**使用例:**
```python
status = machine.summary()
# {"state": "portal", "description": "通常運用"}
```

##### `get_thresholds()`
`azazel.yaml`からshield/lockdown閾値とアンロックタイマーを読み取ります。

**戻り値:**
- 閾値設定を含む辞書

**使用例:**
```python
thresholds = machine.get_thresholds()
# {"t1": 25, "t2": 75, "shield_unlock_seconds": 300, ...}
```

##### `get_actions_preset()`
現在のモードの遅延/シェーピング/ブロック プリセットを取得します。

**戻り値:**
- アクション設定を含む辞書

**使用例:**
```python
preset = machine.get_actions_preset()
# {"delay_ms": 100, "bandwidth_kbps": null, "block_enabled": false}
```

##### `apply_score(severity)`
移動平均スコアウィンドウを更新し、適切なモードに遷移して、評価メタデータを返します。

**パラメータ:**
- `severity`: イベントの重要度スコア

**戻り値:**
- 評価結果を含む辞書

**使用例:**
```python
result = machine.apply_score(45)
print(f"平均スコア: {result['average']}")
print(f"目標モード: {result['desired_mode']}")
print(f"適用モード: {result['applied_mode']}")
```

## `azazel_pi.core.scorer`

### ScoreEvaluator クラス

累積重要度を計算し、スコア分類を提供します。

#### `ScoreEvaluator(baseline: int = 0)`

**パラメータ:**
- `baseline`: ベースラインスコア（デフォルト: 0）

#### メソッド

##### `evaluate(events: Iterable[Event]) -> int`
複数のイベントから累積重要度スコアを計算します。

**パラメータ:**
- `events`: Eventオブジェクトのイテラブル

**戻り値:**
- 累積スコア値

**使用例:**
```python
scorer = ScoreEvaluator(baseline=10)
events = [
    Event("alert1", severity=15),
    Event("alert2", severity=20)
]
total_score = scorer.evaluate(events)
# 結果: 45 (10 + 15 + 20)
```

##### `classify(score: int) -> str`
スコアの文字列分類を返します。

**パラメータ:**
- `score`: 分類するスコア値

**戻り値:**
- `"normal"`, `"guarded"`, `"elevated"`, または `"critical"`

**分類基準:**
- `score >= 80`: `"critical"`
- `score >= 50`: `"elevated"`  
- `score >= 20`: `"guarded"`
- `score < 20`: `"normal"`

**使用例:**
```python
classification = scorer.classify(65)
print(classification)  # "elevated"
```

## `azazel_pi.core.actions`

ネットワーク制御アクションのための共通インターフェースです。

### 基底クラス

#### `Action`
すべてのアクションの基底クラスです。

##### `plan(target: str) -> Iterator[ActionResult]`
実行計画を生成します（副作用なし）。

**パラメータ:**
- `target`: 対象インターフェース名

**戻り値:**
- ActionResultオブジェクトのイテレータ

##### `execute(target: str) -> List[ActionResult]`
計画を実際に実行します。

### 実装済みアクション

#### `DelayAction`
パケット遅延を注入します。

**使用例:**
```python
delay_action = DelayAction(delay_ms=200)
results = delay_action.execute("eth0")
```

#### `ShapeAction`  
帯域制限を適用します。

**使用例:**
```python
shape_action = ShapeAction(bandwidth_kbps=128)
results = shape_action.execute("eth0")
```

#### `BlockAction`
IPアドレスをブロックします。

**使用例:**
```python
block_action = BlockAction(blocked_ips=["192.168.1.100"])
results = block_action.execute("eth0")
```

#### `RedirectAction`
トラフィックをリダイレクトします。

**使用例:**
```python
redirect_action = RedirectAction(
    source_ip="192.168.1.100",
    target_ip="192.168.1.200"
)
results = redirect_action.execute("eth0")
```

### ActionResult

各アクションが返す結果オブジェクトです。

**プロパティ:**
- `command`: 実行されたコマンド
- `success`: 実行成功フラグ
- `output`: コマンド出力
- `error`: エラーメッセージ（ある場合）

## `azazel_pi.core.ingest`

ログファイルからイベントを読み取り、Eventインスタンスを発行します。意図的に決定論的であり、ユニットテストのカバレッジを容易にします。

### SuricataTail クラス

SuricataのEVE JSONログを処理します。

#### `SuricataTail(log_path: str)`

**パラメータ:**
- `log_path`: SuricataのEVEログファイルパス

#### メソッド

##### `tail_events() -> Iterator[Event]`
ログファイルを追跡してEventオブジェクトを生成します。

**使用例:**
```python
suricata_tail = SuricataTail("/var/log/suricata/eve.json")
for event in suricata_tail.tail_events():
    print(f"Suricataイベント: {event.name}, 重要度: {event.severity}")
```

### CanaryTail クラス

OpenCanaryハニーポットイベントを処理します。

#### `CanaryTail(log_path: str)`

**パラメータ:**
- `log_path`: OpenCanaryログファイルパス

#### メソッド

##### `tail_events() -> Iterator[Event]`
ハニーポットログからEventオブジェクトを生成します。

**使用例:**
```python
canary_tail = CanaryTail("/opt/azazel/logs/opencanary.log")
for event in canary_tail.tail_events():
    print(f"ハニーポットイベント: {event.name}, 重要度: {event.severity}")
```

## `azazel_pi.core.api`

将来のHTTPフロントエンドで使用される最小限のディスパッチャーです。

### APIServer クラス

#### `APIServer(host: str = "localhost", port: int = 8080)`

**パラメータ:**
- `host`: バインドするホスト
- `port`: バインドするポート

#### メソッド

##### `add_health_route(version: str)`
ヘルスチェックエンドポイントを追加します。

**パラメータ:**
- `version`: APIバージョン文字列

**使用例:**
```python
server = APIServer()
server.add_health_route("1.0.0")
server.start()
```

### HealthResponse

ヘルスチェックAPI応答のデータクラスです。

**プロパティ:**
- `status`: システム状態（"healthy", "degraded", "down"）
- `version`: システムバージョン
- `uptime`: 稼働時間（秒）
- `mode`: 現在の防御モード
- `timestamp`: 応答タイムスタンプ

## `azctl.cli`

systemdサービスを支援し、イベントを`AzazelDaemon`に送信してスコアベースの決定を適用し、選択されたモードとアクションプリセットを含む`decisions.log`エントリを書き込みます。

## `azctl.tui_zero` - Unified Textual TUI

Azazel-Pi のメニューTUIは、Azazel-Zero由来の unified Textual UI に統一されました。  
旧 `azctl/menu` モジュラー実装は削除済みです。

### 実装ファイル

```
azctl/tui_zero.py
azctl/tui_zero_textual.py
```

### 起動経路

- CLI: `python3 -m azctl.cli menu`
- 内部実装: `azctl.cli.cmd_menu()` -> `azctl.tui_zero.run_menu()`

### 主要挙動

- 状態取得は `runtime/ui_snapshot.json` を優先
- フォールバックとして `python3 -m azctl.cli status --json` を使用
- メニューアクションは以下へ変換:
  - `stage_open` -> `portal`
  - `reprobe` -> `shield`
  - `contain` -> `lockdown`

### 依存関係

- `textual`（メニューTUI必須）
- `rich`（他CLI/TUIの描画で利用）

### 主要関数

#### `build_machine() -> StateMachine`
portal/shield/lockdown状態を配線します。

**戻り値:**
- 設定済みのStateMachineオブジェクト

**使用例:**
```python
machine = build_machine()
print(f"初期状態: {machine.current_state.name}")
```

#### `load_events(path: str) -> Iterable[Event]`
合成イベントを記述したYAMLを読み込みます。

**パラメータ:**
- `path`: YAMLファイルのパス

**戻り値:**
- Eventオブジェクトのイテラブル

**YAMLフォーマット例:**
```yaml
events:
  - name: "test_alert"
    severity: 25
  - name: "high_priority"
    severity: 75
```

**使用例:**
```python
events = load_events("test_events.yaml")
for event in events:
    machine.dispatch(event)
```

#### `main(argv: List[str]) -> int`
メインCLIエントリーポイントです。

**パラメータ:**
- `argv`: コマンドライン引数

**戻り値:**
- 終了コード

### AzazelDaemon クラス

#### `AzazelDaemon(machine: StateMachine, scorer: ScoreEvaluator)`

**パラメータ:**
- `machine`: 状態マシンインスタンス
- `scorer`: スコア評価インスタンス

#### メソッド

##### `process_events(events: Iterable[Event])`
複数のイベントを処理し、決定ログに記録します。

**使用例:**
```python
daemon = AzazelDaemon(machine=build_machine(), scorer=ScoreEvaluator())
daemon.process_events([Event("alert", severity=30)])
```

##### `process_event(event: Event)`
単一のイベントを処理し、決定エントリを即座に追加します。

## HTTP エンドポイント

コントローラーは監督オーバーライドのための最小限のHTTPインターフェースを公開します。

### `POST /v1/mode`

防御モードの手動変更を行います。

**リクエスト:**
```bash
curl -X POST http://localhost:8080/v1/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "shield"}'
```

**リクエストボディ:**
```json
{
  "mode": "portal" | "shield" | "lockdown"
}
```

**レスポンス:**
```json
{
  "status": "success",
  "previous_mode": "portal",
  "current_mode": "shield",
  "applied_preset": {
    "delay_ms": 200,
    "bandwidth_kbps": 128,
    "block_enabled": false
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### `GET /v1/health`

システムヘルス状態を取得します。

**リクエスト:**
```bash
curl http://localhost:8080/v1/health
```

**レスポンス:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 3600,
  "mode": "portal",
  "score": 15,
  "events_processed": 142,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### `GET /v1/status`

詳細なシステム状態を取得します。

**リクエスト:**
```bash
curl http://localhost:8080/v1/status
```

**レスポンス:**
```json
{
  "system": {
    "hostname": "azazel-gateway",
    "uptime": 3600,
    "cpu_percent": 25.5,
    "memory_percent": 45.2
  },
  "network": {
    "interface": "eth0",
    "rx_bytes": 1048576,
    "tx_bytes": 524288
  },
  "security": {
    "mode": "portal",
    "score": 15,
    "alerts_last_hour": 3,
    "last_mode_change": "2024-01-15T09:15:00Z"
  }
}
```

### `POST /v1/reset`

システム状態をリセットします。

**リクエスト:**
```bash
curl -X POST http://localhost:8080/v1/reset
```

**レスポンス:**
```json
{
  "status": "success",
  "message": "System reset to initial state",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## スクリプト

### `scripts/suricata_generate.py`
SuricataのYAMLテンプレートをレンダリングします。

**使用方法:**
```bash
sudo python3 scripts/suricata_generate.py \
  /etc/azazel/azazel.yaml \
  /etc/azazel/suricata/suricata.yaml.tmpl \
  --output /etc/suricata/suricata.yaml
```

**オプション:**
- `--interface`: 監視インターフェース指定
- `--home-net`: ホームネットワーク範囲指定
- `--output`: 出力ファイルパス

### `scripts/nft_apply.sh`
nftablesファイアウォールルールを管理します。

**使用方法:**
```bash
# ルール適用
sudo scripts/nft_apply.sh /etc/azazel/nftables/lockdown.nft

# ルール確認
sudo scripts/nft_apply.sh --verify

# ルールクリア
sudo scripts/nft_apply.sh --clear
```

### `scripts/tc_reset.sh`
トラフィック制御設定を管理します。

**使用方法:**
```bash
# TC設定リセット
sudo scripts/tc_reset.sh

# 特定インターフェースのリセット
sudo scripts/tc_reset.sh eth0

# 設定確認
sudo scripts/tc_reset.sh --show
```

### `scripts/sanity_check.sh`
依存サービスが非アクティブの場合に警告を出力します。

**使用方法:**
```bash
# 基本ヘルスチェック
sudo scripts/sanity_check.sh

# 詳細チェック
sudo scripts/sanity_check.sh --verbose

# JSON形式出力
sudo scripts/sanity_check.sh --json
```

**出力例:**
```
[OK] azctl-unified.service is active
[OK] suricata.service is active  
[WARNING] azazel_opencanary container is inactive
[OK] vector.service is active
[ERROR] mattermost.service failed to start
```

### `scripts/rollback.sh`
インストールされたアセットを削除します。

**使用方法:**
```bash
# 完全削除
sudo scripts/rollback.sh

# 設定保持して削除
sudo scripts/rollback.sh --keep-config

# ドライラン（何が削除されるかを表示）
sudo scripts/rollback.sh --dry-run
```

### `scripts/resolve_allowlist.py`
医療FQDNをCIDRに解決し、生成されたテンプレートで使用されるlockdown nftables許可リストを書き込みます。

**使用方法:**
```bash
# 許可リスト生成
sudo python3 scripts/resolve_allowlist.py \
  --config /etc/azazel/azazel.yaml \
  --output /etc/azazel/nftables/allowlist.conf

# 特定ドメイン追加
sudo python3 scripts/resolve_allowlist.py \
  --add-domain "emergency.hospital.local" \
  --output /etc/azazel/nftables/allowlist.conf
```

**設定例:**
```yaml
# azazel.yaml内
lockdown:
  medical_domains:
    - "*.hospital.local"
    - "emergency.medical.gov"
    - "telemedicine.health.org"
```

**生成される許可リスト例:**
```
# Generated allowlist for lockdown mode
192.168.100.0/24  # hospital.local
203.0.113.0/24    # emergency.medical.gov
198.51.100.0/24   # telemedicine.health.org
```

## 使用例とベストプラクティス

### 基本的な状態マシン使用例

```python
from azazel_pi.core.state_machine import StateMachine, State, Event, Transition
from azazel_pi.core.scorer import ScoreEvaluator

# 状態定義
portal = State("portal", "通常運用")
shield = State("shield", "強化監視")
lockdown = State("lockdown", "緊急封じ込め")

# 状態マシン初期化
machine = StateMachine(initial_state=portal)

# 遷移定義
machine.add_transition(Transition(
    source=portal, target=shield,
    condition=lambda event: event.severity >= 25
))

machine.add_transition(Transition(
    source=shield, target=lockdown,
    condition=lambda event: event.severity >= 75
))

# イベント処理
event = Event("intrusion_detected", severity=30)
new_state = machine.dispatch(event)
print(f"新しい状態: {new_state.name}")
```

### カスタムアクション実装

```python
from azazel_pi.core.actions import Action, ActionResult

class CustomLogAction(Action):
    def __init__(self, log_message: str):
        self.log_message = log_message
    
    def plan(self, target: str) -> Iterator[ActionResult]:
        yield ActionResult(
            command=f"logger '{self.log_message}'",
            success=True,
            output=f"Logged: {self.log_message}"
        )
    
    def execute(self, target: str) -> List[ActionResult]:
        import subprocess
        results = []
        for result in self.plan(target):
            try:
                subprocess.run(result.command.split(), check=True)
                results.append(result)
            except subprocess.CalledProcessError as e:
                results.append(ActionResult(
                    command=result.command,
                    success=False,
                    error=str(e)
                ))
        return results
```

### イベント監視とテスト

```python
import time
from azazel_pi.core.ingest import SuricataTail

# リアルタイム監視
suricata_tail = SuricataTail("/var/log/suricata/eve.json")

for event in suricata_tail.tail_events():
    if event.severity > 50:
        print(f"高重要度アラート: {event.name}")
        # 状態マシンに送信
        machine.dispatch(event)
    
    time.sleep(0.1)  # CPU使用率制御
```

## 関連ドキュメント

- [`ARCHITECTURE_ja.md`](ARCHITECTURE_ja.md) - システム全体のアーキテクチャ詳細
- [`OPERATIONS_ja.md`](OPERATIONS_ja.md) - 日常運用とメンテナンス手順
- [`INSTALLATION_ja.md`](INSTALLATION_ja.md) - インストールと初期設定
- [`TROUBLESHOOTING_ja.md`](TROUBLESHOOTING_ja.md) - API関連のトラブルシューティング

---

*API仕様の最新情報については、[Azazel-Piリポジトリ](https://github.com/01rabbit/Azazel-Pi)のソースコードとテストスイートを参照してください。*
