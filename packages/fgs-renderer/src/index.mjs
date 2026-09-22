import fontkit from "@pdf-lib/fontkit";
import { PDFDocument, rgb } from "pdf-lib";

// FGS Page Rendering Profile 1.0. All geometry is in PDF points (1/72 inch).
export const PROFILE = Object.freeze({
  id: "fgs-page-1.0",
  pages: { letter: [612, 792], a4: [595.28, 841.89] },
  margin: 36, columnGap: 16, rowGap: 14,
  titleSize: 20, sectionSize: 11, bodySize: 8.5,
  tableTitleHeight: 22, tableRowHeight: 19,
  tableLabelFraction: .26, tableLabelMinimum: 68,
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

  function layout(document) {
    if (!document || document.format !== "forge-gamesheets" || document.format_version !== "1.0") throw new Error("Expected validated FGS 1.0");
    const page = PROFILE.pages[document.page.size];
    if (!page) throw new Error("Unsupported page size");
    const [width, height] = document.page.orientation === "landscape" ? [page[1], page[0]] : page;
    const commands = [];
    const accent = document.theme.accent;
    parseColor(accent);
    const accentText = headingAccent(accent);
    const line = (x1, y1, x2, y2, color = GRID, thickness = PROFILE.tableLine) => commands.push({type:"line",x1,y1,x2,y2,color,thickness});
    const rect = (x, y, w, h, color) => commands.push({type:"rect",x,y,w,h,color});
    const text = (value, x, y, font = "sans", size = PROFILE.bodySize, color = BLACK, anchor = "start") => {
      const content=String(value);
      for(const character of content) if(!parsed[font].hasGlyphForCodePoint(character.codePointAt(0))) throw new Error(`FGS page rendering profile ${PROFILE.id} cannot render U+${character.codePointAt(0).toString(16).toUpperCase()}; a fallback font is required.`);
      commands.push({type:"text",value:content,x,y,font,size,color,anchor});
    };
    const cellText = (value, left, top, cellWidth, cellHeight, options = {}) => {
      const {font="sans",size=PROFILE.bodySize,center=false,marker=false} = options;
      const lines = wrap(value, cellWidth - 10, font, size);
      const lineHeight = size + 1.5;
      const reserved = marker ? 7 : 0;
      const base = top + Math.max(size + 2, (cellHeight - lines.length * lineHeight - reserved) / 2 + size);
      for (const [index, part] of lines.entries()) text(part, center ? left + cellWidth / 2 : left + 5, base + index * lineHeight, font, size, BLACK, center ? "middle" : "start");
      if (marker) text("CALCULATED", left + 5, top + cellHeight - 3, "bold", 5, MUTED);
    };
    const scoreGeometry = (block, width) => {
      const labels = labelsFor(block);
      const labelWidth = Math.max(PROFILE.tableLabelMinimum, width * (width < 350 && block.players.length <= 2 ? .5 : PROFILE.tableLabelFraction));
      const columnWidth = (width - labelWidth) / block.players.length;
      const playerLines = block.players.map((name, index) => wrap(name || `Player ${index + 1}`, columnWidth - 8, "bold", 8));
      const headerHeight = Math.max(PROFILE.tableRowHeight, ...playerLines.map((lines) => lines.length * 9.5 + 8));
      const labelLines = labels.map((label) => wrap(label, labelWidth - 10, "bold", PROFILE.bodySize));
      const rowHeights = labelLines.map((lines, index) => Math.max(PROFILE.tableRowHeight, lines.length * 10 + 6 + (calculated(labels[index]) ? 7 : 0)));
      return {labels,labelWidth,columnWidth,headerHeight,rowHeights,height:PROFILE.tableTitleHeight + headerHeight + rowHeights.reduce((a,b)=>a+b,0)};
    };
    const measure = (block, blockWidth) => {
      if (block.type === "header") return block.subtitle ? 54 : 40;
      if (block.type === "score_table") return scoreGeometry(block, blockWidth).height;
      if (block.type === "notes") return 27 + block.lines * 24;
      if (block.type === "reference" || block.type === "checklist") {
        const textWidth = blockWidth - 36;
        return 27 + block.items.reduce((sum,item) => sum + Math.max(1, wrap(item,textWidth,"sans",9.5).length) * 13 + 3, 0);
      }
      throw new Error(`Unsupported FGS block: ${block.type}`);
    };
    const drawBlock = (block, x, y, blockWidth) => {
      if (block.type === "header") {
        if (widthOf(block.title,"serif",PROFILE.titleSize)>blockWidth-10) throw new Error(`Page heading "${block.title}" is too wide for this layout.`);
        if (block.subtitle && widthOf(block.subtitle,"sans",10)>blockWidth-10) throw new Error(`Subtitle in "${block.title}" is too wide for this layout.`);
        text(block.title,x+blockWidth/2,y+25,"serif",PROFILE.titleSize,accentText,"middle");
        if (block.subtitle) text(block.subtitle,x+blockWidth/2,y+43,"sans",10,MUTED,"middle");
        return;
      }
      if (widthOf(block.title,"serif",PROFILE.sectionSize)>blockWidth) throw new Error(`Section heading "${block.title}" is too wide for this layout.`);
      text(block.title,x,y+14,"serif",PROFILE.sectionSize,accentText);
      line(x,y+21,x+blockWidth,y+21,accent,PROFILE.accentLine);
      if (block.type === "score_table") {
        const geometry = scoreGeometry(block,blockWidth);
        const top = y + PROFILE.tableTitleHeight;
        const boundaries = [top,top+geometry.headerHeight];
        geometry.rowHeights.forEach((h)=>boundaries.push(boundaries.at(-1)+h));
        geometry.labels.forEach((label,index)=>{if(calculated(label)) rect(x,boundaries[index+1],blockWidth,geometry.rowHeights[index],FILL);});
        boundaries.forEach((at)=>line(x,at,x+blockWidth,at));
        for(let index=0;index<=block.players.length+1;index++) {
          const at=index===0?x:index===1?x+geometry.labelWidth:x+geometry.labelWidth+(index-1)*geometry.columnWidth;
          line(at,top,at,boundaries.at(-1));
        }
        cellText("Category",x,top,geometry.labelWidth,geometry.headerHeight,{font:"bold"});
        block.players.forEach((name,index)=>cellText(name||`Player ${index+1}`,x+geometry.labelWidth+index*geometry.columnWidth,top,geometry.columnWidth,geometry.headerHeight,{font:"bold",size:8,center:true}));
        geometry.labels.forEach((label,index)=>cellText(label,x,boundaries[index+1],geometry.labelWidth,geometry.rowHeights[index],{font:"bold",marker:calculated(label)}));
        return;
      }
      if (block.type === "notes") { for(let index=0;index<block.lines;index++) line(x,y+29+index*24,x+blockWidth,y+29+index*24,MUTED); return; }
      let cursor=y+40;
      for(const item of block.items) {
        if(block.type==="checklist") {line(x+3,cursor-9,x+12,cursor-9);line(x+12,cursor-9,x+12,cursor);line(x+12,cursor,x+3,cursor);line(x+3,cursor,x+3,cursor-9);}
        else text("•",x+5,cursor,"sans",10);
        const lines=wrap(item,blockWidth-36,"sans",9.5);
        lines.forEach((part,index)=>text(part,x+22,cursor+index*13,"sans",9.5));
        cursor+=Math.max(17,lines.length*13+3);
      }
    };
    let cursor = PROFILE.margin;
    const blockBounds=[];
    for(const row of document.rows) {
      const columns=row.blocks.length;
      if(columns!==1&&columns!==2) throw new Error("FGS rows must have one or two blocks");
      const blockWidth=(width-2*PROFILE.margin-(columns===2?PROFILE.columnGap:0))/columns;
      const blockHeight=Math.max(...row.blocks.map((block)=>measure(block,blockWidth)));
      if(cursor+blockHeight>height-PROFILE.margin+0.001) return {profile:PROFILE.id,width,height,fits:false,overflow:row.blocks[0].title,commands,blockBounds};
      row.blocks.forEach((block,index)=>{
        const x=PROFILE.margin+index*(blockWidth+PROFILE.columnGap);
        blockBounds.push({id:block.id,x,y:cursor,width:blockWidth,height:blockHeight});
        drawBlock(block,x,cursor,blockWidth);
      });
      cursor+=blockHeight+PROFILE.rowGap;
    }
    return {profile:PROFILE.id,width,height,fits:true,commands,blockBounds};
  }

  function toSvg(result) {
    const parts=[`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${result.width} ${result.height}" role="img" aria-label="GameSheet page" class="fgs-page-render"><rect width="100%" height="100%" fill="#ffffff"/>`];
    for(const command of result.commands) {
      if(command.type==="rect") parts.push(`<rect x="${numbers(command.x)}" y="${numbers(command.y)}" width="${numbers(command.w)}" height="${numbers(command.h)}" fill="${command.color}"/>`);
      else if(command.type==="line") parts.push(`<path d="M${numbers(command.x1)} ${numbers(command.y1)}L${numbers(command.x2)} ${numbers(command.y2)}" stroke="${command.color}" stroke-width="${command.thickness}" fill="none"/>`);
      else parts.push(`<text x="${numbers(command.x)}" y="${numbers(command.y)}" text-anchor="${command.anchor}" fill="${command.color}" font-family="FGS ${command.font}" font-size="${command.size}">${escapeXml(command.value)}</text>`);
    }
    parts.push("</svg>");
    return parts.join("");
  }

  async function toPdf(result, title="GameSheet") {
    if(!result.fits) throw new Error(`Section "${result.overflow}" does not fit on one page.`);
    const pdf=await PDFDocument.create();
    pdf.registerFontkit(fontkit);
    const fonts={};
    for(const key of ["sans","bold","serif"]) fonts[key]=await pdf.embedFont(bytes[key],{subset:true});
    const page=pdf.addPage([result.width,result.height]);
    for(const command of result.commands) {
      if(command.type==="rect") page.drawRectangle({x:command.x,y:result.height-command.y-command.h,width:command.w,height:command.h,color:parseColor(command.color)});
      else if(command.type==="line") page.drawLine({start:{x:command.x1,y:result.height-command.y1},end:{x:command.x2,y:result.height-command.y2},thickness:command.thickness,color:parseColor(command.color)});
      else {
        const font=fonts[command.font];
        const textWidth=widthOf(command.value,command.font,command.size);
        const x=command.anchor==="middle"?command.x-textWidth/2:command.x;
        page.drawText(command.value,{x,y:result.height-command.y,size:command.size,font,color:parseColor(command.color)});
      }
    }
    pdf.setTitle(title);pdf.setCreator("FGS Renderer " + PROFILE.id);pdf.setProducer("FGS Renderer");
    pdf.setCreationDate(new Date("2000-01-01T00:00:00Z"));pdf.setModificationDate(new Date("2000-01-01T00:00:00Z"));
    return pdf.save({useObjectStreams:false});
  }
  return {layout,toSvg,toPdf,widthOf};
}
