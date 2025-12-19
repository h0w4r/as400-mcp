# AS400 MCP Server

Claude Code用のAS400/IBM i開発支援MCPサーバーです。
ODBC経由でAS400のメタデータやソースコードを取得し、CL/RPG/COBOLプログラムの開発を支援します。

## 特徴

- **日本語ラベル対応**: カラムやテーブルの日本語説明（TEXT）を取得・活用
- **ソースコード参照**: QCLSRC/QRPGSRC等からソースを取得
- **プログラム依存関係調査**: 参照ファイル・呼び出し関係を取得
- **システム情報取得**: OSバージョン、PTFレベル等を確認
- **読み取り専用**: セキュリティのため全て読み取り操作のみ

## 利用可能なツール

| ツール | 説明 |
|--------|------|
| `list_libraries` | ライブラリ一覧（ラベル付き） |
| `list_tables` | テーブル/ファイル一覧 |
| `get_columns` | カラム一覧（日本語ラベル、型、キー情報） |
| `list_source_files` | ソースファイル一覧（QCLSRC, QRPGSRC等） |
| `list_sources` | ソースメンバー一覧 |
| `get_source` | ソースコード取得 |
| `get_data` | テーブルデータ取得 |
| `get_table_info` | テーブル詳細情報 |
| `get_system_info` | システム情報（OSバージョン、PTF等） |
| `list_programs` | プログラム一覧（RPG/CL/COBOL等） |
| `get_program_references` | プログラムの参照ファイル・呼び出し関係 |
| `list_data_areas` | データエリア一覧（共有変数） |
| `execute_sql` | 任意SELECT実行（読み取り専用） |

## インストール

### 前提条件

- Python 3.10以上
- IBM i Access ODBC Driver
- AS400/IBM i 7.3以上（推奨: 7.4以上）
  - 7.3: 基本機能が動作
  - 7.4+: `get_program_references`等の追加機能が利用可能
- AS400/IBM iへの接続情報

### インストール手順

```bash
# 1. リポジトリをクローン
git clone https://github.com/omni-s/as400-mcp.git
cd as400-mcp

# 2. 仮想環境を作成・有効化
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

# 3. パッケージをインストール
pip install -e .
```

## Claude Code設定

実際にClaude Codeを動かすプロジェクトルートに `.mcp.json` ファイルを作成してください。

接続情報（パスワード等）を含む場合は `.gitignore` に `.mcp.json` を追加することを推奨します。

### Windows（.mcp.json）

```json
{
  "mcpServers": {
    "as400": {
      "command": "C:/path/to/as400-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "as400_mcp.server"],
      "env": {
        "AS400_CONNECTION_STRING": "DRIVER={IBM i Access ODBC Driver};SYSTEM=YOUR_SYSTEM;UID=USER;PWD=PASS;CCSID=1208;EXTCOLINFO=1"
      }
    }
  }
}
```

### Linux/macOS（.mcp.json）

```json
{
  "mcpServers": {
    "as400": {
      "command": "/path/to/as400-mcp/.venv/bin/python",
      "args": ["-m", "as400_mcp.server"],
      "env": {
        "AS400_CONNECTION_STRING": "DRIVER={IBM i Access ODBC Driver};SYSTEM=YOUR_SYSTEM;UID=USER;PWD=PASS;CCSID=1208;EXTCOLINFO=1"
      }
    }
  }
}
```

設定後、Claude Codeを再起動して `/mcp` コマンドでas400サーバーが表示されることを確認してください。

### 接続文字列のオプション

| オプション | 説明 |
|-----------|------|
| `SYSTEM` | AS400のホスト名またはIPアドレス |
| `UID` | ユーザーID |
| `PWD` | パスワード |
| `CCSID=1208` | UTF-8通信（日本語対応） |
| `EXTCOLINFO=1` | 拡張カラム情報（COLUMN_TEXT等）を取得 |

## 使い方

### 基本的なワークフロー

```
ユーザー: MYLIBの受注テーブルを使ったWeb画面を作って

Claude Code:
1. get_table_info("MYLIB", "ORDER") でテーブル情報取得
2. カラム情報（日本語ラベル付き）を確認
3. get_data でサンプルデータを確認
4. Web画面（React等）とAPI（FastAPI等）を生成
```

### 使用例

#### テーブル構造確認

```
> MYLIBのORDERテーブルの構造を教えて
```

#### 既存ソース参照

```
> MYLIBのソースファイル一覧を見せて
> MYLIB/QRPGSRC内のORDMNTソースを見せて
```

#### プログラム調査

```
> MYLIBにあるRPGプログラムの一覧を見せて
> ORDER001プログラムが参照しているファイルを教えて
```

#### Web画面生成

```
> MYLIBのCUSTOMERテーブルでWebの一覧・詳細画面を作って
  - 日本語ラベルを画面項目名に
  - 検索機能付き
```

#### システム情報確認

```
> AS400のバージョンを教えて
```

## ODBCドライバーの設定

ODBCドライバーの導入方法については、以下の公式ドキュメントを参照してください。

[IBM i Access ODBC Installation](https://ibmi-oss-docs.readthedocs.io/en/latest/odbc/installation.html)


## 開発

### Claude Code無しでテストする

MCPサーバーはClaude Code無しでも動作確認できます。

```bash
# .env.exampleをコピーして接続情報を設定
cp .env.example .env
# .envを編集して接続情報を入力

# 直接起動（stdinにJSON-RPCを入力）
python -m as400_mcp.server

# ツール一覧を取得
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m as400_mcp.server
```
> 上記はClaude Code経由ではなく単独でas400-mcp動作させたい場合です。

#### MCP Inspector（推奨）

Anthropic提供のデバッグ用WebUIでGUIからツールをテストできます。

```bash
npx @modelcontextprotocol/inspector python -m as400_mcp.server
```
> 「Claude Code無しでテストする」の .env の編集は行ってある事が前提です

ブラウザが開き、ツール一覧の確認や実行テストが可能です。

### ユニットテスト

```bash
# 開発用依存パッケージをインストール
pip install -e ".[dev]"

# テスト実行
pytest tests/ -v
```

### リント

```bash
ruff check .
ruff format .
```

## トラブルシューティング

### 接続エラー

```
[HY000] [IBM][System i Access ODBC Driver]Communication link failure
```

→ SYSTEM、UID、PWDを確認。ファイアウォールでポート446/449/8470等が開いているか確認。

### 文字化け

```
UnicodeDecodeError
```

→ 接続文字列に`CCSID=1208`を追加（UTF-8通信）。

### 日本語ラベルが取得できない

```
COLUMN_TEXT が空
```

→ 接続文字列に`EXTCOLINFO=1`を追加。

### 権限エラー

```
[42501] User not authorized to object
```

→ AS400側でユーザーにQSYS2カタログビューへのアクセス権限を付与。

## ライセンス

MIT License - Copyright (c) 2025 kozokaAI Inc.

## 関連リンク

- [FastMCP](https://github.com/jlowin/fastmcp)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25)
