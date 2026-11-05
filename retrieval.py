"""Bounded Search/Fetch retrieval. The model cannot initiate more searches."""
import ipaddress,re
from urllib.parse import urlsplit,urlunsplit,unquote

MAX_SEARCH=4
MAX_FETCH=4

def annotate_recency(source,today):
    context=str(source.get('title',''))+' '+unquote(urlsplit(source.get('url','')).path)
    years=[int(year) for year in re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)',context)]
    financial=bool(re.search(r'annual|financial|results|report|20-f|10-k|6-k|年报|财报',context,re.I))
    historical=bool(financial and years and max(years)<int(today[:4])-3)
    source['document_year_hint']=max(years) if years else None
    source['evidence_scope']='historical_background' if historical else 'current_candidate'
    return historical

def apply_recency_policy(packet,today):
    excluded=[]
    for source in packet['sources']:
        if annotate_recency(source,today):
            source['content']=''
            source['method']='历史材料，仅作背景，不用于当前财务或采购结论'
            excluded.append(source['id'])
    packet['excluded_historical_sources']=excluded
    packet['usable_body_sources']=sum(bool(s.get('content')) for s in packet['sources'])
    return packet

def usable_url(value):
    if not isinstance(value,str) or len(value)>8192:return False
    try:
        p=urlsplit(value)
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.password or p.port not in (None,80,443):return False
        host=p.hostname.lower()
        if host=='localhost' or host.endswith(('.localhost','.local','.internal')) or '.' not in host:return False
        try:return ipaddress.ip_address(host).is_global
        except ValueError:return True
    except ValueError:return False

def content_excerpt(content,limit=18000):
    # Keep context from financial tables beyond the opening pages, without inference.
    if len(content)<=limit:return content
    spans=[(0,5500)]
    for match in re.finditer(r'revenue|cash flow|net earnings|net income|EBITDA|sales volume|营收|现金流|净利润|硫酸铵|ammonium',content,re.I):
        start=max(0,match.start()-600);end=min(len(content),match.start()+1700)
        if any(a<=start<=b for a,b in spans):continue
        spans.append((start,end))
        if sum(b-a for a,b in spans)>=limit:break
    return '\n\n[原文节选分隔]\n\n'.join(content[a:b] for a,b in sorted(spans))[:limit]

def gather_evidence(inputs,request,today):
    company=inputs['company_name'][:70]
    website=inputs.get('website','').strip()
    host=urlsplit(website).hostname if usable_url(website) else ''
    domain=host.removeprefix('www.') if host else ''
    site=' site:'+domain if domain else ''
    queries=[company+' official company business contact',
             company+site+' annual report '+str(int(today[:4])-1)+' financial results',
             company+site+' products supplier procurement distribution',
             company+site+' latest quarterly results revenue cash flow']
    stats={'search_attempted':0,'search_success':0,'fetch_attempted':0,'fetch_success':0}
    sources=[];by_url={};errors=[]
    def record(row):
        url=row.get('url','')
        if not usable_url(url):return
        parts=urlsplit(url);url=urlunsplit((parts.scheme,parts.netloc,parts.path,parts.query,''))
        if url in by_url:
            if not by_url[url].get('_search_body') and row.get('content'):by_url[url]['_search_body']=str(row['content'])[:120000]
            return
        parsed=urlsplit(url);rd=parsed.hostname.removeprefix('www.')
        source={'id':'S'+str(len(sources)+1),'url':url,'title':str(row.get('title',''))[:220],
                'date':row.get('date') or '未提供','method':'搜索线索，未读取正文',
                'summary':str(row.get('summary') or row.get('snippet') or '')[:1800],
                'content':'','_search_body':str(row.get('content') or '')[:120000],
                'official_domain_match':bool(domain and (rd==domain or rd.endswith('.'+domain)))}
        sources.append(source);by_url[url]=source
    for query in queries[:MAX_SEARCH]:
        stats['search_attempted']+=1
        try:
            response=request('/v1/tools/search',{'query':query[:128],'count':5,'need_content':True},45)
            results=response.get('results',[])
            if results:stats['search_success']+=1
            for row in results[:5]:
                if isinstance(row,dict):record(row)
        except Exception as error:
            if getattr(error,'status',None) in (401,402):raise
            errors.append({'operation':'search','query':query[:128],'error':str(error)[:200]})
    if not sources:raise RuntimeError('未取得可用检索结果，已停止生成，避免凭空补充公司事实。')
    def priority(source):
        years=[int(year) for year in re.findall(r'20\d{2}',source['title']+' '+source['url'])]
        age_bonus=0 if not years else 4 if max(years)>=int(today[:4])-1 else -8
        return (int(source['official_domain_match'])*10+
                age_bonus+(6 if re.search(r'annual|financial|results|report|年报|财报',source['title']+' '+source['url'],re.I) else 0))
    for source in sources:annotate_recency(source,today)
    selected=sorted((s for s in sources if s['evidence_scope']!='historical_background'),key=priority,reverse=True)[:MAX_FETCH]
    stats['search_body_success']=0
    for source in selected:
        if source.get('_search_body'):
            source['content']=content_excerpt(source['_search_body'])
            source['method']='搜索接口返回的正文节选；非摘要，非完整财报审阅'
            stats['search_body_success']+=1
            continue
        stats['fetch_attempted']+=1
        try:
            response=request('/v1/tools/fetch',{'url':source['url']},45)
            content=response.get('content','')
            if isinstance(content,str) and content.strip():
                source['content']=content_excerpt(content)
                source['method']='正文节选已取得；未等于完整财报审阅'
                stats['fetch_success']+=1
            else:source['method']='Fetch未返回可用正文'
        except Exception as error:
            if getattr(error,'status',None) in (401,402):raise
            source['method']='Fetch失败：'+str(error)[:140]
            errors.append({'operation':'fetch','url':source['url'],'error':str(error)[:200]})
    for source in sources:source.pop('_search_body',None)
    return apply_recency_policy({'sources':sources,'retrieval_stats':stats,'retrieval_errors':errors,'retrieval_version':3,
            'coverage':'仅以下节选为本次取得资料；搜索摘要不是已读原文。历史财务材料仅作背景，不能用于当前财务或采购判断。官方域名匹配以输入官网为线索，法律主体仍须核验。'},today)

def source_ledger(report,packet):
    """Keep model-to-fact mapping but bind IDs, URLs and read status to real retrieval."""
    from report_format import source_records
    claimed=source_records(report)
    rows=['## 13. 来源与数据缺口','','| 索引 | 来源名称 | URL | 报告期/发布日期 | 本次取得方式 | 适用事实 | 限制 |','|---|---|---|---|---|---|---|']
    def cell(value,limit=300):return str(value).replace('|','/').replace('\n',' ')[:limit]
    for s in packet['sources']:
        facts=claimed.get(s['id'],{}).get('facts','适用事实待核对')
        method=('官方域名匹配；' if s['official_domain_match'] else '第三方/域名待核；')+s['method']
        limit='历史材料，不作为当前财务/采购证据' if s.get('evidence_scope')=='historical_background' else '程序记录取得方式；主体与指标语义未人工核验'
        values=[s['id'],s['title'],s['url'],s['date'],method,facts,limit]
        rows.append('| '+' | '.join(cell(value,8192 if i==2 else 300) for i,value in enumerate(values))+' |')
    rows+=['','### 资料采集覆盖',str(packet['retrieval_stats']),'采集时间：'+packet.get('retrieved_at','未记录'),'本次复用已缓存资料。' if packet.get('reused') else '本次新采集资料。','','Search/Fetch接口404仅表示未取得可用正文，不等于目标网站HTTP404；可能涉及内容类型、站点策略、空正文或页面问题。']
    for error in packet['retrieval_errors']:rows.append('- '+cell(error))
    return '\n'.join(rows)
