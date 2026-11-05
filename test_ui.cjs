const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const ids=new Set([...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]));
for(const match of script.matchAll(/\$\('([^']+)'\)/g))assert.ok(ids.has(match[1]),'Missing DOM element: '+match[1]);
assert.ok(!html.includes('Google 补充检索'));assert.ok(!html.includes('查看扣子参考报告'));
assert.ok(!html.match(/<style>([\s\S]*?)<\/style>/)[1].includes('\\n.card'));
new vm.Script(script);
const nodes=[];
function el(tag){return {tag,children:[],attrs:{},append(...items){this.children.push(...items)},setAttribute(k,v){this.attrs[k]=v},set textContent(x){this.text=x}}}
const ctx={document:{createElement(tag){const n=el(tag);nodes.push(n);return n},createElementNS(ns,tag){const n=el(tag);nodes.push(n);return n},createTextNode(text){return {text}}}};
vm.createContext(ctx);vm.runInContext(script.split("let activeReport=''")[0],ctx);
const parts=ctx.splitReport('# Title\n\n## 公司档案\ncompany\n\n## 财报\nfinancial\n\n### 开发邮件\nmail');
assert.equal(parts.length,3);assert.equal(parts[0].title,'公司档案');assert.equal(parts[2].lines.join('').trim(),'mail');
assert.equal(ctx.sourceUrls('https://a.com/；https://a.com/').length,1);
const parent=el('p');ctx.appendInline(parent,'<script>alert(1)</script> **bold** [bad](javascript:alert(1)) https://example.com');
assert.equal(nodes.filter(n=>n.tag==='script').length,0);assert.equal(nodes.filter(n=>n.tag==='a').length,1);assert.equal(nodes.find(n=>n.tag==='a').href,'https://example.com');
assert.ok(parent.children.some(n=>(n.text||'').includes('<script>')));
if(fs.existsSync(__dirname+'/reference-report.md')){
 const reference=ctx.splitReport(fs.readFileSync(__dirname+'/reference-report.md','utf8'));
 assert.ok(reference.length>=14);
 assert.ok(reference.some(p=>p.title.includes('财务')));
 assert.ok(reference.some(p=>p.title.includes('英文会后跟进邮件')));
}
const table=el('article');ctx.fillBody(table,['|项目|数据|','|---|---|','|测试|123|']);
assert.ok(nodes.some(n=>n.tag==='th'));
const spec={type:'line',title:'收入',unit:'USD million',labels:['2023','2024','2025'],values:[10,null,20],source_ids:['S1'],structural_checks:'table-source-v1'};
assert.ok(ctx.validateChart(spec));assert.ok(!ctx.validateChart({...spec,values:[10,20]}));assert.ok(!ctx.validateChart({...spec,values:[10,null,null]}));
const chartStart=nodes.length;ctx.renderChart(spec);assert.equal(nodes.slice(chartStart).filter(n=>n.tag==='line'&&n.attrs.stroke==='#245d91').length,0);
assert.equal(nodes.slice(chartStart).filter(n=>n.tag==='details').length,0);
assert.ok(nodes.slice(chartStart).some(n=>n.className==='table-wrap chart-data'));
assert.ok(nodes.slice(chartStart).some(n=>n.tag==='th'&&n.text==='报告期 / 日期'));
const category={...spec,type:'bar',labels:['欧洲','东南亚'],values:[10,20]};assert.ok(ctx.validateChart(category));assert.equal(ctx.chartAxis(category),'category');assert.ok(!ctx.validateChart({...category,type:'line'}));assert.ok(!ctx.validateChart({...category,type:'line',labels:['欧洲2025','东南亚2025']}));
assert.ok(ctx.isMailSection('9. 定制英文开发邮件'));assert.ok(ctx.isMailSection('11. 英文会后跟进邮件'));assert.ok(!ctx.isMailSection('10. 15分钟英文会议提纲'));
const mail=el('article');ctx.fillMail(mail,['Subject: Supply enquiry','','Dear team,','','We are a supplier. This is a draft.','','Best regards,','[Name]','[Company]']);assert.equal(mail.children[0].className,'mail-body');assert.equal(mail.children[0].children[0].className,'mail-subject');assert.equal(mail.children[0].children.length,4);assert.ok(mail.children[0].children[3].children.some(n=>(n.text||'').includes('Best regards,\n[Name]\n[Company]')));
assert.ok(!ctx.validateChart({...spec,note:'2024为反向推导'}));assert.ok(!ctx.validateChart({...spec,structural_checks:undefined}));
const repaired=ctx.prepareReport('planning text\n## 1. 摘要\n正文\n## 14. 来源\n|S1|年报|example.com/report.pdf|');assert.ok(!repaired.includes('planning text'));assert.ok(repaired.includes('https://example.com/report.pdf'));
const cleaned=ctx.cleanBodyLines(['营收10亿元（来源：https://example.com）','|项目|值|来源|','|---|---|---|','|收入|10亿元|官方|']);assert.ok(cleaned.join('').includes('10亿元'));assert.ok(!cleaned.join('').includes('https'));assert.ok(!cleaned.join('').includes('|官方|'));
const inline=ctx.cleanBodyLines(['正文S6显示收入10；S1、S2为待核验线索。']);assert.ok(!inline.join('').match(/S\d+/));assert.ok(inline.join('').includes('收入10'));
const merged=ctx.mergeSupplements([{title:'财务分析',lines:[]},{title:'贸易与海关',lines:[]},{title:'Google 补充核验',lines:['年报营收待核验 https://example.com/report','','海关港口记录未取得 https://example.com/trade']}]);
assert.ok(merged.find(p=>p.title==='财务分析').lines.join('').includes('年报营收'));
assert.ok(merged.find(p=>p.title==='贸易与海关').lines.join('').includes('海关港口'));
assert.ok(!merged.some(p=>p.title.includes('Google')));
assert.ok(!merged.find(p=>p.title==='财务分析').lines.join('').includes('https'));
console.log('PASS: heading sections, sources, safe text/link rendering');
// Directly opening the HTML must not call file:///credential-status or file:///status.
const fileNodes=new Map();let fileFetches=0;
function fileNode(id){if(!fileNodes.has(id))fileNodes.set(id,{hidden:true,handlers:{},addEventListener(name,fn){this.handlers[name]=fn},setAttribute(){}});return fileNodes.get(id)}
vm.runInNewContext(script,{location:{protocol:'file:'},document:{getElementById:fileNode,body:{classList:{toggle(){}}}},sessionStorage:{getItem(){return null},setItem(){}},fetch(){fileFetches++;throw Error('file mode must not fetch')},window:{}});
assert.equal(fileFetches,0);assert.equal(fileNode('file-entry').hidden,false);assert.equal(fileNode('go').disabled,true);assert.equal(fileNode('recognize').disabled,true);
fileNode('settings-open').handlers.click();assert.equal(fileFetches,0);
console.log('PASS: file entry shows local service link without network or credential requests');
