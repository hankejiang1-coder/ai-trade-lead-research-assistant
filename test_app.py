import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
import app

class ConnectionTests(unittest.TestCase):
    def test_stdio_mcp_chinese_output_even_if_parent_encoding_ascii(self):
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'research_company','arguments':{'company_name':''}}}]
        result=subprocess.run([sys.executable,'-B',str(app.ROOT/'app.py'),'--mcp'],input='\n'.join(json.dumps(m) for m in messages)+'\n',capture_output=True,text=True,encoding='utf-8',env={'PYTHONIOENCODING':'ascii'},timeout=10)
        self.assertEqual(result.returncode,0)
        responses=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(responses[1]['result']['isError'])
        self.assertIn('公司名称',responses[1]['result']['content'][0]['text'])

    def setUp(self):
        self.vault=patch('credentials._vault',side_effect=RuntimeError('test vault unavailable'))
        self.vault.start(); self.addCleanup(self.vault.stop)
        self.memory=patch('credentials._memory',''); self.memory.start(); self.addCleanup(self.memory.stop)
        self.retrieval=patch('app.cached_evidence',return_value={'sources':[{'id':'S1','url':'https://example.com/report','title':'Example','date':'2025','method':'正文节选','content':'public report fixture','official_domain_match':True}],'retrieval_stats':{},'retrieval_errors':[]})
        self.retrieval.start();self.addCleanup(self.retrieval.stop)
        self.archive=patch('app.preserve_draft');self.archive.start();self.addCleanup(self.archive.stop)

    def test_response_and_secret_transport(self):
        body={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'report':'## 1. 执行摘要\n测试报告'})}]}]}
        response=subprocess.CompletedProcess([],0,json.dumps(body)+'\n200','')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-only-not-a-secret'}),patch('app.shutil.which',return_value='/usr/bin/curl'),patch('app.subprocess.run',return_value=response) as run:
            report,_=app.research({'company_name':'云天化'})
            self.assertIn('测试报告',report)
            self.assertIn('未确认联网取证成功',report)
            args,kwargs=run.call_args
            self.assertNotIn('test-only-not-a-secret',str(args))
            self.assertNotIn('--insecure',args[0])
            self.assertIn('Authorization: Bearer '+'test-only-not-a-secret',kwargs['input'])
            self.assertIn('云天化',kwargs['input'])
            self.assertEqual(kwargs['encoding'],'utf-8')
            config_line=next(line for line in kwargs['input'].splitlines() if line.startswith('data-binary = '))
            payload=json.loads(json.loads(config_line.split(' = ',1)[1]))
            self.assertEqual(payload['tools'],[])
            self.assertEqual(payload['tool_choice'],'none')
            self.assertEqual(payload['text']['format']['type'],'json_schema')
            self.assertEqual(run.call_count,1)

    def test_composition_never_receives_unread_search_claims(self):
        packet={'sources':[{'id':'S1','url':'https://example.com/results','title':'Results','date':'2025','method':'官方正文节选','content':'Sales 10','summary':'UNTRUSTED-SUMMARY','official_domain_match':True},{'id':'S2','url':'https://example.com/port','title':'Port','content':'','summary':'UNREAD-CLAIM','method':'搜索线索','date':'未提供','official_domain_match':True}], 'retrieval_stats':{},'retrieval_errors':[]}
        response={'status':'completed','output_text':json.dumps({'report':'## 1. 执行摘要\n资料不足'})}
        with patch('app.cached_evidence',return_value=packet),patch('app.credential_key',return_value='fake-test-key'),patch('app.deepseek_call',return_value=response) as call:
            app.research({'company_name':'TEST'})
        evidence=json.loads(call.call_args.args[0]['input'])['evidence']
        self.assertEqual([s['id'] for s in evidence['sources']],['S1'])
        self.assertNotIn('summary',evidence['sources'][0])
        self.assertNotIn('UNREAD-CLAIM',call.call_args.args[0]['input'])

    def test_tls_failure_is_not_report(self):
        response=subprocess.CompletedProcess([],60,'','certificate failure')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test'}),patch('app.shutil.which',return_value='curl'),patch('app.subprocess.run',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'系统证书'):
                app.research({'company_name':'Yara'})

    def test_connection_check_uses_get_without_generation(self):
        response=subprocess.CompletedProcess([],0,'{"data": [{"id": "deepseek-flash"}]}\n200','')
        with patch('app.shutil.which',return_value='curl'),patch('app.subprocess.run',return_value=response) as run:
            result=app.provider_request('/models',{},key='fake-test-key-not-secret')
        self.assertEqual(result['data'][0]['id'],'deepseek-flash')
        self.assertIn('request = "GET"',run.call_args.kwargs['input'])
        self.assertNotIn('data-binary',run.call_args.kwargs['input'])

    def test_reasoning_is_never_report(self):
        with self.assertRaisesRegex(RuntimeError,'未返回报告正文'):
            app.parse_response({'output':[{'type':'reasoning','content':[{'type':'reasoning_text','text':'private reasoning'}]}]})

    def test_direct_text_and_source_counters(self):
        report,usage=app.parse_response({'output_text':'report','usage':{'server_tool_use':{'tool_search':1,'tool_fetch':0}}})
        self.assertIn('搜索结果不能冒充已读原文',report)
        self.assertTrue(report.endswith('report'))

    def test_progress_is_not_a_finished_report(self):
        with self.assertRaisesRegex(RuntimeError,'过程说明'):
            app.parse_response({'output':[{'type':'message','phase':'commentary','content':[{'type':'output_text','text':'I will research now'}]}]})

    def test_final_answer_ignores_progress(self):
        report,_=app.parse_response({'output':[{'type':'message','phase':'commentary','content':[{'type':'output_text','text':'progress only'}]},{'type':'message','phase':'final_answer','content':[{'type':'output_text','text':'final report'}]}]})
        self.assertNotIn('progress only',report)
        self.assertIn('final report',report)

    def test_stale_format_module_reloaded_before_import_and_paid_work(self):
        import report_format
        original=report_format.source_records
        del report_format.source_records
        try:
            with patch('app.provider_request') as paid:
                with self.assertRaisesRegex(ValueError,'公司名称'):app.research({'company_name':''})
                paid.assert_not_called()
            self.assertTrue(callable(report_format.source_records))
        finally:
            report_format.source_records=original

    def test_image_rejects_url_and_wrong_content(self):
        for image in ('https://example.com/card.jpg','data:image/png;base64,aGVsbG8=','data:image/svg+xml;base64,aGVsbG8='):
            with self.assertRaises(ValueError): app.validate_card_image(image)

    def test_ocr_uses_vision_model_and_returns_review_fields(self):
        image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aBvUAAAAASUVORK5CYII='
        response={'status':'completed','output_text':json.dumps({'company_name':'TEST COMPANY','person':'Example','raw_text':'TEST COMPANY'})}
        with patch('app.deepseek_call',return_value=response) as call:
            result=app.recognize_card({'image':image})
        self.assertEqual(result['card']['company_name'],'TEST COMPANY')
        self.assertEqual(call.call_args.args[0]['model'],'deepseek-flash')
        self.assertEqual(result['card']['email'],'')

    def test_quality_gate_detects_role_and_missing_sections(self):
        report='## 9. 定制英文开发邮件\nSubject: Test\nDear team, we are a manufacturer.\n## 10. 会议\nTBD'
        result=app.quality_report(report,True)
        self.assertIn('卖方身份',result)
        self.assertIn('报告章节完整性',result)
        self.assertIn('会议时段',result)
        self.assertIn('未自动验证',result)

    def test_negative_quality_statement_not_mistaken_for_promise(self):
        from quality import boundary_checks as q
        self.assertFalse(q.check_quality_boundaries('规格书可发送，不虚构SGS或第三方报告。'))
        self.assertTrue(q.check_quality_boundaries('我们提供SGS报告。'))
        self.assertTrue(q.check_quality_boundaries('不虚构SGS报告，但我们可提供SGS证书。'))

    def test_no_body_evidence_stops_before_model_generation(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-only-placeholder'}),patch('app.cached_evidence',return_value={'sources':[{'content':''}],'retrieval_stats':{'search_success':4},'retrieval_errors':[]}),patch('app.deepseek_call') as generate:
            with self.assertRaisesRegex(app.ProviderError,'未取得任何可用正文'):app.research({'company_name':'Test'})
            generate.assert_not_called()

if __name__=='__main__': unittest.main()
