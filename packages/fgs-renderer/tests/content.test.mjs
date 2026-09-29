import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {createPrintEngine} from "../src/index.mjs";
import {newContent,patternDefaults,validateContent,validateFill,applyPaperTemplate,PATTERNS,APPEARANCES} from "../src/content.mjs";
const fonts={};for(const [key,file] of Object.entries({sans:"NotoSans-Regular.ttf",bold:"NotoSans-Bold.ttf",serif:"NotoSerif-Bold.ttf"}))fonts[key]=new Uint8Array(await readFile(new URL("../fonts/"+file,import.meta.url)));
const engine=createPrintEngine(fonts);
const sheet=block=>({format:"forge-gamesheets",format_version:"1.3",id:"sheet",title:"Paper",page:{size:"letter",orientation:"portrait"},theme:{accent:"#c84b24"},rows:[{id:"row",blocks:[{id:"content",...block}]}]});
for(const pattern of Object.keys(PATTERNS))test(pattern+" shares vector SVG/PDF geometry across page formats",async()=>{
  for(const size of ["letter","a4"])for(const orientation of ["portrait","landscape"]){
    const b={...newContent("paper_pattern"),pattern,settings:patternDefaults(pattern),sizing:{mode:"fill_remaining"}};
    const d=sheet(b);d.page={size,orientation};d.footer="Example credit";
    const result=engine.layout(d);assert.equal(result.fits,true);assert.ok(result.commands.length>10);
    for(const c of result.commands.filter(c=>c.type==="line"||c.type==="circle")){for(const y of [c.y,c.y1,c.y2].filter(v=>v!==undefined))assert.ok(y<=result.height-58+.001,pattern);}
    assert.match(engine.toSvg(result),/<svg/);assert.ok((await engine.toPdf(result)).length>100);
  }
});
for(const appearance of Object.keys(APPEARANCES))test(appearance+" prints blank spaces and starting guidance",()=>{
  const result=engine.layout(sheet({...newContent("tracker"),appearance,initial_value:5}));assert.equal(result.fits,true);assert.ok(result.commands.some(c=>c.value==="Start: 5"));
});
test("complete music groups, paired staves and tab labels",()=>{
  const b={...newContent("paper_pattern"),pattern:"music_staff",settings:{...patternDefaults("music_staff"),staff_style:"paired",pair_gap_pt:18},sizing:{mode:"fixed_count",count:2}};
  assert.equal(engine.layout(sheet(b)).commands.filter(c=>c.type==="line").length,20);
  b.pattern="tablature";b.settings={...patternDefaults("tablature"),string_labels:["E","B","G","D","A","E"]};
  assert.equal(engine.layout(sheet(b)).commands.filter(c=>c.type==="line").length,12);
  assert.equal(engine.layout(sheet(b)).commands.filter(c=>c.type==="text").length,12);
});
test("strict validation, fill placement and overflow",()=>{
  const d=sheet({...newContent("paper_pattern"),sizing:{mode:"fill_remaining"}});d.rows.push({id:"next",blocks:[{id:"tracker",...newContent("tracker")}]});assert.throws(()=>validateFill(d),/last full-width/);
  assert.throws(()=>validateContent({...newContent("tracker"),id:"tracker",capacity:true}),/numeric/);
  assert.throws(()=>validateContent({...newContent("paper_pattern"),id:"paper",settings:{spacing_pt:.0001}}),/numeric/);
  assert.throws(()=>validateContent({...newContent("tracker"),id:"tracker",initial_value:11}),/numeric/);
  assert.throws(()=>engine.layout(sheet({...newContent("tracker"),appearance:"segmented_bar",capacity:100})),/too narrow/);
  const paper=sheet({...newContent("paper_pattern"),title:"Paper",sizing:{mode:"fixed_height",height_pt:720}});assert.equal(engine.layout(paper).fits,false);
});
test("paper starters create one fill block, with paired piano settings",()=>{
  for(const pattern of [...Object.keys(PATTERNS),"piano"]){let next=0;const d=applyPaperTemplate(sheet(newContent("tracker")),pattern,()=>"id"+next++);assert.equal(d.rows.length,1);assert.equal(d.rows[0].blocks.length,1);assert.equal(d.rows[0].blocks[0].sizing.mode,"fill_remaining");validateFill(d);assert.equal(engine.layout(d).fits,true);}
});
test("coerced enum values are rejected and dense grids remain bounded",()=>{
  assert.throws(()=>validateContent({id:"x",...newContent("tracker"),appearance:["checkboxes"]}),/Unsupported/);
  const d=sheet({...newContent("paper_pattern"),pattern:"dot_grid",settings:{spacing_pt:7},sizing:{mode:"fill_remaining"}});
  assert.ok(engine.layout(d).commands.length<20000);
});

test("blank boards retain square cells, complete geometry and exact counts",()=>{
  for(const [pattern,count] of [["tic_tac_toe",4],["sudoku",20],["dots_and_boxes",36]]){
    const b={...newContent("paper_pattern"),pattern,settings:{...patternDefaults(pattern),arrangement:"single"},sizing:{mode:"fixed_height",height_pt:216}};
    const result=engine.layout(sheet(b));
    assert.equal(result.commands.filter(c=>["line","circle"].includes(c.type)).length,count);
    assert.equal(result.commands.filter(c=>c.type==="text").length,0);
    if(pattern==="sudoku")assert.equal(result.commands.filter(c=>c.thickness===1.5).length,8);
    b.settings.board_size_pt=504;assert.throws(()=>engine.layout(sheet(b)),/complete board/);
  }
  const b={...newContent("paper_pattern"),pattern:"dots_and_boxes",settings:{...patternDefaults("dots_and_boxes"),dot_rows:4,dot_columns:8,arrangement:"single"}};
  const points=engine.layout(sheet(b)).commands.filter(c=>c.type==="circle");assert.equal(points.length,32);
  assert.ok(Math.abs((points[1].x-points[0].x)-(points[8].y-points[0].y))<.0001);
});
test("coordinate origins, negative labels, scale, and disabled numbering",()=>{
  const b={...newContent("paper_pattern"),pattern:"coordinate_grid",settings:{...patternDefaults("coordinate_grid"),units_per_step:5}};
  const centered=engine.layout(sheet(b));assert.ok(centered.commands.some(c=>c.type==="text"&&c.value==="-10"));
  b.settings.origin="bottom_left";assert.ok(!engine.layout(sheet(b)).commands.some(c=>c.type==="text"&&c.value.startsWith("-")));
  b.settings.numbered=false;assert.deepEqual(engine.layout(sheet(b)).commands.filter(c=>c.type==="text").map(c=>c.value),["X","Y"]);
  for(const bad of [{units_per_step:0},{numbered:"true"},{origin:"other"},{x_label:"X\nY"},{label_every:true}])assert.throws(()=>validateContent({id:"axes",...b,settings:{...b.settings,...bad}}));
});

test("coordinate grids use available page area without stretching square cells",()=>{
  for(const origin of ["center","bottom_left"]){
    const b={...newContent("paper_pattern"),pattern:"coordinate_grid",settings:{...patternDefaults("coordinate_grid"),origin},sizing:{mode:"fill_remaining"}};
    const result=engine.layout(sheet(b));
    const grid=result.commands.filter(c=>c.type==="line"&&c.thickness===.5);
    const left=Math.min(...grid.map(c=>Math.min(c.x1,c.x2))),right=Math.max(...grid.map(c=>Math.max(c.x1,c.x2)));
    const top=Math.min(...grid.map(c=>Math.min(c.y1,c.y2))),bottom=Math.max(...grid.map(c=>Math.max(c.y1,c.y2)));
    assert.ok(left<72&&right>result.width-72);
    assert.ok(top<72&&bottom>result.height-72);
    const xs=[...new Set(grid.filter(c=>c.x1===c.x2).map(c=>c.x1))].sort((a,b)=>a-b);
    const ys=[...new Set(grid.filter(c=>c.y1===c.y2).map(c=>c.y1))].sort((a,b)=>a-b);
    assert.equal(xs[1]-xs[0],b.settings.spacing_pt);
    assert.equal(ys[1]-ys[0],b.settings.spacing_pt);
  }
});
