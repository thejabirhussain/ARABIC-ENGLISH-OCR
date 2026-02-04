function OutputBox({ arabicText, englishText }) {
  const copyToClipboard = (text, type) => {
    navigator.clipboard.writeText(text).then(() => {
      // Simple non-blocking feedback
      // In future, replace with a toast
      console.log(`${type} text copied to clipboard`)
    })
  }

  return (
    <div className="grid md:grid-cols-2 gap-6">
      {/* Arabic Text Output */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2>Arabic Text</h2>
          <button
            onClick={() => copyToClipboard(arabicText, 'Arabic')}
            className="btn-secondary"
          >
            Copy
          </button>
        </div>
        <div className="bg-ink-50 rounded-lg p-4 max-h-96 overflow-y-auto border border-slate-200/60">
          <pre className="whitespace-pre-wrap text-right font-arabic text-lg leading-relaxed text-ink-900">
            {arabicText}
          </pre>
        </div>
      </div>

      {/* English Text Output */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2>English Translation</h2>
          <button
            onClick={() => copyToClipboard(englishText, 'English')}
            className="btn-secondary"
          >
            Copy
          </button>
        </div>
        <div className="bg-ink-50 rounded-lg p-4 max-h-96 overflow-y-auto border border-slate-200/60">
          <pre className="whitespace-pre-wrap text-left text-base leading-relaxed text-ink-900">
            {englishText}
          </pre>
        </div>
      </div>
    </div>
  )
}

export default OutputBox


