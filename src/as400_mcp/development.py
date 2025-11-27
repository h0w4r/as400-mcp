"""
AS400/IBM i 開発支援ツール
ソースコードのアップロードとコンパイルを行うツール群

注意: これらのツールはAS400上のオブジェクトを作成・変更します。
      システムライブラリ（Q*）への操作は禁止されています。
"""

from datetime import datetime


def _check_library_allowed(library: str) -> str | None:
    """
    ライブラリ名が許可されているかチェックする。

    Args:
        library: ライブラリ名

    Returns:
        エラーメッセージ（問題なければNone）
    """
    lib_upper = library.upper()

    # システムライブラリ（Q*）は禁止
    if lib_upper.startswith("Q"):
        return f"System libraries (Q*) are protected: {lib_upper}"

    return None


def _source_file_exists(cursor, library: str, source_file: str) -> bool:
    """ソースファイルが存在するかチェックする。"""
    cursor.execute(
        """
        SELECT
            1
        FROM
            QSYS2.SYSTABLES
        WHERE
            SYSTEM_TABLE_SCHEMA = ?
            AND SYSTEM_TABLE_NAME = ?
            AND FILE_TYPE = 'S'
        """,
        (library.upper(), source_file.upper()),
    )
    return cursor.fetchone() is not None


def _member_exists(cursor, library: str, source_file: str, member: str) -> bool:
    """メンバーが存在するかチェックする。"""
    cursor.execute(
        """
        SELECT
            1
        FROM
            QSYS2.SYSPARTITIONSTAT
        WHERE
            SYSTEM_TABLE_SCHEMA = ?
            AND SYSTEM_TABLE_NAME = ?
            AND SYSTEM_TABLE_MEMBER = ?
        """,
        (library.upper(), source_file.upper(), member.upper()),
    )
    return cursor.fetchone() is not None


def _execute_cl_command(cursor, command: str) -> dict:
    """
    CLコマンドを実行する。

    Args:
        cursor: DBカーソル
        command: 実行するCLコマンド

    Returns:
        {"success": True/False, "message": "..."}
    """
    try:
        # QSYS2.QCMDEXC でCLコマンド実行
        cursor.execute("CALL QSYS2.QCMDEXC(?)", (command,))
        return {"success": True, "message": f"Command executed: {command}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _detect_compile_command(source_type: str) -> str | None:
    """
    ソースタイプからコンパイルコマンドを判定する。

    Args:
        source_type: ソースタイプ（CLP, RPGLE, CBLLE等）

    Returns:
        コンパイルコマンド名（不明な場合はNone）
    """
    compile_map = {
        # CL系
        "CLP": "CRTCLPGM",
        "CLLE": "CRTBNDCL",
        # RPG系
        "RPG": "CRTRPGPGM",
        "RPGLE": "CRTBNDRPG",
        "SQLRPG": "CRTSQLRPG",
        "SQLRPGLE": "CRTSQLRPGI",
        # COBOL系
        "CBL": "CRTCBLPGM",
        "CBLLE": "CRTBNDCBL",
        "SQLCBL": "CRTSQLCBL",
        "SQLCBLLE": "CRTSQLCBLI",
        # DDS系
        "PF": "CRTPF",
        "LF": "CRTLF",
        "DSPF": "CRTDSPF",
        "PRTF": "CRTPRTF",
        # CMD
        "CMD": "CRTCMD",
    }
    return compile_map.get(source_type.upper())


def register_development_tools(mcp, get_connection):
    """
    開発系ツールをMCPサーバーに登録する。

    Args:
        mcp: FastMCPインスタンス
        get_connection: DB接続を取得する関数
    """

    @mcp.tool()
    def upload_source(
        library: str,
        source_file: str,
        member: str,
        source_code: str,
        source_type: str = "RPGLE",
        description: str = "",
    ) -> dict:
        """
        ソースコードをAS400に登録します。
        メンバーが存在しない場合は作成、存在する場合は上書きします。

        Args:
            library: ライブラリ名（Q*は禁止）
            source_file: ソースファイル名（QRPGSRC, QCLSRC等、事前に存在が必要）
            member: メンバー名（新規作成または上書き）
            source_code: ソースコード（複数行の文字列）
            source_type: ソースタイプ（RPGLE, CLP, CBLLE, DSPF, PF等）
            description: メンバーの説明テキスト

        Returns:
            結果（success, message, line_count）
        """
        # ライブラリチェック
        error = _check_library_allowed(library)
        if error:
            return {"success": False, "error": error}

        conn = get_connection()
        try:
            cursor = conn.cursor()

            lib_upper = library.upper()
            srcf_upper = source_file.upper()
            mbr_upper = member.upper()

            # ソースファイル存在チェック
            if not _source_file_exists(cursor, lib_upper, srcf_upper):
                return {
                    "success": False,
                    "error": f"Source file not found: {lib_upper}/{srcf_upper}. "
                    "Create it first with CRTSRCPF command.",
                }

            # メンバー存在チェック → なければ作成
            if not _member_exists(cursor, lib_upper, srcf_upper, mbr_upper):
                # ADDPFM でメンバー作成
                desc_escaped = description.replace("'", "''") if description else ""
                add_cmd = (
                    f"ADDPFM FILE({lib_upper}/{srcf_upper}) "
                    f"MBR({mbr_upper}) "
                    f"SRCTYPE({source_type.upper()}) "
                    f"TEXT('{desc_escaped}')"
                )
                result = _execute_cl_command(cursor, add_cmd)
                if not result["success"]:
                    return {
                        "success": False,
                        "error": f"Failed to create member: {result['message']}",
                    }
                conn.commit()
            else:
                # 既存メンバーの場合、ソースをクリア
                alias_name = f"QTEMP.UPL_{mbr_upper}"
                cursor.execute(
                    f"CREATE OR REPLACE ALIAS {alias_name} "
                    f"FOR {lib_upper}.{srcf_upper} ({mbr_upper})"
                )
                cursor.execute(f"DELETE FROM {alias_name}")
                conn.commit()

            # ソースコードを1行ずつINSERT
            alias_name = f"QTEMP.UPL_{mbr_upper}"
            cursor.execute(
                f"CREATE OR REPLACE ALIAS {alias_name} FOR {lib_upper}.{srcf_upper} ({mbr_upper})"
            )

            lines = source_code.split("\n")
            today = datetime.now().strftime("%y%m%d")  # YYMMDD形式
            line_count = 0

            for i, line in enumerate(lines, start=1):
                # 空行もそのまま登録（ソースの構造を維持）
                seq = float(i)  # 行番号
                # 行が長すぎる場合は切り詰め（ソースファイルのレコード長による）
                src_line = line[:100] if len(line) > 100 else line

                cursor.execute(
                    f"INSERT INTO {alias_name} (SRCSEQ, SRCDAT, SRCDTA) VALUES (?, ?, ?)",
                    (seq, today, src_line),
                )
                line_count += 1

            conn.commit()

            return {
                "success": True,
                "message": f"Source uploaded: {lib_upper}/{srcf_upper}({mbr_upper})",
                "line_count": line_count,
                "source_type": source_type.upper(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    @mcp.tool()
    def compile_source(
        library: str,
        source_file: str,
        member: str,
        compile_type: str = "AUTO",
        target_library: str = "",
        options: str = "",
    ) -> dict:
        """
        ソースをコンパイルしてプログラム/オブジェクトを作成します。

        Args:
            library: ソースライブラリ名（Q*は禁止）
            source_file: ソースファイル名（QRPGSRC, QCLSRC等）
            member: メンバー名
            compile_type: コンパイルコマンド（AUTO=ソースタイプから自動判定）
                - AUTO: ソースタイプから自動判定
                - CRTCLPGM, CRTBNDCL: CL
                - CRTRPGPGM, CRTBNDRPG, CRTSQLRPGI: RPG
                - CRTCBLPGM, CRTBNDCBL: COBOL
                - CRTDSPF, CRTPRTF: 画面/帳票
                - CRTPF, CRTLF: 物理/論理ファイル
            target_library: 出力先ライブラリ（省略時はソースと同じライブラリ）
            options: 追加のコンパイルオプション（例: "DBGVIEW(*SOURCE)"）

        Returns:
            結果（success, message, command）
        """
        # ライブラリチェック
        error = _check_library_allowed(library)
        if error:
            return {"success": False, "error": error}

        if target_library:
            error = _check_library_allowed(target_library)
            if error:
                return {"success": False, "error": error}

        conn = get_connection()
        try:
            cursor = conn.cursor()

            lib_upper = library.upper()
            srcf_upper = source_file.upper()
            mbr_upper = member.upper()
            tgt_lib = target_library.upper() if target_library else lib_upper

            # ソースファイル存在チェック
            if not _source_file_exists(cursor, lib_upper, srcf_upper):
                return {
                    "success": False,
                    "error": f"Source file not found: {lib_upper}/{srcf_upper}",
                }

            # メンバー存在チェック
            if not _member_exists(cursor, lib_upper, srcf_upper, mbr_upper):
                return {
                    "success": False,
                    "error": f"Member not found: {lib_upper}/{srcf_upper}({mbr_upper})",
                }

            # ソースタイプを取得
            cursor.execute(
                """
                SELECT
                    SOURCE_TYPE
                FROM
                    QSYS2.SYSPARTITIONSTAT
                WHERE
                    SYSTEM_TABLE_SCHEMA = ?
                    AND SYSTEM_TABLE_NAME = ?
                    AND SYSTEM_TABLE_MEMBER = ?
                """,
                (lib_upper, srcf_upper, mbr_upper),
            )
            row = cursor.fetchone()
            source_type = row[0].strip() if row and row[0] else ""

            # コンパイルコマンドを決定
            if compile_type.upper() == "AUTO":
                cmd_name = _detect_compile_command(source_type)
                if not cmd_name:
                    return {
                        "success": False,
                        "error": f"Cannot detect compile command for source type: {source_type}. "
                        "Please specify compile_type explicitly.",
                    }
            else:
                cmd_name = compile_type.upper()

            # コンパイルコマンドを組み立て
            # コマンドによってパラメータ形式が異なる
            if cmd_name in ("CRTPF", "CRTLF", "CRTDSPF", "CRTPRTF"):
                # DDSコンパイル
                compile_cmd = (
                    f"{cmd_name} FILE({tgt_lib}/{mbr_upper}) "
                    f"SRCFILE({lib_upper}/{srcf_upper}) "
                    f"SRCMBR({mbr_upper})"
                )
            elif cmd_name == "CRTCMD":
                # コマンド定義
                compile_cmd = (
                    f"{cmd_name} CMD({tgt_lib}/{mbr_upper}) "
                    f"PGM(*LIBL/{mbr_upper}) "
                    f"SRCFILE({lib_upper}/{srcf_upper}) "
                    f"SRCMBR({mbr_upper})"
                )
            else:
                # プログラムコンパイル（RPG, CL, COBOL等）
                compile_cmd = (
                    f"{cmd_name} PGM({tgt_lib}/{mbr_upper}) "
                    f"SRCFILE({lib_upper}/{srcf_upper}) "
                    f"SRCMBR({mbr_upper})"
                )

            # 追加オプション
            if options:
                compile_cmd += f" {options}"

            # コンパイル実行
            result = _execute_cl_command(cursor, compile_cmd)
            conn.commit()

            if result["success"]:
                return {
                    "success": True,
                    "message": f"Compiled successfully: {tgt_lib}/{mbr_upper}",
                    "command": compile_cmd,
                    "source_type": source_type,
                }
            else:
                return {
                    "success": False,
                    "error": f"Compile failed: {result['message']}",
                    "command": compile_cmd,
                }

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()
