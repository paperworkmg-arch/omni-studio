import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error) {
    console.error('React Error:', error)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          width: '100vw',
          height: '100vh',
          backgroundColor: '#0B0908',
          color: '#EFE6D6',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          fontFamily: 'monospace',
          padding: '20px',
          textAlign: 'center',
        }}>
          <h1 style={{ color: '#E8A33D', marginBottom: '20px' }}>⚠️ Error</h1>
          <pre style={{
            maxWidth: '800px',
            backgroundColor: '#141110',
            padding: '20px',
            borderRadius: '4px',
            border: '1px solid #2C251D',
            textAlign: 'left',
            overflow: 'auto',
            maxHeight: '300px',
          }}>
            {this.state.error?.toString()}
            {'\n\n'}
            {this.state.error?.stack}
          </pre>
          <p style={{ marginTop: '20px', fontSize: '12px' }}>
            Check browser console (F12) for more details
          </p>
        </div>
      )
    }

    return this.props.children
  }
}
