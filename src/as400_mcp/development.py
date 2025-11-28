"""
AS400/IBM i 開発支援ツール
ソースコードのアップロードとコンパイルを行うツール群

注意: これらのツールはAS400上のオブジェクトを作成・変更します。
      システムライブラリ（Q*）への操作は禁止されています。
"""

import ftplib
import os
import platform
import subprocess
import uuid
from datetime import datetime
from io import BytesIO


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


def _get_source_file_ccsid(cursor, library: str, source_file: str) -> int | None:
    """
    ソースファイルのCCSIDを取得する。
    SRCDTAカラムのCCSIDを使用する。

    Args:
        cursor: DBカーソル
        library: ライブラリ名
        source_file: ソースファイル名

    Returns:
        CCSID（取得できない場合はNone）
    """
    try:
        # SYSCOLUMNSからSRCDTAカラムのCCSIDを取得
        cursor.execute(
            """
            SELECT CCSID
            FROM QSYS2.SYSCOLUMNS
            WHERE TABLE_SCHEMA = ?
            AND TABLE_NAME = ?
            AND COLUMN_NAME = 'SRCDTA'
            """,
            (library.upper(), source_file.upper()),
        )
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] else None
    except Exception:
        return None


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


def _get_iconv_command() -> list[str] | None:
    """
    利用可能なiconvコマンドを取得する。

    Returns:
        iconvコマンドのリスト（WSLまたはネイティブ）、利用不可の場合はNone
    """
    if platform.system() == "Windows":
        # WindowsではWSL経由でiconvを使用
        try:
            result = subprocess.run(
                ["wsl", "which", "iconv"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return ["wsl", "iconv"]
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None
    else:
        # Linux/Macではネイティブのiconvを使用
        try:
            result = subprocess.run(
                ["which", "iconv"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return ["iconv"]
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None


def _convert_utf8_to_ebcdic(text: str, iconv_cmd: list[str]) -> bytes | None:
    """
    UTF-8テキストをIBM-939（日本語EBCDIC）に変換する。

    Args:
        text: UTF-8テキスト
        iconv_cmd: iconvコマンド（例: ["wsl", "iconv"] または ["iconv"]）

    Returns:
        EBCDIC バイト列、変換失敗時はNone
    """
    try:
        result = subprocess.run(
            iconv_cmd + ["-f", "UTF-8", "-t", "IBM-939"],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def _convert_ebcdic_to_utf8(data: bytes, iconv_cmd: list[str]) -> str | None:
    """
    IBM-939（日本語EBCDIC）をUTF-8テキストに変換する。

    Args:
        data: EBCDIC バイト列
        iconv_cmd: iconvコマンド

    Returns:
        UTF-8テキスト、変換失敗時はNone
    """
    try:
        result = subprocess.run(
            iconv_cmd + ["-f", "IBM-939", "-t", "UTF-8"],
            input=data,
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8")
        return None
    except (subprocess.SubprocessError, FileNotFoundError, UnicodeDecodeError):
        return None


def _upload_via_ftp_and_cpyfrmstmf(
    cursor,
    host: str,
    user: str,
    password: str,
    ebcdic_data: bytes,
    library: str,
    source_file: str,
    member: str,
    ccsid: int,
) -> dict:
    """
    FTPでEBCDICデータをアップロードし、CPYFRMSTMFでソースファイルにコピーする。

    Args:
        cursor: DBカーソル
        host: AS400ホスト名/IPアドレス
        user: FTPユーザー名
        password: FTPパスワード
        ebcdic_data: EBCDIC変換済みバイト列
        library: ライブラリ名
        source_file: ソースファイル名
        member: メンバー名
        ccsid: ソースファイルのCCSID

    Returns:
        {"success": True/False, "message": "..."}
    """
    random_id = uuid.uuid4().hex[:8].upper()
    stmf = f"/tmp/MCP_{random_id}.ebcdic"

    try:
        # FTPでバイナリ送信
        ftp = ftplib.FTP(host)
        ftp.login(user, password)
        ftp.storbinary(f"STOR {stmf}", BytesIO(ebcdic_data))
        ftp.quit()

        # CCSIDを設定（IBM-939 → CCSID 5123相当）
        target_ccsid = 5123 if ccsid in (5035, 5123) else ccsid
        cursor.execute("CALL QSYS2.QCMDEXC(?)", (f"QSH CMD('setccsid {target_ccsid} {stmf}')",))

        # CPYFRMSTMFでソースファイルにコピー
        cpyfrom = (
            f"CPYFRMSTMF FROMSTMF('{stmf}') "
            f"TOMBR('/QSYS.LIB/{library}.LIB/{source_file}.FILE/{member}.MBR') "
            f"MBROPT(*REPLACE) STMFCCSID(*STMF)"
        )
        cursor.execute("CALL QSYS2.QCMDEXC(?)", (cpyfrom,))

        return {"success": True, "message": "Uploaded via FTP and CPYFRMSTMF"}

    except ftplib.error_perm as e:
        return {"success": False, "message": f"FTP permission error: {e}"}
    except ftplib.all_errors as e:
        return {"success": False, "message": f"FTP error: {e}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        # クリーンアップ
        try:
            cursor.execute("CALL QSYS2.QCMDEXC(?)", (f"QSH CMD('rm -f {stmf}')",))
        except Exception:
            pass


def _get_ftp_credentials() -> dict | None:
    """
    FTP接続情報を取得する。

    環境変数を優先し、なければODBC接続文字列から抽出する。

    環境変数:
        AS400_FTP_HOST: FTPホスト名/IPアドレス
        AS400_FTP_USER: FTPユーザー名
        AS400_FTP_PASSWORD: FTPパスワード

    フォールバック:
        AS400_CONNECTION_STRING から SYSTEM/UID/PWD を抽出

    Returns:
        {"host": "...", "user": "...", "password": "..."} または None
    """
    # 環境変数を優先
    host = os.environ.get("AS400_FTP_HOST")
    user = os.environ.get("AS400_FTP_USER")
    password = os.environ.get("AS400_FTP_PASSWORD")

    if host and user and password:
        return {"host": host, "user": user, "password": password}

    # ODBC接続文字列からフォールバック
    conn_str = os.environ.get("AS400_CONNECTION_STRING", "")
    if not conn_str:
        return None

    parts = {}
    for item in conn_str.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key.strip().upper()] = value.strip()

    host = host or parts.get("SYSTEM") or parts.get("SERVER") or parts.get("DSN")
    user = user or parts.get("UID") or parts.get("USER")
    password = password or parts.get("PWD") or parts.get("PASSWORD")

    if host and user and password:
        return {"host": host, "user": user, "password": password}
    return None


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

    def _contains_non_ascii(text: str) -> bool:
        """文字列にASCII以外の文字（日本語等）が含まれているかチェックする。"""
        return any(ord(c) > 127 for c in text)

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

        日本語等の非ASCII文字を含むソースは以下の方法で処理されます:
        - CCSID 1208（UTF-8）: 直接SQL INSERTで登録
        - CCSID 5035/5123（日本語EBCDIC）: iconv経由でEBCDIC変換後、
          FTP+CPYFRMSTMFで登録（WSL/Linux環境でiconvが必要）

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

            # ファイルのCCSIDを取得
            file_ccsid = _get_source_file_ccsid(cursor, lib_upper, srcf_upper)

            # 日本語等の非ASCII文字が含まれているかチェック
            has_non_ascii = _contains_non_ascii(source_code)

            # 日本語EBCDIC（CCSID 5035/5123）に非ASCII文字をアップロードする場合
            use_iconv = False
            if has_non_ascii and file_ccsid in (5035, 5123):
                iconv_cmd = _get_iconv_command()
                if iconv_cmd:
                    use_iconv = True
                else:
                    return {
                        "success": False,
                        "error": (
                            f"Source file {lib_upper}/{srcf_upper} has CCSID {file_ccsid} "
                            "(Japanese EBCDIC). Non-ASCII upload requires iconv. "
                            "On Windows, install WSL. On Linux/Mac, ensure iconv is available. "
                            "Alternatively, use a CCSID 1208 (UTF-8) source file."
                        ),
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

            # iconv経由でEBCDICアップロード
            if use_iconv:
                conn.autocommit = True

                # UTF-8 → IBM-939（日本語EBCDIC）変換
                ebcdic_data = _convert_utf8_to_ebcdic(source_code, iconv_cmd)
                if ebcdic_data is None:
                    return {
                        "success": False,
                        "error": "Failed to convert source to EBCDIC with iconv",
                    }

                # FTP接続情報を取得
                ftp_creds = _get_ftp_credentials()
                if not ftp_creds:
                    return {
                        "success": False,
                        "error": (
                            "FTP credentials not found. "
                            "Set AS400_FTP_HOST, AS400_FTP_USER, AS400_FTP_PASSWORD "
                            "or ensure AS400_CONNECTION_STRING contains SYSTEM, UID, PWD."
                        ),
                    }

                # FTP + CPYFRMSTMFでアップロード
                upload_result = _upload_via_ftp_and_cpyfrmstmf(
                    cursor,
                    ftp_creds["host"],
                    ftp_creds["user"],
                    ftp_creds["password"],
                    ebcdic_data,
                    lib_upper,
                    srcf_upper,
                    mbr_upper,
                    file_ccsid,
                )
                if not upload_result["success"]:
                    return {
                        "success": False,
                        "error": f"Upload failed: {upload_result['message']}",
                    }

                line_count = len(source_code.split("\n"))
                return {
                    "success": True,
                    "message": f"Source uploaded: {lib_upper}/{srcf_upper}({mbr_upper})",
                    "line_count": line_count,
                    "source_type": source_type.upper(),
                    "file_ccsid": file_ccsid,
                    "method": "iconv+ftp",
                }

            # 既存メンバーの場合、ソースをクリア（SQL INSERT方式）
            if _member_exists(cursor, lib_upper, srcf_upper, mbr_upper):
                alias_name = f"QTEMP.UPL_{mbr_upper}"
                cursor.execute(
                    f"CREATE OR REPLACE ALIAS {alias_name} "
                    f"FOR {lib_upper}.{srcf_upper} ({mbr_upper})"
                )
                cursor.execute(f"DELETE FROM {alias_name}")
                conn.commit()

            # ソースコードを1行ずつINSERT
            # ジャーナリングなしのファイルに対応するため自動コミットを使用
            conn.autocommit = True

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

                # パラメータマーカーを使用してINSERT
                # ODBCドライバが文字コード変換を処理
                cursor.execute(
                    f"INSERT INTO {alias_name} (SRCSEQ, SRCDAT, SRCDTA) VALUES (?, ?, ?)",
                    (seq, today, src_line),
                )
                line_count += 1

            result = {
                "success": True,
                "message": f"Source uploaded: {lib_upper}/{srcf_upper}({mbr_upper})",
                "line_count": line_count,
                "source_type": source_type.upper(),
                "method": "sql_insert",
            }
            if file_ccsid:
                result["file_ccsid"] = file_ccsid
            return result

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

    @mcp.tool()
    def create_utf8_source_file(
        library: str,
        source_file: str,
        record_length: int = 112,
        description: str = "UTF-8 source file for Unicode support",
    ) -> dict:
        """
        CCSID 1208（UTF-8）のソースファイルを作成します。
        日本語等の非ASCII文字を含むソースコードをアップロードする際に使用します。

        Args:
            library: ライブラリ名（Q*は禁止）
            source_file: ソースファイル名（例: QCLUTF8, QRPGUTF8）
            record_length: レコード長（デフォルト112）
            description: ソースファイルの説明

        Returns:
            結果（success, message）
        """
        error = _check_library_allowed(library)
        if error:
            return {"success": False, "error": error}

        conn = get_connection()
        try:
            cursor = conn.cursor()

            lib_upper = library.upper()
            srcf_upper = source_file.upper()

            # 既に存在するかチェック
            if _source_file_exists(cursor, lib_upper, srcf_upper):
                # CCSIDを確認
                ccsid = _get_source_file_ccsid(cursor, lib_upper, srcf_upper)
                if ccsid == 1208:
                    return {
                        "success": True,
                        "message": (
                            f"Source file already exists: {lib_upper}/{srcf_upper} (CCSID 1208)"
                        ),
                        "already_exists": True,
                    }
                else:
                    return {
                        "success": False,
                        "error": (
                            f"Source file {lib_upper}/{srcf_upper} exists "
                            f"with CCSID {ccsid}. "
                            "Use a different name for UTF-8 source file."
                        ),
                    }

            # CRTSRCPF で CCSID 1208 のソースファイルを作成
            desc_escaped = description.replace("'", "''")
            cmd = (
                f"CRTSRCPF FILE({lib_upper}/{srcf_upper}) "
                f"RCDLEN({record_length}) "
                f"CCSID(1208) "
                f"TEXT('{desc_escaped}')"
            )

            result = _execute_cl_command(cursor, cmd)
            conn.commit()

            if result["success"]:
                return {
                    "success": True,
                    "message": f"Created UTF-8 source file: {lib_upper}/{srcf_upper}",
                    "ccsid": 1208,
                    "record_length": record_length,
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to create source file: {result['message']}",
                }

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()
