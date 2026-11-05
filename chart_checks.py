"""Reject unusable or untraceable chart payloads; no synthetic datapoints."""
import json,math,re
from report_format import source_records

BLOCK=re.compile(r'```chart\s*\n([\s\S]*?)```')
TIME_LABEL=re.compile(r'^(?:(?:FY\s*)?(?:19|20)\d{2}(?:年度?|全年|[./-]\d{1,2}(?:[./-]\d{1,2})?|\s*(?:Q[1-4]|H[12]))?|(?:Q[1-4]|H[12])\s*(?:19|20)\d{2})$',re.I)

def check_chart_blocks(report,evidence=None):
    outside=BLOCK.sub('',report)
    sources=source_records(outside)
    actual={row['id']:row for row in (evidence or [])}
    url_ids={row['url']:row['id'] for row in (evidence or [])}
    groups=re.findall(r'(?:^\|[^\n]+\n?)+',outside,re.M)
    issues=[]
    def replace(match):
        try:
            spec=json.loads(match[1]); values=spec.get('values',[]); labels=spec.get('labels',[])
            valid=(spec.get('type') in ('bar','line') and isinstance(spec.get('title'),str) and isinstance(spec.get('unit'),str) and spec['unit'].strip() and isinstance(values,list) and isinstance(labels,list) and 2<=len(labels)<=40 and len(labels)==len(values) and all(isinstance(x,str) for x in labels) and all(x is None or (type(x) in (int,float) and math.isfinite(x)) for x in values) and sum(x is not None for x in values)>=2 and isinstance(spec.get('source_ids'),list) and bool(spec['source_ids']))
            if not valid: raise ValueError('缺少有效的观测值、时间、单位或来源标记')
            if spec['type']=='line' and (spec.get('axis_type')=='category' or not all(TIME_LABEL.fullmatch(label.strip()) for label in labels)):
                raise ValueError('类别数据不能连成时间趋势；请使用柱形图并保留分类数据表')
            spec['source_ids']=[url_ids.get(sid,sid) for sid in spec['source_ids']]
            periods=set()
            for label in labels:
                if re.search(r'H[12]|半年',label,re.I):periods.add('half')
                elif re.search(r'Q[1-4]|季度',label,re.I):periods.add('quarter')
                elif re.search(r'FY\s*\d{4}|^\d{4}$|年度',label,re.I):periods.add('year')
            if len(periods)>1:raise ValueError('年度、半年度和季度跨度不同，必须分图比较')
            if re.search(r'反向|推导|推算|估算|估计|近似|derived|estimated|approx',str(spec.get('note','')),re.I):
                raise ValueError('含推导或估算数据，禁止替代缺失的原始观测值')
            metric=spec.get('metric') or re.split(r'[（(]',spec['title'])[0].strip()
            if not metric: raise ValueError('缺少明确指标名称')
            source_numbers=set()
            for sid in spec['source_ids']:
                record=sources.get(sid)
                if not record or not record['url'].startswith('https://') or '...' in record['url'] or '…' in record['url']:
                    raise ValueError('图表来源标记没有对应的完整来源路径')
                if re.search(r'片段|线索|第三方|失败|未读|截断|登录|历史材料',record['method']+' '+record['limits']):
                    raise ValueError('图表仅有片段、第三方或未读来源，暂不作为官方财务图展示')
                if metric.casefold() not in record['facts'].casefold():
                    raise ValueError('图表指标未被所指来源的适用事实覆盖')
                if evidence is not None:
                    original=actual.get(sid,{})
                    if not original.get('official_domain_match') or not original.get('content'):
                        raise ValueError('本次检索记录没有相应官方正文，不能凭模型声称已读取')
                    source_numbers.update(float(x) for x in re.findall(r'(?<![\w])[-+]?\d+(?:\.\d+)?',original['content'].replace(',','')))
            if evidence is not None and not all(float(x) in source_numbers for x in values if x is not None):
                raise ValueError('图中有数值未出现在本次实际取得的正文节选中')
            def number(cell,value):
                cell=cell.replace(',','').replace('**','').strip()
                return bool(re.fullmatch(r'[-+]?\d+(?:\.\d+)?',cell)) and float(cell)==value
            def supports(group):
                if metric.casefold() not in group.casefold() or spec['unit'].casefold() not in group.casefold(): return False
                rows=[[cell.strip() for cell in line.strip().strip('|').split('|')] for line in group.splitlines()]
                header=rows[0]
                for label,value in zip(labels,values):
                    if value is None: continue
                    long_form=any(any(label in cell for cell in row) and any(number(cell,value) for cell in row) for row in rows[1:])
                    columns=[i for i,cell in enumerate(header) if label in cell]
                    wide_form=any(metric.casefold() in ' '.join(row).casefold() and any(i<len(row) and number(row[i],value) for i in columns) for row in rows[1:])
                    if not (long_form or wide_form): return False
                return True
            if not any(supports(group) for group in groups): raise ValueError('指标、期间、单位与数值未在同一正文表格逐点对齐')
            spec['structural_checks']='table-source-v1'
            return '```chart\n'+json.dumps(spec,ensure_ascii=False)+'\n```'
        except (ValueError,TypeError,AttributeError) as exc:
            issues.append({'rule':'图表数据检查','context':str(exc)})
            return '\n图表暂不展示：数据结构或正文对应关系需要核对，详见交付检查。\n'
    return BLOCK.sub(replace,report),issues
