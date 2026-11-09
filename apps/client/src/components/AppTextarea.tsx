import { Textarea as TaroTextarea } from '@tarojs/components'

type ValueEvent = { detail: { value: string } }
type Props = {
  id?: string; className?: string; value: string; maxlength: number; disabled?: boolean
  placeholder?: string; confirmType?: 'send'
  onInput: (event: ValueEvent) => void; onBlur?: (event: ValueEvent) => void
  onConfirm?: (event: ValueEvent) => void
  nativeProps?: { onKeyDown?: (event: KeyboardEvent) => void }
}
// Taro 4.3.2 H5 textarea can loop indefinitely in calculateContentHeight during
// remount. Fixed-size native H5 controls avoid that code; mini-program keeps its
// platform control. No dependency files are patched.
export default function AppTextarea(props: Props) {
  if (process.env.TARO_ENV !== 'h5') return <TaroTextarea {...props} />
  return <textarea id={props.id} className={props.className} value={props.value}
    maxLength={props.maxlength} disabled={props.disabled} placeholder={props.placeholder}
    onChange={event => props.onInput({ detail: { value: event.currentTarget.value } })}
    onBlur={event => props.onBlur?.({ detail: { value: event.currentTarget.value } })}
    onKeyDown={event => props.nativeProps?.onKeyDown?.(event.nativeEvent)} />
}
