/* Synthetic meeting journey; no real account or transcript data. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
  const session=JSON.parse(fs.readFileSync(process.env.APP_SESSION_FILE||'.ui-test/session.json','utf8'));
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1100}});
    const fixture={source:'facechat',jobs:{},next:0,empty:false,fail:false};
    const code='9007199254740999', errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/**',async route=>{
      const r=route.request(),url=new URL(r.url()),body=r.method()==='POST'?r.postDataJSON():{};
      let result={},status=200;
      if(url.pathname==='/api/health')result={windows:true,crypto:true,powershell:true,output_folder:'C:\\Example\\Exports',consented_databases:[]};
      else if(url.pathname==='/api/job')result=fixture.jobs[url.searchParams.get('id')];
      else if(['/api/discover','/api/connect','/api/export'].includes(url.pathname)){
        const id=String(++fixture.next);let output={};
        if(url.pathname==='/api/discover'){
          fixture.source=body.source;
          output={candidates:[{path:'C:\\Example\\WXWork\\Profiles\\sample\\'+(body.source==='meeting'?'io_data.json':'voice_room5.db'),size:4096,modified:1792375200}]};
        }
        if(url.pathname==='/api/connect'){
          assert.equal(body.source,fixture.source);
          output={database:body.path,source:body.source,rooms:fixture.empty?[]:[
            {room_id:code,title:'研究讨论（演示）',started:1788501600,passages:3},
            {room_id:'9007199254740998',title:'缓存内容暂不可导出',started:0,unavailable:true}]};
        }
        if(url.pathname==='/api/export'){
          assert.equal(body.room_id,code);assert.equal(body.resolve_speakers,false);
          output={id:'sample-meeting',title:'研究讨论（演示）',passages:3,elapsed:.4,markdown:'sample.md',json:'sample.json',
            warnings:['会议原文来自本机缓存，尚未核对服务器端完整性；缓存可能过期或不完整。'],
            preview:[{speaker:'示例成员',time:'2026-09-04 14:00:01.500',text:'原文  保留\n<script>示例</script>'}],preview_truncated:false};
        }
        fixture.jobs[id]=fixture.fail&&url.pathname==='/api/connect'?{state:'error',error:{message:'会议缓存暂时无法读取。',action:'请加载后刷新。'}}:{state:'done',result:output};
        result={job:id};status=202;
      }
      await route.fulfill({status,contentType:'application/json',body:JSON.stringify(result)});
    });
    await page.goto(session.url);await page.locator('.candidate').waitFor();
    await page.locator('#source-meeting').check();
    await page.locator('#candidate-list').getByText(/io_data.json/).waitFor();
    assert.equal(await page.locator('#meeting-cache-help').isVisible(),true);
    await page.locator('#consent').check();await page.locator('#connect').click();
    await page.locator('.recording').first().waitFor();
    assert.equal(await page.locator('#speaker-options').isHidden(),true);
    assert.equal(await page.locator('.recording').nth(1).isEnabled(),false);
    await page.locator('.recording').first().click();await page.locator('#export').click();
    await page.getByText('转录原文已保存',{exact:true}).waitFor();
    assert.match(await page.locator('#result-warnings').innerText(),/服务器/);
    assert.equal(await page.locator('.utterance p').innerText(),'原文  保留\n<script>示例</script>');
    await page.screenshot({path:'.ui-test/meeting-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:'.ui-test/meeting-mobile.png',fullPage:true});
    fixture.empty=true;await page.locator('#refresh-recordings').click();
    await page.locator('#empty-recordings').waitFor();assert.equal(await page.locator('#export').isEnabled(),false);
    assert.match(await page.locator('#empty-recordings-message').innerText(),/智能纪要/);
    fixture.empty=false;await page.locator('#refresh-recordings').click();await page.locator('.recording').first().click();
    fixture.fail=true;await page.locator('#refresh-recordings').click();await page.locator('#setup-view').waitFor();
    assert.equal(await page.locator('#recordings-view').isHidden(),true);
    fixture.fail=false;await page.locator('#source-facechat').check();
    await page.locator('#candidate-list').getByText(/voice_room5.db/).waitFor();
    assert.equal(await page.locator('#meeting-cache-help').isHidden(),true);
    assert.equal(await page.locator('#resolve-speakers').isChecked(),false);
    assert.deepEqual(errors,[]);
    console.log('Meeting browser journey passed: source isolation, discovery, export, safe text, warning, unavailable/empty/error states, mobile layout.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
