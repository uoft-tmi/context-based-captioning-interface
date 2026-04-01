'use client';

import { useState, useRef } from 'react';
import { uploadSessionNote } from '@/lib/api';

interface NotesUploadProps {
  sessionId: string;
  onSuccess: () => void;
  onCancel: () => void;
}

export default function NotesUpload({
  sessionId,
  onSuccess,
  onCancel,
}: NotesUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

  const isPdfFile = (candidate: File) => {
    const hasPdfMime = candidate.type === 'application/pdf';
    const hasPdfExtension = candidate.name.toLowerCase().endsWith('.pdf');
    return hasPdfMime || hasPdfExtension;
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setErrorMsg(null);
    const selected = e.target.files?.[0];
    if (!selected) return;

    if (!isPdfFile(selected)) {
      setErrorMsg('Please select a valid PDF file.');
      return;
    }

    if (selected.size > MAX_FILE_SIZE) {
      setErrorMsg('File size exceeds 10MB limit.');
      return;
    }

    setFile(selected);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setErrorMsg(null);

    const dropped =
      e.dataTransfer.items?.[0]?.getAsFile() ?? e.dataTransfer.files?.[0];
    if (!dropped) return;

    if (!isPdfFile(dropped)) {
      setErrorMsg('Please drop a valid PDF file.');
      return;
    }
    if (dropped.size > MAX_FILE_SIZE) {
      setErrorMsg('File size exceeds 10MB limit.');
      return;
    }

    setFile(dropped);
  };

  const handleUploadAndContinue = async () => {
    if (!file) {
      setErrorMsg('No file selected.');
      return;
    }

    setIsUploading(true);
    setErrorMsg(null);

    try {
      await uploadSessionNote(sessionId, file);

      onSuccess();
    } catch (err: unknown) {
      console.error(err);
      setErrorMsg(
        err instanceof Error ? err.message : 'An error occurred during upload.',
      );
      setIsUploading(false);
    }
  };

  return (
    <div className='space-y-6 text-center w-full'>
      <h2 className='text-2xl font-bold text-foreground'>
        Upload Course Notes
      </h2>
      <p className='text-(--text-secondary)'>
        Upload PDF notes for this session to improve model accuracy. Max 10MB.
      </p>

      {/* Hidden File Input */}
      <input
        type='file'
        accept='.pdf,application/pdf'
        className='hidden'
        ref={fileInputRef}
        onChange={handleFileSelect}
      />

      <div
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => !file && fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-12 mt-8 flex flex-col items-center justify-center transition-all w-full ${
          file
            ? 'border-(--brand) bg-(--brand) bg-opacity-5'
            : 'border-(--input-border) bg-(--input-bg) hover:border-(--brand) cursor-pointer'
        }`}
      >
        <span className='text-4xl mb-4'>{file ? '📝' : '📄'}</span>

        {file ? (
          <div className='space-y-4 text-center'>
            <p className='text-sm font-semibold text-foreground break-all max-w-64 mx-auto'>
              {file.name}
            </p>
            <p className='text-xs text-(--text-secondary)'>
              {(file.size / (1024 * 1024)).toFixed(2)} MB
            </p>
            {!isUploading && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setFile(null);
                }}
                className='text-xs text-red-500 hover:text-red-700 underline font-medium'
              >
                Remove File
              </button>
            )}
          </div>
        ) : (
          <>
            <p className='text-sm font-medium mb-4'>
              Click to browse or drag PDF here.
            </p>
            <button className='px-6 py-2 bg-(--brand) text-(--brand-text) font-semibold rounded-full shadow hover:bg-(--brand-accent) transition-colors pointer-events-none'>
              Select File
            </button>
          </>
        )}
      </div>

      {errorMsg && (
        <p className='text-sm text-red-500 font-medium'>{errorMsg}</p>
      )}

      <div className='pt-4 flex justify-between items-center w-full'>
        <button
          onClick={onCancel}
          disabled={isUploading}
          className='text-sm font-medium text-(--text-secondary) hover:text-foreground px-4 py-2 disabled:opacity-50'
        >
          Cancel Session
        </button>

        <button
          onClick={handleUploadAndContinue}
          disabled={isUploading || !file}
          className='text-sm font-medium px-6 py-2 bg-(--brand) text-(--brand-text) rounded-full shadow hover:bg-(--brand-accent) transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
        >
          {isUploading ? 'Uploading...' : 'Upload & Continue'}
        </button>
      </div>
    </div>
  );
}
