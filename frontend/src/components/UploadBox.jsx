import { useRef } from 'react'

function UploadBox({ onFileSelect, selectedFile, onProcess, onTranslatePdf, loading, loadingPdf }) {
  const fileInputRef = useRef(null)

  const handleFileChange = (e) => {
    const file = e.target.files[0]
    if (file) {
      if (file.type !== 'application/pdf') {
        alert('Please select a PDF file')
        return
      }
      onFileSelect(file)
    }
  }

  const handleClick = () => {
    fileInputRef.current?.click()
  }

  const handleDragOver = (e) => {
    e.preventDefault()
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file) {
      if (file.type !== 'application/pdf') {
        alert('Please select a PDF file')
        return
      }
      onFileSelect(file)
    }
  }

  return (
    <div className="w-full">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        onChange={handleFileChange}
        className="hidden"
      />

      {/* Dropzone clickable area */}
      <div
        onClick={handleClick}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className="rounded-xl border border-dashed border-slate-200 bg-slate-50 hover:bg-slate-100 transition-colors cursor-pointer p-6 text-center"
      >
        <div className="mx-auto h-12 w-12 rounded-lg bg-white shadow-subtle flex items-center justify-center text-indigo-700">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <path fillRule="evenodd" d="M1.5 6A2.25 2.25 0 013.75 3.75h16.5A2.25 2.25 0 0122.5 6v12a2.25 2.25 0 01-2.25 2.25H3.75A2.25 2.25 0 011.5 18V6zm3 3.75A.75.75 0 015.25 9h13.5a.75.75 0 010 1.5H5.25A.75.75 0 014.5 9.75zm0 3.75a.75.75 0 01.75-.75h13.5a.75.75 0 010 1.5H5.25a.75.75 0 01-.75-.75zm.75 3a.75.75 0 000 1.5h6a.75.75 0 000-1.5h-6z" clipRule="evenodd" />
          </svg>
        </div>
        <div className="mt-4">
          <p className="text-slate-900 font-medium">Drag & drop your PDF here</p>
          <p className="text-sm text-slate-600 mt-1">or click to choose a file</p>
        </div>
      </div>

      {/* File info and actions (non-clickable container) */}
      {selectedFile && (
        <div className="mt-4 inline-flex items-center gap-3 rounded-lg bg-white px-4 py-2 shadow-subtle border border-slate-200/70">
          <span className="text-sm font-medium text-slate-800">{selectedFile.name}</span>
          <span className="text-xs text-slate-500">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</span>
        </div>
      )}

      <div className="mt-6 space-y-3">
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <button onClick={handleClick} type="button" className="btn-secondary w-full sm:w-auto">
            {selectedFile ? 'Choose a different file' : 'Choose PDF'}
          </button>
        </div>
        
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <button
            onClick={(e) => { e.stopPropagation(); onProcess(); }}
            disabled={!selectedFile || loading || loadingPdf}
            type="button"
            className="btn-primary w-full sm:w-auto"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Extracting Text...
              </span>
            ) : (
              'Extract & Translate Text'
            )}
          </button>
          
          <button
            onClick={(e) => { e.stopPropagation(); onTranslatePdf(); }}
            disabled={!selectedFile || loading || loadingPdf}
            type="button"
            className="btn-primary w-full sm:w-auto bg-indigo-600 hover:bg-indigo-700"
          >
            {loadingPdf ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Translating PDF...
              </span>
            ) : (
              'Translate PDF (Preserve Layout)'
            )}
          </button>
        </div>
        
        <p className="text-xs text-center text-slate-500 mt-2">
          Choose "Extract & Translate Text" for JSON output, or "Translate PDF" for a new PDF with preserved layout
        </p>
      </div>
    </div>
  )
}

export default UploadBox


