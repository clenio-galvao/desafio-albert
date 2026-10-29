export interface Citation {
  source: string
  title: string
  page: number
}

export interface ChatRequestBody {
  sessionId: string
  message: string
  model: string
}

export interface ChatStreamHandlers {
  onMetadata: (citations: Citation[]) => void
  onToken: (content: string) => void
}
