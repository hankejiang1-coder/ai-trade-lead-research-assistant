import unittest
from retrieval import gather_evidence,source_ledger,usable_url,apply_recency_policy

class RetrievalTests(unittest.TestCase):
    def test_search_and_fetch_are_hard_bounded(self):
        calls=[]
        def request(path,data,timeout):
            calls.append(path)
            if path.endswith('search'):return {'results':[{'title':'Annual report','url':'https://example.com/report'+str(n),'summary':'snippet'} for n in range(20)]}
            return {'content':'Revenue 2025 100 USD million'}
        packet=gather_evidence({'company_name':'Example','website':'https://example.com'},request,'2026-11-04')
        self.assertEqual(calls.count('/v1/tools/search'),4);self.assertEqual(calls.count('/v1/tools/fetch'),4)
        self.assertEqual(packet['retrieval_stats']['fetch_success'],4)
        self.assertTrue(all(s['official_domain_match'] for s in packet['sources']))

    def test_failed_fetch_cannot_be_labelled_read_by_model(self):
        packet={'sources':[{'id':'S1','url':'https://example.com/report','title':'Official report','date':'2025','official_domain_match':True,'method':'Fetch失败：HTTP404'}],'retrieval_stats':{},'retrieval_errors':[]}
        report='## 13. 来源\n|S1|报告|https://madeup.example/fake|2025|官方全文已读|收入|完整|'
        ledger=source_ledger(report,packet)
        self.assertIn('https://example.com/report',ledger);self.assertNotIn('madeup.example',ledger);self.assertIn('Fetch失败',ledger);self.assertNotIn('全文已读',ledger)

    def test_private_or_credential_url_not_sent(self):
        for url in ('http://127.0.0.1/a','http://localhost/a','http://192.168.1.1/a','https://user:pass@example.com/a','file:///tmp/a'):
            self.assertFalse(usable_url(url))
        self.assertTrue(usable_url('https://example.com/report.pdf'))

    def test_long_evidence_url_is_not_truncated(self):
        url='https://example.com/report?tracking='+'a'*400
        packet={'sources':[{'id':'S1','url':url,'title':'report','date':'2025','official_domain_match':True,'method':'正文节选'}],'retrieval_stats':{},'retrieval_errors':[]}
        self.assertIn(url,source_ledger('',packet))

    def test_search_body_used_without_fetch_and_summaries_not_promoted(self):
        def request(path,data,timeout):
            self.assertEqual(path,'/v1/tools/search')
            return {'results':[{'title':'2025 results','url':'https://example.com/report#anchor','summary':'short summary','content':'Original public body: annual revenue 100.'}]}
        packet=gather_evidence({'company_name':'Example','website':'https://example.com'},request,'2026-11-04')
        self.assertEqual(packet['retrieval_stats']['fetch_attempted'],0)
        self.assertEqual(packet['retrieval_stats']['search_body_success'],1)
        self.assertNotIn('#',packet['sources'][0]['url'])
        self.assertIn('Original public body',packet['sources'][0]['content'])
        self.assertNotIn('_search_body',packet['sources'][0])

    def test_old_financial_report_not_selected_over_current_documents(self):
        def request(path,data,timeout):
            self.assertEqual(path,'/v1/tools/search')
            return {'results':[{'title':'Financial report 2008','url':'https://example.com/2008/report.pdf','content':'old financial numbers'}, {'title':'Annual report 2025','url':'https://example.com/2025/report','content':'current financial excerpt'}]}
        packet=gather_evidence({'company_name':'Example','website':'https://example.com'},request,'2026-11-04')
        old=next(s for s in packet['sources'] if '2008' in s['url'])
        self.assertFalse(old['content']);self.assertEqual(old['evidence_scope'],'historical_background')
        self.assertEqual(packet['usable_body_sources'],1)

    def test_policy_also_filters_old_cached_bodies_without_erasing_current_body(self):
        packet={'sources':[{'id':'S1','title':'2008 Annual Report','url':'https://example.com/2008/report','content':'historical original'}, {'id':'S2','title':'2025 Results','url':'https://example.com/2025/results','content':'current original'}]}
        filtered=apply_recency_policy(packet,'2026-11-04')
        self.assertFalse(filtered['sources'][0]['content']);self.assertEqual(filtered['sources'][1]['content'],'current original')
        self.assertEqual(filtered['excluded_historical_sources'],['S1'])

    def test_encoded_date_in_real_style_path_not_misread_as_2020(self):
        packet={'sources':[{'id':'S9','title':'Contents','url':'https://example.com/Financial%20Reports/December%2031,%202008.pdf','content':'old report'}]}
        result=apply_recency_policy(packet,'2026-11-04')
        self.assertEqual(result['sources'][0]['document_year_hint'],2008)
        self.assertFalse(result['sources'][0]['content'])

if __name__=='__main__':unittest.main()
