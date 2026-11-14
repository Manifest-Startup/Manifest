import React, { useState, useRef } from 'react';
import { useMutation } from '@apollo/client/react';
import { EXPORT_IDEAS, IMPORT_IDEAS, GET_IDEAS } from 'features/core/apollo/queries';
import { useMessage } from 'features/notifications/context/MessageContext';
import { logError, createLogger } from 'features/core/logError';

const logger = createLogger('ImportExportModal');
const MAX_IMPORT_SIZE_BYTES = 25 * 1024 * 1024;
const SUPPORTED_IMPORT_EXTENSIONS = [
  '.json',
  '.csv',
  '.md',
  '.markdown',
  '.html',
  '.htm',
  '.txt',
  '.pdf',
  '.zip',
  '.tgz',
  '.tar.gz',
] as const;

const inferImportFormat = (fileName: string) => {
  const lowerName = fileName.toLowerCase();

  if (lowerName.endsWith('.tar.gz') || lowerName.endsWith('.tgz')) {
    return 'tgz';
  }
  if (lowerName.endsWith('.zip')) {
    return 'zip';
  }
  if (lowerName.endsWith('.markdown') || lowerName.endsWith('.md')) {
    return 'markdown';
  }
  if (lowerName.endsWith('.html') || lowerName.endsWith('.htm')) {
    return 'html';
  }
  if (lowerName.endsWith('.txt')) {
    return 'txt';
  }
  if (lowerName.endsWith('.pdf')) {
    return 'pdf';
  }
  if (lowerName.endsWith('.csv')) {
    return 'csv';
  }
  if (lowerName.endsWith('.json')) {
    return 'json';
  }

  return '';
};

interface ImportExportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ImportExportModal: React.FC<ImportExportModalProps> = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState<'import' | 'export'>('export');
  const [exportFormat, setExportFormat] = useState<'json' | 'csv' | 'markdown'>('json');
  const [isExporting, setIsExporting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { setMessage } = useMessage();

  const [exportIdeas] = useMutation(EXPORT_IDEAS, {
    refetchQueries: [{ query: GET_IDEAS }],
  });

  const [importIdeas] = useMutation(IMPORT_IDEAS, {
    refetchQueries: [{ query: GET_IDEAS }],
  });

  if (!isOpen) return null;

  const handleExport = async () => {
    try {
      setIsExporting(true);
      const { data } = await exportIdeas({
        variables: { format: exportFormat },
      });

      if (data?.exportIdeas) {
        const { content, filename } = data.exportIdeas;
        
        // Decode base64 content (handle Unicode properly)
        const binaryString = atob(content);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }
        const decodedContent = new TextDecoder('utf-8').decode(bytes);
        
        // Create blob and download
        const blob = new Blob([decodedContent], {
          type: exportFormat === 'json' ? 'application/json' : 
                exportFormat === 'csv' ? 'text/csv' : 
                'text/markdown',
        });
        
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        setMessage(`Successfully exported ideas as ${exportFormat.toUpperCase()}`, 'success');
        onClose();
      }
    } catch (error: any) {
      logger.error('Export error:', error);
      setMessage(error.message || 'Failed to export ideas', 'error');
    } finally {
      setIsExporting(false);
    }
  };

  const handleFileSelect = (file: File) => {
    if (!SUPPORTED_IMPORT_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension))) {
      setMessage(
        'Invalid file type. Please upload JSON, CSV, Markdown, HTML, TXT, PDF, ZIP, or TGZ exports.',
        'error'
      );
      return;
    }

    if (file.size > MAX_IMPORT_SIZE_BYTES) {
      setMessage('File size too large. Maximum size is 25MB.', 'error');
      return;
    }

    setImportFile(file);
  };

  const handleImport = async () => {
    if (!importFile) {
      setMessage('Please select a file to import', 'error');
      return;
    }

    try {
      setIsImporting(true);
      const fileFormat = inferImportFormat(importFile.name);
      if (!fileFormat) {
        throw new Error('Unsupported file type');
      }

      const reader = new FileReader();
      reader.onload = async (e) => {
        try {
          const arrayBuffer = e.target?.result as ArrayBuffer;
          const bytes = new Uint8Array(arrayBuffer);
          let binary = '';
          const chunkSize = 0x8000;

          for (let index = 0; index < bytes.length; index += chunkSize) {
            const chunk = bytes.slice(index, index + chunkSize);
            binary += String.fromCharCode(...chunk);
          }

          const base64Content = btoa(binary);

          const { data } = await importIdeas({
            variables: {
              fileContent: base64Content,
              fileFormat,
              filename: importFile.name,
            },
          });

          if (data?.importIdeas) {
            const { importedCount, skippedCount, errors } = data.importIdeas;
            
            let message = `Successfully imported ${importedCount} idea(s)`;
            if (skippedCount > 0) {
              message += `. ${skippedCount} idea(s) skipped.`;
            }
            if (errors.length > 0) {
              message += ` ${errors.length} error(s) occurred.`;
              logger.warn('Import errors:', errors);
            }
            
            setMessage(message, importedCount > 0 ? 'success' : 'error');
            setImportFile(null);
            if (fileInputRef.current) {
              fileInputRef.current.value = '';
            }
            onClose();
          }
        } catch (error: any) {
          logger.error('Import error:', error);
          setMessage(error.message || 'Failed to import ideas', 'error');
        } finally {
          setIsImporting(false);
        }
      };

      reader.onerror = () => {
        setMessage('Failed to read file', 'error');
        setIsImporting(false);
      };

      reader.readAsArrayBuffer(importFile);
    } catch (error: any) {
      logger.error('Import error:', error);
      setMessage(error.message || 'Failed to import ideas', 'error');
      setIsImporting(false);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-md animate-fade-in">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col animate-scale-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray200 bg-gradient-to-b from-white to-gray50">
          <h2 className="text-2xl font-bold text-neutral900 tracking-tight">Import & Export Ideas</h2>
          <button
            onClick={onClose}
            className="text-gray400 hover:text-neutral900 transition-all duration-200 p-1.5 rounded-lg hover:bg-gray100"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray200 bg-white">
          <button
            onClick={() => setActiveTab('export')}
            className={`flex-1 px-6 py-4 font-semibold text-sm transition-all duration-200 ${
              activeTab === 'export'
                ? 'text-neutral900 border-b-2 border-neutral900'
                : 'text-gray500 hover:text-neutral900'
            }`}
          >
            Export
          </button>
          <button
            onClick={() => setActiveTab('import')}
            className={`flex-1 px-6 py-4 font-semibold text-sm transition-all duration-200 ${
              activeTab === 'import'
                ? 'text-neutral900 border-b-2 border-neutral900'
                : 'text-gray500 hover:text-neutral900'
            }`}
          >
            Import
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-white">
          {activeTab === 'export' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-bold text-neutral900 mb-2 tracking-tight">Export Format</h3>
                <p className="text-sm text-gray500 mb-5 font-medium">
                  Choose a format to export all your ideas
                </p>
                <div className="space-y-3">
                  {(['json', 'csv', 'markdown'] as const).map((format) => (
                    <label
                      key={format}
                      className={`flex items-center p-4 border-2 rounded-xl cursor-pointer transition-all duration-200 ${
                        exportFormat === format
                          ? 'border-accent-500 bg-accent-50 shadow-sm'
                          : 'border-gray200 hover:border-gray300 hover:shadow-sm'
                      }`}
                    >
                      <input
                        type="radio"
                        name="exportFormat"
                        value={format}
                        checked={exportFormat === format}
                        onChange={(e) => setExportFormat(e.target.value as typeof exportFormat)}
                        className="mr-4 w-4 h-4 text-accent-500"
                      />
                      <div className="flex-1">
                        <div className="font-semibold text-neutral900 capitalize">{format}</div>
                        <div className="text-sm text-gray500 mt-1">
                          {format === 'json' && 'Structured data format, best for backups'}
                          {format === 'csv' && 'Spreadsheet format, easy to view in Excel'}
                          {format === 'markdown' && 'Text format, compatible with Apple Notes'}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'import' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-bold text-neutral900 mb-2 tracking-tight">Bring ideas from your notes</h3>
                <p className="text-sm text-gray500 mb-5 font-medium">
                  Upload one export file or archive. Manifest reads the notes, filters for startup ideas, and imports only the ideas into your workspace.
                </p>

                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-2xl border border-stone200 bg-stone50/80 p-5">
                    <p className="text-[0.72rem] font-bold uppercase tracking-[0.16em] text-gray500">Apple Notes</p>
                    <p className="mt-2 text-sm leading-6 text-neutral900">
                      Works best with Markdown or PDF exports from Notes on Mac. If you exported multiple notes, zip the folder and upload once.
                    </p>
                    <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-gray500">
                      Supported: `.md`, `.markdown`, `.html`, `.txt`, `.pdf`, `.zip`
                    </p>
                  </div>
                  <div className="rounded-2xl border border-stone200 bg-stone50/80 p-5">
                    <p className="text-[0.72rem] font-bold uppercase tracking-[0.16em] text-gray500">Google Keep</p>
                    <p className="mt-2 text-sm leading-6 text-neutral900">
                      Export Keep from Google Takeout, then upload the `.zip` or `.tgz` archive directly. Labels come through when present.
                    </p>
                    <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-gray500">
                      Supported: `.zip`, `.tgz`, `.tar.gz`
                    </p>
                  </div>
                </div>

                {/* File Upload Area */}
                <div
                  onDragEnter={handleDrag}
                  onDragLeave={handleDrag}
                  onDragOver={handleDrag}
                  onDrop={handleDrop}
                  className={`border-2 border-dashed rounded-xl p-10 text-center transition-all duration-200 ${
                    dragActive
                      ? 'border-accent-500 bg-accent-50 shadow-md'
                      : 'border-gray300 hover:border-gray400 hover:shadow-sm'
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".json,.csv,.md,.markdown,.html,.htm,.txt,.pdf,.zip,.tgz,.tar.gz"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        handleFileSelect(e.target.files[0]);
                      }
                    }}
                    className="hidden"
                  />
                  
                  {!importFile ? (
                    <>
                      <svg
                        className="mx-auto h-12 w-12 text-gray400 mb-4"
                        stroke="currentColor"
                        fill="none"
                        viewBox="0 0 48 48"
                      >
                        <path
                          d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                          strokeWidth={2}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      <p className="text-gray600 mb-2 font-medium">
                        Drag and drop a file here, or
                      </p>
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        className="text-accent-600 hover:text-accent-700 font-semibold transition-colors"
                      >
                        browse to upload
                      </button>
                      <p className="text-xs text-gray400 mt-3">
                        Supported: JSON, CSV, Markdown, HTML, TXT, PDF, ZIP, and TGZ exports
                      </p>
                      <p className="text-xs text-gray400 mt-1">
                        Max size: 25MB
                      </p>
                    </>
                  ) : (
                    <div className="space-y-4">
                      <div className="flex items-center justify-center">
                        <svg
                          className="h-12 w-12 text-success-600"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                          />
                        </svg>
                      </div>
                      <p className="text-neutral900 font-semibold">{importFile.name}</p>
                      <p className="text-sm text-gray500">
                        {(importFile.size / 1024).toFixed(2)} KB
                      </p>
                      <button
                        onClick={() => {
                          setImportFile(null);
                          if (fileInputRef.current) {
                            fileInputRef.current.value = '';
                          }
                        }}
                        className="text-sm text-danger hover:text-red-700 font-medium transition-colors"
                      >
                        Remove file
                      </button>
                    </div>
                  )}
                </div>

                <div className="mt-6 rounded-2xl border border-accent-200 bg-accent-50 p-5">
                  <h4 className="font-semibold text-neutral900 mb-3">Smoothest import path</h4>
                  <ol className="text-sm text-gray600 space-y-2 list-decimal list-inside leading-relaxed">
                    <li>Export notes from Apple Notes as Markdown/PDF or export Keep with <a href="https://takeout.google.com" target="_blank" rel="noopener noreferrer" className="underline text-accent-600 hover:text-accent-700 font-medium">Google Takeout</a>.</li>
                    <li>If you have multiple Apple Notes files, zip them together first so you only upload once.</li>
                    <li>Manifest reads the file, uses AI to separate startup ideas from ordinary notes, and imports only the idea notes.</li>
                  </ol>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-5 border-t border-gray200 bg-gradient-to-b from-gray50 to-white">
          <button
            onClick={onClose}
            className="px-5 py-2.5 text-gray600 hover:text-neutral900 font-semibold transition-all duration-200 rounded-lg hover:bg-gray100"
          >
            Cancel
          </button>
          {activeTab === 'export' && (
            <button
              onClick={handleExport}
              disabled={isExporting}
              className="px-6 py-2.5 bg-neutral900 text-white rounded-lg font-semibold hover:bg-neutral800 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-md hover:shadow-lg flex items-center gap-2"
            >
              {isExporting ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Exporting...
                </>
              ) : (
                'Export Ideas'
              )}
            </button>
          )}
          {activeTab === 'import' && (
            <button
              onClick={handleImport}
              disabled={!importFile || isImporting}
              className="px-6 py-2.5 bg-neutral900 text-white rounded-lg font-semibold hover:bg-neutral800 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-md hover:shadow-lg flex items-center gap-2"
            >
              {isImporting ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Importing...
                </>
              ) : (
                'Import Ideas'
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ImportExportModal;
