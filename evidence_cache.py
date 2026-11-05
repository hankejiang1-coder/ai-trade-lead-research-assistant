"""Keep public retrieval evidence for bounded retries; no credentials or seller inputs."""
import hashlib,json,time
import retrieval
from datetime import datetime
from zoneinfo import ZoneInfo
from retrieval import gather_evidence
CACHE_VERSION=3

def cached_evidence(root,inputs,request,today,refresh=False):
    key=hashlib.sha256(json.dumps({k:inputs.get(k,'') for k in ('company_name','country','website')},sort_keys=True).encode()).hexdigest()[:24]
    folder=root/'.local'/'evidence'
    files=sorted(folder.glob(key+'-*.json'),reverse=True) if folder.exists() else []
    if not refresh and files and time.time()-files[0].stat().st_mtime<6*3600:
        try:
            data=json.loads(files[0].read_text(encoding='utf-8'))
            if data.get('sources') and isinstance(data.get('retrieval_stats'),dict) and (any(s.get('content') for s in data['sources']) or data.get('retrieval_version',0)>=2):
                data['reused']=True;return retrieval.apply_recency_policy(data,today)
        except (ValueError,OSError):pass
    packet=retrieval.gather_evidence(inputs,request,today)
    packet['retrieved_at']=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    packet['reused']=False
    if packet.get('sources'):
        folder.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        with (folder/(key+'-'+stamp+'.json')).open('x',encoding='utf-8') as stream:json.dump(packet,stream,ensure_ascii=False)
    return packet
