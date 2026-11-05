import unittest
from unittest.mock import patch
from types import SimpleNamespace
from report_format import organize_report, final_report_only, normalize_source_links, source_issues, source_records, unread_source_issues
from source_probe import public_url,probe
from chart_checks import check_chart_blocks

class ReportFormatTests(unittest.TestCase):
    def test_chinese_inline_ids_move_to_appendix_with_section_mapping(self):
        raw='## 3. 财务\nS6显示收入100。正文S12提供季度信息。\n## 13. 来源\n|S6|财报|https://example.com/report|2025|官方正文|收入|节选|'
        result=organize_report(raw)
        body,appendix=result.split('## 14. 来源与访问核验')
        self.assertNotIn('S6',body);self.assertNotIn('S12',body)
        self.assertIn('| 3. 财务 | S6 |',appendix)
        self.assertIn('| 3. 财务 | S12 |',appendix)
        self.assertIn('收入100',body)

    def test_unread_source_reference_is_flagged_not_missing_statement(self):
        report='## 7. 海关\nS11显示港口吞吐100万吨。\n未取得S9正文，不作结论。\n## 13. 来源\nS11待核验'
        issues=unread_source_issues(report,[{'id':'S11','content':''},{'id':'S9','content':''}])
        self.assertEqual(len(issues),1);self.assertIn('S11',issues[0]['context'])

    def test_sources_move_without_changing_values(self):
        report='## 3. 财报\n收入157亿美元（来源：https://example.com/a）\n净利润 [10亿元](https://example.com/b)\n## 13. 来源\n官方材料 https://example.com/a\n## 14. 自检与交付状态\n未自动验证'
        result=organize_report(report)
        body,appendix=result.split('## 14. 来源与访问核验')
        self.assertNotIn('https://',body);self.assertIn('157亿美元',body);self.assertIn('10亿元',body);self.assertIn('https://example.com/a',appendix)

    def test_chart_json_preserved(self):
        chart='```chart\n{"type":"line","values":[1,null,3],"source_ids":["S1"]}\n```'
        self.assertIn(chart,organize_report('## 3. 财报\n'+chart))

    def test_attribution_detection_only_uses_table_header(self):
        raw='## 3. 财报\n|检查项|结果|\n|---|---|\n|主体、来源、财务|未验证|\n|邮件词数|155|'
        self.assertIn('|主体、来源、财务|未验证|',organize_report(raw))
        self.assertIn('|邮件词数|155|',organize_report(raw))

    def test_private_and_credential_urls_rejected(self):
        with patch('source_probe.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]): self.assertFalse(public_url('https://example.com'))
        self.assertFalse(public_url('https://user:password@example.com'))

    def test_http_404_not_called_anti_bot(self):
        with patch('source_probe.public_addresses',return_value=['93.184.216.34']),patch('source_probe.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='HTTP/2 404\n\n404')):
            result=probe('https://example.com/old')
        self.assertIn('未找到该路径',result);self.assertNotIn('反爬',result)

    def test_chart_rejects_numbers_not_in_report(self):
        raw='|2023|10|\n|2025|20|\n```chart\n{"type":"bar","title":"收入","unit":"USD million","labels":["2023","2025"],"values":[10,99],"source_ids":["S1"]}\n```'
        clean,issues=check_chart_blocks(raw);self.assertEqual(len(issues),1);self.assertNotIn('```chart',clean)

    def test_chart_preserves_actual_values_and_missing_point(self):
        raw='|收入 USD million|2023|2024|2025|\n|---|---|---|---|\n|收入|10|—|20|\n```chart\n{"type":"line","title":"收入","unit":"USD million","labels":["2023","2024","2025"],"values":[10,null,20],"source_ids":["S1"]}\n```\n## 13. 来源\n|S1|官方年报|https://example.com/report.pdf|2025|官方原文|收入|已读取|'
        clean,issues=check_chart_blocks(raw);self.assertFalse(issues);self.assertIn('table-source-v1',clean);self.assertIn('10, null, 20',clean)

    def test_category_distribution_keeps_table_and_uses_bars(self):
        import json
        table='|区域收入 USD million|欧洲|亚洲|\n|---|---|---|\n|区域收入|10|20|\n'
        spec={'type':'bar','title':'区域收入','unit':'USD million','labels':['欧洲','亚洲'],'values':[10,20],'source_ids':['S1']}
        source='\n## 13. 来源\n|S1|官方结果|https://example.com/results|2025|官方正文节选|区域收入|期间已列明|'
        evidence=[{'id':'S1','url':'https://example.com/results','content':'Europe sales 10, Asia sales 20 USD million for FY2025','official_domain_match':True}]
        clean,issues=check_chart_blocks(table+'```chart\n'+json.dumps(spec)+'\n```'+source,evidence)
        self.assertFalse(issues);self.assertIn('|区域收入|10|20|',clean);self.assertIn('table-source-v1',clean)
        spec['type']='line'
        clean,issues=check_chart_blocks(table+'```chart\n'+json.dumps(spec)+'\n```'+source,evidence)
        self.assertIn('类别数据',issues[0]['context']);self.assertNotIn('```chart',clean)

    def test_preamble_never_becomes_report_or_chart_evidence(self):
        raw='Process narrative with unverified 2046.\n## 1. 执行摘要\n正式报告'
        self.assertEqual(final_report_only(raw),'## 1. 执行摘要\n正式报告')

    def test_source_paths_are_not_invented(self):
        raw='## 13. 来源\n|S1|年报|example.com/reports/2025.pdf|2025|官方原文|收入|完整|\n|S2|季报|example.com/.../2026.pdf|2026|线索|收入|未读|\n|S3|网站|example.com|2026|线索|公司|路径未知|'
        cleaned=normalize_source_links(raw)
        self.assertIn('https://example.com/reports/2025.pdf',cleaned)
        self.assertNotIn('https://example.com/...',cleaned)
        self.assertEqual(len(source_issues(cleaned)),2)

    def test_body_table_cannot_spoof_source_ledger(self):
        raw='## 2. 公司\n|S1|例子|https://example.com/spoof|2025|官方原文|收入|完整|\n## 13. 来源\n|S2|原文|https://example.com/report|2025|官方原文|收入|完整|'
        self.assertEqual(set(source_records(raw)),{'S2'})

    def test_mixed_period_chart_rejected(self):
        raw='```chart\n{"type":"bar","title":"收入","unit":"USD million","labels":["FY2025","H1 2026"],"values":[10,20],"source_ids":["S1"]}\n```'
        clean,issues=check_chart_blocks(raw)
        self.assertNotIn('```chart',clean);self.assertIn('跨度不同',issues[0]['context'])

    def test_derived_points_and_wrong_source_cannot_pass(self):
        import json
        prefix='|EBITDA USD m|2024|2025|\n|---|---|---|\n|EBITDA|2046|2803|\n'
        source='\n## 13. 来源\n|S1|原文|https://example.com/results/|2025|官方原文|EBITDA|完整|'
        spec={'type':'bar','title':'EBITDA','unit':'USD m','labels':['2024','2025'],'values':[2046,2803],'source_ids':['S1'],'note':'2024按同比反向推导'}
        for update in ({},{'note':'原始数值','source_ids':['S2']},{'note':'原始数值','labels':['2025','2024']},{'note':'原始数值','title':'氨产量'}):
            chart={**spec,**update}
            cleaned,issues=check_chart_blocks(prefix+'```chart\n'+json.dumps(chart)+'\n```'+source)
            self.assertTrue(issues);self.assertNotIn('```chart',cleaned)

if __name__=='__main__': unittest.main()
