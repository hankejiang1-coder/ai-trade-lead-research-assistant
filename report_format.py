"""Move attribution to a traceable appendix without changing numeric facts."""
import re

URL_RE=re.compile(r'https?://[^\s<>"\'）\]，；|]+')
SOURCE_ID_RE=re.compile(r'(?<![A-Za-z0-9_])S\d+(?![A-Za-z0-9_])')
SOURCE_GROUP_RE=re.compile(r'(?<![A-Za-z0-9_])S\d+(?:\s*[,，、/]\s*S\d+)*(?![A-Za-z0-9_])')

def unread_source_issues(report,evidence):
    """Report references to unread evidence without pretending to verify all claims."""
    actual={row['id']:row for row in evidence}
    section='报告'; issues=[]; seen=set(); in_chart=False
    for line in report.splitlines():
        heading=re.match(r'^##\s+(.+)',line)
        if heading:
            section=heading[1]
            if re.match(r'(?:13|14)[.、．]',section):break
        if line.startswith('```chart'):in_chart=True;continue
        if in_chart:
            if line.startswith('```'):in_chart=False
            continue
        # Explicit missing-source statements are useful and are not asserted facts.
        if re.search(r'未读|未取得|未获取|排除|历史文件|缺失|缺口',line):continue
        for sid in SOURCE_ID_RE.findall(line):
            if (section,sid) in seen:continue
            seen.add((section,sid))
            if not actual.get(sid,{}).get('content'):
                issues.append({'rule':'未读来源引用','context':section+'引用'+sid+'，未取得正文；相关事实必须改为待核验。'})
    return issues

def final_report_only(report):
    """Discard a provider's preamble; retain only the numbered final report."""
    first=re.search(r'^##\s*1[.、．]\s+[^\n]+',report,re.M)
    if not first: return report
    metadata=re.search(r'^本次服务记录：[^\n]+',report,re.M)
    return ((metadata[0]+'\n\n') if metadata else '')+report[first.start():]

def normalize_source_links(report):
    """Add a scheme to complete source paths, never reconstruct missing paths."""
    lines=[]; in_sources=False
    for line in report.splitlines():
        if re.match(r'^##\s',line):
            in_sources=bool(re.search(r'来源|证据清单',line))
        if in_sources and line.lstrip().startswith('|'):
            cells=line.split('|')
            for i,cell in enumerate(cells):
                value=cell.strip()
                if ('...' not in value and '…' not in value and
                    re.fullmatch(r'(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}/[^\s|<>]*',value)):
                    cells[i]=' https://'+value+' '
            line='|'.join(cells)
        lines.append(line)
    return '\n'.join(lines)

def source_records(report):
    records={}; in_sources=False
    for line in normalize_source_links(report).splitlines():
        if re.match(r'^##\s',line): in_sources=bool(re.search(r'来源|证据清单',line))
        if not in_sources: continue
        cells=[x.strip() for x in line.strip().strip('|').split('|')]
        if len(cells)>=7 and re.fullmatch(r'S\d+',cells[0]):
            records[cells[0]]={'url':cells[2], 'method':cells[4], 'facts':cells[5], 'limits':cells[6]}
    return records

def source_issues(report):
    issues=[]
    for key,record in source_records(report).items():
        if not re.fullmatch(r'https?://[^\s]+',record['url']) or re.search(r'\.\.\.|…',record['url']):
            issues.append({'rule':'来源链接完整性','context':key+'未提供完整可访问路径，仅保留为检索线索'})
    if not URL_RE.search(normalize_source_links(report)):
        issues.append({'rule':'来源可追溯性','context':'未取得完整来源URL，不能作为有据报告交付'})
    return issues

def organize_report(report):
    report=normalize_source_links(final_report_only(report))
    report=re.sub(r'^### 正文与链接对应索引\n[\s\S]*?(?=^##\s|\Z)','',report,flags=re.M)
    sources=[]; seen=set(); section='报告'; appendix=[]; body=[]; in_source=False; id_sections=[]
    for line in report.splitlines():
        heading=re.match(r'^##\s+(.+)',line)
        if heading:
            section=heading[1]
            in_source=bool(re.match(r'(?:13|14)[.、．]?\s*.*来源',section))
            if in_source: continue
        for match in URL_RE.finditer(line):
            url=match[0].rstrip(').,;')
            key=(section,url)
            if key not in seen: sources.append((section,url)); seen.add(key)
        if in_source and '正文与链接对应索引' not in line: appendix.append(line)
        else:
            if not line.startswith(('```','{')):
                for sid in SOURCE_ID_RE.findall(line):
                    if (section,sid) not in id_sections:id_sections.append((section,sid))
            body.append(line)
    text='\n'.join(body)
    charts=[]
    def keep_chart(m):
        charts.append(m[0]);return '\x00CHART'+str(len(charts)-1)+'\x00'
    text=re.sub(r'```chart\s*\n[\s\S]*?```',keep_chart,text)
    text=re.sub(r'[（(](?:来源|出处|source)[:：][^\n）)]*[）)]','',text,flags=re.I)
    text=re.sub(r'^\s*(?:\*\*)?(?:来源|出处|Sources?)[:：][^\n]*','',text,flags=re.I|re.M)
    text=re.sub(r'\[([^\]]+)\]\(https?://[^\s)]+\)',r'\1',text)
    text=URL_RE.sub('',text)
    text=re.sub(r'\[S\d+\]','',text)
    text=SOURCE_GROUP_RE.sub('',text)
    text=re.sub(r'[（(]\s*[,，、\s]*[）)]','',text)
    # Move attribution columns as well as inline links out of the reading body.
    cleaned=[]; attribution=[]; in_table=False
    for line in text.splitlines():
        if not line.startswith('|'): attribution=[]; in_table=False
        else:
            cells=line.strip().strip('|').split('|')
            if not in_table:
                attribution=[i for i,cell in enumerate(cells) if re.search(r'来源|出处|source',cell,re.I)]
                in_table=True
            if attribution: line='|'+'|'.join(cell for i,cell in enumerate(cells) if i not in attribution)+'|'
        cleaned.append(line)
    text='\n'.join(cleaned)
    text=re.sub(r'^\s*[-*]?\s*(?:官网|网站|Official website)[:：]\s*$','',text,flags=re.I|re.M)
    text=re.sub(r'^\s*\|\s*(?:官网|网站|来源链接|Source URL)\s*\|[^\n]*$','',text,flags=re.I|re.M)
    text=re.sub(r'\n{3,}','\n\n',text).strip()
    for i,chart in enumerate(charts): text=text.replace('\x00CHART'+str(i)+'\x00',chart)
    text=text.replace('## 14. 自检与交付状态','## 13. 交付检查')
    appendix_text='\n'.join(appendix).strip()
    ledger=['## 14. 来源与访问核验','',appendix_text,'','### 正文与链接对应索引','| 对应章节 | 链接 | 状态 |','|---|---|---|']
    for title,url in sources: ledger.append('| '+title.replace('|','/')+' | '+url.replace('|','%7C')+' | 提取自本次报告；不等于已读原文 |')
    if not sources: ledger.append('| 全文 | 未取得可提取链接 | 事实依据需补充 |')
    if id_sections:
        ledger+=['','### 正文与证据编号对应','| 对应章节 | 证据编号 | 状态 |','|---|---|---|']
        ledger+=['| '+title.replace('|','/')+' | '+sid+' | 来自原稿引用；请结合上方取得方式核验 |' for title,sid in id_sections]
    return text+'\n\n'+'\n'.join(ledger)
