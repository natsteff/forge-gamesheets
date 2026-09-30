// Print-job geometry is deliberately separate from the portable FGS document.
// PDF points are the shared unit: 72 points are exactly one inch.
export const PAPER_SIZES = Object.freeze({letter:[612,792],a4:[595.28,841.89]});
export const PRINT_PRESETS = Object.freeze(["full","half","poker","bridge","custom"]);
const CARD_SIZES = Object.freeze({poker:[180,252],bridge:[162,252]});
const roundPoint = value => Math.round(value * 1000) / 1000;

function paperSize(name) {
  const dimensions=PAPER_SIZES[name];
  if(!dimensions)throw new Error("Choose Letter or A4 printer paper.");
  return dimensions;
}

export function finishedSize(document, selection={}) {
  if(!selection||typeof selection!=="object"||Array.isArray(selection))throw new Error("Invalid print size selection.");
  const preset=selection.preset??"full";
  if(!PRINT_PRESETS.includes(preset))throw new Error("Choose a supported print size.");
  const [paperWidth,paperHeight]=paperSize(document.page.size);
  const orientation=document.page.orientation;
  if(!["portrait","landscape"].includes(orientation))throw new Error("Unsupported page orientation.");
  let dimensions;
  if(preset==="full")dimensions=[paperWidth,paperHeight];
  else if(preset==="half")dimensions=[paperHeight/2,paperWidth];
  else if(CARD_SIZES[preset])dimensions=CARD_SIZES[preset];
  else {
    const unit=selection.unit;
    if(!["in","cm"].includes(unit))throw new Error("Custom size needs an explicit inch or centimeter unit.");
    const factor=unit==="in"?72:72/2.54;
    dimensions=[selection.width,selection.height].map(value=>{
      if(typeof value!=="number"&&typeof value!=="string")throw new Error("Custom width and height must be numbers.");
      const number=Number(value);
      const points=number*factor;
      if(value===""||value===null||value===undefined||!Number.isFinite(points)||points<36||points>1008)
        throw new Error("Custom width and height must each be between 0.5 and 14 inches (1.27–35.56 cm).");
      return roundPoint(points);
    });
  }
  const [width,height]=preset==="custom"||orientation==="portrait"?dimensions:[dimensions[1],dimensions[0]];
  return {preset,width,height};
}

function coordinates(width,height,pieceWidth,pieceHeight,margin,gap) {
  const columns=Math.floor((width-2*margin+gap+0.001)/(pieceWidth+gap));
  const rows=Math.floor((height-2*margin+gap+0.001)/(pieceHeight+gap));
  return {width,height,columns:Math.max(0,columns),rows:Math.max(0,rows),capacity:Math.max(0,columns)*Math.max(0,rows)};
}

export function printSheetPlan(result, options={}) {
  if(!result?.fits)throw new Error("The finished sheet must fit before creating a print sheet.");
  if(!options||typeof options!=="object"||Array.isArray(options))throw new Error("Invalid print-sheet options.");
  const paper=options.paper??"letter";
  const [short,long]=paperSize(paper);
  const copies=options.copies??1;
  if(!Number.isInteger(copies)||copies<1||copies>48)throw new Error("Choose between 1 and 48 copies.");
  const cutGuides=options.cutGuides??true;
  if(typeof cutGuides!=="boolean")throw new Error("Cut guides must be on or off.");
  const borderless=options.borderless??false;
  if(typeof borderless!=="boolean")throw new Error("Borderless mode must be on or off.");
  let chosen;
  if(borderless) {
    if(result.printPreset!=="half")throw new Error("Borderless two-up is only available for Half Page.");
    const candidates=[
      {width:short,height:long,columns:1,rows:2,capacity:2},
      {width:long,height:short,columns:2,rows:1,capacity:2},
    ];
    chosen=candidates.find(candidate=>
      Math.abs(candidate.width-candidate.columns*result.width)<0.011&&
      Math.abs(candidate.height-candidate.rows*result.height)<0.011);
    if(!chosen)throw new Error("Borderless two-up requires the same Letter or A4 paper used for Half Page.");
  } else {
    // Reserve printable space for both the finished piece and outward cut marks.
    const margin=36+(cutGuides?8:0),gap=12;
    const portrait=coordinates(short,long,result.width,result.height,margin,gap);
    const landscape=coordinates(long,short,result.width,result.height,margin,gap);
    // A printer sheet is arranged for maximum capacity, regardless of the
    // currently requested copy count, so later copies use the same layout.
    chosen=landscape.capacity>portrait.capacity?landscape:portrait;
    if(!chosen.capacity)throw new Error("The finished sheet does not fit within the printer paper's 0.5-inch printable margins. Use larger paper or export the finished-size PDF for suitable card stock.");
  }
  const gap=borderless?0:12;
  const usedWidth=chosen.columns*result.width+(chosen.columns-1)*gap;
  const usedHeight=chosen.rows*result.height+(chosen.rows-1)*gap;
  const left=(chosen.width-usedWidth)/2,top=(chosen.height-usedHeight)/2;
  const pages=[];
  for(let copy=0;copy<copies;copy++) {
    const pageIndex=Math.floor(copy/chosen.capacity),slot=copy%chosen.capacity;
    pages[pageIndex]??=[];
    pages[pageIndex].push({x:left+(slot%chosen.columns)*(result.width+gap),y:top+Math.floor(slot/chosen.columns)*(result.height+gap)});
  }
  return {paper,width:chosen.width,height:chosen.height,orientation:chosen.width>chosen.height?"landscape":"portrait",capacity:chosen.capacity,pages,cutGuides,borderless};
}
