import fontkit from "@pdf-lib/fontkit";
import { PDFDocument, rgb } from "pdf-lib";
import {validateFill} from "./content.mjs";
import {contentHeight,drawContent,CONTENT_COMMAND_LIMIT} from "./layout-content.mjs";
import {finishedSize,printSheetPlan,PAPER_SIZES} from "./print-sizes.mjs";

// FGS Page Rendering Profile 1.3.1. All geometry is in PDF points (1/72 inch).
export const PROFILE = Object.freeze({
  id: "fgs-page-1.3.1",
  pages: PAPER_SIZES,
  margin: 36, columnGap: 16, rowGap: 14,
  footerReserve: 22, footerSize: 8, footerLineHeight: 11,
  logoWidth: 48, logoHeight: 32, logoGap: 8,
  titleSize: 20, sectionSize: 11, bodySize: 8.5,
  tableTitleHeight: 22, tableRowHeight: 19,
  tableColumnMinimum: 28, tableHeadingMaximumFraction: .4,
  tableLine: .5, accentLine: 1.2,
});

const BLACK = "#242424";
const GRID = "#333333";
const FILL = "#f6f5f3";
const MUTED = "#555555";
const calculated = (value) => /^(?:total|grand total)$/i.test(value.trim());
const labelsFor = (block) => block.show_total ? [...block.score_rows, block.total_label] : block.score_rows;
const escapeXml = (value) => String(value).replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&apos;"})[ch]);
const numbers = (value) => Number(value.toFixed(3));

function parseColor(color) {
  if (!/^#[0-9a-f]{6}$/.test(color)) throw new Error("Invalid FGS accent color");
  return rgb(parseInt(color.slice(1, 3), 16) / 255, parseInt(color.slice(3, 5), 16) / 255, parseInt(color.slice(5, 7), 16) / 255);
}

// A light rule color is permitted, but headings must remain legible on white.
function headingAccent(color) {
  const channels = [1, 3, 5].map((at) => parseInt(color.slice(at, at + 2), 16));
  const luminance = (scale) => {
    const linear = channels.map((channel) => {
      const value = Math.round(channel * scale / 255) / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  };
  if (luminance(255) <= 0.1833) return color;
  let low = 0, high = 255;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (luminance(mid) <= 0.1833) low = mid;
    else high = mid - 1;
  }
  return `#${channels.map((channel) => Math.round(channel * low / 255).toString(16).padStart(2, "0")).join("")}`;
}

function normalizeFontData(fontData) {
  for (const key of ["sans", "bold", "serif"]) {
    if (!(fontData?.[key] instanceof Uint8Array) || fontData[key].length === 0) throw new Error(`Missing ${key} font`);
  }
  return fontData;
}

// The same font files and metric function drive line breaks in SVG and PDF.
export function createPrintEngine(fontData) {
  const bytes = normalizeFontData(fontData);
  const parsed = Object.fromEntries(["sans","bold","serif"].map((key) => [key, fontkit.create(bytes[key])]));
  const widthOf = (value, font, size) => parsed[font].layout(String(value)).advanceWidth * size / parsed[font].unitsPerEm;

  function wrap(value, maxWidth, font, size) {
    const output = [];
    for (const paragraph of String(value).split("\n")) {
      let line = "";
      for (const word of paragraph.split(/\s+/u)) {
        if (!word) continue;
        const pieces=[];
        let piece="";
        const graphemes=Array.from(new Intl.Segmenter("und",{granularity:"grapheme"}).segment(word),item=>item.segment);
        for(const grapheme of graphemes) {
          if(piece && widthOf(piece+grapheme,font,size)>maxWidth) {pieces.push(piece);piece=grapheme;}
          else piece+=grapheme;
        }
        if(piece) pieces.push(piece);
        for(const [index,part] of pieces.entries()) {
          const candidate=line&&index===0?`${line} ${part}`:part;
          if(widthOf(candidate,font,size)<=maxWidth) line=candidate;
          else {if(line) output.push(line);line=part;}
        }
      }
      output.push(line);
    }
    return output;
  }

  function layout(document, printSize={}) {
    if (!document || document.format !== "forge-gamesheets" || !["1.0","1.1","1.2","1.3"].includes(document.format_version)) throw new Error("Expected validated FGS 1.0–1.3");
    validateFill(document);
    const size=finishedSize(document,printSize);
    const compact=size.preset!=="full";
    const profile=size.preset==="full"?PROFILE:{
      ...PROFILE,
      margin:Math.min(size.width,size.height)<300?12:24,
      columnGap:10,rowGap:9,logoWidth:32,logoHeight:24,logoGap:5,
      titleSize:14,sectionSize:10,tableTitleHeight:20,
      footerReserve:18,footerSize:7,footerLineHeight:9,
    };
    // A compact design is composed on a canvas tall enough to hold all content.
    // Only after composition do we uniformly fit it to the finished item. The
    // Full Page path continues to use its exact historical page dimensions.
    let minimumContentWidth=size.width-2*profile.margin;
    if(compact)for(const row of document.rows){
      let rowMinimum=row.blocks.length===2?220+profile.columnGap:0;
      for(const block of row.blocks)if(block.type==="score_table"){
        const tableMinimum=54+block.players.length*28;
        rowMinimum=Math.max(rowMinimum,row.blocks.length===2?2*tableMinimum+profile.columnGap:tableMinimum);
      }
      minimumContentWidth=Math.max(minimumContentWidth,rowMinimum);
    }
    const width=compact?Math.max(size.width,minimumContentWidth+2*profile.margin):size.width;
    const height=compact?20000:size.height;
    if (document.footer && document.format_version === "1.0") throw new Error("An author footer requires FGS 1.1 or later");
    const footerLineCount=document.footer?document.footer.split("\n").length:0;
    const footerReserve=compact?profile.footerReserve:profile.footerReserve+Math.max(0,footerLineCount-1)*profile.footerLineHeight;
    const commands = [];
    const editTargets=[];
    const editTarget=(blockId,field,x,y,w,h,lineIndex)=>editTargets.push({blockId,field,x,y,width:w,height:h,...(lineIndex===undefined?{}:{lineIndex})});
    const push=command=>{if(commands.length>=CONTENT_COMMAND_LIMIT)throw new Error("Page exceeds the 20,000 drawing operation limit.");commands.push(command);};
    const accent = document.theme.accent;
    parseColor(accent);
    const accentText = headingAccent(accent);
    const line = (x1, y1, x2, y2, color = GRID, thickness = profile.tableLine) => push({type:"line",x1,y1,x2,y2,color,thickness});
    const rect = (x, y, w, h, color) => push({type:"rect",x,y,w,h,color});
    const circle=(x,y,r,color)=>push({type:"circle",x,y,r,color});
    const text = (value, x, y, font = "sans", size = profile.bodySize, color = BLACK, anchor = "start") => {
      const content=String(value);
      for(const character of content) if(!parsed[font].hasGlyphForCodePoint(character.codePointAt(0))) throw new Error(`FGS page rendering profile ${profile.id} cannot render U+${character.codePointAt(0).toString(16).toUpperCase()}; a fallback font is required.`);
      push({type:"text",value:content,x,y,font,size,color,anchor});
    };
    const cellText = (value, left, top, cellWidth, cellHeight, options = {}) => {
      const {font="sans",size=profile.bodySize,center=false,marker=false} = options;
      const lines = wrap(value, cellWidth - 10, font, size);
      const lineHeight = size + 1.5;
      const reserved = marker ? 7 : 0;
      const base = top + Math.max(size + 2, (cellHeight - lines.length * lineHeight - reserved) / 2 + size);
      for (const [index, part] of lines.entries()) text(part, center ? left + cellWidth / 2 : left + 5, base + index * lineHeight, font, size, BLACK, center ? "middle" : "start");
      if (marker) text("CALCULATED", left + 5, top + cellHeight - 3, "bold", 5, MUTED);
    };
    const scoreGeometry = (block, width) => {
      const labels = labelsFor(block);
      const labelText = [block.first_column_heading ?? "Category", ...labels];
      const preferred=[
        Math.max(...labelText.map(value=>widthOf(value,"bold",profile.bodySize)))+10,
        ...block.players.map((name,index)=>widthOf(name||`Player ${index+1}`,"bold",8)+10),
      ].map(value=>Math.min(width*profile.tableHeadingMaximumFraction,value));
      const minimum=Math.min(profile.tableColumnMinimum,width/preferred.length);
      const widths=Array(preferred.length).fill(0);
      let remaining=width;
      let open=preferred.map((_,index)=>index);
      while(open.length){
        const total=open.reduce((sum,index)=>sum+preferred[index],0);
        const narrow=open.filter(index=>remaining*preferred[index]/total<minimum);
        if(!narrow.length){for(const index of open)widths[index]=remaining*preferred[index]/total;break;}
        for(const index of narrow){widths[index]=minimum;remaining-=minimum;}
        open=open.filter(index=>!narrow.includes(index));
      }
      const [labelWidth,...columnWidths]=widths;
      const playerLines = block.players.map((name, index) => wrap(name || `Player ${index + 1}`, columnWidths[index] - 8, "bold", 8));
      const firstHeadingLines = wrap(block.first_column_heading ?? "Category", labelWidth - 10, "bold", profile.bodySize);
      const headerHeight = Math.max(profile.tableRowHeight, firstHeadingLines.length * 10 + 6, ...playerLines.map((lines) => lines.length * 9.5 + 8));
      const labelLines = labels.map((label) => wrap(label, labelWidth - 10, "bold", profile.bodySize));
      const rowHeights = labelLines.map((lines, index) => Math.max(profile.tableRowHeight, lines.length * 10 + 6 + (calculated(labels[index]) ? 7 : 0)));
      return {labels,labelWidth,columnWidths,headerHeight,rowHeights,height:profile.tableTitleHeight + headerHeight + rowHeights.reduce((a,b)=>a+b,0)};
    };
    const headerLines=(block,blockWidth)=>{
      const titleWidth=block.logo?blockWidth-2*(profile.logoWidth+profile.logoGap):blockWidth-10;
      const lines=compact?wrap(block.title,titleWidth,"serif",profile.titleSize):[block.title];
      if(lines.some(value=>widthOf(value,"serif",profile.titleSize)>titleWidth))
        throw new Error(size.preset==="full"
          ? `Page heading "${block.title}" is too wide for this layout.`
          : `Page heading "${block.title}" cannot be wrapped for this print size.`);
      if(!compact&&block.subtitle&&widthOf(block.subtitle,"sans",10)>titleWidth)
        throw new Error(`Subtitle in "${block.title}" is too wide for this layout.`);
      return lines;
    };
    const subtitleLines=(block,blockWidth)=>{
      if(!block.subtitle)return [];
      if(!compact)return [block.subtitle];
      const titleWidth=block.logo?blockWidth-2*(profile.logoWidth+profile.logoGap):blockWidth-10;
      return wrap(block.subtitle,titleWidth,"sans",10);
    };
    const sectionLines=(block,blockWidth)=>{
      if(!compact){
        if(widthOf(block.title,"serif",profile.sectionSize)>blockWidth)throw new Error(`Section heading "${block.title}" is too wide for this layout.`);
        return [block.title];
      }
      return wrap(block.title,blockWidth,"serif",profile.sectionSize);
    };
    const measure = (block, blockWidth, available) => {
      const headingExtra=compact&&block.type!=="header"?(sectionLines(block,blockWidth).length-1)*13:0;
      const patternAvailable=compact?Math.max(0,size.height-2*profile.margin-(document.footer?footerReserve:0)):available;
      if (["tracker","paper_pattern"].includes(block.type)) return headingExtra+contentHeight(block,blockWidth,patternAvailable);
      if (block.type === "header") return 40+(headerLines(block,blockWidth).length-1)*16+(subtitleLines(block,blockWidth).length?14+(subtitleLines(block,blockWidth).length-1)*12:0);
      if (block.type === "score_table") return headingExtra+scoreGeometry(block, blockWidth).height;
      if (block.type === "notes") return headingExtra+27 + block.lines * 24;
      if (block.type === "reference" || block.type === "checklist") {
        const textWidth = blockWidth - 36;
        if(compact)return headingExtra+40+block.items.reduce((sum,item)=>sum+Math.max(17,Math.max(1,wrap(item,textWidth,"sans",9.5).length)*13+3),0);
        return 27 + block.items.reduce((sum,item) => sum + Math.max(1, wrap(item,textWidth,"sans",9.5).length) * 13 + 3, 0);
      }
      throw new Error(`Unsupported FGS block: ${block.type}`);
    };
    const drawBlock = (block, x, y, blockWidth) => {
      if (block.type === "header") {
        if (block.logo && document.format_version === "1.0") throw new Error("A header logo requires FGS 1.1 or later");
        const titleLines=headerLines(block,blockWidth);
        if (block.logo) {
          const image = atob(block.logo.data);
          const dimension = (at) => (((image.charCodeAt(at)*256+image.charCodeAt(at+1))*256+image.charCodeAt(at+2))*256+image.charCodeAt(at+3));
          const ratio = Math.min(profile.logoWidth/dimension(16),profile.logoHeight/dimension(20));
          const w=dimension(16)*ratio,h=dimension(20)*ratio;
          commands.push({type:"image",data:block.logo.data,alt:block.logo.alt,decorative:block.logo.decorative,x:x+(profile.logoWidth-w)/2,y:y+(profile.logoHeight-h)/2,w,h});
        }
        const titleCenter=x+blockWidth/2;
        titleLines.forEach((value,index)=>text(value,titleCenter,y+25+index*16,"serif",profile.titleSize,accentText,"middle"));
        editTarget(block.id,"title",x,y+4,blockWidth,30+(titleLines.length-1)*16);
        subtitleLines(block,blockWidth).forEach((value,index)=>text(value,titleCenter,y+43+(titleLines.length-1)*16+index*12,"sans",10,MUTED,"middle"));
        if(block.subtitle)editTarget(block.id,"subtitle",x,y+32+(titleLines.length-1)*16,blockWidth,16+(subtitleLines(block,blockWidth).length-1)*12);
        return;
      }
      const heading=sectionLines(block,blockWidth);
      const headingExtra=compact?(heading.length-1)*13:0;
      const contentY=y+headingExtra;
      if(block.title)editTarget(block.id,"title",x,y,blockWidth,contentY+21-y);
      if (["tracker","paper_pattern"].includes(block.type)) {
        if(block.title)heading.forEach((value,index)=>text(value,x,y+14+index*13,"serif",profile.sectionSize,accentText));
        const patternAvailable=compact?Math.max(0,size.height-2*profile.margin-(document.footer?footerReserve:0)):height-profile.margin-(document.footer?footerReserve:0)-y;
        drawContent(block,x,contentY,blockWidth,contentHeight(block,blockWidth,patternAvailable),{line,text,circle,widthOf});
        return;
      }
      heading.forEach((value,index)=>text(value,x,y+14+index*13,"serif",profile.sectionSize,accentText));
      line(x,contentY+21,x+blockWidth,contentY+21,accent,profile.accentLine);
      if (block.type === "score_table") {
        const geometry = scoreGeometry(block,blockWidth);
        const top = contentY + profile.tableTitleHeight;
        const boundaries = [top,top+geometry.headerHeight];
        geometry.rowHeights.forEach((h)=>boundaries.push(boundaries.at(-1)+h));
        geometry.labels.forEach((label,index)=>{if(calculated(label)) rect(x,boundaries[index+1],blockWidth,geometry.rowHeights[index],FILL);});
        boundaries.forEach((at)=>line(x,at,x+blockWidth,at));
        let columnEdge=x;
        line(columnEdge,top,columnEdge,boundaries.at(-1));
        columnEdge+=geometry.labelWidth;
        line(columnEdge,top,columnEdge,boundaries.at(-1));
        for(const columnWidth of geometry.columnWidths){columnEdge+=columnWidth;line(columnEdge,top,columnEdge,boundaries.at(-1));}
        cellText(block.first_column_heading ?? "Category",x,top,geometry.labelWidth,geometry.headerHeight,{font:"bold"});
        editTarget(block.id,"first_column_heading",x,top,geometry.labelWidth,geometry.headerHeight);
        let playerX=x+geometry.labelWidth;
        block.players.forEach((name,index)=>{
          cellText(name||`Player ${index+1}`,playerX,top,geometry.columnWidths[index],geometry.headerHeight,{font:"bold",size:8,center:true});
          editTarget(block.id,"players",playerX,top,geometry.columnWidths[index],geometry.headerHeight,index);
          playerX+=geometry.columnWidths[index];
        });
        geometry.labels.forEach((label,index)=>{
          cellText(label,x,boundaries[index+1],geometry.labelWidth,geometry.rowHeights[index],{font:"bold",marker:calculated(label)});
          editTarget(block.id,"score_rows",x,boundaries[index+1],geometry.labelWidth,geometry.rowHeights[index],index);
        });
        return;
      }
      if (block.type === "notes") { for(let index=0;index<block.lines;index++) line(x,contentY+29+index*24,x+blockWidth,contentY+29+index*24,MUTED); editTarget(block.id,"lines",x,contentY+22,blockWidth,block.lines*24); return; }
      let cursor=contentY+40;
      for(const [itemIndex,item] of block.items.entries()) {
        if(block.type==="checklist") {line(x+3,cursor-9,x+12,cursor-9);line(x+12,cursor-9,x+12,cursor);line(x+12,cursor,x+3,cursor);line(x+3,cursor,x+3,cursor-9);}
        else text("•",x+5,cursor,"sans",10);
        const lines=wrap(item,blockWidth-36,"sans",9.5);
        lines.forEach((part,index)=>text(part,x+22,cursor+index*13,"sans",9.5));
        const itemHeight=Math.max(17,lines.length*13+3);
        editTarget(block.id,"items",x,cursor-12,blockWidth,itemHeight,itemIndex);
        cursor+=itemHeight;
      }
    };
    let cursor = profile.margin;
    const blockBounds=[];
    for(const row of document.rows) {
      const commandCount=commands.length,boundCount=blockBounds.length,targetCount=editTargets.length;
      try {
      const columns=row.blocks.length;
      if(columns!==1&&columns!==2) throw new Error("FGS rows must have one or two blocks");
      const blockWidth=(width-2*profile.margin-(columns===2?profile.columnGap:0))/columns;
      const blockHeight=Math.max(...row.blocks.map((block)=>measure(block,blockWidth,height-profile.margin-(document.footer?footerReserve:0)-cursor)));
      if(cursor+blockHeight>height-profile.margin-(document.footer?footerReserve:0)+0.001) return {profile:profile.id,width,height,printPreset:size.preset,fits:false,overflow:row.blocks[0].title,commands,blockBounds};
      row.blocks.forEach((block,index)=>{
        const x=profile.margin+index*(blockWidth+profile.columnGap);
        blockBounds.push({id:block.id,x,y:cursor,width:blockWidth,height:blockHeight});
        drawBlock(block,x,cursor,blockWidth);
      });
      cursor+=blockHeight+profile.rowGap;
      }catch(error){
        if(size.preset==="full")throw error;
        commands.length=commandCount;blockBounds.length=boundCount;editTargets.length=targetCount;
        return {profile:profile.id,width,height,printPreset:size.preset,fits:false,overflow:row.blocks[0].title,reason:error.message,commands,blockBounds};
      }
    }
    const contentBottom=cursor-profile.rowGap;
    const footerLines=document.footer
      ? (compact?document.footer.split("\n").flatMap(value=>wrap(value,width-2*profile.margin,"sans",profile.footerSize)):document.footer.split("\n"))
      : [];
    const naturalHeight=compact
      ? contentBottom+profile.margin+(document.footer?Math.max(profile.footerReserve,footerLines.length*profile.footerLineHeight+7):0)
      : height;
    if (document.footer) {
      for (const [index, value] of footerLines.entries()) {
        if (widthOf(value,"sans",profile.footerSize)>width-2*profile.margin) {
          return {profile:profile.id,width:compact?size.width:width,height:compact?size.height:height,printPreset:size.preset,fits:false,overflow:"Footer",reason:`Footer line ${index+1} is too wide for the selected finished size. Shorten or split the text; it has not been cut off.`,commands,blockBounds};
        }
        const baseline = naturalHeight-profile.margin+(size.preset==="full"?-6:0)+(index-(footerLines.length-1))*profile.footerLineHeight;
        text(value,width/2,baseline,"sans",profile.footerSize,MUTED,"middle");
        editTarget(null,"footer",profile.margin,baseline-profile.footerSize-2,width-2*profile.margin,profile.footerLineHeight,index);
      }
    }
    if(compact){
      const usableWidth=size.width-2*profile.margin;
      const usableHeight=size.height-2*profile.margin;
      const composedWidth=width-2*profile.margin;
      const composedHeight=naturalHeight-2*profile.margin;
      const scale=Math.min(1,usableWidth/composedWidth,usableHeight/composedHeight);
      if(!Number.isFinite(scale)||scale<=0)throw new Error("The compact design cannot be fitted to this size.");
      const tx=x=>size.width/2+(x-width/2)*scale;
      const ty=y=>profile.margin+(y-profile.margin)*scale;
      const fittedCommands=commands.map(command=>{
        const value={...command};
        if(command.type==="line"){
          value.x1=tx(command.x1);value.x2=tx(command.x2);
          value.y1=ty(command.y1);value.y2=ty(command.y2);
          value.thickness=command.thickness*scale;
        }else if(command.type==="circle"){
          value.x=tx(command.x);value.y=ty(command.y);value.r=command.r*scale;
        }else{
          value.x=tx(command.x);value.y=ty(command.y);
          if(command.type==="rect"||command.type==="image"){
            value.w=command.w*scale;value.h=command.h*scale;
          }
          if(command.type==="text")value.size=command.size*scale;
        }
        return value;
      });
      const fittedBounds=blockBounds.map(bound=>({
        ...bound,x:tx(bound.x),y:ty(bound.y),width:bound.width*scale,height:bound.height*scale,
      }));
      const fittedTargets=editTargets.map(target=>({
        ...target,x:tx(target.x),y:ty(target.y),width:target.width*scale,height:target.height*scale,
      }));
      return {profile:profile.id,width:size.width,height:size.height,printPreset:size.preset,
        fits:true,commands:fittedCommands,blockBounds:fittedBounds,editTargets:fittedTargets,fitScale:scale,
        effectiveBodySize:profile.bodySize*scale};
    }
    return {profile:profile.id,width,height,printPreset:size.preset,fits:true,commands,blockBounds,editTargets};
  }

  function toSvg(result) {
    const parts=[`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${result.width} ${result.height}" role="img" aria-label="GameSheet page" class="fgs-page-render"><rect width="100%" height="100%" fill="#ffffff"/>`];
    for(const command of result.commands) {
      if(command.type==="rect") parts.push(`<rect x="${numbers(command.x)}" y="${numbers(command.y)}" width="${numbers(command.w)}" height="${numbers(command.h)}" fill="${command.color}"/>`);
      else if(command.type==="line") parts.push(`<path d="M${numbers(command.x1)} ${numbers(command.y1)}L${numbers(command.x2)} ${numbers(command.y2)}" stroke="${command.color}" stroke-width="${command.thickness}" fill="none"/>`);
      else if(command.type==="circle")parts.push(`<circle cx="${numbers(command.x)}" cy="${numbers(command.y)}" r="${command.r}" fill="${command.color}"/>`);
      else if(command.type==="image") parts.push(`<image x="${numbers(command.x)}" y="${numbers(command.y)}" width="${numbers(command.w)}" height="${numbers(command.h)}" href="data:image/png;base64,${command.data}" ${command.decorative?'aria-hidden="true"':`role="img" aria-label="${escapeXml(command.alt)}"`}/>`);
      else parts.push(`<text x="${numbers(command.x)}" y="${numbers(command.y)}" text-anchor="${command.anchor}" fill="${command.color}" font-family="FGS ${command.font}" font-size="${command.size}">${escapeXml(command.value)}</text>`);
    }
    parts.push("</svg>");
    return parts.join("");
  }

  function toPrintSheetSvg(result,options={},pageIndex=0) {
    const plan=printSheetPlan(result,options);
    if(!Number.isInteger(pageIndex)||pageIndex<0||pageIndex>=plan.pages.length)throw new Error("Choose an existing print-sheet page.");
    const parts=[`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${plan.width} ${plan.height}" role="img" aria-label="Arranged print sheet" class="fgs-print-sheet-render"><rect width="100%" height="100%" fill="#ffffff"/>`];
    const guide=(x1,y1,x2,y2)=>parts.push(`<path d="M${numbers(x1)} ${numbers(y1)}L${numbers(x2)} ${numbers(y2)}" stroke="${MUTED}" stroke-width="0.5" fill="none"/>`);
    for(const placement of plan.pages[pageIndex]){
      parts.push(toSvg(result).replace("<svg ",`<svg x="${numbers(placement.x)}" y="${numbers(placement.y)}" width="${result.width}" height="${result.height}" `));
      if(plan.cutGuides&&!plan.borderless){
        const {x,y}=placement,w=result.width,h=result.height;
        for(const edgeY of [y,y+h]){
          guide(x-8,edgeY,x-2,edgeY);guide(x+w+2,edgeY,x+w+8,edgeY);
        }
        for(const edgeX of [x,x+w]){
          guide(edgeX,y-8,edgeX,y-2);guide(edgeX,y+h+2,edgeX,y+h+8);
        }
      }
    }
    if(plan.cutGuides&&plan.borderless){
      if(Math.abs(plan.width-2*result.width)<.011)guide(result.width,0,result.width,plan.height);
      else guide(0,result.height,plan.width,result.height);
    }
    parts.push("</svg>");
    return parts.join("");
  }

  async function makePdf(result, title, plan) {
    if(!result.fits) throw new Error(`Section "${result.overflow}" does not fit on one page.`);
    const pdf=await PDFDocument.create();
    pdf.registerFontkit(fontkit);
    const fonts={};
    for(const key of ["sans","bold","serif"]) fonts[key]=await pdf.embedFont(bytes[key],{subset:true});
    const images=new Map();
    const pdfLine=(page,x1,y1,x2,y2,thickness=.5)=>page.drawLine({start:{x:x1,y:plan.height-y1},end:{x:x2,y:plan.height-y2},thickness,color:parseColor(MUTED)});
    for(const placements of plan.pages) {
      const page=pdf.addPage([plan.width,plan.height]);
      for(const placement of placements) {
        const ox=placement.x,oy=placement.y;
        for(const command of result.commands) {
          if(command.type==="rect") page.drawRectangle({x:ox+command.x,y:plan.height-oy-command.y-command.h,width:command.w,height:command.h,color:parseColor(command.color)});
          else if(command.type==="line") page.drawLine({start:{x:ox+command.x1,y:plan.height-oy-command.y1},end:{x:ox+command.x2,y:plan.height-oy-command.y2},thickness:command.thickness,color:parseColor(command.color)});
          else if(command.type==="circle")page.drawCircle({x:ox+command.x,y:plan.height-oy-command.y,size:command.r,color:parseColor(command.color)});
          else if(command.type==="image") {
            let logo=images.get(command.data);
            if(!logo){logo=await pdf.embedPng(Uint8Array.from(atob(command.data),ch=>ch.charCodeAt(0)));images.set(command.data,logo);}
            page.drawImage(logo,{x:ox+command.x,y:plan.height-oy-command.y-command.h,width:command.w,height:command.h});
          }
          else {
            const font=fonts[command.font];
            const textWidth=widthOf(command.value,command.font,command.size);
            const x=command.anchor==="middle"?command.x-textWidth/2:command.x;
            page.drawText(command.value,{x:ox+x,y:plan.height-oy-command.y,size:command.size,font,color:parseColor(command.color)});
          }
        }
        if(plan.cutGuides&&!plan.borderless) {
          const x=ox,y=oy,w=result.width,h=result.height;
          for(const edgeY of [y,y+h]) {
            pdfLine(page,x-8,edgeY,x-2,edgeY);
            pdfLine(page,x+w+2,edgeY,x+w+8,edgeY);
          }
          for(const edgeX of [x,x+w]) {
            pdfLine(page,edgeX,y-8,edgeX,y-2);
            pdfLine(page,edgeX,y+h+2,edgeX,y+h+8);
          }
        }
      }
      if(plan.cutGuides&&plan.borderless) {
        if(Math.abs(plan.width-2*result.width)<.011)pdfLine(page,result.width,0,result.width,plan.height);
        else pdfLine(page,0,result.height,plan.width,result.height);
      }
    }
    pdf.setTitle(title);pdf.setCreator("FGS Renderer " + PROFILE.id);pdf.setProducer("FGS Renderer");
    pdf.setCreationDate(new Date("2000-01-01T00:00:00Z"));pdf.setModificationDate(new Date("2000-01-01T00:00:00Z"));
    return pdf.save({useObjectStreams:false});
  }
  function toPdf(result,title="GameSheet") {
    return makePdf(result,title,{width:result.width,height:result.height,pages:[[{x:0,y:0}]],cutGuides:false,borderless:false});
  }
  function toPrintSheetPdf(result,title="GameSheet",options={}) {
    const plan=printSheetPlan(result,options);
    return makePdf(result,title,plan);
  }
  return {layout,toSvg,toPrintSheetSvg,toPdf,toPrintSheetPdf,printSheetPlan,widthOf};
}
