"""卖方产品边界（供应范围）的确定性解析与后验校验。

职责：
1. 从“我方产品/优势”文本中尽量提取卖方**明确供应**的产品白名单（如 颗粒NPK 15-15-15/10-10-10/20-20-20、颗粒硫酸铵、颗粒氯化铵等），用于在报告里直观展示“我方供应范围”。
2. 定义卖方**未供应**的常见肥料产品标记（磷矿/磷肥/磷酸盐、钾盐/氯化钾/硫酸钾、尿素、硝铵等），用于后验扫描生成的联系建议/英文邮件/会议提纲/跟进邮件/待办，发现把这些超范围产品**当作卖点主动推销**时上报违规，供自动自检与人工核验。
3. 提供 `supply_scope_note()` 生成“我方供应范围与目标产品边界”说明文本。

防误报设计（重要）：
- 中文推销词**不使用裸单字“供”**（否则“Yara 的供应链采购钾盐”等客户事实会误报），改用有语义的供应/销售/报价短语；并对“供应”加 `(?!链)` 负向断言排除“供应链”。
- 判为“主动推销”采用**动宾相邻**规则：超范围产品必须紧跟在推销动词之后（作为其直接宾语）才会被判定，客户自身业务的“采购/生产/销售”事实表述不会误报。
- 英文缩写（MOP/SOP/DAP/MAP）与英文产品词均使用 `\\b` 单词边界匹配，避免命中 roadmap/company 等普通单词；并按最长优先去重防止重叠重复报错。

所有判定均为确定性字符串/正则规则，不依赖大模型。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# 卖方明确供应的产品类别特征项（每项含正则与展示名）
_SUPPLY_PATTERNS: List[Dict[str, Any]] = [
    {"cat": "NPK", "display": "颗粒 NPK", "patterns": [r"颗粒\s*NPK", r"NPK\s*\d{1,2}-\d{1,2}-\d{1,2}", r"氮磷钾复合肥"]},
    {"cat": "硫酸铵", "display": "颗粒硫酸铵", "patterns": [r"颗粒\s*硫酸铵", r"硫酸铵", r"ammonium\s*sulfate"]},
    {"cat": "氯化铵", "display": "颗粒氯化铵", "patterns": [r"颗粒\s*氯化铵", r"氯化铵", r"ammonium\s*chloride"]},
]

# 卖方未供应的常见肥料/原料产品标记（中文）。
_OUT_OF_SCOPE_CN: List[str] = [
    # 磷系
    "磷矿石", "磷矿", "磷肥", "磷酸盐", "磷酸二铵", "磷酸一铵", "过磷酸钙", "重钙", "磷酸铵", "磷酸",
    # 钾系
    "氯化钾", "硫酸钾", "钾肥", "钾盐",
    # 氮系（非我方供应的氮肥）
    "尿素", "硝铵", "硝酸铵",
]

# 卖方未供应的常见肥料/原料产品标记（英文，含缩写，必须用单词边界）。
_OUT_OF_SCOPE_EN: List[str] = [
    "phosphate rock", "superphosphate", "phosphoric acid", "potash", "muriate of potash",
    "potassium chloride", "urea", "ammonium nitrate", "mop", "sop", "dap", "map",
]

# 超范围产品被「声明为超出供应范围」的保护性短语。当超范围产品紧邻这类“out-of-scope 声明”
# 出现时，说明正文是在按要求把该产品标为“超出当前供应范围”（而非当作卖点推销），不应判违规。
_OUT_OF_SCOPE_DECL_CN: List[str] = [
    "超出当前供应范围", "超出我方供应范围", "超出供应范围", "不在我方供应范围", "不在供应范围",
    "不予供应", "无法供应", "不提供", "未供应", "供应范围之外",
]
_OUT_OF_SCOPE_DECL_EN: List[str] = [
    r"beyond\s+our\s+(?:current\s+)?supply\s+scope", r"beyond\s+our\s+scope",
    r"is\s+beyond\s+our\s+(?:current\s+)?supply\s+scope", r"out\s+of\s+scope",
    r"outside\s+(?:our\s+)?(?:supply\s+)?scope",
    r"not\s+(?:within|in)\s+our\s+supply\s+scope",
    r"(?:do\s+not|cannot|don'?t)\s+(?:supply|offer|provide|sell)",
    r"are\s+beyond\s+our\s+(?:current\s+)?scope",
]
_OUT_OF_SCOPE_DECL_RE: List[re.Pattern] = (
    [re.compile(re.escape(p)) for p in _OUT_OF_SCOPE_DECL_CN]
    + [re.compile(p, re.IGNORECASE) for p in _OUT_OF_SCOPE_DECL_EN]
)

# 主动推销“动宾相邻”阈值（字符）：超范围产品与推销动词结束位置的距离上限。
_ADJACENT_DIST: int = 26

# “out-of-scope 声明”与超范围产品的最大允许字符间距：小于等于该值视为“声明上下文”。
_DECL_PROXIMITY: int = 46

# 主动推销动词（中文，有语义短语；不使用裸单字“供”）。
_PROMO_CN: List[str] = [
    "我方可提供", "我们可以提供", "能够提供", "可以供应", "可以供货", "我们供应", "我方供应",
    "可提供", "可供", "可供应", "可发", "出货", "报价", "供货能力", "供应能力", "月供货", "月供",
    "供给", "提供", "供应(?!链)",
]

# 主动推销动词（英文，单词边界）。
_PROMO_EN: List[str] = [
    r"\bwe\s+can\s+(?:supply|offer|provide|sell|ship|export|deliver|quote)\b",
    r"\bwe\s+(?:supply|offer|provide|sell|ship|export|deliver)\b",
    r"\bcan\s+(?:supply|offer|provide|sell)\b",
    r"\bsupply\b", r"\bsupplies\b", r"\bsupplier\b",
    r"\boffers?\b", r"\boffering\b", r"\bprovided?\b", r"\bprovides?\b", r"\bproviding\b",
    r"\bsells?\b", r"\bselling\b", r"\bavailable\b", r"\bin stock\b", r"\bquotation\b",
    r"\bquote\b", r"\bships?\b", r"\bshipping\b", r"\bshipment\b", r"\bexports?\b",
    r"\bexporting\b", r"\bdelivery\b", r"\bdeliver(?:ies|ed)?\b", r"\bFOB\b", r"\bCFR\b", r"\bCIF\b",
]

_PROMO_CN_RE: List[re.Pattern] = [re.compile(p) for p in _PROMO_CN]
_PROMO_EN_RE: List[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in _PROMO_EN]


def _build_scope_regexes() -> List[Tuple[str, re.Pattern]]:
    """构建 (标记, 编译正则)，中文用子串、英文用单词边界；按标记长度降序以优先最长匹配。"""
    items: List[Tuple[str, re.Pattern]] = []
    for m in _OUT_OF_SCOPE_CN:
        items.append((m, re.compile(re.escape(m))))
    for m in _OUT_OF_SCOPE_EN:
        items.append((m, re.compile(r"\b" + re.escape(m) + r"\b", re.IGNORECASE)))
    # 按标记原始长度降序（长标记优先，避免 “muriate of potash” 与 “potash” 重叠重复报）
    items.sort(key=lambda t: -len(t[0]))
    return items


_SCOPE_REGEXES: List[Tuple[str, re.Pattern]] = _build_scope_regexes()


def parse_supply_scope(product_text: str) -> List[str]:
    """从“我方产品/优势”文本中确定性提取卖方明确供应的产品白名单（去重、保序）。

    未匹配任何已知类别的，返回空列表（此时报告仅作通用说明，由提示词保证边界）。
    """
    if not product_text or not str(product_text).strip():
        return []
    text: str = str(product_text)
    found: List[str] = []
    seen: set = set()
    for item in _SUPPLY_PATTERNS:
        matched: bool = False
        for pat in item["patterns"]:
            if re.search(pat, text, re.IGNORECASE):
                matched = True
                break
        if matched and item["display"] not in seen:
            seen.add(item["display"])
            found.append(item["display"])
    # 若命中 NPK，进一步展开明确规格（如 15-15-15/10-10-10/20-20-20）
    if any(d == "颗粒 NPK" for d in found):
        specs: List[str] = []
        for m in re.finditer(r"NPK\s*(\d{1,2}-\d{1,2}-\d{1,2})", text, re.IGNORECASE):
            spec: str = m.group(1)
            if spec not in specs:
                specs.append(spec)
        idx: int = found.index("颗粒 NPK")
        if specs:
            found[idx] = "颗粒 NPK " + "、".join(specs)
    return found


def _promo_verb_ends(body: str) -> List[int]:
    """返回文本中所有“主动推销动词”的结束位置（升序）。"""
    ends: List[int] = []
    for r in _PROMO_CN_RE:
        for m in r.finditer(body):
            ends.append(m.end())
    lower: str = body.lower()
    for r in _PROMO_EN_RE:
        for m in r.finditer(lower):
            ends.append(m.end())
    ends.sort()
    return ends


def _has_seller_promo_before(verb_ends: List[int], marker_start: int) -> bool:
    """判断是否存在一个推销动词 end <= marker_start 且与 marker 相邻（产品作为动词宾语）。"""
    # 二分查找最后一个 end <= marker_start 的动词
    lo, hi = 0, len(verb_ends) - 1
    best: int = -1
    while lo <= hi:
        mid: int = (lo + hi) // 2
        if verb_ends[mid] <= marker_start:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if best < 0:
        return False
    return (marker_start - verb_ends[best]) <= _ADJACENT_DIST


def check_scope_violations(text: str) -> List[Dict[str, str]]:
    """扫描文本，返回把“卖方未供应产品”当卖点主动推销的违规范例。

    返回项：{"product": <命中的超范围产品>， "context": <命中前后窗口文本>}。
    判定规则：超范围产品作为某个推销动词的“直接宾语”（动宾相邻）才算违规；
    客户自身业务的采购/生产/供应事实表述不会被误报；英文缩写与英文产品用单词边界匹配；
    重叠命中的长标记优先，避免重复报错。
    """
    if not text or not str(text).strip():
        return []
    body: str = str(text)
    verb_ends: List[int] = _promo_verb_ends(body)
    # 预处理 “out-of-scope 声明”出现区间（用于抑制“把超范围产品声明为超出供应范围”的误报）
    decl_spans: List[Tuple[int, int]] = []
    for r in _OUT_OF_SCOPE_DECL_RE:
        for d in r.finditer(body):
            decl_spans.append((d.start(), d.end()))
    decl_spans.sort(key=lambda x: x[0])

    def _protected(s: int) -> bool:
        """判断超范围产品位置 s 是否紧邻某条“超出供应范围”声明（声明在其前或与其重叠）。

        仅当“乐在其前/重叠”时才视为声明上下文，避免“We can supply potash but it is beyond
        our supply scope”这类仍属主动推销的句子被误判为合规。
        """
        for ds, de in decl_spans:
            if ds <= s <= de + 12:
                return True
            if ds < s and (s - de) <= _DECL_PROXIMITY:
                return True
        return False

    violations: List[Dict[str, str]] = []
    reported_spans: List[Tuple[int, int]] = []

    def _overlap(s: int, e: int) -> bool:
        nonlocal reported_spans
        return any(not (e <= rs or s >= re_) for rs, re_ in reported_spans)

    for marker, r in _SCOPE_REGEXES:
        for m in r.finditer(body):
            s, e = m.start(), m.end()
            if _overlap(s, e):
                continue  # 该位置已被更长标记覆盖，跳过避免重复
            if _protected(s):
                continue  # 该处是在声明“超出供应范围”，非主动推销，跳过
            sample: str = body[max(0, s - 42): min(len(body), e + 42)]
            if _has_seller_promo_before(verb_ends, s):
                reported_spans.append((s, e))
                violations.append(
                    {
                        "product": marker,
                        "context": sample.strip().replace("\n", " "),
                    }
                )
    return violations


def supply_scope_note(product_text: str) -> str:
    """生成报告用“我方供应范围与目标产品边界”说明文本。"""
    whitelist: List[str] = parse_supply_scope(product_text)
    if not str(product_text or "").strip():
        return (
            "**我方供应范围：** 未填写“我方产品/优势”，请补充后再明确可供应产品边界。"
        )
    if whitelist:
        scope_disp: str = "、".join(whitelist)
    else:
        scope_disp = "（未能在产品文本中确定性识别到标准规格，请以人工核验为准）"
    out: str = (
        f"**我方供应范围（仅以下明确产品可用于联系/开发材料，其余一律视为“超出当前供应范围”）：** {scope_disp}\n\n"
        f"**目标产品边界：** 若客户存在对**磷矿石/磷肥/磷酸盐、钾盐/氯化钾/硫酸钾、尿素、硝铵**等我方未供应品类的需求，"
        f"只能标注为“**超出当前供应范围**”，**不得**作为销售切入品或写入英文联系材料/下一步建议。"
    )
    return out
