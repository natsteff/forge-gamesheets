import {validateContent,BOARD_PATTERNS} from "./content.mjs";
export const CONTENT_COMMAND_LIMIT=20000;
const titleSpace=b=>b.title?27:0;
export function boardDimensions(b){
  const p=b.settings;
  const step=b.pattern==="dots_and_boxes"?p.board_size_pt/Math.max(p.dot_columns-1,p.dot_rows-1):p.board_size_pt;
  return b.pattern==="dots_and_boxes"?{width:(p.dot_columns-1)*step,height:(p.dot_rows-1)*step}:{width:step,height:step};
}
export function groupHeight(b) {
  const p=b.settings;
  return b.pattern==="tablature"?(p.strings-1)*p.line_spacing_pt:p.staff_style==="paired"?8*p.line_spacing_pt+p.pair_gap_pt:4*p.line_spacing_pt;
}
export function contentHeight(b,w,available) {
  validateContent(b);
  const title=titleSpace(b);
  if(b.type==="tracker") {
    if(b.appearance==="segmented_bar" && w/b.capacity<6) throw new Error("Tracker segments are too narrow; choose current / maximum or numbered boxes.");
    if(["checkboxes","numbered_boxes"].includes(b.appearance)) {
      const columns=Math.floor((w+4)/22);
      if(columns<1)throw new Error("Tracker boxes do not fit.");
      return title+Math.ceil(b.capacity/columns)*22-4+(b.initial_value!==undefined?16:0);
    }
    return title+22+(b.initial_value!==undefined?16:0);
  }
  const s=b.sizing;
  const body=s.mode==="fill_remaining"?available-title:s.mode==="fixed_height"?s.height_pt:s.count*groupHeight(b)+(s.count-1)*b.settings.group_gap_pt+.5;
  if(BOARD_PATTERNS.includes(b.pattern)){
    const size=boardDimensions(b);
    if(size.width+3>w||size.height+3>body)throw new Error("Not enough room for one complete board. Reduce board size or increase section height.");
    return title+body;
  }
  if(b.pattern==="coordinate_grid"){
    if(w<72||body<72)throw new Error("Coordinate grid needs at least 72 points in width and height.");
    return title+body;
  }
  const min=["music_staff","tablature"].includes(b.pattern)?groupHeight(b)+.5:b.pattern==="hex_grid"?Math.sqrt(3)*b.settings.side_pt+.5:b.settings.spacing_pt+.5;
  if(body<min)throw new Error("Not enough room for one complete pattern group.");
  return title+body;
}
export function drawContent(b,x,y,w,h,{line,text,circle,widthOf}) {
  const top=y+titleSpace(b);
  const outline=(left,t,width,height)=>{line(left,t,left+width,t);line(left+width,t,left+width,t+height);line(left+width,t+height,left,t+height);line(left,t+height,left,t);};
  if(b.type==="tracker") {
    if(["checkboxes","numbered_boxes"].includes(b.appearance)) {
      const columns=Math.floor((w+4)/22);
      for(let i=0;i<b.capacity;i++){const left=x+i%columns*22,t=top+Math.floor(i/columns)*22;outline(left+.25,t+.25,17.5,17.5);if(b.appearance==="numbered_boxes")text(i+1,left+9,t+12,"sans",8,"#242424","middle");}
    } else if(b.appearance==="segmented_bar"){
      outline(x+.25,top+.25,w-.5,17.5);for(let i=1;i<b.capacity;i++)line(x+w*i/b.capacity,top,x+w*i/b.capacity,top+18);
    } else {line(x,top+18,x+54,top+18);text("/ "+b.capacity,x+60,top+15,"sans",12);}
    if(b.initial_value!==undefined)text("Start: "+b.initial_value,x,y+h-2,"sans",8.5);
    return;
  }
  const p=b.settings,body=h-titleSpace(b),color="#808080";
  // Inset strokes so marks never extend outside their allocated rectangle.
  const mark=(a,c,d,e)=>line(a,c,d,e,color,.5);
  if(BOARD_PATTERNS.includes(b.pattern)){
    const size=boardDimensions(b),gap=p.gap_pt;
    const columns=p.arrangement==="single"?1:Math.floor((w-3+gap)/(size.width+gap));
    const rows=p.arrangement==="single"?1:Math.floor((body-3+gap)/(size.height+gap));
    const left=x+(w-(columns*size.width+(columns-1)*gap))/2;
    for(let row=0;row<rows;row++)for(let col=0;col<columns;col++){
      const bx=left+col*(size.width+gap),by=top+1.5+row*(size.height+gap);
      if(b.pattern==="dots_and_boxes"){
        const step=p.board_size_pt/Math.max(p.dot_columns-1,p.dot_rows-1);
        for(let r=0;r<p.dot_rows;r++)for(let c=0;c<p.dot_columns;c++)circle(bx+c*step,by+r*step,1.5,"#242424");
      }else if(b.pattern==="tic_tac_toe"){
        for(let i=1;i<3;i++){line(bx+size.width*i/3,by,bx+size.width*i/3,by+size.height,"#242424",1);line(bx,by+size.height*i/3,bx+size.width,by+size.height*i/3,"#242424",1);}
      }else{
        for(let i=0;i<=9;i++){const weight=i%3===0?1.5:.5;line(bx+size.width*i/9,by,bx+size.width*i/9,by+size.height,"#242424",weight);line(bx,by+size.height*i/9,bx+size.width,by+size.height*i/9,"#242424",weight);}
      }
    }
  }else if(b.pattern==="coordinate_grid"){
    const rightText=(value,right,baseline,size)=>text(value,right-widthOf(value,"sans",size),baseline,"sans",size);
    const s=p.spacing_pt;
    const bound=Math.ceil(Math.max(w,body)/s)*p.units_per_step;
    const labelWidth=p.numbered?Math.max(widthOf(String(bound),"sans",7),widthOf(String(-bound),"sans",7)):0;
    // Keep ordinary page margins; only reserve space needed by axis labels.
    const inset=Math.max(12,p.origin==="bottom_left"?labelWidth+4:labelWidth/2+2);
    if(w<2*inset+s||body<2*inset+s)throw new Error("Coordinate grid needs more room for its axes and labels.");
    const ox=p.origin==="center"?x+w/2:x+inset;
    const oy=p.origin==="center"?top+body/2:top+body-inset;
    const nx0=Math.ceil((x+inset-ox)/s),nx1=Math.floor((x+w-inset-ox)/s);
    const ny0=Math.ceil((oy-(top+body-inset))/s),ny1=Math.floor((oy-(top+inset))/s);
    const l=ox+nx0*s,r=ox+nx1*s,t=oy-ny1*s,bottom=oy-ny0*s;
    for(let i=nx0;i<=nx1;i++)mark(ox+i*s,t,ox+i*s,bottom);
    for(let i=ny0;i<=ny1;i++)mark(l,oy-i*s,r,oy-i*s);
    line(l,oy,r,oy,"#242424",1);line(ox,t,ox,bottom,"#242424",1);
    // Arrowheads and axis titles remain inside the reserved edge gutter.
    line(r,oy,r-4,oy-2,"#242424",1);line(r,oy,r-4,oy+2,"#242424",1);
    line(ox,t,ox-2,t+4,"#242424",1);line(ox,t,ox+2,t+4,"#242424",1);
    if(Math.max(widthOf(p.x_label,"sans",8),widthOf(p.y_label,"sans",8))>w-4)throw new Error("Axis label is too wide for this section.");
    rightText(p.x_label,r,oy-6,8);
    text(p.y_label,x+Math.max(2,Math.min(w-widthOf(p.y_label,"sans",8)-2,ox-x+5)),t+8,"sans",8);
    if(p.numbered){
      const label=n=>String(n*p.units_per_step);
      const maxWidth=Math.max(...[nx0,nx1,ny0,ny1].map(n=>widthOf(label(n),"sans",7)));
      const every=Math.max(p.label_every,Math.ceil((maxWidth+4)/s));
      rightText("0",ox-3,oy+10,7);
      for(let i=nx0;i<=nx1;i++)if(i&&i%every===0)text(label(i),ox+i*s,oy+10,"sans",7,"#242424","middle");
      for(let i=ny0;i<=ny1;i++)if(i&&i%every===0)rightText(label(i),ox-4,oy-i*s+2,7);
    }
  }else if(["music_staff","tablature"].includes(b.pattern)){
    const gh=groupHeight(b),step=gh+p.group_gap_pt;
    const count=b.sizing.mode==="fixed_count"?b.sizing.count:Math.floor((body-.5+p.group_gap_pt)/step);
    const gutter=p.string_labels?Math.max(...p.string_labels.map(v=>widthOf(v,"sans",8)))+8:0;
    if(w-gutter<36)throw new Error("Tablature labels leave too little writing space.");
    for(let i=0;i<count;i++){
      const base=top+.25+i*step;
      const staves=b.pattern==="music_staff"&&p.staff_style==="paired"?2:1;
      const lines=b.pattern==="tablature"?p.strings:5;
      for(let s=0;s<staves;s++)for(let j=0;j<lines;j++){
        const at=base+s*(4*p.line_spacing_pt+(p.pair_gap_pt??0))+j*p.line_spacing_pt;
        mark(x+gutter,at,x+w,at);if(p.string_labels)text(p.string_labels[j],x,at+2.5,"sans",8);
      }
    }
  }else if(b.pattern==="hex_grid"){
    const side=p.side_pt,vertical=Math.sqrt(3)*side,edges=new Set();
    for(let col=0;.25+side+col*1.5*side+side<=w-.25;col++)for(let row=0;;row++){
      const cx=.25+side+col*1.5*side,cy=.25+vertical/2+row*vertical+(col%2)*vertical/2;
      if(cy+vertical/2>body-.25)break;
      const vertices=Array.from({length:6},(_,i)=>[x+cx+side*Math.cos(i*Math.PI/3),top+cy+side*Math.sin(i*Math.PI/3)]);
      for(let i=0;i<6;i++){const a=vertices[i],c=vertices[(i+1)%6];const key=[a,c].map(v=>v.map(n=>n.toFixed(5)).join(",")).sort().join(";");if(!edges.has(key)){edges.add(key);mark(...a,...c);}}
    }
  }else {
    const spacing=p.spacing_pt;
    if(b.pattern==="dot_grid"){
      for(let at=spacing;at+.75<=body;at+=spacing)for(let left=spacing;left+.75<=w;left+=spacing)circle(x+left,top+at,.75,color);
    }else {
      for(let at=b.pattern==="ruled"?spacing:.25;at<=body-.25;at+=spacing)mark(x,top+at,x+w,top+at);
      if(b.pattern==="square_grid")for(let left=.25;left<=w-.25;left+=spacing)mark(x+left,top,x+left,top+body);
      if(p.margin_guide_pt!==undefined){if(w-p.margin_guide_pt<36)throw new Error("Margin guide leaves too little writing space.");mark(x+p.margin_guide_pt,top,x+p.margin_guide_pt,top+body);}
    }
  }
}
