import { useState } from 'react'

function ImageUpload({ onSubmit, loading }) {
  const [file, setFile] = useState(null)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (file) onSubmit(file)
  }

  return (
    <form onSubmit={handleSubmit} className="flex w-full max-w-2xl items-center gap-2">
      <input
        type="file"
        accept="image/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="flex-1 text-sm text-gray-700 file:mr-3 file:rounded file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-indigo-700 hover:file:bg-indigo-100"
      />
      <button
        type="submit"
        disabled={loading || !file}
        className="rounded bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {loading ? 'Translating…' : 'Translate image'}
      </button>
    </form>
  )
}

export default ImageUpload
