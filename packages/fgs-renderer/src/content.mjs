// FGS 1.3 primitives shared by both editors and the print engine.
export const PATTERNS = {ruled:"Ruled",square_grid:"Square grid",dot_grid:"Dot grid",hex_grid:"Hex grid",coordinate_grid:"Coordinate grid (axes)",music_staff:"Music staff",tablature:"Tablature",tic_tac_toe:"Tic-tac-toe boards",dots_and_boxes:"Dots and Boxes boards",sudoku:"Blank Sudoku grids"};
export const BOARD_PATTERNS = ["tic_tac_toe","dots_and_boxes","sudoku"];
export const APPEARANCES = {checkboxes:"Checkboxes",numbered_boxes:"Numbered boxes",segmented_bar:"Segmented bar",current_maximum:"Current / maximum"};
export function patternDefaults(pattern) {
  if(pattern === "coordinate_grid") return {spacing_pt:18,origin:"center",numbered:true,units_per_step:1,label_every:2,x_label:"X",y_label:"Y"};
  if(BOARD_PATTERNS.includes(pattern)) return {board_size_pt:144,gap_pt:pattern==="dots_and_boxes"?54:18,arrangement:"repeat",...(pattern==="dots_and_boxes"?{dot_rows:6,dot_columns:6}:{})};
  if (pattern === "music_staff") return {staff_style:"single",line_spacing_pt:5,group_gap_pt:24};
  if (pattern === "tablature") return {strings:6,line_spacing_pt:7,group_gap_pt:24};
  return pattern === "hex_grid" ? {side_pt:14.25} : {spacing_pt:pattern === "ruled"?18:14.25};
}
const exact = (value, required, optional=[]) => {
  if (!value || typeof value!=="object" || Array.isArray(value) || required.some(key=>!(key in value)) || Object.keys(value).some(key=>![...required,...optional].includes(key))) throw new Error("Invalid or unknown content settings");
};
const numeric = (value,min,max,integer=false) => {
  if (typeof value!=="number" || !Number.isFinite(value) || value<min || value>max || (integer?!Number.isInteger(value):!Number.isInteger(value*4))) throw new Error("Invalid numeric content setting");
};
export function validateContent(block) {
  if (block.type === "tracker") {
    exact(block,["id","type","title","appearance","capacity"],["initial_value","extensions"]);
    if (typeof block.appearance!=="string" || !Object.hasOwn(APPEARANCES,block.appearance)) throw new Error("Unsupported tracker appearance");
    numeric(block.capacity,1,block.appearance==="current_maximum"?1000000:100,true);
    if (block.initial_value!==undefined) numeric(block.initial_value,0,block.capacity,true);
  } else if (block.type === "paper_pattern") {
    exact(block,["id","type","title","pattern","sizing","settings"],["extensions"]);
    if (typeof block.pattern!=="string" || !Object.hasOwn(PATTERNS,block.pattern)) throw new Error("Unsupported paper pattern");
    const {sizing:s,settings:p}=block;
    const music=["music_staff","tablature"].includes(block.pattern);
    if (s?.mode === "fill_remaining") exact(s,["mode"]);
    else if (s?.mode === "fixed_height" && !music) {exact(s,["mode","height_pt"]);numeric(s.height_pt,18,720);}
    else if (s?.mode === "fixed_count" && music) {exact(s,["mode","count"]);numeric(s.count,1,40,true);}
    else throw new Error("Unsupported sizing for this pattern");
    if (block.pattern === "music_staff") {
      exact(p,["staff_style","line_spacing_pt","group_gap_pt"],p?.staff_style==="paired"?["pair_gap_pt"]:[]);
      if (!["single","paired"].includes(p.staff_style)) throw new Error("Invalid staff style");
      numeric(p.line_spacing_pt,3,9);numeric(p.group_gap_pt,12,72);
      if (p.staff_style==="paired") numeric(p.pair_gap_pt,9,36);
    } else if (block.pattern === "tablature") {
      exact(p,["strings","line_spacing_pt","group_gap_pt"],["string_labels"]);
      numeric(p.strings,4,8,true);numeric(p.line_spacing_pt,4,12);numeric(p.group_gap_pt,12,72);
      if (p.string_labels!==undefined && (!Array.isArray(p.string_labels) || p.string_labels.length!==p.strings || p.string_labels.some(label=>typeof label!=="string" || [...label].length>8 || /[\u0000-\u001f\u007f]/.test(label)))) throw new Error("Supply one short label per string");
    } else if(block.pattern === "coordinate_grid") {
      exact(p,["spacing_pt","origin","numbered","units_per_step","label_every","x_label","y_label"]);
      numeric(p.spacing_pt,7,36);numeric(p.units_per_step,.25,1000);numeric(p.label_every,1,10,true);
      if(!["center","bottom_left"].includes(p.origin)||typeof p.numbered!=="boolean")throw new Error("Invalid coordinate axes");
      for(const key of ["x_label","y_label"])if(typeof p[key]!=="string"||[...p[key]].length>16||/[\u0000-\u001f\u007f]/.test(p[key]))throw new Error("Invalid axis label");
    } else if(BOARD_PATTERNS.includes(block.pattern)) {
      exact(p,["board_size_pt","gap_pt","arrangement",...(block.pattern==="dots_and_boxes"?["dot_rows","dot_columns"]:[])]);
      numeric(p.board_size_pt,72,504);numeric(p.gap_pt,9,72);
      if(!["single","repeat"].includes(p.arrangement))throw new Error("Invalid board arrangement");
      if(block.pattern==="dots_and_boxes"){numeric(p.dot_rows,3,21,true);numeric(p.dot_columns,3,21,true);}
    } else {
      const key=block.pattern==="hex_grid"?"side_pt":"spacing_pt";
      exact(p,[key],block.pattern==="ruled"?["margin_guide_pt"]:[]);
      numeric(p[key],block.pattern==="ruled"?9:7,36);
      if (p.margin_guide_pt!==undefined) numeric(p.margin_guide_pt,18,90);
    }
  }
  return block;
}
export function validateFill(document) {
  document.rows.forEach((row,index)=>row.blocks.forEach(block=>{
    if (block.type==="paper_pattern" && block.sizing.mode==="fill_remaining" && (index!==document.rows.length-1 || row.blocks.length!==1)) throw new Error("Fill remaining page requires the last full-width section. Choose fixed sizing before moving, pairing or adding after it.");
  }));
}
export function newContent(type) {
  if(type==="tracker") return {type,title:"Tracker",appearance:"current_maximum",capacity:10};
  if(type==="paper_pattern") return {type,title:"",pattern:"ruled",sizing:{mode:"fixed_height",height_pt:216},settings:patternDefaults("ruled")};
  throw new Error("Unsupported content type");
}
let dimensionUnit="mm";
export function applyPaperTemplate(model,pattern,id) {
  if(pattern==="score_sheet")return model;
  const paired=pattern==="piano";
  const kind=paired?"music_staff":pattern;
  if(!Object.hasOwn(PATTERNS,kind))throw new Error("Unknown paper template");
  const block={id:id("block"),...newContent("paper_pattern"),pattern:kind,settings:patternDefaults(kind),sizing:{mode:"fill_remaining"}};
  if(paired){block.settings.staff_style="paired";block.settings.pair_gap_pt=18;}
  model.rows=[{id:id("row"),blocks:[block]}];
  if(model.format_version!=="1.4")model.format_version="1.3";
  return model;
}
// Uses existing label/input styling, with identical controls in both editors.
export function contentControls(block,{change,canFill,onError=()=>{}}) {
  const root=document.createElement("div");root.className="content-controls";
  const apply=fn=>{try {const next=structuredClone(block);fn(next);validateContent(next);change(next);} catch(error){onError(error.message);}};
  const field=(label,value,handler,{options,min,max,step=1}={})=>{
    const wrapper=document.createElement("label");wrapper.textContent=label;
    const input=document.createElement(options?"select":"input");
    if(options) for(const [key,text] of Object.entries(options)) {const option=document.createElement("option");option.value=key;option.textContent=text;input.append(option);}
    else {input.type="number";if(min!==undefined)input.min=min;if(max!==undefined)input.max=max;input.step=step;}
    input.value=value;input.addEventListener("change",()=>apply(next=>handler(next,options?input.value:(input.value===""?undefined:Number(input.value)))));
    wrapper.append(input);root.append(wrapper);return input;
  };
  if(block.type==="tracker") {
    field("Appearance",block.appearance,(b,value)=>{b.appearance=value;if(value!=="current_maximum")b.capacity=Math.min(100,b.capacity);if(b.initial_value>b.capacity)delete b.initial_value;},{options:APPEARANCES});
    field("Capacity / maximum",block.capacity,(b,v)=>{b.capacity=v;},{min:1,max:block.appearance==="current_maximum"?1000000:100});
    field("Starting value (optional)",block.initial_value??"",(b,v)=>{if(v===undefined)delete b.initial_value;else b.initial_value=v;},{min:0,max:block.capacity});
  } else {
    field("Pattern",block.pattern,(b,v)=>{b.pattern=v;b.settings=patternDefaults(v);if(b.sizing.mode!=="fill_remaining")b.sizing=["music_staff","tablature"].includes(v)?{mode:"fixed_count",count:4}:{mode:"fixed_height",height_pt:216};},{options:PATTERNS});
    const music=["music_staff","tablature"].includes(block.pattern);
    const options=music?{fixed_count:"Number of staff groups"}:{fixed_height:"Fixed height"};
    if(canFill||block.sizing.mode==="fill_remaining")options.fill_remaining="Fill remaining page";
    field("Size",block.sizing.mode,(b,v)=>{b.sizing=v==="fill_remaining"?{mode:v}:v==="fixed_count"?{mode:v,count:4}:{mode:v,height_pt:216};},{options});
    if(block.sizing.mode==="fixed_count")field("Number of staff groups",block.sizing.count,(b,v)=>{b.sizing.count=v;},{min:1,max:40});
    const units=document.createElement("select");const unitLabel=document.createElement("label");unitLabel.textContent="Spacing units";
    for(const [v,t] of [["mm","Millimeters"],["in","Inches"]]){const o=document.createElement("option");o.value=v;o.textContent=t;units.append(o);}units.value=dimensionUnit;units.addEventListener("change",()=>{dimensionUnit=units.value;});unitLabel.append(units);root.append(unitLabel);
    const dimensions=document.createElement("div");root.append(dimensions);
    const dimension=(label,key,min,max,target="settings")=>{
      const wrap=document.createElement("label");const input=document.createElement("input");input.type="number";input.step="any";
      const refresh=()=>{const factor=units.value==="mm"?25.4/72:1/72;wrap.firstChild.textContent=label+" ("+units.value+")";input.value=block[target][key]===undefined?"":Number((block[target][key]*factor).toFixed(3));input.min=min*factor;input.max=max*factor;};
      wrap.append(document.createTextNode(""),input);dimensions.append(wrap);refresh();units.addEventListener("change",refresh);
      input.addEventListener("change",()=>apply(b=>{if(input.value===""&&key==="margin_guide_pt")delete b[target][key];else b[target][key]=Math.round(Number(input.value)*(units.value==="mm"?72/25.4:72)*4)/4;}));
    };
    if(block.sizing.mode==="fixed_height")dimension("Height","height_pt",18,720,"sizing");
    if(block.pattern==="music_staff")field("Staff grouping",block.settings.staff_style,(b,v)=>{b.settings.staff_style=v;if(v==="paired")b.settings.pair_gap_pt=18;else delete b.settings.pair_gap_pt;},{options:{single:"Single five-line staff",paired:"Paired piano staves"}});
    if(block.pattern==="tablature"){
      field("Strings",block.settings.strings,(b,v)=>{b.settings.strings=v;delete b.settings.string_labels;},{min:4,max:8});
      const label=document.createElement("label");label.textContent="String labels (optional, one per line, top to bottom)";const input=document.createElement("textarea");input.value=(block.settings.string_labels??[]).join("\n");input.rows=4;label.append(input);root.append(label);input.addEventListener("change",()=>apply(b=>{if(input.value) b.settings.string_labels=input.value.split("\n");else delete b.settings.string_labels;}));
    }
    if(BOARD_PATTERNS.includes(block.pattern)){
      field("Boards",block.settings.arrangement,(b,v)=>{b.settings.arrangement=v;},{options:{single:"One board",repeat:"Repeat complete boards"}});
      dimension("Board size (longest side)","board_size_pt",72,504);dimension("Gap between boards","gap_pt",9,72);
      if(block.pattern==="dots_and_boxes"){
        field("Dot rows",block.settings.dot_rows,(b,v)=>{b.settings.dot_rows=v;},{min:3,max:21});
        field("Dot columns",block.settings.dot_columns,(b,v)=>{b.settings.dot_columns=v;},{min:3,max:21});
        const note=document.createElement("p");note.textContent="Counts are dots: 6 × 6 dots create 5 × 5 playable boxes.";root.append(note);
      }
    }
    else if(music){dimension("Line spacing","line_spacing_pt",block.pattern==="music_staff"?3:4,block.pattern==="music_staff"?9:12);dimension("Space between groups","group_gap_pt",12,72);if(block.settings.staff_style==="paired")dimension("Space between paired staves","pair_gap_pt",9,36);}
    else {dimension(block.pattern==="hex_grid"?"Hexagon side length":"Spacing",block.pattern==="hex_grid"?"side_pt":"spacing_pt",block.pattern==="ruled"?9:7,36);if(block.pattern==="ruled")dimension("Margin guide (optional)","margin_guide_pt",18,90);}
    if(block.pattern==="coordinate_grid"){
      field("Origin",block.settings.origin,(b,v)=>{b.settings.origin=v;},{options:{center:"Centered (four quadrants)",bottom_left:"Bottom-left (positive quadrant)"}});
      field("Numbered axes",String(block.settings.numbered),(b,v)=>{b.settings.numbered=v==="true";},{options:{true:"Yes",false:"No"}});
      field("Value per grid step",block.settings.units_per_step,(b,v)=>{b.settings.units_per_step=v;},{min:.25,max:1000,step:.25});
      field("Label every N grid steps",block.settings.label_every,(b,v)=>{b.settings.label_every=v;},{min:1,max:10});
      for(const key of ["x_label","y_label"]){const label=document.createElement("label");label.textContent=key==="x_label"?"X axis label":"Y axis label";const input=document.createElement("input");input.type="text";input.maxLength=16;input.value=block.settings[key];input.addEventListener("change",()=>apply(b=>{b.settings[key]=input.value;}));label.append(input);root.append(label);}
    }
  }
  const help=document.createElement("p");help.className="designer-field-help";help.textContent=block.type==="tracker"?"Printable spaces stay blank. A starting value is guidance; LiveSheet values are separate temporary data.":"One section generates the whole pattern. Fill requires the final full-width section. Print at actual size (100%) to preserve spacing.";root.append(help);
  return root;
}
