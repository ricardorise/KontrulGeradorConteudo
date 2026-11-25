interface Props {
  label: string
  value: number // 0–max (1 = 100%)
  max?: number
  disabled?: boolean
  hint?: string
  onChange: (value: number) => void
}

export const percent = (value: number) => `${Math.round(value * 100)}%`

export function VolumeSlider({ label, value, max = 1.5, disabled, hint, onChange }: Props) {
  return (
    <label className="field volume">
      <span>
        {label}: <strong>{value === 0 ? 'mudo' : percent(value)}</strong>
      </span>
      <input
        type="range"
        min={0}
        max={Math.round(max * 100)}
        step={1}
        aria-label={label}
        disabled={disabled}
        value={Math.round(value * 100)}
        onChange={(e) => onChange(Number(e.target.value) / 100)}
      />
      {hint && <small className="muted">{hint}</small>}
    </label>
  )
}
