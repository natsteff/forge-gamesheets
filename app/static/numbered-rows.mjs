export function numberedRows(label, start, count) {
  const prefix = label.trim();
  return Array.from({length: count}, (_, index) => prefix ? `${prefix} ${start + index}` : String(start + index));
}
