import {createPrintEngine, PROFILE} from "./index.mjs";

export {createPrintEngine, PROFILE};

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
