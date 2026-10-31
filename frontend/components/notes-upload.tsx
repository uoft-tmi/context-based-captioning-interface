'use client';

import { useRef, useState } from 'react';
import { uploadSessionNote } from '@/lib/api';
import { Icon, Notice } from '@/components/ui';

interface NotesUploadProps {
  sessionId: string;
  onSuccess: () => void;
  onCancel: () => void;
  onSkip: () => void;
  disabled?: boolean;
  compact?: boolean;
}

export default function NotesUpload({ sessionId, onSuccess, onCancel, onSkip, disabled = false, compact = false }: NotesUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const uploading = useRef(false);
  const locked = isUploading || disabled;

  function selectFile(candidate?: File) {
    if (locked) return;
    setError('');
    setFile(null);
    if (!candidate) return;
    if (candidate.type !== 'application/pdf' && !candidate.name.toLowerCase().endsWith('.pdf')) {
      setError('Please choose a PDF. You can export your notes or slides as a PDF first.');
    } else if (candidate.size === 0) {
      setError('This file is empty. Please choose another PDF.');
    } else if (candidate.size > 10 * 1024 * 1024) {
      setError('This PDF is over 10 MB. Choose a smaller file or compress it first.');
    } else {
      setFile(candidate);
    }
  }

  async function upload() {
    if (!file || locked || uploading.current) return;
    uploading.current = true;
    setIsUploading(true);
    setError('');
    try {
      await uploadSessionNote(sessionId, file);
      onSuccess();
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Upload failed. Please try again.');
    } finally { setIsUploading(false); uploading.current = false; }
  }

  return <div className="upload-content" aria-busy={isUploading}>
    <input id="lecture-pdf" type="file" accept=".pdf,application/pdf" className="file-input" ref={fileInput} disabled={locked} aria-label="Choose lecture notes PDF" aria-describedby="pdf-help" onChange={(event) => { selectFile(event.target.files?.[0]); event.target.value = ''; }} />
    <div className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); if (!locked) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); if (event.dataTransfer.files.length > 1) { setError('Please choose one PDF for this lecture.'); return; } selectFile(event.dataTransfer.files[0]); }}>
      <span className="upload-icon"><Icon name={file ? 'file' : 'upload'} width="24" height="24" /></span>
      {file ? <><p className="file-name">{file.name}</p><p className="muted small">{(file.size / (1024 * 1024)).toFixed(2)} MB · Ready to upload</p><button className="text-link" disabled={locked} onClick={() => { setFile(null); setError(''); fileInput.current?.focus(); }}>Remove file</button></> : <><p className="small">Drag your PDF here, or <button className="text-link" disabled={locked} onClick={() => fileInput.current?.click()}>browse files</button></p><p id="pdf-help" className="muted small">One PDF, up to 10 MB</p></>}
    </div>
    {file && <p id="pdf-help" className="muted small" style={{ marginTop: 10 }}>One PDF, up to 10 MB</p>}
    {error && <div style={{ marginTop: 16 }}><Notice tone="error">{error}</Notice></div>}
    <div className="upload-actions">{!compact && <button className="btn btn-ghost" onClick={onSkip} disabled={locked}>Skip for now</button>}<button className="btn btn-primary" disabled={locked || !file} onClick={() => void upload()}>{isUploading ? <><span className="spinner" />Uploading notes…</> : <>{compact ? 'Upload file' : 'Upload and continue'} <Icon name="arrow" width="16" height="16" /></>}</button></div>
    {!compact && <div style={{ marginTop: 17 }}><button className="text-link" disabled={locked} onClick={onCancel}>Cancel session</button></div>}
  </div>;
}
