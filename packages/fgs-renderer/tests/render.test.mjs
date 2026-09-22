import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {createHash} from "node:crypto";
import {fileURLToPath} from "node:url";
import {dirname,join} from "node:path";
import {PDFDocument} from "pdf-lib";
import {createPrintEngine,PROFILE} from "../src/index.mjs";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const files={sans:"NotoSans-Regular.ttf",bold:"NotoSans-Bold.ttf",serif:"NotoSerif-Bold.ttf"};
const fonts={};
for(const [key,file] of Object.entries(files)) fonts[key]=new Uint8Array(await readFile(join(root,"fonts",file)));
const engine=createPrintEngine(fonts);
const sheet=()=>({
  format:"forge-gamesheets",format_version:"1.0",id:"sheet-test",title:"Test Score Sheet",
  page:{size:"letter",orientation:"portrait"},theme:{accent:"#b94f2b"},
  rows:[
    {id:"row-header",blocks:[{id:"header",type:"header",title:"Test Game",subtitle:""}]},
    {id:"row-score",blocks:[{id:"score",type:"score_table",title:"Scoring",players:["Player 1","Player 2"],score_rows:["Ordinary category","Total"],show_total:false,total_label:"Total"}]},
  ],
});

test("built artifacts and third-party notices match the pinned manifest",async()=>{
  const output=join(root,"dist");
  const manifest=JSON.parse(await readFile(join(output,"manifest.json"),"utf8"));
  assert.equal(manifest.profile,PROFILE.id);
  assert.ok(manifest.files["THIRD_PARTY_NOTICES.md"]);
  assert.ok(manifest.files["licenses/pdf-lib-MIT.txt"]);
  assert.ok(manifest.files["licenses/fontkit-MIT.txt"]);
  for(const [file,expected] of Object.entries(manifest.files)) {
    const actual=createHash("sha256").update(await readFile(join(output,file))).digest("hex");
    assert.equal(actual,expected,file);
  }
});

test("one display list specifies bold category labels for both outputs",async()=>{
  const document=sheet();
  const layout=engine.layout(document);
  assert.equal(layout.profile,PROFILE.id);
  assert.equal(layout.fits,true);
  assert.deepEqual([layout.width,layout.height],[612,792]);
  assert.equal(layout.blockBounds[1].x,PROFILE.margin);
  const category=layout.commands.find((item)=>item.type==="text"&&item.value==="Ordinary category");
  assert.equal(category.font,"bold");
  assert.equal(layout.commands.find((item)=>item.value==="Test Game").color,"#b94f2b");
  assert.equal(layout.commands.find((item)=>item.value==="Scoring").color,"#b94f2b");
  const svg=engine.toSvg(layout);
  assert.match(svg,/font-family="FGS bold"[^>]*>Ordinary category<\/text>/);
  const pdf=await engine.toPdf(layout,document.title);
  const parsed=await PDFDocument.load(pdf);
  assert.equal(parsed.getPageCount(),1);
  assert.deepEqual(parsed.getPage(0).getSize(),{width:612,height:792});
  assert.deepEqual(pdf,await engine.toPdf(layout,document.title));
});

test("pale accent rules retain their color while heading text is darkened",async()=>{
  const document=sheet();
  document.theme.accent="#ffff00";
  const layout=engine.layout(document);
  const heading=layout.commands.find((item)=>item.value==="Test Game");
  const section=layout.commands.find((item)=>item.value==="Scoring");
  assert.equal(heading.color,section.color);
  assert.equal(heading.color,"#7a7a00");
  assert.equal(layout.commands.find((item)=>item.type==="line"&&item.color===document.theme.accent).color,"#ffff00");
  const pdf=await engine.toPdf(layout,document.title);
  assert.equal((await PDFDocument.load(pdf)).getPageCount(),1);
});

test("overflow is identical for preview and PDF",async()=>{
  const document=sheet();
  for(let index=0;index<4;index++) document.rows.push({id:`row-notes-${index}`,blocks:[{id:`notes-${index}`,type:"notes",title:`Notes ${index}`,lines:20}]});
  const layout=engine.layout(document);
  assert.equal(layout.fits,false);
  assert.equal(layout.overflow,"Notes 1");
  assert.match(engine.toSvg(layout),/<svg/);
  await assert.rejects(engine.toPdf(layout,document.title),/does not fit/);
});

test("special text is escaped in preview markup",()=>{
  const document=sheet();
  document.rows[1].blocks[0].score_rows[0]="<script>bad</script>";
  const preview=engine.toSvg(engine.layout(document));
  assert.match(preview,/&lt;script&gt;bad&lt;\/script&gt;/);
  assert.doesNotMatch(preview,/<script>/);
});

test("long reference text is measured with the same width used to draw it",()=>{
  const document=sheet();
  document.rows=[
    {id:"row-reference",blocks:[{id:"reference",type:"reference",title:"Reference",items:["Supercalifragilisticexpialidocious ".repeat(8)]}]},
  ];
  const result=engine.layout(document);
  assert.equal(result.fits,true);
  const content=result.commands.filter((item)=>item.type==="text"&&item.font==="sans");
  assert.ok(content.length>3);
  assert.ok(content.at(-1).y<=result.blockBounds[0].y+result.blockBounds[0].height);
  for(const item of content) assert.ok(engine.widthOf(item.value,item.font,item.size)<=result.blockBounds[0].width-36+0.001);
});
