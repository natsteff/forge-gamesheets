const contains = (region, x, y) => x >= region.x && x <= region.x + region.width && y >= region.y && y <= region.y + region.height;

export function previewTargetAt(layout, x, y) {
  if (!layout?.fits || !Number.isFinite(x) || !Number.isFinite(y)) return null;
  const targets=layout.editTargets||[];
  for (let index=targets.length-1;index>=0;index--) {
    const target=targets[index];
    if (contains(target, x, y)) return target;
  }
  const blocks=layout.blockBounds||[];
  for (let index=blocks.length-1;index>=0;index--) {
    const block=blocks[index];
    if (contains(block, x, y)) return {blockId:block.id, field:"title"};
  }
  return null;
}

export function lineSelection(value, lineIndex) {
  const lines=String(value).split("\n");
  const index=Math.max(0,Math.min(lines.length-1,Number.isInteger(lineIndex)?lineIndex:0));
  let start=0;
  for(let line=0;line<index;line++)start+=lines[line].length+1;
  return {start,end:start+lines[index].length};
}
