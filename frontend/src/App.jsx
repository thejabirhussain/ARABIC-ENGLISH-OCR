import { useState } from 'react'
import UploadBox from './components/UploadBox'
import OutputBox from './components/OutputBox'
import ChatSidebar from './components/ChatSidebar'

function App() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingPdf, setLoadingPdf] = useState(false)
  const [results, setResults] = useState(null)
  const [translatedPdfUrl, setTranslatedPdfUrl] = useState(null)
  const [docId, setDocId] = useState(null)
  const [showChat, setShowChat] = useState(false)
  const [error, setError] = useState(null)

  const handleFileSelect = (selectedFile) => {
    setFile(selectedFile)
    setResults(null)
    setResults(null)
    setTranslatedPdfUrl(null)
    setDocId(null)
    setShowChat(false)
    setError(null)
  }

  const handleProcess = async () => {
    if (!file) {
      setError('Please select a PDF file first')
      return
    }

    setLoading(true)
    setError(null)
    setResults(null)
    setResults(null)
    setTranslatedPdfUrl(null)
    setDocId(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('http://127.0.0.1:8000/process', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to process PDF')
      }

      const data = await response.json()
      setResults(data)
    } catch (err) {
      setError(err.message || 'An error occurred while processing the PDF')
    } finally {
      setLoading(false)
    }
  }

  const handleTranslatePdf = async () => {
    if (!file) {
      setError('Please select a PDF file first')
      return
    }

    setLoadingPdf(true)
    setError(null)
    setResults(null)
    setResults(null)
    setTranslatedPdfUrl(null)
    setDocId(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('http://127.0.0.1:8000/translate-pdf', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to translate PDF')
      }

      // Get the PDF blob
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      setTranslatedPdfUrl(url)

      // Get translation stats from headers
      const stats = response.headers.get('X-Translation-Stats')
      if (stats) {
        console.log('Translation stats:', stats)
      }

      // Get Document ID for Chat
      const newDocId = response.headers.get('X-Document-ID')
      if (newDocId) {
        setDocId(newDocId)
      }
    } catch (err) {
      setError(err.message || 'An error occurred while translating the PDF')
    } finally {
      setLoadingPdf(false)
    }
  }

  return (
    <div className="min-h-screen bg-ink-50">
      {/* Top Navigation */}
      <header className="border-b border-slate-200/70 bg-white/80 backdrop-blur supports-[backdrop-filter]:bg-white/60">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-brand-700 text-white flex items-center justify-center font-semibold shadow-subtle">A</div>
            <div>
              <div className="text-ink-900 font-semibold">Arabia OCR</div>
              <div className="text-xs text-ink-500">Premium Translation Suite</div>
            </div>
          </div>
          <nav className="hidden md:flex items-center gap-6 text-sm text-ink-600">
            <span className="hover:text-ink-900 transition-colors">Home</span>
            <span className="hover:text-ink-900 transition-colors">Docs</span>
            <span className="hover:text-ink-900 transition-colors">Support</span>
          </nav>
        </div>
      </header>

      {/* Page Content */}
      <main
        className={`max-w-6xl mx-auto px-4 py-10 transition-all duration-300 ease-in-out ${showChat ? 'mr-[420px]' : ''
          }`}
      >
        <div className="mb-8">
          <h1>Arabic OCR → English Translation</h1>
          <p className="mt-2">Upload a scanned Arabic PDF to extract text and translate to English with high fidelity.</p>
        </div>

        <section className="card p-6 mb-6">
          <UploadBox
            onFileSelect={handleFileSelect}
            selectedFile={file}
            onProcess={handleProcess}
            onTranslatePdf={handleTranslatePdf}
            onChat={() => setShowChat(true)}
            docId={docId}
            loading={loading}
            loadingPdf={loadingPdf}
          />
        </section>

        <ChatSidebar
          isOpen={showChat}
          onClose={() => setShowChat(false)}
          docId={docId}
        />

        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 text-red-800 p-4">
            <div className="flex items-start gap-3">
              <svg className="h-5 w-5 mt-0.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M18 10A8 8 0 11.001 10 8 8 0 0118 10zm-8-4a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 6zm0 8a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
              </svg>
              <div>
                <p className="font-medium">There was an error processing your file</p>
                <p className="text-sm mt-1 text-red-700">{error}</p>
              </div>
            </div>
          </div>
        )}

        {translatedPdfUrl && (
          <div className="card p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2>Translated PDF Ready</h2>
              <a
                href={translatedPdfUrl}
                download="translated_english.pdf"
                className="btn-primary inline-flex items-center gap-2"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                  <path fillRule="evenodd" d="M12 2.25a.75.75 0 01.75.75v11.25l-2.22-2.22a.75.75 0 00-1.06 1.06l3.5 3.5a.75.75 0 001.06 0l3.5-3.5a.75.75 0 10-1.06-1.06l-2.22 2.22V3a.75.75 0 01.75-.75zm-9 13.5a.75.75 0 01.75.75v2.25a1.5 1.5 0 001.5 1.5h13.5a1.5 1.5 0 001.5-1.5V16.5a.75.75 0 011.5 0v2.25a3 3 0 01-3 3H5.25a3 3 0 01-3-3V16.5a.75.75 0 01.75-.75z" clipRule="evenodd" />
                </svg>
                Download Translated PDF
              </a>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-[600px]">
              {/* Original PDF */}
              <div className="flex flex-col h-full">
                <div className="bg-slate-100 px-3 py-2 rounded-t-lg border border-slate-200 border-b-0 text-sm font-medium text-slate-700 flex justify-between">
                  <span>Original Arabic PDF</span>
                  <span className="text-xs bg-slate-200 px-2 py-0.5 rounded text-slate-600">Source</span>
                </div>
                {file && (
                  <iframe
                    src={URL.createObjectURL(file)}
                    className="w-full h-full border border-slate-200 rounded-b-lg bg-slate-50"
                    title="Original PDF"
                  />
                )}
              </div>

              {/* Translated PDF */}
              <div className="flex flex-col h-full">
                <div className="bg-green-100 px-3 py-2 rounded-t-lg border border-green-200 border-b-0 text-sm font-medium text-green-800 flex justify-between">
                  <span>Translated English PDF</span>
                  <span className="text-xs bg-green-200 px-2 py-0.5 rounded text-green-700">Result</span>
                </div>
                <iframe
                  src={translatedPdfUrl}
                  className="w-full h-full border border-green-200 rounded-b-lg bg-green-50"
                  title="Translated PDF"
                />
              </div>
            </div>
          </div>
        )}

        {results && (
          <OutputBox
            arabicText={results.arabic_text}
            englishText={results.english_text}
          />
        )}
      </main>

      {/* Processing Popup */}
      {loadingPdf && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-sm w-full text-center animate-in fade-in zoom-in duration-300">
            <div className="mx-auto w-16 h-16 bg-indigo-50 rounded-full flex items-center justify-center mb-6">
              <svg className="animate-spin h-8 w-8 text-indigo-600" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-slate-900 mb-2">Processing Document</h3>
            <p className="text-slate-600">
              AI-powered translation and vector indexing in progress. This ensures high-quality results and enables chat.
            </p>
            <div className="mt-6 flex justify-center gap-1">
              <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse"></span>
              <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse delay-75"></span>
              <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse delay-150"></span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App


