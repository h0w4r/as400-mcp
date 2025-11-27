"""
AS400/IBM i MCP Server for Claude Code
CL/RPGプログラム開発支援のためのMCPサーバー

このサーバーはMCP（Model Context Protocol）を使用して、
Claude CodeからAS400/IBM iシステムへのアクセスを提供します。

主な機能:
    - ライブラリ、テーブル、カラム情報の取得
    - ソースコード（CL/RPG/COBOL）の取得・参照
    - プログラム一覧・依存関係の調査
    - データエリア（共有変数）の取得
    - システム情報の取得

必要な環境:
    - Python 3.10+
    - IBM i Access ODBC Driver
    - AS400_CONNECTION_STRING 環境変数

使用例:
    $ export AS400_CONNECTION_STRING="DRIVER={IBM i Access ODBC Driver};SYSTEM=YOUR_SYSTEM;UID=USER;PWD=PASS;CCSID=1208;EXTCOLINFO=1"
    $ python -m as400_mcp.server
"""

import pyodbc
from typing import Optional
from fastmcp import FastMCP, Context

# MCPサーバーの初期化
mcp = FastMCP(
    name="as400-mcp",
    instructions="""
# AS400/IBM i 開発支援MCPサーバー

このMCPサーバーはAS400（IBM i）のCL/RPGプログラム開発を支援します。

## 主な機能
- ライブラリ、ファイル、カラム情報の取得
- ソースコード（CL/RPG/COBOL等）の取得・参照
- テーブルデータの取得
- プログラム一覧・参照関係の調査
- データエリア（共有変数）の取得
- システム情報（OSバージョン等）の取得

## 使用時のガイドライン

### CL/RPGプログラム作成時
1. まず `list_libraries` でライブラリ一覧を確認
2. `list_tables` で対象ライブラリのファイル一覧を確認
3. `get_columns` でカラム情報（日本語ラベル含む）を取得
4. 既存のソースがあれば `list_sources` と `get_source` で参照
5. 上記情報を元にCL/RPGプログラムを生成

### 既存プログラムの調査時
1. `list_programs` でライブラリ内のプログラム一覧を取得
2. `get_program_references` で参照ファイル・呼び出し関係を調査
3. `get_source` でソースコードを取得して内容を確認

### バッチ処理CL作成時
1. `list_data_areas` で共有パラメータ（処理日付、実行フラグ等）を確認
2. `list_tables` で処理対象ファイルを確認
3. 既存のCLがあれば `list_sources`（QCLSRC）で参照

### CRUD画面作成時
- カラムのラベル（COLUMN_TEXT）を画面の項目名として使用
- データ型（DATA_TYPE）に応じた入力バリデーションを設定
- キー項目を考慮した画面設計

### ソースコード参照時
- ソースファイル名を指定:
  - QCLSRC: CLプログラム
  - QRPGSRC: RPG（固定形式）
  - QRPGLESRC: RPG ILE（自由形式）
  - QCBLSRC: COBOL
  - QDDSSRC: DDS（画面/ファイル定義）
- メンバー名でソースを特定

### システム情報の確認
- `get_system_info` でOSバージョン、PTFレベル、システム状態を取得

## 注意事項
- ライブラリ名、ファイル名は大文字で指定（自動変換されます）
- ODBCドライバーが必要（IBM i Access ODBC Driver）
- `execute_sql` はSELECT文のみ実行可能（セキュリティのため）
"""
)

# =============================================================================
# 接続設定
# =============================================================================

# ODBC接続文字列（main()で環境変数から設定される）
CONNECTION_STRING = ""


def get_connection() -> pyodbc.Connection:
    """
    AS400へのODBC接続を取得する。

    各ツール関数から呼び出され、新しい接続を作成する。
    接続は呼び出し元のfinally句でclose()すること。

    Returns:
        pyodbc.Connection: AS400への接続オブジェクト

    Raises:
        ValueError: CONNECTION_STRINGが未設定の場合
        pyodbc.Error: 接続に失敗した場合
    """
    if not CONNECTION_STRING:
        raise ValueError(
            "CONNECTION_STRING が設定されていません。"
            "環境変数 AS400_CONNECTION_STRING を設定してください。"
        )
    return pyodbc.connect(CONNECTION_STRING)


def strip_values(row_dict: dict) -> dict:
    """
    辞書内の文字列値から両端の空白を除去する。

    AS400は固定長フィールドのため、文字列がスペース埋めされる。
    この関数で余分な空白を除去して使いやすくする。

    Args:
        row_dict: カラム名と値の辞書

    Returns:
        文字列値がstripされた辞書
    """
    return {
        key: value.strip() if isinstance(value, str) else value
        for key, value in row_dict.items()
    }


# =============================================================================
# Tools - ライブラリ・テーブル情報系
# =============================================================================

@mcp.tool()
def list_libraries(
    pattern: str = "%",
    include_system: bool = False
) -> list[dict]:
    """
    ライブラリ一覧を取得します。
    
    Args:
        pattern: ライブラリ名のパターン（%でワイルドカード）
        include_system: システムライブラリを含めるか
    
    Returns:
        ライブラリ一覧（名前、ラベル、タイプ）
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # QSYS2.SYSSCHEMAS: ライブラリ（スキーマ）のカタログビュー
        # 注意: SCHEMA_TYPEは新しいIBM iバージョンのみ存在
        # 互換性のため、システムライブラリはライブラリ名パターンで除外
        sql = """
            SELECT
                SYSTEM_SCHEMA_NAME AS LIBRARY_NAME,
                COALESCE(SCHEMA_TEXT, '') AS LIBRARY_TEXT
            FROM
                QSYS2.SYSSCHEMAS
            WHERE
                SYSTEM_SCHEMA_NAME LIKE ?
        """

        # システムライブラリ（Q*で始まるライブラリ）を除外する場合
        if not include_system:
            sql += " AND SYSTEM_SCHEMA_NAME NOT LIKE 'Q%'"
        
        sql += " ORDER BY SYSTEM_SCHEMA_NAME"
        
        cursor.execute(sql, (pattern,))
        
        # 結果をdict形式に変換して返す
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(strip_values(dict(zip(columns, row))))

        return results
    finally:
        conn.close()


def _list_tables_internal(
    library: str,
    pattern: str = "%",
    table_type: str = "ALL"
) -> list[dict]:
    """テーブル一覧を取得する内部関数（他のツールから呼び出し可能）。"""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # QSYS2.SYSTABLES: テーブル（ファイル）のカタログビュー
        # TABLE_TYPE: 'P'=物理ファイル, 'L'=論理ファイル, 'V'=ビュー
        # 注意: NUMBER_ROWSは新しいIBM iバージョンのみ存在するため除外
        sql = """
            SELECT
                SYSTEM_TABLE_NAME AS TABLE_NAME,
                COALESCE(TABLE_TEXT, '') AS TABLE_TEXT,
                TABLE_TYPE
            FROM QSYS2.SYSTABLES
            WHERE SYSTEM_TABLE_SCHEMA = ?
              AND SYSTEM_TABLE_NAME LIKE ?
        """

        # library.upper(): AS400は大文字が標準なので変換
        params = [library.upper(), pattern]

        # テーブルタイプでフィルタリング
        if table_type != "ALL":
            sql += " AND TABLE_TYPE = ?"
            params.append(table_type)

        sql += " ORDER BY SYSTEM_TABLE_NAME"

        cursor.execute(sql, params)

        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(strip_values(dict(zip(columns, row))))

        return results
    finally:
        conn.close()


@mcp.tool()
def list_tables(
    library: str,
    pattern: str = "%",
    table_type: str = "ALL"
) -> list[dict]:
    """
    指定ライブラリのテーブル（物理ファイル/論理ファイル）一覧を取得します。

    Args:
        library: ライブラリ名
        pattern: テーブル名のパターン（%でワイルドカード）
        table_type: ALL/P（物理）/L（論理）/V（ビュー）

    Returns:
        テーブル一覧（名前、ラベル、タイプ）
    """
    return _list_tables_internal(library, pattern, table_type)


def _get_columns_internal(library: str, table: str) -> list[dict]:
    """
    カラム情報を取得する内部関数（他のツールから呼び出し可能）。
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # QSYS2.SYSCOLUMNS: カラム情報のカタログビュー
        # COLUMN_TEXT: 日本語ラベル（画面項目名として使用可能）
        # CCSID: 文字コード（日本語は5035や1399等）
        sql = """
            SELECT
                c.SYSTEM_COLUMN_NAME AS COLUMN_NAME,
                COALESCE(c.COLUMN_TEXT, '') AS COLUMN_TEXT,
                c.DATA_TYPE,
                c.LENGTH,
                COALESCE(c.NUMERIC_SCALE, 0) AS DECIMAL_PLACES,
                c.IS_NULLABLE,
                c.ORDINAL_POSITION,
                COALESCE(c.COLUMN_DEFAULT, '') AS DEFAULT_VALUE,
                c.CCSID
            FROM
                QSYS2.SYSCOLUMNS c
            WHERE
                c.SYSTEM_TABLE_SCHEMA = ?
                AND c.SYSTEM_TABLE_NAME = ?
            ORDER BY
                c.ORDINAL_POSITION
        """

        cursor.execute(sql, (library.upper(), table.upper()))

        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(strip_values(dict(zip(columns, row))))

        return results
    finally:
        conn.close()


@mcp.tool()
def get_columns(
    library: str,
    table: str
) -> list[dict]:
    """
    テーブルのカラム情報を取得します（ラベル付き）。

    Args:
        library: ライブラリ名
        table: テーブル名

    Returns:
        カラム一覧（名前、ラベル、データ型、長さ、桁数、NULL可否、キー情報）
    """
    return _get_columns_internal(library, table)


# =============================================================================
# Tools - ソースコード系
# =============================================================================

@mcp.tool()
def list_sources(
    library: str,
    source_file: str = "QCLSRC",
    pattern: str = "%"
) -> list[dict]:
    """
    ソースファイル内のメンバー一覧を取得します。

    Args:
        library: ライブラリ名
        source_file: ソースファイル名
            - QCLSRC: CLプログラム
            - QRPGSRC: RPG（固定形式）
            - QRPGLESRC: RPG ILE（自由形式）
            - QCBLSRC: COBOL
            - QDDSSRC: DDS（画面/ファイル定義）
        pattern: メンバー名のパターン（%でワイルドカード）

    Returns:
        ソースメンバー一覧（MEMBER_NAME, SOURCE_TYPE, MEMBER_TEXT, LAST_UPDATED, LINE_COUNT）
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # QSYS2.SYSPARTITIONSTAT: ソースファイルのメンバー情報
        # AS400のソースは「ソースファイル」内の「メンバー」として管理される
        # SOURCE_TYPE: CLP, RPGLE, CBLLE, DSPF 等
        # 注意: NUMBER_ROWS, LAST_SOURCE_UPDATEは新しいIBM iバージョンのみ存在するため除外
        sql = """
            SELECT
                SYSTEM_TABLE_MEMBER AS MEMBER_NAME,
                SOURCE_TYPE,
                COALESCE(PARTITION_TEXT, '') AS MEMBER_TEXT
            FROM
                QSYS2.SYSPARTITIONSTAT
            WHERE
                SYSTEM_TABLE_SCHEMA = ?
                AND SYSTEM_TABLE_NAME = ?
                AND SYSTEM_TABLE_MEMBER LIKE ?
            ORDER BY
                SYSTEM_TABLE_MEMBER
        """

        cursor.execute(sql, (library.upper(), source_file.upper(), pattern))
        
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(strip_values(dict(zip(columns, row))))
        
        return results
    finally:
        conn.close()


def _get_source_internal(library: str, source_file: str, member: str) -> dict:
    """ソースコードを取得する内部関数（他のツールから呼び出し可能）。"""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Step 1: メンバーのメタ情報を取得
        meta_sql = """
            SELECT
                SYSTEM_TABLE_MEMBER AS MEMBER_NAME,
                SOURCE_TYPE,
                COALESCE(PARTITION_TEXT, '') AS MEMBER_TEXT
            FROM
                QSYS2.SYSPARTITIONSTAT
            WHERE
                SYSTEM_TABLE_SCHEMA = ?
                AND SYSTEM_TABLE_NAME = ?
                AND SYSTEM_TABLE_MEMBER = ?
        """

        cursor.execute(meta_sql, (library.upper(), source_file.upper(), member.upper()))
        meta_row = cursor.fetchone()

        if not meta_row:
            return {"error": f"Source member not found: {library}/{source_file}/{member}"}

        meta_columns = [desc[0] for desc in cursor.description]
        metadata = strip_values(dict(zip(meta_columns, meta_row)))

        # Step 2: ソースコード本体を取得
        # ソースファイルは特殊な構造: SRCSEQ(行番号), SRCDAT(更新日), SRCDTA(ソース行)
        # メンバー指定にはALIASを使用（古いIBM iでの互換性のため）
        alias_name = f"QTEMP.SRC_{member.upper()}"
        cursor.execute(f"CREATE OR REPLACE ALIAS {alias_name} FOR {library.upper()}.{source_file.upper()} ({member.upper()})")

        source_sql = f"""
            SELECT
                SRCSEQ, SRCDAT, SRCDTA
            FROM
                {alias_name}
            ORDER BY
                SRCSEQ
        """

        cursor.execute(source_sql)

        # 各行を構造化して格納
        lines = []
        for row in cursor.fetchall():
            lines.append({
                "seq": float(row[0]) if row[0] else 0,      # 行番号（小数点付き）
                "date": str(row[1]) if row[1] else "",      # 更新日（YYMMDD形式）
                "text": row[2].strip() if row[2] else ""   # ソース行（トリム）
            })

        return {
            "metadata": metadata,
            "source_lines": lines,
            "source_text": "\n".join(line["text"] for line in lines)  # 全行を結合
        }
    finally:
        conn.close()


@mcp.tool()
def get_source(
    library: str,
    source_file: str,
    member: str
) -> dict:
    """
    ソースコードを取得します。

    Args:
        library: ライブラリ名
        source_file: ソースファイル名（QCLSRC=CL, QRPGSRC=RPG, QRPGLESRC=RPGLE, QCBLSRC=COBOL, QDDSSRC=DDS）
        member: メンバー名

    Returns:
        ソースコード情報（メタデータ + ソース行）
    """
    return _get_source_internal(library, source_file, member)


# =============================================================================
# Tools - データ取得系
# =============================================================================

@mcp.tool()
def get_data(
    library: str,
    table: str,
    columns: str = "",
    where: str = "",
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    テーブルデータを取得します（カラムラベル付き）。

    Args:
        library: ライブラリ名
        table: テーブル名
        columns: 取得するカラム名（カンマ区切り、例: "COL1,COL2,COL3"）省略時は全カラム
        where: WHERE句の条件（WHEREキーワード不要、例: "STATUS = 'OPEN' AND AMOUNT > 1000"）
        limit: 取得件数上限（デフォルト100）
        offset: 開始位置（ページング用、デフォルト0）

    Returns:
        {columns: [{name, label}...], rows: [...], row_count}
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # まずカラム情報を取得（日本語ラベルを結果に含めるため）
        column_info = _get_columns_internal(library, table)
        column_labels = {col["COLUMN_NAME"]: col["COLUMN_TEXT"] for col in column_info}

        # SELECT文を動的に構築
        if columns and columns.strip():
            # カンマ区切りの文字列を分割してカラムリストに変換
            col_list = [col.strip().upper() for col in columns.split(",")]
            select_cols = ", ".join(col_list)
        else:
            select_cols = "*"

        # ROW_NUMBER()を使ったページング（古いIBM iでも動作）
        table_name = f"{library.upper()}.{table.upper()}"

        # *は使えないのでカラム名を明示
        if select_cols == "*":
            actual_cols = [col["COLUMN_NAME"] for col in column_info]
            select_cols = ", ".join(actual_cols)

        sql = f"SELECT {select_cols}, ROW_NUMBER() OVER() AS RN__ FROM {table_name}"
        if where:
            sql += f" WHERE {where}"

        sql = f"SELECT * FROM ({sql}) AS T WHERE RN__ > {offset} FETCH FIRST {limit} ROWS ONLY"

        cursor.execute(sql)

        # 結果のカラム情報を構築（名前とラベルのペア）
        # RN__（行番号用の内部カラム）は除外
        result_columns = []
        for desc in cursor.description:
            col_name = desc[0]
            if col_name == "RN__":
                continue
            result_columns.append({
                "name": col_name,
                "label": column_labels.get(col_name, "")
            })

        # 行データを取得（RN__は除外）
        rows = []
        for row in cursor.fetchall():
            row_dict = {}
            col_idx = 0
            for i, desc in enumerate(cursor.description):
                if desc[0] == "RN__":
                    continue
                value = row[i]
                # AS400の文字列は右パディングされるのでトリム
                if isinstance(value, str):
                    value = value.strip()
                row_dict[result_columns[col_idx]["name"]] = value
                col_idx += 1
            rows.append(row_dict)

        return {
            "columns": result_columns,
            "rows": rows,
            "row_count": len(rows)
        }
    finally:
        conn.close()


def _get_table_info_internal(library: str, table: str) -> dict:
    """テーブル詳細情報を取得する内部関数（他のツールから呼び出し可能）。"""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Step 1: テーブル基本情報を取得
        # 注意: NUMBER_ROWS, DATA_SIZEは新しいIBM iバージョンのみ存在するため除外
        table_sql = """
            SELECT
                SYSTEM_TABLE_NAME AS TABLE_NAME,
                COALESCE(TABLE_TEXT, '') AS TABLE_TEXT,
                TABLE_TYPE
            FROM
                QSYS2.SYSTABLES
            WHERE
                SYSTEM_TABLE_SCHEMA = ?
                AND SYSTEM_TABLE_NAME = ?
        """

        cursor.execute(table_sql, (library.upper(), table.upper()))
        table_row = cursor.fetchone()

        if not table_row:
            return {"error": f"Table not found: {library}/{table}"}

        table_cols = [desc[0] for desc in cursor.description]
        table_info = strip_values(dict(zip(table_cols, table_row)))

        # Step 2: カラム情報を取得
        columns = _get_columns_internal(library, table)

        # Step 3: キー情報を取得
        # QSYS2.SYSKEYCST: 主キー制約のカラム情報
        key_sql = """
            SELECT
                COLUMN_NAME,
                ORDINAL_POSITION
            FROM
                QSYS2.SYSKEYCST
            WHERE
                SYSTEM_TABLE_SCHEMA = ?
                AND SYSTEM_TABLE_NAME = ?
            ORDER BY
                ORDINAL_POSITION
        """

        cursor.execute(key_sql, (library.upper(), table.upper()))
        keys = [row[0] for row in cursor.fetchall()]

        # Step 4: インデックス情報を取得
        # QSYS2.SYSINDEXES: インデックス（論理ファイル）の情報
        index_sql = """
            SELECT
                SYSTEM_INDEX_NAME AS INDEX_NAME,
                COALESCE(INDEX_TEXT, '') AS INDEX_TEXT,
                IS_UNIQUE
            FROM
                QSYS2.SYSINDEXES
            WHERE
                SYSTEM_TABLE_SCHEMA = ?
                AND SYSTEM_TABLE_NAME = ?
        """

        cursor.execute(index_sql, (library.upper(), table.upper()))
        index_cols = [desc[0] for desc in cursor.description]
        indexes = [strip_values(dict(zip(index_cols, row))) for row in cursor.fetchall()]

        return {
            "table": table_info,
            "columns": columns,
            "primary_key": keys,
            "indexes": indexes
        }
    finally:
        conn.close()


@mcp.tool()
def get_table_info(
    library: str,
    table: str
) -> dict:
    """
    テーブルの詳細情報を取得します（DDL生成用）。

    Args:
        library: ライブラリ名
        table: テーブル名

    Returns:
        テーブル詳細情報（基本情報、カラム、インデックス、キー）
    """
    return _get_table_info_internal(library, table)


# =============================================================================
# Tools - システム情報系
# =============================================================================

@mcp.tool()
def get_system_info() -> dict:
    """
    AS400/IBM iのシステム情報を取得します。

    Returns:
        システム情報（OSバージョン、リリース、システム名、CPU、メモリ等）
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        result = {}

        # Step 1: 開発に必要なシステム値を取得
        # QSYS2.SYSTEM_VALUE_INFO から取得（互換性が高い）
        os_sql = """
            SELECT
                SYSTEM_VALUE_NAME,
                COALESCE(CURRENT_CHARACTER_VALUE, CAST(CURRENT_NUMERIC_VALUE AS VARCHAR(50)))
            FROM QSYS2.SYSTEM_VALUE_INFO
            WHERE SYSTEM_VALUE_NAME IN (
                'QSRLNBR',    -- シリアル番号
                'QMODEL',     -- モデル
                'QLANGID',    -- 言語ID（JPN等）
                'QDATFMT',    -- 日付形式（YMD, MDY等）
                'QDATSEP',    -- 日付区切り文字
                'QTIMFMT',    -- 時刻形式（HMS等）
                'QTIMSEP',    -- 時刻区切り文字
                'QDECFMT',    -- 小数点形式
                'QCURSYM',    -- 通貨記号
                'QSYSLIBL',   -- システムライブラリリスト
                'QUSRLIBL'    -- ユーザーライブラリリスト
            )
        """

        try:
            cursor.execute(os_sql)
            os_info = {}
            for row in cursor.fetchall():
                name = row[0].strip() if row[0] else ""
                value = row[1].strip() if row[1] else ""
                if name == 'QSRLNBR':
                    os_info["serial_number"] = value
                elif name == 'QMODEL':
                    os_info["model"] = value
                elif name == 'QLANGID':
                    os_info["language_id"] = value
                elif name == 'QDATFMT':
                    os_info["date_format"] = value
                elif name == 'QDATSEP':
                    os_info["date_separator"] = value
                elif name == 'QTIMFMT':
                    os_info["time_format"] = value
                elif name == 'QTIMSEP':
                    os_info["time_separator"] = value
                elif name == 'QDECFMT':
                    os_info["decimal_format"] = value
                elif name == 'QCURSYM':
                    os_info["currency_symbol"] = value
                elif name == 'QSYSLIBL':
                    # スペース区切りのライブラリリストを配列に変換
                    os_info["system_library_list"] = value.split()
                elif name == 'QUSRLIBL':
                    os_info["user_library_list"] = value.split()
            if os_info:
                result["system_info"] = os_info
        except Exception as e:
            result["system_info_error"] = str(e)

        # Step 2: IBMi バージョン情報を取得
        ver_sql = """
            SELECT
                OS_NAME,
                OS_VERSION,
                OS_RELEASE
            FROM SYSIBMADM.ENV_SYS_INFO
            FETCH FIRST 1 ROW ONLY
        """

        try:
            cursor.execute(ver_sql)
            row = cursor.fetchone()
            if row:
                result["version"] = {
                    "os_name": row[0].strip() if row[0] else "",
                    "os_version": row[1].strip() if row[1] else "",
                    "os_release": row[2].strip() if row[2] else ""
                }
        except Exception:
            # 古いバージョンでは取得できない場合がある
            pass

        # Step 3: SQL機能レベルを取得（RPG/SQLプログラム作成時に重要）
        sql_sql = """
            SELECT
                SQL_STANDARD_VERSION,
                SQL_PATH
            FROM QSYS2.SQL_SIZING
            FETCH FIRST 1 ROW ONLY
        """

        try:
            cursor.execute(sql_sql)
            row = cursor.fetchone()
            if row:
                result["sql_info"] = {
                    "sql_standard": row[0].strip() if row[0] else "",
                    "sql_path": row[1].strip() if row[1] else ""
                }
        except Exception:
            pass

        # Step 4: CCSID情報（文字コード関連）
        ccsid_info = {}

        # システムデフォルトCCSID（SYSTEM_VALUE_INFOは7.1+で使用可能）
        try:
            cursor.execute("""
                SELECT CURRENT_NUMERIC_VALUE
                FROM QSYS2.SYSTEM_VALUE_INFO
                WHERE SYSTEM_VALUE_NAME = 'QCCSID'
            """)
            row = cursor.fetchone()
            if row:
                ccsid_info["default_ccsid"] = row[0]
        except Exception:
            pass

        # ジョブCCSID（JOB_INFOは7.4+のみ）
        try:
            cursor.execute("""
                SELECT JOB_CCSID
                FROM QSYS2.JOB_INFO
                WHERE JOB_NAME = '*'
            """)
            row = cursor.fetchone()
            if row:
                ccsid_info["job_ccsid"] = row[0]
        except Exception:
            pass

        if ccsid_info:
            result["ccsid_info"] = ccsid_info

        # Step 5: 接続ユーザー情報
        user_sql = """
            SELECT
                CURRENT_USER,
                USER,
                CURRENT_SCHEMA
            FROM SYSIBM.SYSDUMMY1
        """

        try:
            cursor.execute(user_sql)
            row = cursor.fetchone()
            if row:
                result["connection_info"] = {
                    "current_user": row[0].strip() if row[0] else "",
                    "user": row[1].strip() if row[1] else "",
                    "current_schema": row[2].strip() if row[2] else ""
                }
        except Exception:
            pass

        # Step 5: 利用可能なコンパイラ/言語環境（インストール済み製品）
        compiler_sql = """
            SELECT
                PRODUCT_ID,
                PRODUCT_OPTION,
                PRODUCT_DESCRIPTION_TEXT
            FROM QSYS2.SOFTWARE_PRODUCT_INFO
            WHERE PRODUCT_ID IN (
                '5770WDS',   -- Rational Development Studio (ILE RPG, COBOL, C/C++)
                '5770SS1'    -- IBM i Operating System
            )
              AND SYMBOLIC_LOAD_STATE = '*INSTALLED'
            ORDER BY PRODUCT_ID, PRODUCT_OPTION
        """

        try:
            cursor.execute(compiler_sql)
            compilers = []
            for row in cursor.fetchall():
                compilers.append({
                    "product_id": row[0].strip() if row[0] else "",
                    "option": row[1].strip() if row[1] else "",
                    "description": row[2].strip() if row[2] else ""
                })
            if compilers:
                result["installed_compilers"] = compilers
        except Exception:
            pass

        return result
    finally:
        conn.close()


# =============================================================================
# Tools - プログラム・オブジェクト情報系
# =============================================================================

@mcp.tool()
def list_programs(
    library: str,
    pattern: str = "%",
    program_type: str = "ALL"
) -> list[dict]:
    """
    ライブラリ内のプログラム一覧を取得します。

    Args:
        library: ライブラリ名
        pattern: プログラム名のパターン（%でワイルドカード）
        program_type: ALL/RPG/RPGLE/CLP/CLLE/CBL/CBLLE 等（OBJATTRIBUTEでフィルタ）

    Returns:
        プログラム一覧（名前、属性、作成日、説明、ソース情報）
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # QSYS2.OBJECT_STATISTICS: オブジェクト情報（IBM i 7.3以降で使用可能）
        # OBJATTRIBUTE: RPG, RPGLE, CLP, CLLE, CBL, CBLLE 等
        sql = f"""
            SELECT
                OBJNAME AS PROGRAM_NAME,
                COALESCE(OBJATTRIBUTE, '') AS ATTRIBUTE,
                COALESCE(OBJTEXT, '') AS PROGRAM_TEXT,
                OBJCREATED AS CREATED,
                CHANGE_TIMESTAMP AS CHANGED,
                OBJSIZE AS PROGRAM_SIZE,
                COALESCE(SOURCE_FILE, '') AS SOURCE_FILE,
                COALESCE(SOURCE_LIBRARY, '') AS SOURCE_LIBRARY,
                COALESCE(SOURCE_MEMBER, '') AS SOURCE_MEMBER
            FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*PGM'))
            WHERE OBJNAME LIKE ?
        """

        params = [library.upper(), pattern]

        # 属性（言語）でフィルタリング
        if program_type != "ALL":
            sql += " AND OBJATTRIBUTE = ?"
            params.append(program_type.upper())

        sql += " ORDER BY OBJNAME"

        cursor.execute(sql, params)

        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                if isinstance(value, str):
                    value = value.strip()
                row_dict[col] = value
            results.append(row_dict)

        return results
    finally:
        conn.close()


def _parse_source_references(source_text: str, source_type: str) -> dict:
    """
    ソースコードを解析してファイル参照とプログラム呼び出しを抽出する。

    Args:
        source_text: ソースコード全文
        source_type: ソースタイプ（CLP, RPG, RPGLE等）

    Returns:
        {"files": [...], "programs": [...]}
    """
    import re
    files = []
    programs = []

    lines = source_text.upper().split('\n')

    if source_type in ('CLP', 'CLLE'):
        # CL: DCLF/DCLPF でファイル宣言、CALL でプログラム呼び出し
        for line in lines:
            # DCLF FILE(LIB/FILE) or DCLF FILE(FILE)
            match = re.search(r'DCL[PF]*\s+FILE\(([^)]+)\)', line)
            if match:
                file_ref = match.group(1).strip()
                if '/' in file_ref:
                    lib, fil = file_ref.split('/')
                    files.append({"file": fil.strip(), "library": lib.strip(), "usage": "DCLF"})
                else:
                    files.append({"file": file_ref, "library": "*LIBL", "usage": "DCLF"})

            # CALL PGM(LIB/PGM) or CALL PGM(PGM)
            match = re.search(r'CALL\s+PGM\(([^)]+)\)', line)
            if match:
                pgm_ref = match.group(1).strip()
                if '/' in pgm_ref:
                    lib, pgm = pgm_ref.split('/')
                    programs.append({"program": pgm.strip(), "library": lib.strip()})
                else:
                    programs.append({"program": pgm_ref, "library": "*LIBL"})

    elif source_type in ('RPG', 'RPGLE', 'SQLRPGLE'):
        for line in lines:
            # 固定形式RPG: F仕様書（6桁目がF）
            # FFILENAME IT  F  132        DISK
            if len(line) > 6 and line[5:6] == 'F':
                file_name = line[6:16].strip()
                if file_name and not file_name.startswith('*'):
                    file_type = line[16:17] if len(line) > 16 else ''
                    usage = 'INPUT' if file_type == 'I' else 'OUTPUT' if file_type == 'O' else 'UPDATE' if file_type == 'U' else 'UNKNOWN'
                    files.append({"file": file_name, "library": "*LIBL", "usage": usage})

            # 固定形式RPG: C仕様書のCALL
            if len(line) > 6 and line[5:6] == 'C':
                match = re.search(r'CALL\s+\'?([A-Z0-9#@$]+)\'?', line)
                if match:
                    programs.append({"program": match.group(1), "library": "*LIBL"})

            # 自由形式RPGLE: DCL-F
            match = re.search(r'DCL-F\s+(\w+)', line)
            if match:
                files.append({"file": match.group(1), "library": "*LIBL", "usage": "DCL-F"})

            # 自由形式RPGLE: 外部プロシージャ呼び出し
            match = re.search(r'EXTPGM\s*\(\s*\'([^\']+)\'\s*\)', line)
            if match:
                programs.append({"program": match.group(1), "library": "*LIBL"})

    return {"files": files, "programs": programs}


@mcp.tool()
def get_program_references(
    library: str,
    program: str
) -> dict:
    """
    プログラムが参照しているファイルや呼び出しているプログラムを取得します。
    IBM i 7.4+ではシステムビューから取得、7.3以下ではソース解析で取得します。

    Args:
        library: ライブラリ名
        program: プログラム名

    Returns:
        参照情報:
        - program: "LIBRARY/PROGRAM"
        - referenced_files: 使用ファイル一覧
        - called_programs: 呼び出しプログラム一覧
        - source: ソース解析を使用した場合の情報
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        result = {
            "program": f"{library.upper()}/{program.upper()}",
            "referenced_files": [],
            "called_programs": []
        }

        # Step 1: 参照ファイル一覧を取得（IBM i 7.4+）
        file_sql = """
            SELECT
                SYSTEM_TABLE_SCHEMA AS FILE_LIBRARY,
                SYSTEM_TABLE_NAME AS FILE_NAME,
                USAGE,
                COALESCE(t.TABLE_TEXT, '') AS FILE_TEXT
            FROM QSYS2.PROGRAM_FILE_REFERENCES r
            LEFT JOIN QSYS2.SYSTABLES t
              ON r.SYSTEM_TABLE_SCHEMA = t.SYSTEM_TABLE_SCHEMA
              AND r.SYSTEM_TABLE_NAME = t.SYSTEM_TABLE_NAME
            WHERE r.PROGRAM_LIBRARY = ?
              AND r.PROGRAM_NAME = ?
            ORDER BY r.SYSTEM_TABLE_NAME
        """

        use_source_analysis = False
        try:
            cursor.execute(file_sql, (library.upper(), program.upper()))
            for row in cursor.fetchall():
                result["referenced_files"].append({
                    "library": row[0].strip() if row[0] else "",
                    "file": row[1].strip() if row[1] else "",
                    "usage": row[2].strip() if row[2] else "",
                    "description": row[3].strip() if row[3] else ""
                })
        except Exception as e:
            if "SQL0204" in str(e):
                use_source_analysis = True

        # Step 2: バインドモジュール取得（IBM i 7.4+）
        if not use_source_analysis:
            call_sql = """
                SELECT BOUND_MODULE_LIBRARY, BOUND_MODULE
                FROM QSYS2.PROGRAM_BOUND_MODULE_INFO
                WHERE PROGRAM_LIBRARY = ? AND PROGRAM_NAME = ?
            """
            try:
                cursor.execute(call_sql, (library.upper(), program.upper()))
                for row in cursor.fetchall():
                    result["called_programs"].append({
                        "library": row[0].strip() if row[0] else "",
                        "program": row[1].strip() if row[1] else ""
                    })
            except Exception:
                pass

        # Step 3: 7.3以下の場合、ソース解析にフォールバック
        if use_source_analysis:
            # プログラムのソース情報を取得
            src_sql = """
                SELECT SOURCE_FILE, SOURCE_LIBRARY, SOURCE_MEMBER, OBJATTRIBUTE
                FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*PGM'))
                WHERE OBJNAME = ?
            """
            cursor.execute(src_sql, (library.upper(), program.upper()))
            src_row = cursor.fetchone()

            if src_row and src_row[0]:
                src_file = src_row[0].strip()
                src_lib = src_row[1].strip()
                src_member = src_row[2].strip()
                src_type = src_row[3].strip() if src_row[3] else ""

                # ソースコードを取得
                source_data = _get_source_internal(src_lib, src_file, src_member)

                if "error" not in source_data:
                    # ソース解析
                    refs = _parse_source_references(source_data["source_text"], src_type)

                    result["referenced_files"] = refs["files"]
                    result["called_programs"] = refs["programs"]
                    result["source"] = {
                        "method": "source_analysis",
                        "source_file": f"{src_lib}/{src_file}({src_member})",
                        "source_type": src_type,
                        "note": "Extracted from source code. May not include runtime-resolved references."
                    }
                else:
                    result["error"] = f"Could not retrieve source: {source_data['error']}"
            else:
                result["error"] = "Program source information not available"

        return result
    finally:
        conn.close()


@mcp.tool()
def list_data_areas(
    library: str,
    pattern: str = "%"
) -> list[dict]:
    """
    ライブラリ内のデータエリア一覧を取得します。

    Args:
        library: ライブラリ名
        pattern: データエリア名のパターン（%でワイルドカード）

    Returns:
        データエリア一覧（名前、タイプ、長さ、値、説明）
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # QSYS2.DATA_AREA_INFO: データエリアの情報
        # データエリア = プログラム間で共有する変数領域
        # 典型的な用途: 処理日付、会社コード、実行フラグ等
        # カラム名はIBM iバージョンによって異なる場合がある
        sql = """
            SELECT
                DATA_AREA_NAME,
                DATA_AREA_TYPE,
                LENGTH,
                COALESCE(DECIMAL_POSITIONS, 0) AS DECIMAL_POSITIONS,
                COALESCE(DATA_AREA_VALUE, '') AS DATA_VALUE,
                COALESCE(TEXT_DESCRIPTION, '') AS DESCRIPTION
            FROM QSYS2.DATA_AREA_INFO
            WHERE DATA_AREA_LIBRARY = ?
              AND DATA_AREA_NAME LIKE ?
            ORDER BY DATA_AREA_NAME
        """

        cursor.execute(sql, (library.upper(), pattern))

        results = []
        for row in cursor.fetchall():
            dtaara = {
                "name": row[0].strip() if row[0] else "",
                "type": row[1].strip() if row[1] else "",  # *CHAR or *DEC
                "length": row[2],
                "decimal_positions": row[3],
                "value": row[4].strip() if isinstance(row[4], str) else row[4],
                "description": row[5].strip() if row[5] else ""
            }

            results.append(dtaara)

        return results
    finally:
        conn.close()


# =============================================================================
# Tools - SQL実行
# =============================================================================

@mcp.tool()
def execute_sql(
    sql: str,
    params: list = [],
    max_rows: int = 1000
) -> dict:
    """
    任意のSELECT文を実行します（読み取り専用）。

    INSERT/UPDATE/DELETEは実行できません（セキュリティのため）。

    Args:
        sql: 実行するSQL文（SELECT文のみ許可）
        params: SQLパラメータ（プレースホルダ ? に対応、デフォルト空配列）
        max_rows: 最大取得行数（デフォルト1000）

    Returns:
        {columns: [カラム名...], rows: [{カラム名: 値}...], row_count: 件数}

    Example:
        execute_sql("SELECT * FROM MYLIB.ORDERS WHERE STATUS = ?", ["OPEN"], 100)
    """
    # セキュリティ: SELECT文以外を拒否（データ変更を防止）
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return {"error": "Only SELECT statements are allowed"}

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # パラメータ付きクエリ（SQLインジェクション対策）
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        columns = [desc[0] for desc in cursor.description]
        rows = []

        # max_rows件まで取得
        for i, row in enumerate(cursor.fetchall()):
            if i >= max_rows:
                break
            row_dict = {}
            for j, col in enumerate(columns):
                value = row[j]
                if isinstance(value, str):
                    value = value.strip()
                row_dict[col] = value
            rows.append(row_dict)

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows)
        }
    finally:
        conn.close()


# =============================================================================
# Resources - 情報参照用（URI経由でのデータアクセス）
# Note: Claude Codeでは現状あまり使用されないが、MCP仕様として実装
# =============================================================================

@mcp.resource("as400://library/{library}/tables")
def resource_tables(library: str) -> str:
    """ライブラリ内のテーブル一覧をリソースとして提供"""
    tables = _list_tables_internal(library)

    lines = [f"# Tables in {library.upper()}", ""]
    for t in tables:
        lines.append(f"- **{t['TABLE_NAME']}**: {t['TABLE_TEXT']} ({t['TABLE_TYPE']})")

    return "\n".join(lines)


@mcp.resource("as400://library/{library}/table/{table}/schema")
def resource_table_schema(library: str, table: str) -> str:
    """テーブルスキーマをリソースとして提供"""
    info = _get_table_info_internal(library, table)

    if "error" in info:
        return info["error"]

    lines = [
        f"# {info['table']['TABLE_NAME']}",
        f"**Description**: {info['table']['TABLE_TEXT']}",
        f"**Type**: {info['table']['TABLE_TYPE']}",
        "",
        "## Columns",
        ""
    ]

    for col in info["columns"]:
        key_mark = "[PK] " if col["COLUMN_NAME"] in info["primary_key"] else ""
        null_mark = "" if col["IS_NULLABLE"] == "Y" else " NOT NULL"
        lines.append(
            f"- {key_mark}**{col['COLUMN_NAME']}** ({col['DATA_TYPE']}({col['LENGTH']})): "
            f"{col['COLUMN_TEXT']}{null_mark}"
        )

    if info["primary_key"]:
        lines.extend(["", f"**Primary Key**: {', '.join(info['primary_key'])}"])

    if info["indexes"]:
        lines.extend(["", "## Indexes", ""])
        for idx in info["indexes"]:
            unique = "UNIQUE " if idx["IS_UNIQUE"] == "Y" else ""
            lines.append(f"- {unique}**{idx['INDEX_NAME']}**: {idx['INDEX_TEXT']}")

    return "\n".join(lines)


@mcp.resource("as400://library/{library}/source/{source_file}/{member}")
def resource_source(library: str, source_file: str, member: str) -> str:
    """ソースコードをリソースとして提供"""
    result = _get_source_internal(library, source_file, member)

    if "error" in result:
        return result["error"]

    meta = result["metadata"]
    lines = [
        f"# {meta['MEMBER_NAME']} ({meta['SOURCE_TYPE']})",
        f"**Description**: {meta['MEMBER_TEXT']}",
        "",
        "```",
        result["source_text"],
        "```"
    ]

    return "\n".join(lines)


# =============================================================================
# Prompts - プロンプトテンプレート
# Note: Claude Codeでは現状あまり使用されないが、MCP仕様として実装
#       ユーザーが明示的に指定した場合に使用される
# =============================================================================

@mcp.prompt()
def create_crud_program(
    library: str,
    table: str,
    program_type: str = "RPG"
) -> str:
    """
    CRUD画面用プログラムの作成プロンプト

    Args:
        library: ライブラリ名
        table: テーブル名
        program_type: RPG/RPGLE/CL
    """
    # テーブル情報を取得
    info = _get_table_info_internal(library, table)
    
    if "error" in info:
        return f"Error: {info['error']}"
    
    columns_desc = []
    for col in info["columns"]:
        key_mark = "[PK] " if col["COLUMN_NAME"] in info["primary_key"] else ""
        columns_desc.append(
            f"  - {key_mark}{col['COLUMN_NAME']}: {col['COLUMN_TEXT']} "
            f"({col['DATA_TYPE']}({col['LENGTH']}))"
        )
    
    return f"""以下のテーブル情報を元に、{program_type}でCRUD画面プログラムを作成してください。

## テーブル情報
- ライブラリ: {library.upper()}
- テーブル名: {info['table']['TABLE_NAME']}
- テーブル説明: {info['table']['TABLE_TEXT']}

## カラム情報
{chr(10).join(columns_desc)}

## 主キー
{', '.join(info['primary_key']) if info['primary_key'] else 'なし'}

## 要件
1. 一覧画面（SUBFILE使用）
   - 全カラムのラベルを日本語で表示
   - ページング機能
   - 検索機能

2. 詳細/編集画面
   - 新規登録、更新、削除機能
   - 入力バリデーション（データ型に応じた）
   - 主キーは更新不可

3. 必要なオブジェクト
   - {program_type}プログラム
   - DSPFファイル（画面定義）
   - 必要に応じてPFILEの定義

プログラムを作成してください。
"""


@mcp.prompt()
def analyze_source(
    library: str,
    source_file: str,
    member: str
) -> str:
    """
    ソースコード分析プロンプト
    
    Args:
        library: ライブラリ名
        source_file: ソースファイル名
        member: メンバー名
    """
    result = _get_source_internal(library, source_file, member)

    if "error" in result:
        return f"Error: {result['error']}"

    meta = result["metadata"]

    return f"""以下のソースコードを分析してください。

## ソース情報
- ライブラリ: {library.upper()}
- ソースファイル: {source_file.upper()}
- メンバー: {meta['MEMBER_NAME']}
- タイプ: {meta['SOURCE_TYPE']}
- 説明: {meta['MEMBER_TEXT']}

## ソースコード
```
{result['source_text']}
```

## 分析項目
1. プログラムの目的と機能概要
2. 使用しているファイル（入出力）
3. 主要な処理ロジック
4. 呼び出しているプログラム/サブルーチン
5. 改善提案（あれば）

分析結果を日本語で説明してください。
"""


@mcp.prompt()
def generate_cl_for_batch(
    library: str,
    description: str
) -> str:
    """
    バッチ処理用CLプログラム作成プロンプト
    
    Args:
        library: ライブラリ名
        description: 処理内容の説明
    """
    # ライブラリ内のテーブル一覧を取得
    tables = _list_tables_internal(library)
    
    table_list = []
    for t in tables:
        table_list.append(f"  - {t['TABLE_NAME']}: {t['TABLE_TEXT']}")
    
    return f"""以下の要件でバッチ処理用のCLプログラムを作成してください。

## 処理概要
{description}

## 対象ライブラリ
{library.upper()}

## 利用可能なテーブル
{chr(10).join(table_list[:20])}  
{'...(他' + str(len(tables) - 20) + 'テーブル)' if len(tables) > 20 else ''}

## CLプログラム要件
1. エラーハンドリング（MONMSG）
2. ジョブログへの処理開始/終了メッセージ出力
3. 必要に応じてファイルのOVRDBF/DLTOVR
4. 適切なコメント

CLプログラムを作成してください。
"""


# =============================================================================
# エントリーポイント
# =============================================================================

def main():
    """
    MCPサーバーを起動する。

    .envファイルまたは環境変数 AS400_CONNECTION_STRING からODBC接続文字列を読み込み、
    FastMCPサーバーを開始する。

    環境変数が未設定の場合はプレースホルダが使用されるが、
    実際の接続時にエラーとなる。
    """
    import os
    from dotenv import load_dotenv

    # .envファイルがあれば読み込む（環境変数が優先される）
    load_dotenv()

    global CONNECTION_STRING
    CONNECTION_STRING = os.environ.get(
        "AS400_CONNECTION_STRING",
        # デフォルト値（実際には環境変数での設定が必須）
        # CCSID=1208: UTF-8で通信（日本語対応）
        # EXTCOLINFO=1: 拡張カラム情報（COLUMN_TEXT等）を取得
        "DRIVER={IBM i Access ODBC Driver};SYSTEM=YOUR_SYSTEM;UID=USER;PWD=PASS;CCSID=1208;EXTCOLINFO=1"
    )

    # FastMCPサーバーを起動（stdin/stdout経由でMCPプロトコル通信）
    mcp.run()


if __name__ == "__main__":
    main()
