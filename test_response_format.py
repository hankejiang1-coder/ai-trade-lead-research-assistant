import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from response_format import decode_report,response_diagnostics
from evidence_cache import cached_evidence

class FinalDocumentTests(unittest.TestCase):
    def test_complete_json_documents_not_concatenated_with_preamble(self):
        data={'output':[{'type':'message','content':[{'type':'output_text','text':'Research progress only'}]}, {'type':'message','phase':'final_answer','content':[{'type':'output_text','text':json.dumps({'report':'## **1.执行摘要**\n完成'})}]}]}
        report,issues=decode_report(data)
        self.assertEqual(report,'## 1. 执行摘要\n完成');self.assertFalse(issues)
        self.assertNotIn('Research',report)

    def test_markdown_recovered_but_progress_not_accepted(self):
        doc='\n'.join('## '+str(n)+'. 内容\n条目' for n in range(1,15))
        report,issues=decode_report({'output_text':doc})
        self.assertIn('## 14.',report);self.assertTrue(issues)
        with self.assertRaises(ValueError):decode_report({'output_text':'I will investigate this company now.'})

    def test_diagnostics_do_not_contain_process_text(self):
        data={'output':[{'type':'reasoning','content':[{'type':'reasoning_text','text':'private process sentinel'}]}]}
        self.assertNotIn('sentinel',json.dumps(response_diagnostics(data)))

    def test_evidence_reused_without_new_search_or_seller_cache(self):
        packet={'sources':[{'id':'S1','content':'public report'}],'retrieval_stats':{'search_success':4},'retrieval_errors':[]}
        with tempfile.TemporaryDirectory() as directory,patch('evidence_cache.retrieval.gather_evidence',return_value=packet) as gather:
            root=Path(directory);inputs={'company_name':'Example','country':'US','website':'https://example.com','product':'private seller sentinel'}
            cached_evidence(root,inputs,None,'2026-11-04')
            second=cached_evidence(root,inputs,None,'2026-11-04')
            self.assertTrue(second['reused']);self.assertEqual(gather.call_count,1)
            self.assertNotIn('private seller sentinel',next((root/'.local'/'evidence').glob('*.json')).read_text())

if __name__=='__main__':unittest.main()
