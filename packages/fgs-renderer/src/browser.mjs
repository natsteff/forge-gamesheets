import {createPrintEngine, PROFILE} from "./index.mjs";

export {createPrintEngine, PROFILE};

// Normalize user-selected PNG/JPEG artwork before placing it in a portable FGS.
export async function prepareHeaderLogo(file, alt, decorative) {
  if (!file || !["image/png","image/jpeg"].includes(file.type) || file.size > 5*1024*1024) throw new Error("Choose a PNG or JPEG logo under 5 MB.");
  const image=await createImageBitmap(file);
  try {
    let scale=Math.min(1,512/image.width,256/image.height);
    for(let attempt=0;attempt<8;attempt++) {
      const canvas=document.createElement("canvas");
      canvas.width=Math.max(1,Math.round(image.width*scale));
      canvas.height=Math.max(1,Math.round(image.height*scale));
      canvas.getContext("2d").drawImage(image,0,0,canvas.width,canvas.height);
      const data=canvas.toDataURL("image/png").split(",",2)[1];
      if (atob(data).length<=128*1024) return {media_type:"image/png",data,alt,decorative};
      scale*=.8;
    }
    throw new Error("The logo could not be reduced below 128 KiB.");
  } finally {image.close();}
}

export async function loadPrintEngine(baseUrl) {
  const files={sans:"NotoSans-Regular.ttf",bold:"NotoSans-Bold.ttf",serif:"NotoSerif-Bold.ttf"};
  const fontData={};
  await Promise.all(Object.entries(files).map(async ([key,file])=>{
    const response=await fetch(new URL(`fonts/${file}`,baseUrl));
    if(!response.ok) throw new Error(`FGS print font could not be loaded: ${file}`);
    fontData[key]=new Uint8Array(await response.arrayBuffer());
  }));
  return createPrintEngine(fontData);
}
