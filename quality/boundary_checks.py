"""v2.0.3 销售材料确定性边界与质量门。

设计为独立模块（不依赖 supply_scope 的会被热缓存的命名），保证在长驻校验/服务进程里也能被
全新 import 到。全部为确定性字符串/正则判定，不依赖大模型；违规返回 {"rule", "context"} 列表。

覆盖完整 final_report 的英文开发邮件、15 分钟会议提纲、会后邮件与下一步待办：
1) 卖方身份边界：仅确认“供应商/销售方”时，只能自称 supplier/seller/exporter，不得自称
   manufacturer/factory/producer（或中文 制造商/生产商/工厂）。
2) 月供能力边界：20,000 吨/月为三种颗粒 NPK 的合计 supply capacity，不得写成 production
   capacity / manufacturing / factory / plant capacity（或 自有/工厂/生产 产能）。
3) 质检承诺边界：仅“可讨论样品与质检”时，不得声称已持有/可直接提供 SGS 或第三方检验报告；
   只能询问客户标准，或写条件式“如双方同意，可安排第三方检验 / third-party inspection can
   be arranged subject to mutual agreement”。
4) 化学常识边界：氯化铵 (NH4Cl) 提供氮和氯，不提供钾；不得写成 potassium source/substitute/
   replacement 或钾肥；若写成分数值，N 必须为 25.5–26.8%，Cl 必须为 65.5–67.2%。
5) 开发邮件正文（不含 Subject）必须为 120–180 个英文词，并返回真实 EMAIL_WORD_COUNT。
6) samples_status=discussable 时，样品只能使用协商式口径，不得承诺可提供、发送、准备或安排样品。
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# ---- 1) 卖方身份边界 ----
_ROLE_BAD_EN_RE: List[re.Pattern] = [
    re.compile(r"\bwe\s+are\s+(?:a\s+)?(?:manufacturer|producer)\b", re.IGNORECASE),
    re.compile(r"\b(?:as|being)\s+(?:a\s+)?(?:manufacturer|producer)\b", re.IGNORECASE),
    re.compile(r"\bour\s+(?:own\s+)?(?:factory|plant)\b", re.IGNORECASE),
    re.compile(r"\bwe\s+(?:manufacture|produce)\b", re.IGNORECASE),
    re.compile(r"\bwe\s+(?:run|operate)\s+(?:our\s+own\s+)?(?:factory|plant)\b", re.IGNORECASE),
]
_ROLE_BAD_CN_RE: List[re.Pattern] = [
    re.compile(r"我们是制造商|我方是制造商|我们是生产商|我方是生产商"),
    re.compile(r"我们的工厂|我方工厂|我们自有工厂|我方自有工厂"),
    re.compile(r"我们制造|我方制造|我们(?:自|投)?建厂|我方建厂"),
    re.compile(r"我们是工厂|我方为工厂"),
]

# ---- 2) 月供能力边界 ----
_CP_BAD_EN_RE: List[re.Pattern] = [
    re.compile(r"\b(?:production|manufacturing|factory|plant)\s+capacity\b", re.IGNORECASE),
    re.compile(r"\bour\s+(?:production|manufacturing)\s+capacity\b", re.IGNORECASE),
    re.compile(r"\bown\s+(?:production|manufacturing)\b", re.IGNORECASE),
]
_CP_BAD_CN_RE: List[re.Pattern] = [
    re.compile(r"自有产能|工厂产能|生产产能|我方产能|我们产能|月产能|年产能|投产产能|制造产能"),
]

# ---- 3) 质检承诺边界 ----
_QC_NOUN_EN_RE: re.Pattern = re.compile(
    r"\b(?:SGS\s*(?:certificate|certificates|report|reports)?|"
    r"certificate|certificates|inspection\s+report|inspection\s+reports|"
    r"third[- ]party(?:\s+inspection)?(?:\s+(?:report|reports|certificate))?)\b",
    re.IGNORECASE,
)
_QC_CLAIM_EN_RE: re.Pattern = re.compile(
    r"\b(?:we\s+can\s+|we\s+|can\s+)?(?:provide|offer|supply|share|send|have|hold|issue|possess)\b",
    re.IGNORECASE,
)
_QC_COND_EN_RE: List[re.Pattern] = [
    re.compile(r"subject\s+to\s+mutual\s+agreement", re.IGNORECASE),
    re.compile(r"by\s+mutual\s+agreement", re.IGNORECASE),
    re.compile(r"if\s+agreed\s+by\s+both\s+parties", re.IGNORECASE),
    re.compile(r"upon\s+mutual\s+agreement", re.IGNORECASE),
    re.compile(r"at\s+(?:the\s+)?client'?s\s+request", re.IGNORECASE),
]
_QC_NOUN_CN_RE: re.Pattern = re.compile(r"SGS|SGS证书|检验报告|质检报告|检测报告|第三方检验报告|第三方检测报告")
_QC_CLAIM_CN_RE: re.Pattern = re.compile(r"可提供|可以提供|我们提供|我方提供|提供|可出具|出具|持有|已持有|备有|可发送|发送|分享")
_QC_COND_CN_RE: List[re.Pattern] = [
    re.compile(r"如双方同意|如客户同意|双方同意|若双方同意|在双方同意下|经双方确认|按客户标准|依客户要求|客户确认后|如贵方确认"),
]
_ALLOWED_ARRANGE: List[re.Pattern] = [
    re.compile(r"可安排|可以安排|可协调|安排第三方|arrange\s+(?:third[- ]party\s+)?inspection|"
               r"third[- ]party\s+inspection\s+can\s+be\s+arranged", re.IGNORECASE),
]

# ---- 4) 化学常识边界 ----
_CHEM_ID_RE: re.Pattern = re.compile(r"氯化铵|ammonium\s*chloride|NH4Cl", re.IGNORECASE)
_K_BAD_SEM_RE: re.Pattern = re.compile(
    r"钾肥|钾源|钾的?来源|钾的?替代|替代钾|补充钾|补钾|提供钾|供应钾|含钾|作(?:为)?钾|当钾|钾含量|钾成分|"
    r"potassium\s+(?:source|substitute|replacement|alternative|fertilizer)|"
    r"source\s+of\s+potassium|as\s+(?:a\s+)?potassium|potash\s+(?:source|substitute|replacement)|"
    r"(?:provide|supply|offer|contain|deliver)\s+(?:potassium|potash)",
    re.IGNORECASE,
)
_K_NEG_RE: re.Pattern = re.compile(
    r"不是钾|并非钾|不含钾|不提供钾|非钾|非钾肥|不(?:是|为|属)钾源|不替代钾|"
    r"no\s+potassium|not\s+(?:a\s+)?potassium|does\s+not\s+(?:provide|contain|supply)\s+potassium|"
    r"without\s+potassium|potassium[- ]free",
    re.IGNORECASE,
)

# ---- 5) 英文开发邮件长度 ----
_SUBJECT_RE: re.Pattern = re.compile(r"^\s*subject\s*:\s*.*$", re.IGNORECASE)
_EN_WORD_RE: re.Pattern = re.compile(r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b")

# ---- 6) 样品状态边界 ----
_SAMPLE_BAD_EN_RE: List[re.Pattern] = [
    re.compile(r"\bsamples?\s+(?:are|is)\s+(?:readily\s+)?available\b", re.IGNORECASE),
    re.compile(
        r"\b(?:send|ship|dispatch|prepare|arrange|provide|offer|supply)\s+"
        r"(?:you\s+|the\s+|product\s+|free\s+|trial\s+){0,3}samples?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:pleased|happy|ready)\s+to\s+(?:send|ship|prepare|arrange|provide|offer|supply)\s+"
        r"(?:you\s+|the\s+){0,2}samples?\b",
        re.IGNORECASE,
    ),
]
_SAMPLE_BAD_CN_RE: List[re.Pattern] = [
    re.compile(r"(?:发送|寄送|邮寄|准备|安排|提供|可提供|备有).{0,6}样品"),
    re.compile(r"样品.{0,5}(?:现成|可提供|可寄送|可发送|已备好|可安排)"),
]

# NH4Cl 百分比数值只在与化学名同一近邻窗口内校验，避免误把硫酸铵约 21% N 算到氯化铵上。
_N_PERCENT_RE: List[re.Pattern] = [
    re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*%\s*(?:N|nitrogen|氮)\b", re.IGNORECASE),
    re.compile(r"(?:N|nitrogen|氮)(?:\s+content|含量)?\s*(?:of|约|~|≈|:|：)?\s*(?P<value>\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
]
_CL_PERCENT_RE: List[re.Pattern] = [
    re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*%\s*(?:Cl|chloride|氯)\b", re.IGNORECASE),
    re.compile(r"(?:Cl|chloride|氯)(?:\s+content|含量)?\s*(?:of|约|~|≈|:|：)?\s*(?P<value>\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
]


def _snippet(body: str, s: int, e: int, pad: int = 42) -> str:
    return body[max(0, s - pad): min(len(body), e + pad)].strip().replace("\n", " ")


def check_role_boundaries(text: str) -> List[Dict[str, str]]:
    violations: List[Dict[str, str]] = []
    if not text or not str(text).strip():
        return violations
    body: str = str(text)
    for r in _ROLE_BAD_EN_RE:
        for m in r.finditer(body):
            violations.append({"rule": "卖方身份边界", "context": _snippet(body, m.start(), m.end())})
    for r in _ROLE_BAD_CN_RE:
        for m in r.finditer(body):
            violations.append({"rule": "卖方身份边界", "context": _snippet(body, m.start(), m.end())})
    return violations


def check_capacity_boundaries(text: str) -> List[Dict[str, str]]:
    violations: List[Dict[str, str]] = []
    if not text or not str(text).strip():
        return violations
    body: str = str(text)
    for r in _CP_BAD_EN_RE:
        for m in r.finditer(body):
            violations.append({"rule": "月供能力边界", "context": _snippet(body, m.start(), m.end())})
    for r in _CP_BAD_CN_RE:
        for m in r.finditer(body):
            violations.append({"rule": "月供能力边界", "context": _snippet(body, m.start(), m.end())})
    return violations


def _has_cond(body: str, start: int, end: int, conds: List[re.Pattern]) -> bool:
    window: str = body[max(0, start): min(len(body), end)]
    return any(c.search(window) for c in conds)


def check_quality_boundaries(text: str) -> List[Dict[str, str]]:
    violations: List[Dict[str, str]] = []
    if not text or not str(text).strip():
        return violations
    body: str = str(text)

    def _arranged(s: int, e: int) -> bool:
        window: str = body[max(0, s - 30): min(len(body), e + 40)]
        return any(ar.search(window) for ar in _ALLOWED_ARRANGE)

    for noun_m in _QC_NOUN_EN_RE.finditer(body):
        ns, ne = noun_m.start(), noun_m.end()
        if _arranged(ns, ne):
            continue
        window_start: int = max(0, ns - 60)
        claim_found: bool = any(
            cl.end() <= ns for cl in _QC_CLAIM_EN_RE.finditer(body, window_start, ns)
        )
        if claim_found and not _has_cond(body, window_start, ne + 10, _QC_COND_EN_RE):
            violations.append({"rule": "质检承诺边界", "context": _snippet(body, window_start, ne)})
    for noun_m in _QC_NOUN_CN_RE.finditer(body):
        ns, ne = noun_m.start(), noun_m.end()
        if re.search(r'(?:不|不得|避免)(?:虚构|声称|承诺|宣称|保证)\s*$',body[max(0,ns-10):ns]):
            continue
        if _arranged(ns, ne):
            continue
        window_start: int = max(0, ns - 40)
        claim_found: bool = any(c.search(body, window_start, ns) for c in [_QC_CLAIM_CN_RE])
        if claim_found and not _has_cond(body, window_start, ne + 6, _QC_COND_CN_RE):
            violations.append({"rule": "质检承诺边界", "context": _snippet(body, window_start, ne)})
    return violations


def check_chemistry_boundaries(text: str) -> List[Dict[str, str]]:
    violations: List[Dict[str, str]] = []
    if not text or not str(text).strip():
        return violations
    body: str = str(text)
    chem_spans: List[Tuple[int, int]] = [(m.start(), m.end()) for m in _CHEM_ID_RE.finditer(body)]
    if not chem_spans:
        return violations
    for k_m in _K_BAD_SEM_RE.finditer(body):
        ks, ke = k_m.start(), k_m.end()
        near: bool = any(
            (ks >= cs and ks - ce <= 60) or (ks < cs and cs - ke <= 60)
            for cs, ce in chem_spans
        )
        if not near:
            continue
        window: str = body[max(0, ks - 30): min(len(body), ke + 30)]
        if _K_NEG_RE.search(window):
            continue
        violations.append({"rule": "化学常识边界", "context": _snippet(body, ks, ke)})
    return violations


def extract_email_body(outreach_email: str) -> str:
    """只返回开发邮件正文；Subject 行不参与词数。"""
    lines: List[str] = str(outreach_email or "").strip().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and _SUBJECT_RE.match(lines[0]):
        lines = lines[1:]
    return "\n".join(lines).strip()


def count_email_words(outreach_email: str) -> int:
    """按英文/数字 token 统计正文词数，连字符词记作一个词。"""
    return len(_EN_WORD_RE.findall(extract_email_body(outreach_email)))


def check_email_word_count(
    outreach_email: str,
    minimum: int = 120,
    maximum: int = 180,
) -> List[Dict[str, str]]:
    count: int = count_email_words(outreach_email)
    if minimum <= count <= maximum:
        return []
    return [
        {
            "rule": "英文开发邮件正文词数",
            "context": f"EMAIL_WORD_COUNT={count}，要求 {minimum}–{maximum}（仅统计正文，不含 Subject）",
        }
    ]


def check_sample_boundaries(text: str, samples_status: str = "discussable") -> List[Dict[str, str]]:
    """samples_status=discussable 时禁止把“可讨论”升级为样品承诺。"""
    if str(samples_status or "").strip().lower() != "discussable":
        return []
    body: str = str(text or "")
    violations: List[Dict[str, str]] = []
    for pattern in _SAMPLE_BAD_EN_RE + _SAMPLE_BAD_CN_RE:
        for m in pattern.finditer(body):
            violations.append({"rule": "样品状态边界", "context": _snippet(body, m.start(), m.end())})
    return violations


def _numeric_violations(
    body: str,
    patterns: List[re.Pattern],
    low: float,
    high: float,
    nutrient: str,
) -> List[Dict[str, str]]:
    violations: List[Dict[str, str]] = []
    for pattern in patterns:
        for match in pattern.finditer(body):
            value: float = float(match.group("value"))
            if not low <= value <= high:
                violations.append(
                    {
                        "rule": "NH4Cl 成分数值边界",
                        "context": (
                            f"{nutrient}={value:g}% 超出允许范围 {low:g}–{high:g}%："
                            + _snippet(body, match.start(), match.end())
                        ),
                    }
                )
    return violations


def check_nh4cl_composition(text: str) -> List[Dict[str, str]]:
    """校验 NH4Cl 近邻窗口中的 N/Cl 数值，不跨产品段落串值。"""
    body: str = str(text or "")
    violations: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for chem in _CHEM_ID_RE.finditer(body):
        window_start: int = max(0, chem.start() - 160)
        window_end: int = min(len(body), chem.end() + 220)
        window: str = body[window_start:window_end]
        for item in _numeric_violations(window, _N_PERCENT_RE, 25.5, 26.8, "N"):
            key = (item["rule"], item["context"])
            if key not in seen:
                seen.add(key)
                violations.append(item)
        for item in _numeric_violations(window, _CL_PERCENT_RE, 65.5, 67.2, "Cl"):
            key = (item["rule"], item["context"])
            if key not in seen:
                seen.add(key)
                violations.append(item)
    return violations
