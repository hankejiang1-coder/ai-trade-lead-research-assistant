"""Optional official MCP Python SDK check; --live-icl performs one paid generation.

Install mcp in a separate test environment, not the application environment.
Credentials are resolved only by the server's normal credential module.
"""
import argparse
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent


async def check(server_python, live_icl=False):
    from mcp import Client, StdioServerParameters
    from importlib.metadata import version

    params = StdioServerParameters(command=server_python, args=['-B', str(ROOT / 'app.py'), '--mcp'])
    async with Client(params, read_timeout_seconds=700) as client:
        listed = await client.list_tools()
        invalid = await client.call_tool('research_company', {'company_name': ''})
        summary = {
            'sdk': version('mcp'), 'server': client.server_info.name,
            'protocol': client.protocol_version,
            'tools': [tool.name for tool in listed.tools],
            'invalid_input_rejected': invalid.is_error,
            'paid_generation_requested': live_icl,
        }
        if live_icl:
            # Abort before the call if public evidence is missing/stale. No new retrieval.
            from evidence_cache import cached_evidence
            customer = {
                'company_name': 'ICL Group Ltd.', 'country': 'Israel',
                'website': 'https://www.icl-group.com',
                'product': '我方为烟台供应商，并非制造商。销售颗粒NPK 15-15-15、10-10-10、20-20-20，三种NPK合计供货能力20000吨/月；另销售颗粒硫酸铵、氯化铵，其规格和供货量待确认。价格随市场变化。目标东南亚、欧洲、澳洲、北美、南美。质检、SGS、样品均须另行确认，不承诺已具备。',
            }
            def no_retrieval(*args, **kwargs):
                raise RuntimeError('没有可用缓存；本检查禁止重新检索。')
            packet = cached_evidence(ROOT, customer, no_retrieval, datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d'))
            if not packet.get('reused') or not packet.get('usable_body_sources'):
                raise RuntimeError('没有可复用正文，停止付费调用。')
            result = await client.call_tool('research_company', customer, read_timeout_seconds=700)
            text = '\n'.join(block.text for block in result.content if getattr(block, 'type', '') == 'text')
            stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d-%H%M%S')
            report, separator, usage_text = text.rpartition('\n\nAPI usage: ')
            folder = ROOT / 'reports'
            folder.mkdir(exist_ok=True)
            if result.is_error:
                summary['tool_error'] = text
            else:
                if not separator:
                    raise RuntimeError('报告缺少用量分隔，未作为成功验收。')
                target = folder / ('ICL-' + stamp + '-mcp-live.md')
                with target.open('x', encoding='utf-8') as output:
                    output.write(report + '\n')
                summary.update({
                    'report_file': str(target), 'usage': json.loads(usage_text),
                    'chapters': len(re.findall(r'^##\s+\d+[.、．]', report, re.M)),
                    'source_links': len(set(re.findall(r'https?://[^\s|)>]+', report))),
                    'excluded_historical_sources': packet.get('excluded_historical_sources', []),
                })
            with (folder / ('MCP-SDK-' + stamp + '.json')).open('x', encoding='utf-8') as output:
                json.dump(summary, output, ensure_ascii=False, indent=2)
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-python', default=str(ROOT / '.venv' / ('Scripts/python.exe' if __import__('os').name == 'nt' else 'bin/python')))
    parser.add_argument('--live-icl', action='store_true', help='Uses saved public evidence and incurs one model generation fee.')
    options = parser.parse_args()
    asyncio.run(check(options.server_python, options.live_icl))
