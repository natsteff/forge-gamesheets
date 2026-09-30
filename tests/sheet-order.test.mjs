import test from "node:test";
import assert from "node:assert/strict";
import {canMoveSectionTo, moveSectionTo, sectionNeighbor} from "../app/static/sheet-order.mjs";

const document = () => ({rows:[
  {id:"header",blocks:[{id:"title"}]},
  {id:"score",blocks:[{id:"high"}]},
  {id:"first",blocks:[{id:"win"},{id:"structures"}]},
  {id:"second",blocks:[{id:"area"},{id:"towns"}]},
]});
const order = sheet => sheet.rows.map(row=>row.blocks.map(block=>block.id));

test("one section step crosses paired rows in reading order without changing widths",()=>{
  const sheet=document();
  assert.deepEqual(sectionNeighbor(sheet,"area",-1),{block:{id:"structures"},blocked:false});
  assert.equal(moveSectionTo(sheet,"area","structures"),true);
  assert.deepEqual(order(sheet),[["title"],["high"],["win","area"],["structures","towns"]]);
  assert.deepEqual(sheet.rows.map(row=>row.id),["header","score","first","second"]);
  assert.equal(moveSectionTo(sheet,"area","win"),true);
  assert.deepEqual(order(sheet)[2],["area","win"]);
});

test("a drag across paired positions preserves the paired slots",()=>{
  const sheet=document();
  assert.equal(moveSectionTo(sheet,"win","towns"),true);
  assert.deepEqual(order(sheet),[["title"],["high"],["structures","area"],["towns","win"]]);
});

test("full-width boundaries prevent section movement without changing the document",()=>{
  const sheet=document();
  const original=structuredClone(sheet);
  assert.deepEqual(sectionNeighbor(sheet,"win",-1),{block:{id:"high"},blocked:true});
  assert.equal(canMoveSectionTo(sheet,"win","high"),false);
  assert.equal(moveSectionTo(sheet,"win","high"),false);
  assert.equal(canMoveSectionTo(sheet,"title","area"),false);
  assert.deepEqual(sheet,original);
});
