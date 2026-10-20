# -*- coding: utf-8 -*-
"""SQL 护栏：只读白名单 + 单语句 + 危险关键字拦截 + 自动行数上限。"""
import re

FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "attach", "detach",
    "pragma", "vacuum", "reindex", "replace", "grant", "revoke", "load_extension",
    "writefile", "readfile", "fsdir", "edit", "shell", "system",
}
MAX_ROWS = 500
MAX_LEN = 6000


def strip_comments(sql):
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def _mask_strings(sql):
    return re.sub(r"'(?:''|[^'])*'", "''", sql)


def validate_sql(sql):
    """返回 (ok, normalized_sql, reason)。"""
    if not sql or not sql.strip():
        return False, "", "SQL 为空"
    if len(sql) > MAX_LEN:
        return False, "", "SQL 过长（>%d 字符）" % MAX_LEN
    cleaned = strip_comments(sql).strip().rstrip(";").strip()
    if not cleaned:
        return False, "", "SQL 为空"
    if ";" in _mask_strings(cleaned):
        return False, "", "检测到多条语句；只允许一条只读查询"
    body = _mask_strings(cleaned).lower()
    first_word = re.match(r"^\s*([a-z_]+)", body)
    if not first_word or first_word.group(1) not in ("select", "with"):
        return False, "", "只允许 SELECT / WITH 只读查询，拒绝 %s 语句" % (
            first_word.group(1).upper() if first_word else "空")
    for kw in FORBIDDEN:
        if re.search(r"\b%s\b" % re.escape(kw), body):
            return False, "", "SQL 包含禁止关键字 %s（只读护栏）" % kw.upper()
    if not re.search(r"\blimit\b", body):
        cleaned = cleaned + " LIMIT %d" % MAX_ROWS
    return True, cleaned, ""


INJECTION_PATTERNS = [
    r"忽略(之前|以上|前面)(的)?(所有)?(指令|规则|提示)",
    r"ignore\s+(all\s+)?(previous|above)\s+instructions",
    r"(直接|必须|请)(输出|回答|写)(：|:)?.*(增长|下降|销售额)",
    r"你现在是|扮演|越狱|jailbreak",
    r"(输出|泄露|打印)(你的)?(系统)?(提示词|prompt|system prompt)",
]


def sanitize_text(s):
    """对工具返回的文本做注入净化：保留正常内容，切除可疑指令段。"""
    if not isinstance(s, str) or not s:
        return s, 0
    from . import guard as _self  # 占位，避免循环导入
    hits = 0
    for pat in INJECTION_PATTERNS:
        m = re.search(pat, s, flags=re.I)
        if m:
            hits += 1
            s = s[:m.start()] + "[疑似注入内容已过滤]"
            break
    return s, hits


def sanitize_value(obj):
    """递归净化工具返回结构中的字符串。"""
    total = 0
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, list):
        out = []
        for v in obj:
            v2, n = sanitize_value(v)
            total += n
            out.append(v2)
        return out, total
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            v2, n = sanitize_value(v)
            total += n
            out[k] = v2
        return out, total
    return obj, total


class SqlTimeout(Exception):
    pass


def scalar(sql):
    return sql