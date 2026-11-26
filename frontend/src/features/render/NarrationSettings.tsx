import type { Narration } from '../../api/types'

interface Props {
  value: Narration
  onChange: (value: Narration) => void
}

export const NARRATION_LIMITS = {
  velocidade_elevenlabs: { label: 'Velocidade', min: 0.7, max: 1.2 },
  estabilidade_elevenlabs: { label: 'Estabilidade', min: 0, max: 1 },
  similaridade_elevenlabs: { label: 'Similaridade', min: 0, max: 1 },
  estilo_elevenlabs: { label: 'Estilo', min: 0, max: 1 },
} as const

/** Padrões do nó PapoNarration (GET /object_info/PapoNarration). */
export const NODE_DEFAULTS: Narration = {
  provedor: 'ElevenLabs',
  voz_elevenlabs: '',
  modelo_elevenlabs: 'eleven_multilingual_v2',
  velocidade_elevenlabs: 1.08,
  estabilidade_elevenlabs: 0.3,
  similaridade_elevenlabs: 0.73,
  estilo_elevenlabs: 0.74,
  idioma_elevenlabs: 'pt',
}

const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, Math.round(n * 100) / 100))

export function NarrationSettings({ value, onChange }: Props) {
  const set = <K extends keyof Narration>(key: K, v: Narration[K]) => onChange({ ...value, [key]: v })
  const eleven = value.provedor === 'ElevenLabs'
  return (
    <details className="vignette narration">
      <summary>
        Voz da narração: {value.provedor}
        {eleven ? ` · ${value.voz_elevenlabs || 'voz padrão do servidor'}` : ''}
      </summary>
      <label className="field">
        Provedor
        <select value={value.provedor} onChange={(e) => set('provedor', e.target.value as Narration['provedor'])}>
          <option value="ElevenLabs">ElevenLabs</option>
          <option value="VoiceStudio">VoiceStudio</option>
        </select>
      </label>
      {eleven && (
        <>
          <label className="field">
            Voz da ElevenLabs
            <input
              value={value.voz_elevenlabs}
              onChange={(e) => set('voz_elevenlabs', e.target.value)}
              placeholder="vazio = voz padrão do servidor"
            />
            <small className="muted">A chave da ElevenLabs fica só no servidor do ComfyUI; ela não passa por esta tela.</small>
          </label>
          <label className="field">
            Modelo
            <select value={value.modelo_elevenlabs} onChange={(e) => set('modelo_elevenlabs', e.target.value as Narration['modelo_elevenlabs'])}>
              <option value="eleven_multilingual_v2">eleven_multilingual_v2</option>
              <option value="eleven_flash_v2_5">eleven_flash_v2_5</option>
            </select>
          </label>
          {(Object.keys(NARRATION_LIMITS) as (keyof typeof NARRATION_LIMITS)[]).map((key) => {
            const { label, min, max } = NARRATION_LIMITS[key]
            const update = (n: number) => !Number.isNaN(n) && set(key, clamp(n, min, max))
            return (
              <label className="field narration-num" key={key}>
                <span>
                  {label} ({min} a {max}): <strong>{value[key].toFixed(2)}</strong>
                </span>
                <span className="narration-controls">
                  <input type="range" aria-label={`${label} (controle)`} min={min} max={max} step={0.01} value={value[key]} onChange={(e) => update(Number(e.target.value))} />
                  <input type="number" aria-label={label} min={min} max={max} step={0.01} value={value[key]} onChange={(e) => update(Number(e.target.value))} />
                </span>
              </label>
            )
          })}
          <label className="field">
            Idioma
            <input aria-label="Idioma" value={value.idioma_elevenlabs} onChange={(e) => set('idioma_elevenlabs', e.target.value)} placeholder="pt" />
            <small className="muted">O multilingual v2 detecta o idioma pelo texto; os outros modelos usam este código.</small>
          </label>
        </>
      )}
      <button type="button" className="secondary" onClick={() => onChange(NODE_DEFAULTS)}>
        Restaurar padrões do nó
      </button>
    </details>
  )
}
