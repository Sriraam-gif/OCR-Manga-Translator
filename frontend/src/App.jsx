import { useState } from 'react'
import UrlInput from './components/UrlInput'
import ImageUpload from './components/ImageUpload'
import PanelResult from './components/PanelResult'
import './index.css'

function App() {
  const [loading, setLoading] = useState(false)
  const [panels, setPanels] = useState([])
  const [error, setError] = useState(null)
  const [submitted, setSubmitted] = useState(false)
  const [tone, setTone] = useState('natural')
  const [keepHonorifics, setKeepHonorifics] = useState(true)

  const handleTranslateChapter = async (url) => {
    setLoading(true)
    setError(null)
    setPanels([])
    setSubmitted(true)
    try {
      const res = await fetch('/translate-chapter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, tone, keep_honorifics: keepHonorifics }),
      })
      if (!res.ok) throw new Error(`Server error (${res.status})`)
      const data = await res.json()
      setPanels(data.panels || [])
    } catch (e) {
      setError(e.message || 'Something went wrong. Check the URL and try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleTranslateImage = async (file) => {
    setLoading(true)
    setError(null)
    setPanels([])
    setSubmitted(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('tone', tone)
      formData.append('keep_honorifics', keepHonorifics)
      const res = await fetch('/translate-image', { method: 'POST', body: formData })
      if (!res.ok) throw new Error(`Server error (${res.status})`)
      const data = await res.json()
      // Reuse PanelResult: show the local image preview + the translation.
      setPanels([{ image_url: URL.createObjectURL(file), ...data }])
    } catch (e) {
      setError(e.message || 'Something went wrong. Try a different image.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-100 text-gray-900">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="mb-6 text-3xl font-bold">Manga / Manhwa OCR Translator</h1>

        <div className="mb-6 flex flex-wrap items-center gap-5 rounded border border-gray-200 bg-white p-3 text-sm">
          <label className="flex items-center gap-2">
            <span className="font-medium text-gray-700">Tone</span>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              disabled={loading}
              className="rounded border border-gray-300 px-2 py-1"
            >
              <option value="natural">Natural</option>
              <option value="literal">Literal</option>
              <option value="localized">Localized</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={keepHonorifics}
              onChange={(e) => setKeepHonorifics(e.target.checked)}
              disabled={loading}
            />
            <span className="text-gray-700">Keep honorifics (-san, -nim, oppa)</span>
          </label>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Translate a whole chapter from a URL
            </label>
            <div className="flex justify-center">
              <UrlInput onSubmit={handleTranslateChapter} loading={loading} />
            </div>
          </div>

          <div className="flex items-center gap-3 text-sm text-gray-400">
            <span className="h-px flex-1 bg-gray-300" />
            or
            <span className="h-px flex-1 bg-gray-300" />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Translate a single panel image
            </label>
            <div className="flex justify-center">
              <ImageUpload onSubmit={handleTranslateImage} loading={loading} />
            </div>
          </div>
        </div>

        {loading && (
          <p className="mt-6 text-center text-gray-500">
            Translating… this can take a minute for long chapters.
          </p>
        )}

        {error && (
          <p className="mt-6 rounded border border-red-200 bg-red-50 p-3 text-center text-red-700">
            {error}
          </p>
        )}

        {!loading && !error && submitted && panels.length === 0 && (
          <p className="mt-6 text-center text-gray-500">No panels found.</p>
        )}

        <div className="mt-8 space-y-6">
          {panels.map((panel, i) => (
            <PanelResult key={`${panel.image_url}-${i}`} panel={panel} />
          ))}
        </div>
      </div>
    </div>
  )
}

export default App
