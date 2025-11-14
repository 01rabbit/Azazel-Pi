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

## `azctl.menu` - モジュラーTUIメニューシステム

Azazel-Piは、保守性と拡張性を重視したモジュラーアーキテクチャによるターミナルユーザーインターフェースを提供します。

### アーキテクチャ

```
azctl/menu/
├── __init__.py      # モジュールエントリーポイント
├── types.py         # 共通データクラス定義
├── core.py          # メインフレームワーク
├── defense.py       # 防御制御モジュール
├── services.py      # サービス管理モジュール
├── network.py       # ネットワーク情報モジュール
├── wifi.py          # WiFi管理モジュール
├── monitoring.py    # ログ監視モジュール
├── system.py        # システム情報モジュール
└── emergency.py     # 緊急操作モジュール
```

### 基本データ型 (`types.py`)

#### `MenuAction`
メニューアクション項目を表現するデータクラスです。

**プロパティ:**
- `title: str` - 表示タイトル
- `description: str` - 詳細説明
- `action: Callable` - 実行される関数
- `requires_root: bool` - root権限の要否（デフォルト: False）
- `dangerous: bool` - 危険な操作かどうか（デフォルト: False）

**使用例:**
```python
from azctl.menu.types import MenuAction

action = MenuAction(
    title="モード切り替え",
    description="防御モードを手動で変更します",
    action=lambda: switch_mode("shield"),
    requires_root=True,
    dangerous=True
)
```

#### `MenuCategory`
メニューカテゴリ（複数のアクションを含む）を表現するデータクラスです。

**プロパティ:**
- `title: str` - カテゴリタイトル
- `description: str` - カテゴリ説明
- `actions: list[MenuAction]` - 含まれるアクション一覧

**使用例:**
```python
from azctl.menu.types import MenuCategory, MenuAction

category = MenuCategory(
    title="防御制御",
    description="防御システムの監視と制御",
    actions=[
        MenuAction("現在の状態表示", "システム状態を確認", show_status),
        MenuAction("モード切り替え", "防御モードを変更", switch_mode)
    ]
)
```

### コアフレームワーク (`core.py`)

#### `AzazelTUIMenu`
メインのTUIメニューシステムクラスです。

**初期化:**
```python
AzazelTUIMenu(
    decisions_log: Optional[str] = None,
    lan_if: str = "wlan0", 
    wan_if: str = "wlan1"
)
```

**パラメータ:**
- `decisions_log` - 決定ログファイルのパス
- `lan_if` - LANインターフェース名
- `wan_if` - WANインターフェース名

**メソッド:**

##### `run()`
メインのTUIループを開始します。

**使用例:**
```python
from azctl.menu import AzazelTUIMenu

menu = AzazelTUIMenu(lan_if="wlan0", wan_if="wlan1")
menu.run()
```

### 機能モジュール

#### 防御制御モジュール (`defense.py`)

##### `DefenseModule`
防御システムの監視と制御を行います。

**提供機能:**
- 現在の防御モード表示
- 手動モード切り替え
- 決定履歴の表示
- リアルタイム脅威スコア監視

**使用例:**
```python
from azctl.menu.defense import DefenseModule
from rich.console import Console

module = DefenseModule(Console())
category = module.get_category()
```

#### サービス管理モジュール (`services.py`)

##### `ServicesModule`
Azazelシステムサービスの管理を行います。

**管理対象サービス:**
- `azctl-unified.service` - 統合制御デーモン
- `azctl-unified.service` - HTTPサーバー
- `suricata.service` - IDS/IPS
- `azazel_opencanary (Docker)` - ハニーポット
- `vector.service` - ログ収集
- `azazel-epd.service` - E-Paperディスプレイ

**提供機能:**
- サービス状態の一覧表示
- サービスの開始/停止/再起動
- ログファイルのリアルタイム表示
- システム全体のヘルスチェック

#### ネットワーク情報モジュール (`network.py`)

##### `NetworkModule`
ネットワーク状態とWiFi管理の統合表示を行います。

**提供機能:**
- インターフェース状態表示
- アクティブプロファイル確認
- WiFi管理機能の統合
- ネットワークトラフィック統計

#### WiFi管理モジュール (`wifi.py`)

##### `WiFiManager`
WiFiネットワークの包括的な管理を行います。

**提供機能:**
- 近隣WiFiネットワークのスキャン
- WPA/WPA2ネットワークへの接続
- 保存済みネットワークの管理
- 接続状態とシグナル強度の表示
- SSID選択とパスワード入力のインタラクティブUI

**技術仕様:**
- `iw scan` による周辺ネットワーク検索
- `wpa_cli` による接続管理
- Rich UIによる見やすい表形式表示
- セキュリティ種別の自動判別

#### ログ監視モジュール (`monitoring.py`)

##### `MonitoringModule`
セキュリティログとシステムログの監視を行います。

**監視対象:**
- Suricataアラートログ (`/var/log/suricata/eve.json`)
- OpenCanaryイベントログ
- Azazel決定ログ (`/var/log/azazel/decisions.log`)
- システムジャーナル

**提供機能:**
- リアルタイムログ監視
- アラート要約とカウント
- ログファイルの履歴表示
- セキュリティイベントの分析

#### システム情報モジュール (`system.py`)

##### `SystemModule`
システムリソースとハードウェア状態の監視を行います。

**監視項目:**
- CPU使用率とプロセッサ情報
- メモリ使用量（物理/スワップ）
- ディスク使用量
- ネットワークインターフェース統計
- システム温度（Raspberry Pi）
- 実行中プロセス一覧

#### 緊急操作モジュール (`emergency.py`)

##### `EmergencyModule`
緊急時の対応操作を提供します。

**提供機能:**
- **緊急ロックダウン**: 即座にネットワークアクセスを遮断
- **ネットワーク設定リセット**: WiFi設定を初期状態に戻す
- **システムレポート生成**: 包括的な状態レポートを作成
- **ファクトリーリセット**: システム全体を初期状態に戻す

**安全機能:**
- 複数段階の確認ダイアログ
- 危険度に応じた警告表示
- 操作ログの自動記録
- 中断可能な操作フロー

### カスタムモジュールの作成

新しい機能モジュールを追加する場合の例：

```python
# azctl/menu/custom.py
from rich.console import Console
from .types import MenuCategory, MenuAction

class CustomModule:
    def __init__(self, console: Console):
        self.console = console
    
    def get_category(self) -> MenuCategory:
        return MenuCategory(
            title="カスタム機能",
            description="カスタム機能の説明",
            actions=[
                MenuAction(
                    title="カスタム操作",
                    description="カスタム操作の説明",
                    action=self._custom_action
                )
            ]
        )
    
    def _custom_action(self):
        self.console.print("カスタム操作を実行中...")
```

### 統合とテスト

```python
# 新しいモジュールをコアシステムに統合
# azctl/menu/core.py の _setup_menu_categories() に追加

from .custom import CustomModule

# __init__ メソッド内
self.custom_module = CustomModule(self.console)

# _setup_menu_categories メソッド内
self.categories.append(self.custom_module.get_category())
```

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
