import test from 'node:test';
import assert from 'node:assert/strict';
import {captureChatScope, compactPatientScope, analysisScopeDefaults, chatExecutionIds} from '../static/js/chat_scope.js';

test('new chats capture qualified membership without sharing a live reference', () => {
  const state = {currentDatasetScopeId:'workspace', activePatientScope:{workspace:'workspace', selection:{
    selection_active:true, members:[{dataset_id:'a', patient_id:'P1'}, {dataset_id:'b', patient_id:'P1'}]}}};
  const captured = captureChatScope(state);
  assert.equal(captured.patient_count, 2);
  assert.notEqual(captured.patient_ids[0], captured.patient_ids[1]);
  state.activePatientScope.selection.members.pop();
  assert.equal(captured.members.length, 2);
  assert.equal(analysisScopeDefaults(state).scope.split(',').length, 1);
  assert.deepEqual(compactPatientScope(captured).members, [{dataset_id:'a', patient_id:'P1'}, {dataset_id:'b', patient_id:'P1'}]);
  assert.deepEqual(chatExecutionIds({currentDatasetIds:['a']}, {patient_ids:[captured.patient_ids[0]]}), ['P1']);
});

test('full workspace and applied empty selection remain distinct', () => {
  const state = {currentDatasetScopeId:'a', activePatientScope:null};
  assert.deepEqual(captureChatScope(state), {});
  state.activePatientScope = {workspace:'a', selection:{selection_active:true, members:[]}};
  assert.equal(captureChatScope(state).selection_active, true);
  assert.equal(captureChatScope(state).patient_count, 0);
  state.currentDatasetScopeId = 'b';
  assert.deepEqual(captureChatScope(state), {});
});
