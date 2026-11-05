"""Recover final documents without exposing model reasoning or progress messages."""
import json,re

def normalize_headings(text):
    lines=[]
    for line in text.splitlines():
        if re.match(r'^\s*#{1,3}\s*',line):
            plain=line.replace('**','')
            match=re.match(r'^\s*#{1,3}\s*(\d{1,2})[.、．:：)](?!\d)\s*(.+)',plain)
            if match:line='## '+match[1]+'. '+match[2].strip()
        lines.append(line)
    return '\n'.join(lines)

def candidates(result):
    texts=[]
    if isinstance(result.get('output_text'),str):texts.append(result['output_text'])
    messages=[item for item in result.get('output',[]) if item.get('type')=='message']
    # Examine documents separately; joining two complete JSON messages corrupts JSON.
    for item in reversed(messages):
        for part in item.get('content',[]):
            if part.get('type')=='output_text' and isinstance(part.get('text'),str):texts.append(part['text'])
    return texts

def decode_report(result):
    texts=candidates(result)
    for text in texts:
        clean=re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip())
        try:obj=json.loads(clean)
        except ValueError:continue
        if isinstance(obj,dict) and isinstance(obj.get('report'),str):
            report=normalize_headings(obj['report'])
            start=re.search(r'^## 1\.\s',report,re.M)
            if start:return report[start.start():],[]
    for text in texts:
        report=normalize_headings(text)
        start=re.search(r'^## 1\.\s',report,re.M)
        if start and len(set(re.findall(r'^## (\d+)\.',report,re.M)))>=10:
            return report[start.start():],[{'rule':'返回格式恢复','context':'接口未按JSON约定返回，已恢复完整Markdown草稿；须检查交付状态'}]
    raise ValueError('未识别到包含编号章节的最终报告')

def response_diagnostics(result):
    return {'status':result.get('status'),'usage':result.get('usage'),
            'items':[{'type':item.get('type'),'phase':item.get('phase'),
                      'part_types':[p.get('type') for p in item.get('content',[])],
                      'output_text_characters':sum(len(p.get('text','')) for p in item.get('content',[]) if p.get('type')=='output_text')}
                     for item in result.get('output',[])]}
