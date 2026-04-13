import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Home } from './pages/Home'
import { Engagement } from './pages/Engagement'
import { FindingDetailPage } from './pages/FindingDetail'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/engagement/:id" element={<Engagement />} />
        <Route path="/engagement/:engagementId/findings/:findingId" element={<FindingDetailPage />} />
      </Routes>
    </BrowserRouter>
  )
}
