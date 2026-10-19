/* Synthetic browser journey. Run against an app started with --no-browser. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

(async()=>{
  const session=JSON.parse(fs.readFileSync(process.env.APP_SESSION_FILE||'.ui-test/session.json','utf8'));
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1100}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    const candidates=[1,2].map(n=>({path:`C:\\Users\\Example\\Documents\\WXWork\\Profiles\\profile${n}\\voice_room5.db`,modified:1792375200,size:4096}));
    const fixture={candidates,failConnect:true,empty:false,jobs:{},next:0};
    const rooms=[{room_id:'9007199254740993123',title:'技术合作交流（演示）',started:1792375200},{room_id:'9007199254740993124',title:'Research interview — sample',started:1792288800}];
    await page.route('**/api/**',async route=>{
      const request=route.request();const url=new URL(request.url());const body=request.method()==='POST'?request.postDataJSON():{};
      let response={},status=200;
      if(url.pathname==='/api/health')response={windows:true,crypto:true,powershell:true,output_folder:'C:\\Users\\Example\\Documents\\WeCom Exports',consented_databases:[]};
      else if(url.pathname==='/api/job')response=fixture.jobs[url.searchParams.get('id')];
      else if(['/api/discover','/api/connect','/api/export','/api/revoke','/api/browse'].includes(url.pathname)){
        const job=String(++fixture.next);let result={},error;
        if(url.pathname==='/api/discover')result={candidates:fixture.candidates};
        if(url.pathname==='/api/connect'){if(fixture.failConnect)error={message:'请打开企业微信并登录后继续。',action:'请保持企业微信后台运行后重试。'};else result={rooms:fixture.empty?[]:rooms,database:body.path};}
        if(url.pathname==='/api/export'){assert.equal(body.room_id,rooms[0].room_id);result={id:'synthetic-export',title:rooms[0].title,passages:2,elapsed:.32,markdown:'sample-transcript.md',json:'sample-transcript.json',warnings:['部分成员姓名缺失，已使用固定的成员编号标注。'],preview:[{speaker:'发言人1',time:'2026-10-19 10:00:00',text:'这是原始转录的演示文本。\nA second line stays intact.'},{speaker:'成员1',time:'2026-10-19 10:00:04',text:'<script>window.untrustedExecuted=true</script>'}],preview_truncated:false};}
        fixture.jobs[job]=error?{state:'error',error}:{state:'done',result};response={job};status=202;
      }
      await route.fulfill({status,contentType:'application/json',body:JSON.stringify(response)});
    });
    await page.goto(session.url);assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN');await page.getByText('找到 2 个账号',{exact:true}).waitFor();
    assert.equal(await page.locator('#connect').isDisabled(),true);
    await page.locator('.candidate').first().click();await page.locator('#consent').check();
    await page.screenshot({path:'.ui-test/setup-desktop.png',fullPage:true});
    await page.locator('#connect').click();await page.getByText('请打开企业微信并登录后继续。',{exact:true}).waitFor();
    assert.equal(await page.locator('#connect').isEnabled(),true);fixture.failConnect=false;
    await page.locator('#connect').click();await page.locator('.recording').first().waitFor();
    await page.locator('#recording-filter').fill('not a title');assert.equal(await page.locator('.recording').count(),0);
    await page.locator('#recording-filter').fill('');await page.locator('.recording').first().click();await page.locator('#export').click();await page.getByText('转录原文已保存',{exact:true}).waitFor();
    assert.equal(await page.locator('.utterance').count(),2);assert.equal(await page.evaluate(()=>window.untrustedExecuted),undefined);
    await page.screenshot({path:'.ui-test/export-desktop.png',fullPage:true});
    const chinese=page.locator('.utterance p').first();const fonts=await page.context().newCDPSession(page);await fonts.send('DOM.enable');await fonts.send('CSS.enable');const doc=await fonts.send('DOM.getDocument');const node=await fonts.send('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'.utterance p'});const evidence=await fonts.send('CSS.getPlatformFontsForNode',{nodeId:node.nodeId});
    assert(evidence.fonts.some(font=>font.isCustomFont && /Noto/i.test(font.familyName)),'Chinese preview must use the bundled Noto font');
    const headingNode=await fonts.send('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#recordings-title'});const headingFonts=await fonts.send('CSS.getPlatformFontsForNode',{nodeId:headingNode.nodeId});assert(headingFonts.fonts.some(font=>font.isCustomFont&&/Noto/.test(font.familyName)));
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:'.ui-test/export-mobile.png',fullPage:true});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal overflow on mobile');
    await page.locator('#help-button').click();await page.getByRole('dialog').waitFor();const helpNode=await fonts.send('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#help-dialog h2'});const helpFonts=await fonts.send('CSS.getPlatformFontsForNode',{nodeId:helpNode.nodeId});assert(helpFonts.fonts.some(font=>font.isCustomFont&&/Noto/.test(font.familyName)));await page.screenshot({path:'.ui-test/help-mobile.png',fullPage:true});await page.locator('#close-help').click();
    for(const width of [320,430,768,1024]){await page.setViewportSize({width,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No overflow at '+width);}
    await page.setViewportSize({width:1440,height:1100});await page.evaluate(()=>document.body.style.zoom='2');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No overflow at 200% zoom');await page.evaluate(()=>document.body.style.zoom='');await page.setViewportSize({width:390,height:844});
    await page.locator('#change-location').click();fixture.candidates=[];await page.locator('#rescan').click();await page.getByText('尚未找到本地面聊数据',{exact:true}).waitFor();
    await page.screenshot({path:'.ui-test/no-data-mobile.png',fullPage:true});
    fixture.candidates=candidates;await page.locator('#rescan').click();await page.locator('.candidate').first().click();await page.locator('#consent').check();fixture.empty=true;await page.locator('#connect').click();await page.getByText('暂无面聊记录',{exact:true}).waitFor();assert.equal(await page.locator('#export').isDisabled(),true);
    fixture.empty=false;await page.locator('#refresh-recordings').click();await page.locator('.recording').first().click();fixture.failConnect=true;await page.locator('#refresh-recordings').click();await page.locator('#setup-view').waitFor();assert.equal(await page.locator('#recordings-view').isHidden(),true);assert.equal(await page.locator('#export').isDisabled(),true);
    assert.deepEqual(errors,[]);fs.writeFileSync('.ui-test/browser-report.json',JSON.stringify({passed:true,checks:['multiple profiles','consent gating','failed connection and retry','title filtering','exact large room IDs','export and safe text preview','responsive layout','help dialog','missing database','empty recordings'],fontEvidence:{chinesePreview:evidence.fonts,recordingHeading:headingFonts.fonts,helpHeading:helpFonts.fonts},validatorNote:'Generic static validator reports no fonts for hidden recording/help headings. Both are verified here in their visible interactive states.'},null,2));console.log('Browser journey passed: 10 scenario checks; bundled Chinese font verified; desktop and mobile screenshots saved.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
