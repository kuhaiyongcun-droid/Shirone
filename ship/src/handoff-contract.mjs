// Pure handoff validation; importing this module does not run an importer or read assets.
import { validateDescriptor } from './asset-contract.mjs';
import { CONTRACT_URI, assertSourcePin } from '../source-selection.mjs';

const hash = /^[a-f0-9]{64}$/;
const EVIDENCE_KINDS = ['geometry', 'protection', 'same-camera'];
export function safeRelative(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_./-]+$/.test(value) || value.startsWith('/') || value.includes('..') || value.includes('//') || value.endsWith('/')) throw Error('Unsafe handoff relative path');
  return value;
}
export function validateHandoff(value, expectedSource) {
  assertSourcePin(expectedSource);
  if (value?.schema !== 'ship-web-handoff-v1' || value.complete !== true) throw Error('Complete ship-web-handoff-v1 required');
  if (value.source?.stage !== expectedSource.stage || value.source?.sha256 !== expectedSource.sha256) throw Error('Handoff source differs from explicit pin');
  if (!/^[A-Za-z0-9_-]+$/.test(value.publicDirectory || '')) throw Error('Handoff publicDirectory must be a direct package child');
  validateDescriptor(value.contract);
  if (value.contract.uri !== CONTRACT_URI) throw Error('Handoff must supply the actual runtime contract at ' + CONTRACT_URI);
  if (value.browserVerified !== false || value.lightingCalibrated !== false) throw Error('Offline handoff cannot assert browser/lighting acceptance');
  if (!Array.isArray(value.evidence) || value.evidence.length !== EVIDENCE_KINDS.length || new Set(value.evidence.map(r => r.kind)).size !== EVIDENCE_KINDS.length) throw Error('Three distinct delivery evidence records required');
  for (const row of value.evidence) {
    if (!EVIDENCE_KINDS.includes(row.kind) || row.status !== 'PASS' || row.sourceSceneSha256 !== expectedSource.sha256 || !hash.test(row.sha256 || '') || !Number.isSafeInteger(row.bytes) || row.bytes <= 0) throw Error('Incomplete or failed evidence: ' + row.kind);
    safeRelative(row.path);
  }
  return value;
}
