"""Local credentials: memory or OS vault only; never a plaintext fallback."""
import importlib
import os
import threading

SERVICE='trade-local-deepseek'
ACCOUNT='api-key'
STATE_VERSION=2
_memory=globals().get('_memory','')
_session_only=globals().get('_session_only',False)
_lock=globals().get('_lock') or threading.RLock()

def _vault():
    try:
        keyring=importlib.import_module('keyring')
        backend=keyring.get_keyring()
    except Exception:
        raise RuntimeError('系统凭据库未就绪；可选择仅本次使用。长期保存需先安装 requirements.txt 中的 keyring。') from None
    # Exclude plaintext, fail, third-party and unverified chained backends.
    if type(backend).__module__ not in ('keyring.backends.macOS','keyring.backends.Windows','keyring.backends.SecretService'):
        raise RuntimeError('未找到支持的系统安全凭据库；不会改用明文文件保存。')
    return backend

def get_key():
    with _lock:
        if _session_only and _memory: return _memory
        try:
            saved=_vault().get_password(SERVICE,ACCOUNT)
        except Exception:
            saved=None
        return saved or _memory or os.environ.get('DEEPSEEK_API_KEY','')

def status():
    try:
        vault=_vault()
        saved=bool(vault.get_password(SERVICE,ACCOUNT))
        available=True
    except Exception:
        saved=False; available=False
    return {'configured':bool(_memory or saved or os.environ.get('DEEPSEEK_API_KEY')),
            'saved':bool(saved and not (_session_only and _memory)),'vault_available':available,
            'environment_configured':bool(os.environ.get('DEEPSEEK_API_KEY'))}

def save_key(value,remember):
    global _memory,_session_only
    if not isinstance(value,str) or not 16<=len(value)<=512 or any(c.isspace() for c in value) or not value.isascii():
        raise ValueError('密钥格式不符合要求，请重新粘贴完整的 DeepSeek API Key。')
    with _lock:
        if remember:
            try: _vault().set_password(SERVICE,ACCOUNT,value)
            except RuntimeError: raise
            except Exception: raise RuntimeError('系统凭据库保存失败，请在电脑上确认权限，或选择仅本次使用。') from None
        _memory='' if remember else value
        _session_only=not remember
    return status()

def delete_key():
    global _memory,_session_only
    with _lock:
        try:
            vault=_vault()
        except RuntimeError:
            vault=None
        try:
            if vault and vault.get_password(SERVICE,ACCOUNT): vault.delete_password(SERVICE,ACCOUNT)
        except Exception:
            raise RuntimeError('系统凭据库删除失败，请检查电脑权限后重试。') from None
        _memory=''
        _session_only=False
    return status()
