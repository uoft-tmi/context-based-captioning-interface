import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { SessionSummary } from '../lib/api';
import { hasTranscript, normalizeSessionName, recordingTime, sessionStatus } from '../lib/session-utils';

const session: SessionSummary = {id:'session',user_id:'user',name:'Lecture',mode:'baseline',is_active:false,is_recording:false,error:null,created_at:'2026-10-31',expires_at:'2026-11-01',finalized_at:null,transcript_key:null,transcript_text:null,recording_limit_seconds:30,recorded_duration_ms:0,recording_started_at:null,deleting_at:null};
test('session names normalize whitespace for duplicate checking', () => {
  assert.equal(normalizeSessionName('  Week   One \n lecture  '), 'Week One lecture');
});
test('dashboard distinguishes active, recorded, failed, and pending-deletion sessions', () => {
  assert.equal(sessionStatus({...session,is_active:true}), 'Ready to record');
  assert.equal(sessionStatus({...session,is_active:true,is_recording:true}), 'Recording');
  assert.equal(sessionStatus({...session,transcript_key:'file.pdf'}), 'Transcript saved');
  assert.equal(sessionStatus({...session,error:'failure'}), 'Ended with an issue');
  assert.equal(sessionStatus({...session,transcript_key:'file.pdf',error:'partial'}), 'Saved with issues');
  assert.equal(sessionStatus({...session,deleting_at:'2026-10-31'}), 'Deletion pending');
});
test('free and paid recording allowances format consistently', () => {
  assert.equal(recordingTime(30000), '00:30');
  assert.equal(recordingTime(3600000), '60:00');
});

test('retained text stays readable and downloadable when PDF storage failed', () => {
  const textOnly = {...session,transcript_text:'A retained transcript.',error:'PDF storage unavailable'};
  assert.ok(hasTranscript(textOnly));
  assert.equal(sessionStatus(textOnly), 'Saved with issues');
  assert.ok(hasTranscript({...session,has_transcript:true}));
  assert.equal(hasTranscript(session), false);
});
