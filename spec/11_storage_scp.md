# 11. Storage SCP仕様

## 概要

DICOM Storage SCP（C-STORE受信）機能の仕様。

**Phase**: Phase 1.5（オプション機能）

**依存**: Phase 0 (Core Engine)

**目的**: 他のDICOMモダリティから画像を受信して保存する。

---

## Phase 1.5の位置づけ

```text
Phase 1: CLI              ✅ 必須
   ↓
Phase 1.5: Storage SCP    🔲 オプション（早期実装推奨）
   ↓
Phase 2: GUI              ✅ 必須
```

**理由**: 早期に必要との要望があるため、Phase 1完了後すぐに実装可能。

---

## 最小要件

### 必須機能

1. **C-STORE受信**: DICOM画像を受信して保存
2. **AE Title / Port設定**: 設定ファイルで変更可能
3. **受信ディレクトリ構造**: Patient ID / Study UID / Series UID / ファイル
4. **ログ出力**: 受信ファイル情報
5. **衝突処理**: 同一SOP Instance UIDが来た場合は上書き or 拒否

### オプション機能（Phase 2以降）

- C-ECHO対応（疎通確認）
- Association制御（複数同時接続）
- Storage Commitment
- Query/Retrieve

---

## 設定

### 設定ファイル

```yaml
# config/app_config.yaml
storage_scp:
  enabled: false  # Phase 1.5で有効化
  ae_title: "DICOM_GEN_SCP"
  port: 11112
  bind_address: "0.0.0.0"  # すべてのネットワークインターフェース
  storage_dir: "scp_storage"
  duplicate_handling: "overwrite"  # overwrite, reject, rename
  supported_sop_classes:
    - "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage
    - "1.2.840.10008.5.1.4.1.1.7"  # Secondary Capture
    - "1.2.840.10008.5.1.4.1.1.4"  # MR Image Storage
```

---

## 受信ディレクトリ構造

```text
scp_storage/
├── P000001/                        # Patient ID
│   └── 2.25.123.../                # Study Instance UID（短縮表示）
│       ├── 2.25.456.../            # Series Instance UID（短縮表示）
│       │   ├── 1.2.840...001.dcm   # SOP Instance UID
│       │   ├── 1.2.840...002.dcm
│       │   └── ...
│       └── 2.25.789.../
│           └── ...
└── P000002/
    └── ...
```

### UID短縮ルール

UIDが長すぎるため、ディレクトリ名は先頭20文字に短縮：

```text
Study UID: 2.25.113059749145936325402354257176981405696
       ↓
Dir Name:  2.25.113059749145936
```

---

## PyNetDICOM実装

### C-STOREハンドラ

```python
# app/scp/storage_scp.py
from pynetdicom import AE, evt, StoragePresentationContexts
from pynetdicom.sop_class import CTImageStorage
import os
import logging

logger = logging.getLogger("dicom_generator.scp")

def handle_store(event):
    """C-STORE受信時のハンドラ"""
    ds = event.dataset
    
    # Patient ID / Study UID / Series UID 取得
    patient_id = ds.PatientID
    study_uid = ds.StudyInstanceUID
    series_uid = ds.SeriesInstanceUID
    sop_uid = ds.SOPInstanceUID
    
    logger.info(f"Received C-STORE: Patient={patient_id}, SOP={sop_uid}")
    
    # ディレクトリ作成
    storage_dir = "scp_storage"
    study_dir_name = study_uid[:20]  # UID短縮
    series_dir_name = series_uid[:20]
    
    output_dir = os.path.join(
        storage_dir,
        patient_id,
        study_dir_name,
        series_dir_name
    )
    os.makedirs(output_dir, exist_ok=True)
    
    # ファイル保存
    filename = f"{sop_uid}.dcm"
    filepath = os.path.join(output_dir, filename)
    
    # 衝突チェック
    if os.path.exists(filepath):
        duplicate_handling = get_config("duplicate_handling")
        
        if duplicate_handling == "reject":
            logger.warning(f"Duplicate SOP UID rejected: {sop_uid}")
            return 0xC000  # Failure
        
        elif duplicate_handling == "rename":
            import time
            filepath = filepath.replace(".dcm", f"_dup{int(time.time())}.dcm")
            logger.info(f"Renamed to avoid duplicate: {filepath}")
    
    # 保存
    ds.save_as(filepath, write_like_original=False)
    logger.info(f"Stored: {filepath}")
    
    return 0x0000  # Success
```

### SCP起動

```python
def start_scp(config: dict):
    """Storage SCP起動"""
    ae = AE(ae_title=config['ae_title'])
    
    # Storage Presentation Contextsを追加
    for sop_class_uid in config['supported_sop_classes']:
        ae.add_supported_context(sop_class_uid)
    
    # C-STOREハンドラ設定
    handlers = [(evt.EVT_C_STORE, handle_store)]
    
    # SCP起動（ブロッキング）
    logger.info(f"Starting SCP: {config['ae_title']}@{config['port']}")
    ae.start_server(
        (config['bind_address'], config['port']),
        evt_handlers=handlers,
        block=True
    )

# 使用例
if __name__ == '__main__':
    import yaml
    
    with open("config/app_config.yaml") as f:
        config = yaml.safe_load(f)
    
    scp_config = config['storage_scp']
    
    if scp_config['enabled']:
        start_scp(scp_config)
    else:
        print("Storage SCP is disabled")
```

---

## CLI統合

### サブコマンド追加

```bash
python -m app.cli scp start
```

```python
# app/cli/commands.py
def scp_start_command(args):
    """SCP起動コマンド"""
    from app.scp.storage_scp import start_scp
    
    # 設定読み込み
    config = load_app_config()
    scp_config = config['storage_scp']
    
    if not scp_config['enabled']:
        print("[ERROR] Storage SCP is disabled in config")
        return 1
    
    print(f"[INFO] Starting SCP: {scp_config['ae_title']}@{scp_config['port']}")
    
    try:
        start_scp(scp_config)
        return 0
    except KeyboardInterrupt:
        print("\n[INFO] SCP stopped by user")
        return 0
    except Exception as e:
        print(f"[ERROR] SCP failed: {e}")
        return 1

# argparse設定
scp_parser = subparsers.add_parser('scp')
scp_subparsers = scp_parser.add_subparsers(dest='scp_command')
scp_start_parser = scp_subparsers.add_parser('start')
```

---

## GUI統合

### SCP設定タブ

```python
# app/gui/widgets/scp_widget.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QPushButton, QLabel
)

class SCPWidget(QWidget):
    """Storage SCP設定ウィジェット"""
    
    def __init__(self):
        super().__init__()
        
        layout = QVBoxLayout()
        
        # 設定グループ
        config_group = QGroupBox("SCP設定")
        config_layout = QFormLayout()
        
        self.ae_title_edit = QLineEdit("DICOM_GEN_SCP")
        config_layout.addRow("AE Title:", self.ae_title_edit)
        
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(11112)
        config_layout.addRow("Port:", self.port_spin)
        
        self.storage_dir_edit = QLineEdit("scp_storage")
        config_layout.addRow("保存先:", self.storage_dir_edit)
        
        self.duplicate_combo = QComboBox()
        self.duplicate_combo.addItems(["上書き", "拒否", "リネーム"])
        config_layout.addRow("衝突時:", self.duplicate_combo)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # 制御ボタン
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("起動")
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        layout.addLayout(button_layout)
        
        # ステータス
        self.status_label = QLabel("ステータス: 停止中")
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
        
        # シグナル接続
        self.start_button.clicked.connect(self.start_scp)
        self.stop_button.clicked.connect(self.stop_scp)
    
    def start_scp(self):
        """SCP起動"""
        # SCPスレッド起動
        # ...
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("ステータス: 起動中")
    
    def stop_scp(self):
        """SCP停止"""
        # SCPスレッド停止
        # ...
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("ステータス: 停止中")
```

### SCPスレッド

```python
# app/gui/scp_thread.py
from PySide6.QtCore import QThread, Signal

class SCPThread(QThread):
    """SCP実行スレッド"""
    
    file_received = Signal(str)  # filepath
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.stop_requested = False
    
    def run(self):
        """SCP実行"""
        from app.scp.storage_scp import start_scp_non_blocking
        
        try:
            start_scp_non_blocking(
                self.config,
                stop_check=lambda: self.stop_requested,
                on_received=self.on_file_received
            )
        except Exception as e:
            logger.error(f"SCP error: {e}")
    
    def request_stop(self):
        """停止要求"""
        self.stop_requested = True
    
    def on_file_received(self, filepath):
        """ファイル受信時"""
        self.file_received.emit(filepath)
```

---

## ログ仕様

### 受信時のログ

```text
[INFO] 2025-02-21 15:00:00 - SCP started
  AE Title: DICOM_GEN_SCP
  Port: 11112
  Storage Dir: scp_storage

[INFO] 2025-02-21 15:00:05 - Association requested
  Calling AE: MODALITY_001
  Calling IP: 192.168.1.100

[INFO] 2025-02-21 15:00:06 - Received C-STORE
  Patient ID: P000001
  Study UID: 2.25.123...
  Series UID: 2.25.456...
  SOP UID: 2.25.789...

[INFO] 2025-02-21 15:00:06 - Stored
  Filepath: scp_storage/P000001/2.25.123.../2.25.456.../2.25.789....dcm
  File Size: 262656 bytes

[WARNING] 2025-02-21 15:00:07 - Duplicate SOP UID rejected
  SOP UID: 2.25.789...
  Duplicate Handling: reject
```

---

## セキュリティ考慮

### アクセス制御

```yaml
storage_scp:
  # ...
  allowed_ae_titles:
    - "MODALITY_001"
    - "MODALITY_002"
  allowed_ips:
    - "192.168.1.0/24"
```

### 実装例

```python
def handle_association_requested(event):
    """Association要求時の検証"""
    calling_ae = event.assoc.requestor.ae_title
    calling_ip = event.assoc.requestor.address
    
    allowed_aes = get_config("allowed_ae_titles")
    allowed_ips = get_config("allowed_ips")
    
    if calling_ae not in allowed_aes:
        logger.warning(f"Rejected: AE Title not allowed: {calling_ae}")
        event.assoc.reject()
        return
    
    # IPチェック（省略）
    # ...
```

---

## テスト

### SCP起動テスト

```python
# tests/scp/test_storage_scp.py
import pytest
from pynetdicom import AE
from app.scp.storage_scp import start_scp

def test_scp_receives_ct_image(scp_server, ct_dataset):
    """CT画像を受信できるか"""
    # SCPを別スレッドで起動
    # ...
    
    # SCUから送信
    ae = AE()
    ae.add_requested_context(CTImageStorage)
    assoc = ae.associate("localhost", 11112)
    
    status = assoc.send_c_store(ct_dataset)
    
    assert status.Status == 0x0000  # Success
    
    # ファイルが保存されているか確認
    assert os.path.exists("scp_storage/P000001/...")
```

---

## パフォーマンス

### 同時接続数

Phase 1.5では単一Association。Phase 2で複数対応。

```python
# Phase 2での拡張例
ae.maximum_associations = 10
```

---

## トラブルシューティング

### ポート使用中エラー

```text
[ERROR] Address already in use: port 11112
```

**対処**:
1. 他のSCPが起動していないか確認
2. ポート番号を変更

### ファイアウォール設定

```bash
# Windowsファイアウォール設定
netsh advfirewall firewall add rule name="DICOM SCP" dir=in action=allow protocol=TCP localport=11112
```

---

## 次のステップ

1. Phase 1完了後にPhase 1.5実装
2. CLI統合（`python -m app.cli scp start`）
3. GUI統合（Phase 2）
