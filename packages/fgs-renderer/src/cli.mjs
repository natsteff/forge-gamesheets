import {readFile,writeFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import {dirname,join} from "node:path";
import {createPrintEngine} from "./index.mjs";

const [, , source, destination] = process.argv;
if (!source || !destination) {
  process.stderr.write("Usage: fgs-renderer INPUT.fgs OUTPUT.pdf\n");
  process.exitCode = 2;
} else {
  try {
    const root=dirname(fileURLToPath(import.meta.url));
    const files={sans:"NotoSans-Regular.ttf",bold:"NotoSans-Bold.ttf",serif:"NotoSerif-Bold.ttf"};
    const fonts={};
    await Promise.all(Object.entries(files).map(async ([key,file])=>{fonts[key]=new Uint8Array(await readFile(join(root,"fonts",file)));}));
    const document=JSON.parse(await readFile(source,"utf8"));
    const engine=createPrintEngine(fonts);
    const result=engine.layout(document);
    if (!result.fits) throw new Error(`FGS_OVERFLOW: Section "${result.overflow}" does not fit on the page.`);
    const pdf=await engine.toPdf(result,document.title);
    await writeFile(destination,pdf,{flag:"wx"});
  } catch(error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode=1;
  }
}
