import fontkit from "@pdf-lib/fontkit";
import { PDFDocument, rgb } from "pdf-lib";
import {validateFill} from "./content.mjs";
import {contentHeight,drawContent,CONTENT_COMMAND_LIMIT} from "./layout-content.mjs";
import {finishedSize,printSheetPlan,PAPER_SIZES} from "./print-sizes.mjs";

// FGS Page Rendering Profile 1.3. All geometry is in PDF points (1/72 inch).
export const PROFILE = Object.freeze({
  id: "fgs-page-1.3",
  pages: PAPER_SIZES,
  margin: 36, columnGap: 16, rowGap: 14,
  footerReserve: 22, footerSize: 8, footerLineHeight: 11,
  logoWidth: 48, logoHeight: 32, logoGap: 8,
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

  function layout(document, printSize={}) {
    if (!document || document.format !== "forge-gamesheets" || !["1.0","1.1","1.2","1.3"].includes(document.format_version)) throw new Error("Expected validated FGS 1.0–1.3");
    validateFill(document);
    const size=finishedSize(document,printSize);
    const {width,height}=size;
    const profile=size.preset==="full"?PROFILE:{
      ...PROFILE,
      margin:Math.min(width,height)<300?12:24,
      columnGap:10,rowGap:9,logoWidth:32,logoHeight:24,logoGap:5,
      titleSize:14,sectionSize:10,tableTitleHeight:20,tableLabelMinimum:54,
      footerReserve:18,footerSize:7,footerLineHeight:9,
    };
    if (document.footer && document.format_version === "1.0") throw new Error("An author footer requires FGS 1.1 or later");
    const commands = [];
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
      const labelWidth = Math.max(profile.tableLabelMinimum, width * (width < 350 && block.players.length <= 2 ? .5 : profile.tableLabelFraction));
      const columnWidth = (width - labelWidth) / block.players.length;
      if(size.preset!=="full"&&columnWidth<28)throw new Error("Too many player columns for this finished size; use fewer players or a larger size.");
      const playerLines = block.players.map((name, index) => wrap(name || `Player ${index + 1}`, columnWidth - 8, "bold", 8));
      const firstHeadingLines = wrap(block.first_column_heading ?? "Category", labelWidth - 10, "bold", profile.bodySize);
      const headerHeight = Math.max(profile.tableRowHeight, firstHeadingLines.length * 10 + 6, ...playerLines.map((lines) => lines.length * 9.5 + 8));
      const labelLines = labels.map((label) => wrap(label, labelWidth - 10, "bold", profile.bodySize));
      const rowHeights = labelLines.map((lines, index) => Math.max(profile.tableRowHeight, lines.length * 10 + 6 + (calculated(labels[index]) ? 7 : 0)));
      return {labels,labelWidth,columnWidth,headerHeight,rowHeights,height:profile.tableTitleHeight + headerHeight + rowHeights.reduce((a,b)=>a+b,0)};
    };
    const headerLines=(block,blockWidth)=>{
      const titleWidth=block.logo?blockWidth-2*(profile.logoWidth+profile.logoGap):blockWidth-10;
      const lines=size.preset==="full"?[block.title]:wrap(block.title,titleWidth,"serif",profile.titleSize);
      if(lines.length>2||lines.some(value=>widthOf(value,"serif",profile.titleSize)>titleWidth))
        throw new Error(size.preset==="full"
          ? `Page heading "${block.title}" is too wide for this layout.`
          : `Page heading "${block.title}" needs more than two lines at this print size. Shorten it or choose a larger size.`);
      if(block.subtitle&&widthOf(block.subtitle,"sans",10)>titleWidth)
        throw new Error(`Subtitle in "${block.title}" is too wide for this layout.`);
      return lines;
    };
    const measure = (block, blockWidth, available) => {
      if (["tracker","paper_pattern"].includes(block.type)) return contentHeight(block,blockWidth,available);
      if (block.type === "header") return (block.subtitle ? 54 : 40)+(headerLines(block,blockWidth).length-1)*16;
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
        if (block.subtitle) text(block.subtitle,titleCenter,y+43+(titleLines.length-1)*16,"sans",10,MUTED,"middle");
        return;
      }
      if (widthOf(block.title,"serif",profile.sectionSize)>blockWidth) throw new Error(`Section heading "${block.title}" is too wide for this layout.`);
      if (["tracker","paper_pattern"].includes(block.type)) {
        if(block.title)text(block.title,x,y+14,"serif",profile.sectionSize,accentText);
        drawContent(block,x,y,blockWidth,contentHeight(block,blockWidth,height-profile.margin-(document.footer?profile.footerReserve:0)-y),{line,text,circle,widthOf});
        return;
      }
      text(block.title,x,y+14,"serif",profile.sectionSize,accentText);
      line(x,y+21,x+blockWidth,y+21,accent,profile.accentLine);
      if (block.type === "score_table") {
        const geometry = scoreGeometry(block,blockWidth);
        const top = y + profile.tableTitleHeight;
        const boundaries = [top,top+geometry.headerHeight];
        geometry.rowHeights.forEach((h)=>boundaries.push(boundaries.at(-1)+h));
        geometry.labels.forEach((label,index)=>{if(calculated(label)) rect(x,boundaries[index+1],blockWidth,geometry.rowHeights[index],FILL);});
        boundaries.forEach((at)=>line(x,at,x+blockWidth,at));
        for(let index=0;index<=block.players.length+1;index++) {
          const at=index===0?x:index===1?x+geometry.labelWidth:x+geometry.labelWidth+(index-1)*geometry.columnWidth;
          line(at,top,at,boundaries.at(-1));
        }
        cellText(block.first_column_heading ?? "Category",x,top,geometry.labelWidth,geometry.headerHeight,{font:"bold"});
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
    let cursor = profile.margin;
    const blockBounds=[];
    for(const row of document.rows) {
      const commandCount=commands.length,boundCount=blockBounds.length;
      try {
      const columns=row.blocks.length;
      if(columns!==1&&columns!==2) throw new Error("FGS rows must have one or two blocks");
      const blockWidth=(width-2*profile.margin-(columns===2?profile.columnGap:0))/columns;
      const blockHeight=Math.max(...row.blocks.map((block)=>measure(block,blockWidth,height-profile.margin-(document.footer?profile.footerReserve:0)-cursor)));
      if(cursor+blockHeight>height-profile.margin-(document.footer?profile.footerReserve:0)+0.001) return {profile:profile.id,width,height,printPreset:size.preset,fits:false,overflow:row.blocks[0].title,commands,blockBounds};
      row.blocks.forEach((block,index)=>{
        const x=profile.margin+index*(blockWidth+profile.columnGap);
        blockBounds.push({id:block.id,x,y:cursor,width:blockWidth,height:blockHeight});
        drawBlock(block,x,cursor,blockWidth);
      });
      cursor+=blockHeight+profile.rowGap;
      }catch(error){
        if(size.preset==="full")throw error;
        commands.length=commandCount;blockBounds.length=boundCount;
        return {profile:profile.id,width,height,printPreset:size.preset,fits:false,overflow:row.blocks[0].title,reason:error.message,commands,blockBounds};
      }
    }
    if (document.footer) {
      const lines = document.footer.split("\n");
      for (const [index, value] of lines.entries()) {
        if (widthOf(value,"sans",profile.footerSize)>width-2*profile.margin) {
          if(size.preset!=="full")return {profile:profile.id,width,height,printPreset:size.preset,fits:false,overflow:"Footer",reason:"Author footer is too wide for the selected print size.",commands,blockBounds};
          throw new Error("Author footer is too wide for the page.");
        }
        const baseline = height-profile.margin+(size.preset==="full"?10:0)+(index-(lines.length-1))*profile.footerLineHeight;
        text(value,width/2,baseline,"sans",profile.footerSize,MUTED,"middle");
      }
    }
    return {profile:profile.id,width,height,printPreset:size.preset,fits:true,commands,blockBounds};
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
  return {layout,toSvg,toPdf,toPrintSheetPdf,printSheetPlan,widthOf};
}
