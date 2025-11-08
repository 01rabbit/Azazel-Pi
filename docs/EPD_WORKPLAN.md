# E‑Paper (EPD) 改修ワークプラン

目的
- EPD デーモンの `Bad file descriptor` エラーを解消し、実ハードウェア／エミュレーションで安定稼働させる。
- systemd ユニットのワーニング（`ConditionPathExists` のセクション位置など）やログ/デバッグを改善する。

受け入れ基準
- `azazel-epd.service` が systemd で警告なく起動し、周期更新で `Errno 9` を出さない。
- エミュレーションモードで生成される画像が `/tmp/azazel_epd_test.png` に保存されること。
- 実機では SPI デバイス（例: `/dev/spidev0.0`）にアクセスし、表示更新が行えること。

調査手順（優先度順）
1. ログと例外の詳細を取得
   - `journalctl -u azazel-epd.service -n 200 --no-pager`
   - `/var/log/syslog` と `dmesg` をチェック（SPI ドライバや permission エラー）
2. systemd ユニットの最小修正
   - `ConditionPathExists` は `[Unit]` セクションへ移動する。
   - ExecStart のラップ（`/bin/sh -c`）は保持するか、EnvironmentFile で展開する。環境変数の扱いを明確に。
3. ファイル記述子/デバイスハンドリング確認
   - epd_daemon を `--mode debug` (必要なら追加) で直接実行し、どの行で Bad FD が発生するか確認する。
   - 標準出力/標準エラーへスタックトレースを出すよう例外処理を改善する。
4. 権限・デバイス確認
   - systemd サービスの `User` / `Group` 設定（現在は root か確認）。SPI デバイスに対するアクセス権を確認。
   - `ls -l /dev/spidev*` と udev ルールの検討。
5. 依存ライブラリの確認
   - Pillow / numpy / Waveshare ドライバのバージョン互換性（libtiff は `libtiff6` 等）
6. エミュレーション vs 実機
   - エミュレートはまず安定させ、次に実機での差分を調べる。

小さな修正候補（チケット）
- unit: move ConditionPathExists to `[Unit]` and add `After=network.target` if needed
- unit: add `EnvironmentFile=/etc/default/azazel-epd` and expand vars there
- daemon: add `--debug` flag to increase logging and print FD states
- daemon: ensure any opened file/socket is closed in finally blocks
- deploy: add a smoke-test script `scripts/test_epd.sh` to run emulation and validate output

テスト手順（ローカル）
- エミュレーション: `python3 azazel_pi/core/display/epd_daemon.py --mode test --emulate`
  - 出力: `/tmp/azazel_epd_test.png` が存在するか
- systemd: `sudo systemctl daemon-reload && sudo systemctl restart azazel-epd.service` → `journalctl -u azazel-epd.service -f`

備考
- 既に本リポジトリ内で行った変更（systemd ExecStart を `/bin/sh -c` でラップ）は残しますが、ユニット内の `ConditionPathExists` の位置は移動する方が正しいです。
- 実ハードウェアでの最終確認は現物接続が必要です（権限/接続を確認してください）。

次のアクション
- このブランチ上で小さな修正（unit/Maintain logs/デバッグフラグ追加）を順番に作成します。

## Quick install & simple test (Waveshare official driver)

If you don't have the Waveshare Python library installed, you can follow these steps (example used successfully on Raspberry Pi Zero2W):

```bash
sudo apt update
sudo apt install -y \
   git python3-pip python3-pil python3-numpy \
   python3-rpi.gpio python3-spidev fonts-dejavu-core

cd ~
git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_Jetson/python
sudo python3 setup.py install
# or: pip3 install .
```

Then use the supplied example or the repository's `scripts/epd_hello.py` to test the display:

```bash
sudo python3 scripts/epd_hello.py
```

Notes:
- If the display is upside-down, either set `EPD_ROTATION=180` in your systemd drop-in or run the test with rotation applied in the daemon (`--rotate 180`).
- To avoid the boot animation powering the module down at startup (which can cause SPI file-descriptor issues), set environment variable `EPD_SKIP_BOOT_ANIM=1` (or `AZAZEL_EPD_SKIP_BOOT=1`) in the systemd drop-in or via `systemctl set-environment`.

Example: enable skip and rotation via systemctl (applies to current boot/runtime):

```bash
sudo systemctl set-environment EPD_SKIP_BOOT_ANIM=1
sudo systemctl set-environment EPD_ROTATION=180
sudo systemctl daemon-reload
sudo systemctl restart azazel-epd.service
```
