"use client";

import { useState, useRef } from "react";
import { fetchWithAuth } from "@/lib/api-client";

interface NotesUploadProps {
  sessionId: string;
  onSuccess: () => void;
  onSkip: () => void;
  onBack: () => void;
}

export default function NotesUpload({ sessionId, onSuccess, onSkip, onBack }: NotesUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setErrorMsg(null);
    const selected = e.target.files?.[0];
    if (!selected) return;
    
    if (selected.type !== "application/pdf") {
      setErrorMsg("Please select a valid PDF file.");
      return;
    }
    
    if (selected.size > MAX_FILE_SIZE) {
      setErrorMsg("File size exceeds 10MB limit.");
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

    const dropped = e.dataTransfer.files?.[0];
    if (!dropped) return;

    if (dropped.type !== "application/pdf") {
      setErrorMsg("Please drop a valid PDF file.");
      return;
    }
    if (dropped.size > MAX_FILE_SIZE) {
      setErrorMsg("File size exceeds 10MB limit.");
      return;
    }

    setFile(dropped);
  };

  const handleUploadAndContinue = async () => {
    if (!file) {
      setErrorMsg("No file selected.");
      return;
    }

    setIsUploading(true);
    setErrorMsg(null);

    const formData = new FormData();
    formData.append("pdf_file", file);

    try {
      const res = await fetchWithAuth(`/api/sessions/${sessionId}/notes`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Failed to upload notes: ${res.statusText}`);
      }

      onSuccess();
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.message || "An error occurred during upload.");
      setIsUploading(false);
    }
  };

  return (
    <div className="space-y-6 text-center w-full">
      <h2 className="text-2xl font-bold text-[var(--foreground)]">Upload Course Notes</h2>
      <p className="text-[var(--text-secondary)]">
        Upload PDF notes for this session to improve model accuracy. Max 10MB.
      </p>

      {/* Hidden File Input */}
      <input 
        type="file" 
        accept=".pdf,application/pdf"
        className="hidden" 
        ref={fileInputRef} 
        onChange={handleFileSelect}
      />

      <div 
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => !file && fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-12 mt-8 flex flex-col items-center justify-center transition-all w-full ${
          file 
            ? "border-[var(--brand)] bg-[var(--brand)] bg-opacity-5" 
            : "border-[var(--input-border)] bg-[var(--input-bg)] hover:border-[var(--brand)] cursor-pointer"
        }`}
      >
        <span className="text-4xl mb-4">{file ? "📝" : "📄"}</span>
        
        {file ? (
          <div className="space-y-4 text-center">
            <p className="text-sm font-semibold text-[var(--foreground)] break-all max-w-[250px] mx-auto">
              {file.name}
            </p>
            <p className="text-xs text-[var(--text-secondary)]">
              {(file.size / (1024 * 1024)).toFixed(2)} MB
            </p>
            {!isUploading && (
              <button 
                onClick={(e) => { e.stopPropagation(); setFile(null); }}
                className="text-xs text-red-500 hover:text-red-700 underline font-medium"
              >
                Remove File
              </button>
            )}
          </div>
        ) : (
          <>
            <p className="text-sm font-medium mb-4">Click to browse or drag PDF here.</p>
            <button className="px-6 py-2 bg-[var(--brand)] text-[var(--brand-text)] font-semibold rounded-full shadow hover:bg-[var(--brand-accent)] transition-colors pointer-events-none">
              Select File
            </button>
          </>
        )}
      </div>

      {errorMsg && <p className="text-sm text-red-500 font-medium">{errorMsg}</p>}

      <div className="pt-4 flex justify-between items-center w-full">
        <button 
          onClick={onBack}
          disabled={isUploading}
          className="text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--foreground)] px-4 py-2 disabled:opacity-50"
        >
          ← Back
        </button>
        
        {file ? (
          <button 
            onClick={handleUploadAndContinue}
            disabled={isUploading}
            className="text-sm font-medium px-6 py-2 bg-[var(--brand)] text-[var(--brand-text)] rounded-full shadow hover:bg-[var(--brand-accent)] transition-colors disabled:opacity-50"
          >
            {isUploading ? "Uploading..." : "Upload & Continue"}
          </button>
        ) : (
          <button 
            onClick={onSkip}
            className="text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--foreground)] px-4 py-2 underline"
          >
            Skip upload
          </button>
        )}
      </div>
    </div>
  );
}
