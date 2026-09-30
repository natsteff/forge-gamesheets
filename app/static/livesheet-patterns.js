import {loadPrintEngine} from "/static/fgs-renderer/browser.mjs?profile=fgs-page-1.3.1";
const nodes=[...document.querySelectorAll("[data-live-paper]")];
if(nodes.length){
  try{
    const engine=await loadPrintEngine(new URL("/static/fgs-renderer/",location.href));
    const documentModel=JSON.parse(document.querySelector("[data-paper-source]").dataset.document);
    const layout=engine.layout(documentModel);
    if(!layout.fits)throw new Error("The original sheet does not fit its page.");
    for(const node of nodes){
      const bounds=layout.blockBounds.find(block=>block.id===node.dataset.livePaper);
      if(!bounds)throw new Error("Pattern section not found.");
      const inside=(x,y)=>x>=bounds.x-.001&&x<=bounds.x+bounds.width+.001&&y>=bounds.y-.001&&y<=bounds.y+bounds.height+.001;
      const commands=layout.commands.filter(c=>c.type==="line"?inside(c.x1,c.y1)&&inside(c.x2,c.y2):inside(c.x,c.y));
      node.innerHTML=engine.toSvg({...layout,commands});
      const image=node.querySelector("svg");image.setAttribute("viewBox",[bounds.x,bounds.y,bounds.width,bounds.height].join(" "));
      image.removeAttribute("width");image.removeAttribute("height");image.style.width="100%";image.style.height="auto";
      image.setAttribute("aria-label","Static writing pattern; no digital drawing or saving");
    }
  }catch(error){nodes.forEach(node=>{node.textContent="Paper pattern unavailable: "+error.message;});}
}
