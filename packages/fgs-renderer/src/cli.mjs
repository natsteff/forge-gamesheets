import {readFile,writeFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import {dirname,join} from "node:path";
import {createPrintEngine} from "./index.mjs";
import {finishedSize} from "./print-sizes.mjs";

const [, , source, destination, settingsFile] = process.argv;
if (!source || !destination) {
  process.stderr.write("Usage: fgs-renderer INPUT.fgs OUTPUT.pdf [PRINT-OPTIONS.json]\n");
  process.exitCode = 2;
} else {
  try {
    const root=dirname(fileURLToPath(import.meta.url));
    const files={sans:"NotoSans-Regular.ttf",bold:"NotoSans-Bold.ttf",serif:"NotoSerif-Bold.ttf"};
    const fonts={};
    await Promise.all(Object.entries(files).map(async ([key,file])=>{fonts[key]=new Uint8Array(await readFile(join(root,"fonts",file)));}));
    const document=JSON.parse(await readFile(source,"utf8"));
    const settings=settingsFile?JSON.parse(await readFile(settingsFile,"utf8")):{};
    if(!settings||typeof settings!=="object"||Array.isArray(settings))throw new Error("FGS_OPTIONS: Invalid print options.");
    try{finishedSize(document,settings.printSize??{});}catch(error){throw new Error(`FGS_OPTIONS: ${error.message}`);}
    const engine=createPrintEngine(fonts);
    const result=engine.layout(document,settings.printSize??{});
    if (!result.fits) throw new Error(`FGS_OVERFLOW: ${result.reason??`Section "${result.overflow}" does not fit on the finished sheet.`}`);
    let pdf,verification={width:result.width,height:result.height,pages:1};
    if(settings.printSheet!==undefined){
      try{
        const plan=engine.printSheetPlan(result,settings.printSheet);
        verification={width:plan.width,height:plan.height,pages:plan.pages.length};
        pdf=await engine.toPrintSheetPdf(result,document.title,settings.printSheet);
      }
      catch(error){throw new Error(`FGS_OPTIONS: ${error.message}`);}
    }else pdf=await engine.toPdf(result,document.title);
    await writeFile(destination,pdf,{flag:"wx"});
    process.stdout.write(JSON.stringify(verification)+"\n");
  } catch(error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode=1;
  }
}
