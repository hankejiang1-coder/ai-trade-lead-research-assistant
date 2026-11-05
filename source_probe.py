"""Small public-URL diagnostics; no credentials and no private-network redirects."""
import ipaddress, socket, subprocess, re
from urllib.parse import urlsplit, urljoin

def public_addresses(url):
    try:
        parts=urlsplit(url)
        if parts.scheme not in ('https','http') or parts.username or parts.password or not parts.hostname or parts.port not in (None,80,443): return []
        addresses=socket.getaddrinfo(parts.hostname,parts.port or (443 if parts.scheme=='https' else 80),type=socket.SOCK_STREAM)
        ips=list(dict.fromkeys(item[4][0] for item in addresses))
        return ips if ips and all(ipaddress.ip_address(ip).is_global for ip in ips) else []
    except (ValueError,OSError): return []

def public_url(url): return bool(public_addresses(url))

def probe(url):
    current=url
    for _ in range(2):
        ips=public_addresses(current)
        if not ips: return '未诊断：地址不是可确认的公网HTTP(S)地址，或DNS解析失败'
        parts=urlsplit(current); port=parts.port or (443 if parts.scheme=='https' else 80)
        address='['+ips[0]+']' if ':' in ips[0] else ips[0]
        try:
            r=subprocess.run(['curl','--disable','--head','--silent','--show-error','--max-time','12','--noproxy','*','--resolve',parts.hostname+':'+str(port)+':'+address,'--write-out','\n%{http_code}','--url',current],capture_output=True,text=True,timeout=15)
        except (OSError,subprocess.TimeoutExpired): return '连接超时或本机缺少网络工具；未确认页面是否存在'
        if r.returncode: return {6:'DNS解析失败',28:'连接超时',60:'TLS证书验证失败，未绕过验证'}.get(r.returncode,'网络连接失败，未确认服务器页面状态')
        headers,_,code=r.stdout.rpartition('\n')
        if code.startswith('3'):
            location=re.search(r'^location:\s*(.+)$',headers,re.I|re.M)
            if not location: return 'HTTP '+code+'：发生重定向，但未取得新地址'
            current=urljoin(current,location[1].strip()); continue
        return {'200':'HTTP 200：本次HEAD请求可达；不代表已读取正文','404':'HTTP 404：服务器未找到该路径；可能是旧链接/改版，不能认定公司没有该资料','410':'HTTP 410：该资源已撤下','401':'HTTP 401：需要授权','403':'HTTP 403：访问被拒；具体限制机制未确认','429':'HTTP 429：访问频率受限'}.get(code,'HTTP '+code+'：需进一步检查；HEAD响应与浏览器GET可能不同')
    return '发生多次重定向，已停止；需人工定位最终官方页面'

def failure_diagnostics(report):
    from report_format import URL_RE
    urls=[]
    for line in report.splitlines():
        if re.search(r'404|403|410|429|读取失败|访问失败|证书失败',line):
            for match in URL_RE.finditer(line):
                url=match[0].rstrip(').,;')
                if url not in urls: urls.append(url)
    if not urls: return ''
    rows=['### 失败链接复核（本次程序检查）','| URL | 诊断 |','|---|---|']
    for url in urls[:3]: rows.append('| '+url.replace('|','%7C')+' | '+probe(url)+' |')
    rows.append('HEAD检测不能独立证明反爬、付费墙或正文内容；原文读取与替代来源仍需另外核验。')
    return '\n\n'+'\n'.join(rows)
