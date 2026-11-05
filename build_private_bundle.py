"""Build an allowlisted, credential-free source preview. Never crawls private data."""
import hashlib
import json
import os
import re
import stat
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
FILES = (
    'app.py', 'credentials.py', 'retrieval.py', 'evidence_cache.py',
    'response_format.py', 'report_format.py', 'chart_checks.py', 'source_probe.py',
    'quality/boundary_checks.py', 'quality/supply_scope.py', 'research_prompt.md',
    'index.html', 'launcher.py', 'requirements.txt', 'start.command', 'start.bat',
    'mcp.example.json', 'README.md', 'DELIVERY.md', 'API_NOTES.md', 'DESIGN.md',
    'regression_cases.json', 'check_mcp_client.py', 'build_private_bundle.py',
    'test_app.py', 'test_credentials.py', 'test_report_format.py', 'test_retrieval.py',
    'test_response_format.py', 'test_ui.cjs', 'test_private_bundle.py',
    'test-card-fixture.png',
)
# One explicitly selected, manually reviewed public-company example; no report history.
EXAMPLES = {'reports/Nutrien-2026-11-04-reviewed.md': 'examples/Nutrien-reviewed-demo.md'}


def build(root=ROOT, destination=None):
    root = Path(root).resolve()
    destination = Path(destination) if destination else root / 'deliverables'
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S-%f')
    target = destination / ('trade-local-0.4.0-preview-' + stamp + '.zip')
    contents = {}
    for local, archive in [(item, item) for item in FILES] + list(EXAMPLES.items()):
        source = root / local
        if local in EXAMPLES and not source.exists() and not source.is_symlink():
            source = root / archive  # The unpacked preview stores the demo under examples/.
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):
            raise ValueError('打包拒绝缺失文件或符号链接：' + local)
        raw = source.read_bytes()
        if source.suffix in ('.py', '.md', '.json', '.html', '.cjs', '.txt', '.bat', '.command'):
            text = raw.decode('utf-8')
            if re.search(r'sk-[A-Za-z0-9_-]{16,}', text) or re.search(r'Bearer\s+[A-Za-z0-9_-]{20,}', text):
                raise ValueError('疑似凭据，停止打包：' + local)
        contents['trade-local/' + archive] = raw
    manifest = {
        'version': '0.4.0-private-preview', 'created_at': stamp,
        'scope': '源代码、说明、离线测试和一份人工复核示例；不含凭据、缓存或报告历史。',
        'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in contents.items()},
    }
    # Exclusive creation protects older archives. Never include env, .local, .venv or vault.
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, raw in contents.items():
                    info = zipfile.ZipInfo(name)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = ((stat.S_IFREG | (0o755 if name.endswith('/start.command') else 0o644)) << 16)
                    archive.writestr(info, raw)
                archive.writestr('trade-local/MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        with zipfile.ZipFile(target) as archive:
            if archive.testzip():
                raise ValueError('压缩包校验失败。')
            for name, expected in manifest['files'].items():
                if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                    raise ValueError('文件校验失败：' + name)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target, manifest


if __name__ == '__main__':
    path, manifest = build()
    print(json.dumps({'archive': str(path), 'files': len(manifest['files']), 'bytes': path.stat().st_size}, ensure_ascii=False))
