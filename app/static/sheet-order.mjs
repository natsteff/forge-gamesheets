// Section order follows the printed reading order, while row widths stay fixed.
export function sectionPositions(document) {
  return document.rows.flatMap((row, rowIndex) => row.blocks.map((block, blockIndex) => ({block, rowIndex, blockIndex})));
}

export function sectionNeighbor(document, blockId, direction) {
  const positions = sectionPositions(document);
  const index = positions.findIndex(({block}) => block.id === blockId);
  const current = positions[index];
  const next = positions[index + direction];
  if (!current || !next) return null;
  const sameRow = current.rowIndex === next.rowIndex;
  return {block: next.block, blocked: !sameRow && (
    document.rows[current.rowIndex].blocks.length === 1 ||
    document.rows[next.rowIndex].blocks.length === 1
  )};
}

export function canMoveSectionTo(document, fromId, toId) {
  const positions = sectionPositions(document);
  const from = positions.findIndex(({block}) => block.id === fromId);
  const to = positions.findIndex(({block}) => block.id === toId);
  if (from < 0 || to < 0 || from === to) return false;
  const direction = Math.sign(to - from);
  for (let index = from; index !== to; index += direction) {
    const left = positions[index];
    const right = positions[index + direction];
    if (left.rowIndex !== right.rowIndex && (
      document.rows[left.rowIndex].blocks.length === 1 ||
      document.rows[right.rowIndex].blocks.length === 1
    )) return false;
  }
  return true;
}

export function moveSectionTo(document, fromId, toId) {
  if (!canMoveSectionTo(document, fromId, toId)) return false;
  const positions = sectionPositions(document);
  const index = positions.findIndex(({block}) => block.id === fromId);
  const target = positions.findIndex(({block}) => block.id === toId);
  const direction = Math.sign(target - index);
  for (let step = 0; step < Math.abs(target - index); step++) {
    const slots = sectionPositions(document);
    const currentIndex = slots.findIndex(({block}) => block.id === fromId);
    const current = slots[currentIndex];
    const next = slots[currentIndex + direction];
    const currentRow = document.rows[current.rowIndex].blocks;
    const nextRow = document.rows[next.rowIndex].blocks;
    [currentRow[current.blockIndex], nextRow[next.blockIndex]] = [nextRow[next.blockIndex], currentRow[current.blockIndex]];
  }
  return true;
}
