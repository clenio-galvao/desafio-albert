import { readApiBaseUrl } from './api/readApiBaseUrl.ts'
import { ChatPage } from './chat/ChatPage.tsx'

/** Liga o chat à URL pública definida no ambiente. */
export function App() {
  return <ChatPage apiBaseUrl={readApiBaseUrl(import.meta.env.VITE_API_BASE_URL)} />
}
