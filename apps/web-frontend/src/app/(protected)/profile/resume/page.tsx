"use client";

import { useState, useRef, useCallback } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  FileText,
  Loader2,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];
const ACCEPTED_EXTENSIONS = ".pdf,.docx";
const MAX_SIZE_MB = 10;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

export default function ResumeUploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isUploaded, setIsUploaded] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function validateFile(f: File): string | null {
    if (!ACCEPTED_TYPES.includes(f.type)) {
      return "Only PDF and DOCX files are accepted.";
    }
    if (f.size > MAX_SIZE_BYTES) {
      return `File must be under ${MAX_SIZE_MB}MB.`;
    }
    return null;
  }

  function handleFile(f: File) {
    const error = validateFile(f);
    if (error) {
      toast.error(error);
      return;
    }
    setFile(f);
    setIsUploaded(false);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
    // Reset input so same file can be re-selected
    e.target.value = "";
  }

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }, []);

  function removeFile() {
    setFile(null);
    setIsUploaded(false);
  }

  async function handleUpload() {
    if (!file) return;
    setIsUploading(true);

    // Simulated upload — replace with real API call when backend is ready
    await new Promise((r) => setTimeout(r, 2000));

    setIsUploading(false);
    setIsUploaded(true);
    toast.success("Resume uploaded! Your skills profile will be updated shortly.");
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <Link
        href="/profile"
        className="mb-4 inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1 size-3.5" />
        Back to profile
      </Link>

      <h1 className="text-2xl font-bold tracking-tight">Upload resume</h1>
      <p className="text-sm text-muted-foreground">
        Your resume is used by TicketForge&apos;s AI to build your skills
        profile for smarter ticket assignment.
      </p>

      <Separator className="my-6" />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Resume file</CardTitle>
          <CardDescription>
            Upload a PDF or DOCX file (max {MAX_SIZE_MB}MB). Your resume will
            be processed to extract skills, experience, and generate your
            engineer profile vector.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Drop zone */}
          {!file && (
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => inputRef.current?.click()}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors ${
                isDragging
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/20 hover:border-muted-foreground/40 hover:bg-accent/30"
              }`}
            >
              <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-muted">
                <Upload className="size-5 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">
                Drag and drop your resume here
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                or click to browse
              </p>
              <p className="mt-3 text-xs text-muted-foreground">
                PDF or DOCX, up to {MAX_SIZE_MB}MB
              </p>
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPTED_EXTENSIONS}
                onChange={handleInputChange}
                className="hidden"
              />
            </div>
          )}

          {/* Selected file */}
          {file && (
            <div className="rounded-lg border bg-muted/30 p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className="flex size-10 items-center justify-center rounded-lg bg-red-100 dark:bg-red-950">
                    <FileText className="size-5 text-red-600 dark:text-red-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatFileSize(file.size)} &middot;{" "}
                      {file.type === "application/pdf" ? "PDF" : "DOCX"}
                    </p>
                    {isUploaded && (
                      <div className="mt-1 flex items-center gap-1">
                        <CheckCircle2 className="size-3.5 text-green-500" />
                        <span className="text-xs font-medium text-green-600 dark:text-green-400">
                          Uploaded successfully
                        </span>
                      </div>
                    )}
                  </div>
                </div>
                <button
                  onClick={removeFile}
                  className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              </div>

              {/* Upload button */}
              {!isUploaded && (
                <div className="mt-4 flex items-center gap-2">
                  <Button
                    onClick={handleUpload}
                    disabled={isUploading}
                    className="w-full"
                  >
                    {isUploading ? (
                      <>
                        <Loader2 className="mr-1.5 size-4 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <Upload className="mr-1.5 size-4" />
                        Upload resume
                      </>
                    )}
                  </Button>
                </div>
              )}

              {/* Replace option after upload */}
              {isUploaded && (
                <div className="mt-4">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      removeFile();
                    }}
                  >
                    <Trash2 className="mr-1.5 size-3.5" />
                    Replace with new resume
                  </Button>
                </div>
              )}
            </div>
          )}

          <Separator />

          {/* What happens next */}
          <div className="space-y-3">
            <p className="text-sm font-medium">What happens after upload?</p>
            <div className="space-y-2">
              {[
                {
                  step: "1",
                  text: "Text is extracted from your resume (PDF/DOCX)",
                },
                {
                  step: "2",
                  text: "Technical skills and keywords are identified",
                },
                {
                  step: "3",
                  text: "A 384-dimensional embedding is generated from your experience",
                },
                {
                  step: "4",
                  text: "Your engineer profile is created for AI ticket matching",
                },
              ].map((item) => (
                <div key={item.step} className="flex items-start gap-3">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
                    {item.step}
                  </span>
                  <p className="text-sm text-muted-foreground">{item.text}</p>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}