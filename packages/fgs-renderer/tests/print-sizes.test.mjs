import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import {dirname,join} from "node:path";
import {PDFDocument} from "pdf-lib";
import {createPrintEngine} from "../src/index.mjs";
import {finishedSize,printSheetPlan} from "../src/print-sizes.mjs";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const files={sans:"NotoSans-Regular.ttf",bold:"NotoSans-Bold.ttf",serif:"NotoSerif-Bold.ttf"};
const fonts={};
for(const [key,file] of Object.entries(files))fonts[key]=new Uint8Array(await readFile(join(root,"fonts",file)));
const engine=createPrintEngine(fonts);
const document=()=>({
  format:"forge-gamesheets",format_version:"1.2",id:"card-test",title:"Card Test",
  page:{size:"letter",orientation:"portrait"},theme:{accent:"#793b25"},
  rows:[{id:"row-1",blocks:[{id:"header-1",type:"header",title:"Scores",subtitle:""}]}],
  designer_notes:"Designed for poker-card printing; not a renderer setting.",
});

test("Full Page is unchanged and ignores editorial notes",async()=>{
  const original=document();
  const full=engine.layout(original);
  assert.deepEqual(engine.layout(original,{preset:"full"}).commands,full.commands);
  assert.deepEqual([full.width,full.height],[612,792]);
  delete original.designer_notes;
  assert.deepEqual(engine.layout(original).commands,full.commands);
  const pdf=await PDFDocument.load(await engine.toPdf(full));
  assert.deepEqual(pdf.getPage(0).getSize(),{width:612,height:792});
});

test("FGS 1.4 finished-size default applies unless explicitly overridden",()=>{
  const sheet=document();sheet.format_version="1.4";sheet.page.finished_size={preset:"poker"};
  assert.deepEqual([engine.layout(sheet).width,engine.layout(sheet).height],[180,252]);
  assert.deepEqual([engine.layout(sheet,{preset:"full"}).width,engine.layout(sheet,{preset:"full"}).height],[612,792]);
});

test("finished PDF dimensions match Half Page, poker, bridge and custom sizes",async()=>{
  const cases=[
    [{preset:"half"},[396,612]],
    [{preset:"poker"},[180,252]],
    [{preset:"bridge"},[162,252]],
    [{preset:"custom",width:5,height:7,unit:"in"},[360,504]],
    [{preset:"custom",width:10,height:15,unit:"cm"},[283.465,425.197]],
  ];
  for(const [selection,expected] of cases){
    const layout=engine.layout(document(),selection);
    assert.equal(layout.fits,true,selection.preset);
    assert.deepEqual([layout.width,layout.height],expected);
    assert.match(engine.toSvg(layout),new RegExp(`viewBox="0 0 ${expected[0]} ${expected[1]}"`));
    const pdf=await PDFDocument.load(await engine.toPdf(layout));
    const size=pdf.getPage(0).getSize();
    assert.ok(Math.abs(size.width-expected[0])<.01);
    assert.ok(Math.abs(size.height-expected[1])<.01);
  }
  const a4=document();a4.page.size="a4";
  assert.deepEqual(finishedSize(a4,{preset:"half"}),{preset:"half",width:420.945,height:595.28});
  a4.page.orientation="landscape";
  assert.deepEqual(finishedSize(a4,{preset:"half"}),{preset:"half",width:595.28,height:420.945});
});

test("custom size validation never guesses units or accepts nonsensical measurements",()=>{
  for(const selection of [
    {preset:"custom",width:2.5,height:3.5},
    {preset:"custom",width:0,height:3,unit:"in"},
    {preset:"custom",width:2,height:3,unit:"mm"},
    {preset:"custom",width:"oops",height:3,unit:"in"},
    {preset:"poster"},
  ])assert.throws(()=>finishedSize(document(),selection));
});

test("small formats compose crowded content and uniformly fit it without omission",async()=>{
  const crowded=document();
  crowded.rows.push({id:"row-2",blocks:[{id:"score-1",type:"score_table",title:"Scores",players:Array.from({length:8},(_,i)=>`Player ${i+1}`),score_rows:["Round 1"],show_total:false,total_label:"Total"}]});
  const layout=engine.layout(crowded,{preset:"poker"});
  assert.equal(layout.fits,true);
  assert.ok(layout.fitScale>0&&layout.fitScale<1);
  assert.ok(layout.commands.some(command=>command.type==="text"&&command.value==="Scores"));
  assert.ok(layout.commands.some(command=>command.type==="text"&&command.value.includes("8")));
  const rowTarget=layout.editTargets.find(target=>target.blockId==="score-1"&&target.field==="score_rows");
  assert.ok(rowTarget);
  assert.equal(rowTarget.lineIndex,0);
  assert.ok(rowTarget.x>=0&&rowTarget.x+rowTarget.width<=layout.width);
  assert.ok(rowTarget.y>=0&&rowTarget.y+rowTarget.height<=layout.height);
  assert.equal((await PDFDocument.load(await engine.toPdf(layout))).getPageCount(),1);
  const footed=document();footed.footer="A long credit line that cannot fit across a narrow poker card";
  const footerLayout=engine.layout(footed,{preset:"poker"});
  assert.equal(footerLayout.fits,true);
  assert.ok(footerLayout.commands.filter(command=>command.type==="text"&&command.value.includes("credit")).length>0);
});

test("small-format Header and section headings wrap beyond two lines",async()=>{
  const card=document();card.rows[0].blocks[0].title="Phase 10 Player Card";
  const layout=engine.layout(card,{preset:"poker"});
  assert.equal(layout.fits,true);
  const titleCommands=layout.commands.filter(command=>command.type==="text"&&command.font==="serif");
  assert.equal(titleCommands.length,2);
  assert.ok(titleCommands.every(command=>command.size===14));
  const long=document();long.rows[0].blocks[0].title="A very long title that requires far more than two card lines";
  long.rows.push({id:"row-2",blocks:[{id:"reference-1",type:"reference",title:"Phase 10 Player Reference and Reminders",items:["Cards 1–9: 5 points each.","Cards 10–12: 10 points each."]}]});
  const fitted=engine.layout(long,{preset:"poker"});
  assert.equal(fitted.fits,true);
  assert.ok(fitted.commands.filter(command=>command.type==="text"&&command.font==="serif").length>4);
  assert.ok(fitted.commands.every(command=>command.type!=="text"||command.size>0));
});

test("a purpose-built Phase 10 reference card fits without clipped drawing commands",async()=>{
  const card=document();
  card.rows[0].blocks[0].title="Phase 10 Player Reference Card";
  card.rows.push({id:"reference-row",blocks:[{
    id:"reference",type:"reference",title:"Scoring reminders",
    items:["Cards 1–9: 5 points each.","Cards 10–12: 10 points each.",
      "Skip cards: 15 points each.","Wild cards: 25 points each.",
      "Complete your phase to advance; otherwise repeat it.",
      "First to complete Phase 10 wins; ties break on lowest score."],
  }]});
  const fitted=engine.layout(card,{preset:"poker"});
  assert.equal(fitted.fits,true);
  assert.deepEqual([fitted.width,fitted.height],[180,252]);
  assert.ok(fitted.fitScale>0&&fitted.fitScale<=1);
  for(const command of fitted.commands){
    if(command.type==="text"){
      const textWidth=engine.widthOf(command.value,command.font,command.size);
      const left=command.anchor==="middle"?command.x-textWidth/2:command.x;
      assert.ok(left>=-.01&&left+textWidth<=fitted.width+.01,`text outside card: ${command.value}`);
      assert.ok(command.y>=0&&command.y<=fitted.height,`text baseline outside card: ${command.value}`);
    }else if(command.type==="line"){
      assert.ok(Math.min(command.x1,command.x2)>=0&&Math.max(command.x1,command.x2)<=fitted.width);
      assert.ok(Math.min(command.y1,command.y2)>=0&&Math.max(command.y1,command.y2)<=fitted.height);
    }
  }
  const pdf=await PDFDocument.load(await engine.toPdf(fitted));
  assert.deepEqual(pdf.getPage(0).getSize(),{width:180,height:252});
});

test("print sheets place exact-size copies with guides and no scaling",async()=>{
  const result=engine.layout(document(),{preset:"poker"});
  const plan=printSheetPlan(result,{paper:"letter",copies:9,cutGuides:true});
  assert.deepEqual([plan.width,plan.height,plan.orientation,plan.capacity,plan.pages.length],[792,612,"landscape",6,2]);
  assert.equal(plan.pages[0].length,6);
  assert.equal(plan.pages[1].length,3);
  assert.ok(plan.pages[0].every(({x,y})=>x>=44&&y>=44&&x+result.width<=plan.width-44&&y+result.height<=plan.height-44));
  const pair=printSheetPlan(result,{paper:"letter",copies:2,cutGuides:true});
  assert.equal(pair.orientation,"portrait");
  assert.equal(pair.capacity,4);
  assert.equal(pair.pages.length,1);
  assert.equal(printSheetPlan(result,{paper:"letter",copies:2,orientation:"landscape"}).orientation,"landscape");
  assert.equal(printSheetPlan(result,{paper:"a4",copies:2,orientation:"auto"}).orientation,"portrait");
  assert.equal(printSheetPlan(result,{paper:"a4",copies:5,cutGuides:false,orientation:"auto"}).orientation,"landscape");
  assert.throws(()=>printSheetPlan(result,{paper:"letter",orientation:"sideways"}),/orientation/);
  const pdf=await PDFDocument.load(await engine.toPrintSheetPdf(result,"Card Test",{paper:"letter",copies:9,cutGuides:true}));
  assert.equal(pdf.getPageCount(),2);
  assert.deepEqual(pdf.getPage(0).getSize(),{width:792,height:612});
  const preview=engine.toPrintSheetSvg(result,{paper:"letter",copies:9,cutGuides:true});
  assert.match(preview,/viewBox="0 0 792 612"/);
  assert.equal((preview.match(/aria-label="GameSheet page"/g)||[]).length,6);
  assert.match(preview,/stroke-width="0.5"/);
  assert.equal((engine.toPrintSheetSvg(result,{paper:"letter",copies:9,cutGuides:true},1).match(/aria-label="GameSheet page"/g)||[]).length,3);
});

test("exact Half Page two-up requires explicit borderless mode",async()=>{
  const result=engine.layout(document(),{preset:"half"});
  const safe=printSheetPlan(result,{paper:"letter",copies:2});
  assert.equal(safe.capacity,1);
  assert.equal(safe.pages.length,2);
  const edge=printSheetPlan(result,{paper:"letter",copies:2,borderless:true});
  assert.deepEqual([edge.width,edge.height,edge.capacity,edge.pages.length],[792,612,2,1]);
  assert.deepEqual(edge.pages[0],[{x:0,y:0},{x:396,y:0}]);
  assert.equal((await PDFDocument.load(await engine.toPrintSheetPdf(result,"Half",{paper:"letter",copies:2,borderless:true}))).getPageCount(),1);
  assert.throws(()=>printSheetPlan(result,{paper:"a4",copies:2,borderless:true}),/matching Half Page paper/);
  assert.throws(()=>printSheetPlan(result,{paper:"letter",copies:2,borderless:true,orientation:"portrait"}),/compatible orientation/);
});
