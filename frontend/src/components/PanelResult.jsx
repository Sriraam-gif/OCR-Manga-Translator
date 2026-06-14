import { useLayoutEffect, useRef, useState } from 'react'

const clamp = (v) => Math.max(0, Math.min(1, v ?? 0))

// Grow each cover box a little so it fully hides the original text underneath.
const GROW = 0.1

// Shrinks the font until the translated text fits inside its cover box.
function OverlayText({ text }) {
  const ref = useRef(null)
  const [fontSize, setFontSize] = useState(14)

  useLayoutEffect(() => {
    const span = ref.current
    if (!span) return
    const box = span.parentElement

    const fit = () => {
      let size = Math.max(8, Math.min(22, box.clientHeight * 0.7))
      span.style.fontSize = `${size}px`
      while (
        size > 6 &&
        (span.scrollHeight > box.clientHeight || span.scrollWidth > box.clientWidth)
      ) {
        size -= 1
        span.style.fontSize = `${size}px`
      }
      setFontSize(size)
    }

    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(box)
    return () => ro.disconnect()
  }, [text])

  return (
    <span
      ref={ref}
      className="block w-full font-semibold leading-tight text-gray-900"
      style={{ fontSize }}
    >
      {text}
    </span>
  )
}

function PanelResult({ panel }) {
  const regions = panel.regions || []

  // Preferred path: the backend already erased the original text and typeset the
  // English into the art (inpaint + typeset), so just show that finished image.
  if (panel.rendered_image) {
    return (
      <div className="w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
        <img
          src={panel.rendered_image}
          alt="translated panel"
          loading="lazy"
          className="block w-full"
        />
      </div>
    )
  }

  // Fallback: CSS overlay on the original image.
  return (
    <div className="relative w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <img
        src={panel.image_url}
        alt="translated panel"
        loading="lazy"
        className="block w-full"
      />
      {regions.map((r, i) => {
        const b = r.box || {}
        const w = clamp(b.width)
        const h = clamp(b.height)
        const style = {
          left: `${clamp(b.x - (w * GROW) / 2) * 100}%`,
          top: `${clamp(b.y - (h * GROW) / 2) * 100}%`,
          width: `${Math.min(1, w * (1 + GROW)) * 100}%`,
          height: `${Math.min(1, h * (1 + GROW)) * 100}%`,
        }
        return (
          <div
            key={i}
            style={style}
            title={r.original_text}
            className="absolute flex items-center justify-center overflow-hidden bg-white px-1 text-center"
          >
            <OverlayText text={r.translated_text} />
          </div>
        )
      })}
    </div>
  )
}

export default PanelResult
