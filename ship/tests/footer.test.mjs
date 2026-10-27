import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {renderFooter} from '../footer.mjs';
import {renderFilingLinks} from '../../blog/scripts/kuhai/configure.mjs';
const config=()=>({schemaVersion:1,site:{author:'kuhai',blogBase:'/blog/'},filing:{icp:{approved:false,displayText:'',url:''},publicSecurity:{approved:false,displayText:'',url:'',iconPath:''}}});
const approved=kind=>({approved:true,displayText:'fixture-'+kind,url:kind==='icp'?'https://beian.miit.gov.cn/':'https://beian.mps.gov.cn/#/query/webSearch?code=fixture',...(kind==='publicSecurity'?{iconPath:'/blog/images/filing/official-icon.png'}:{})});
const render=c=>renderFooter(c,{about:'About'});
const consumers=c=>[()=>render(c),()=>renderFilingLinks(c.filing)];

test('both consumers hide unapproved entries without requiring retained fields to be valid',()=>{
  const c=config();
  c.filing.icp={approved:false,displayText:'not-approved',url:'javascript:alert(1)'};
  c.filing.publicSecurity={approved:false,displayText:'not-approved-security',url:'invalid',iconPath:'/outside/../icon%2epng?x=1'};
  for(const consume of consumers(c)){
    assert.doesNotThrow(consume);assert.doesNotMatch(consume(),/not-approved|javascript|icon%/);
  }
  c.filing={};for(const consume of consumers(c))assert.doesNotMatch(consume(),/<img|target="_blank"/);
});

test('both consumers render normalized official links and escape the complete issued text',()=>{
  const c=config();c.filing.icp={...approved('icp'),displayText:'  <issued & "complete">  '};
  c.filing.publicSecurity={...approved('publicSecurity'),displayText:'  issued-security  '};
  for(const consume of consumers(c)){
    const html=consume();assert.match(html,/href="https:\/\/beian\.miit\.gov\.cn\/"/);
    assert.match(html,/&lt;issued &amp; &quot;complete&quot;&gt;<\/a>/);
    assert.match(html,/src="\/blog\/images\/filing\/official-icon\.png"/);
    assert.match(html,/>\s*issued-security<\/a>/);
    assert.equal((html.match(/rel="noopener noreferrer"/g)||[]).length,2);
  }
});

test('approved missing text or nonofficial URLs fail equally instead of disappearing',()=>{
  for(const kind of ['icp','publicSecurity']){
    const host=kind==='icp'?'beian.miit.gov.cn':'beian.mps.gov.cn';
    for(const patch of [{displayText:''},{displayText:'  '},{displayText:123},{url:''},{url:`http://${host}/`},{url:'https://example.test/record'},{url:`https://${host}.evil.test/`},{url:`https://user:password@${host}/`},{url:`https://${host}:8443/`}]){
      const c=config();c.filing[kind]={...approved(kind),...patch};
      const messages=[];
      for(const consume of consumers(c))assert.throws(consume,error=>{messages.push(error.message);return error instanceof Error&&error.message.includes(kind);},`${kind} ${JSON.stringify(patch)}`);
      assert.equal(messages[0],messages[1]);
    }
  }
});

test('both consumers use exact lowercase filing prefix and safe case-insensitive image extensions',()=>{
  const c=config();c.filing.publicSecurity=approved('publicSecurity');
  for(const extension of ['png','jpg','jpeg','webp','svg','PNG','JpEg','SVG']){
    c.filing.publicSecurity.iconPath=`/blog/images/filing/official_2026/icon-approved.${extension}`;
    for(const consume of consumers(c))assert.match(consume(),new RegExp('src="/blog/images/filing/official_2026/icon-approved\\.'+extension+'"'));
  }
});

test('approved icon traversal, encoded, external and incomplete paths fail in both consumers',()=>{
  for(const iconPath of ['',null,'/assets/official.png','//example.test/icon.png','/BLOG/images/filing/icon.png','/blog/Images/filing/icon.png','/blog/images/FILING/icon.png','/blog/images/filing//icon.png','/blog/images/filing/./icon.png','/blog/images/filing/../icon.png','/blog/images/filing/%2e%2e/icon.png','/blog/images/filing/icon%2epng','/blog/images/filing/icon.png?x=1','/blog/images/filing/icon.png#x','/blog/images/filing/dir\\icon.png','/blog/images/filing/官方.png','/blog/images/filing/icon.html']){
    const c=config();c.filing.publicSecurity={...approved('publicSecurity'),iconPath};
    for(const consume of consumers(c))assert.throws(consume,error=>error instanceof Error&&/publicSecurity|iconPath/.test(error.message),String(iconPath));
  }
});

test('official host allowlists and default HTTPS port are consistent across both consumers',()=>{
  for(const host of ['beian.mps.gov.cn','www.beian.gov.cn','beian.gov.cn']){
    const c=config();c.filing.publicSecurity={...approved('publicSecurity'),url:`https://${host}:443/portal/registerSystemInfo?recordcode=fixture&view=public`};
    for(const consume of consumers(c)){
      const html=consume();assert.ok(html.includes(`href="https://${host}/portal/registerSystemInfo?recordcode=fixture&amp;view=public"`));
    }
  }
  const c=config();c.filing.icp={...approved('icp'),url:'https://beian.mps.gov.cn/'};
  for(const consume of consumers(c))assert.throws(consume,/icp:/);
  c.filing.icp.approved=false;c.filing.publicSecurity={...approved('publicSecurity'),url:'https://beian.miit.gov.cn/'};
  for(const consume of consumers(c))assert.throws(consume,/publicSecurity:/);
});

test('current shared configuration preserves the frozen no-filing baseline while both entries remain unapproved',async(t)=>{
  const c=JSON.parse(await readFile(new URL('../../site.json',import.meta.url),'utf8'));
  if(c.filing.icp.approved!==false||c.filing.publicSecurity.approved!==false){
    t.skip('Historical no-filing output is not the comparison baseline once filing approval changes.');return;
  }
  const fixture=JSON.parse(await readFile(new URL('./fixtures/no-filing-footer.json',import.meta.url),'utf8'));
  const oldFooter=fixture.shipLegalFooterInnerHTML;
  assert.ok(oldFooter);assert.equal(renderFooter(c,{about:'关于 kuhai'}),oldFooter);
  const blogFragment=renderFilingLinks(c.filing);
  assert.equal(blogFragment,await readFile(new URL('../../content/config/footer.html',import.meta.url),'utf8'));
  // Footer.astro strips comments and omits its custom wrapper for empty HTML.
  assert.equal(blogFragment.replace(/<!--[\s\S]*?-->/g,'').trim(),'');
  const blogFooters=fixture.blogFooterHTML;
  assert.equal(blogFooters?.length,2);
  for(const footer of blogFooters)assert.doesNotMatch(footer,/m3-blog-footer__custom|beian\.(?:miit|mps)\.gov\.cn|beian\.gov\.cn|\/blog\/images\/filing\//);
});
