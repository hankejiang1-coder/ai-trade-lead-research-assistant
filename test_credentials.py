import json,os,threading,unittest,urllib.request,urllib.error
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
import credentials,app

class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.original_vault=credentials._vault
        self.entry={}
        vault=SimpleNamespace(get_password=lambda *a:self.entry.get('key'),set_password=lambda s,a,k:self.entry.update(key=k),delete_password=lambda *a:self.entry.pop('key',None))
        self.patches=[patch('credentials._vault',return_value=vault),patch('credentials._memory',''),patch('credentials._session_only',False),patch.dict(os.environ,{'DEEPSEEK_API_KEY':''})]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def test_persisted_key_is_used_without_being_returned(self):
        fake='unit-test-key-only-0123456'
        result=credentials.save_key(fake,True)
        self.assertTrue(result['saved']);self.assertNotIn(fake,json.dumps(result))
        with patch('credentials._memory',''): self.assertEqual(credentials.get_key(),fake)
        self.assertFalse(credentials.delete_key()['configured'])

    def test_no_plaintext_fallback(self):
        with patch('credentials._vault',side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):credentials.save_key('test-only-0123456789',True)
            self.assertFalse(credentials.status()['saved'])
            self.assertTrue(credentials.save_key('test-only-0123456789',False)['configured'])
        self.assertFalse(self.entry)

    def test_saved_updates_override_old_persistent_cache(self):
        self.entry['key']='fresh-test-key-123456'
        with patch('credentials._memory','stale-test-key-123456'):
            self.assertEqual(credentials.get_key(),'fresh-test-key-123456')

    def test_session_override_preserved_and_not_claimed_saved(self):
        self.entry['key']='saved-test-key-123456'
        result=credentials.save_key('session-test-key-123456',False)
        self.assertFalse(result['saved'])
        self.assertEqual(credentials.get_key(),'session-test-key-123456')

    def test_insecure_backend_is_rejected(self):
        insecure=type('PlaintextBackend',(),{'__module__':'keyrings.alt.file'})()
        with patch('credentials.importlib.import_module',return_value=SimpleNamespace(get_keyring=lambda:insecure)):
            # Bypass this test class's fake vault to exercise the actual backend filter.
            with self.assertRaisesRegex(RuntimeError,'不会改用明文'):self.original_vault()

    def test_http_rejects_foreign_origin_and_host(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for path,headers,body in [('/credential-status',{'Host':'attacker.example'},None),('/credentials',{'Origin':'https://attacker.example'},b'{}')]:
            request=urllib.request.Request(base+path,data=body,headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as raised:opener.open(request)
            self.assertEqual(raised.exception.code,403)
            raised.exception.close()
        request=urllib.request.Request(base+'/credentials',data=json.dumps({'action':'save','key':'http-test-only-12345678','remember':False}).encode(),headers={'Origin':base,'Content-Type':'application/json'})
        with opener.open(request) as result:data=json.load(result)
        self.assertTrue(data['configured']);self.assertNotIn('http-test-only',json.dumps(data))

if __name__=='__main__':unittest.main()
